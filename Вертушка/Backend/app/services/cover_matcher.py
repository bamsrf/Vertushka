"""
Визуальный матчинг обложек винила через CLIP (ViT-B-32) на ONNX Runtime.

Зачем: текстовое угадывание artist/album даёт ложные срабатывания, особенно на
обложках без текста. Этот сервис сравнивает ФОТО юзера с обложками-кандидатами
напрямую в визуальном пространстве (косинус между CLIP-эмбеддингами) и
переранжирует кандидатов по реальной визуальной близости + отдаёт score, по
которому можно отсечь мусор порогом.

Модель: CLIP ViT-B-32 vision tower, ONNX (~350 МБ). Качается один раз в
uploads/models/ (persistent volume), не входит в docker-образ. CPU-инференс.
"""
import asyncio
import logging
from pathlib import Path

import httpx
import numpy as np
from PIL import Image
from io import BytesIO

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ONNX-экспорт vision-башни CLIP ViT-B-32 (выдаёт спроецированный image embedding, 512-dim)
_MODEL_URL = "https://huggingface.co/Qdrant/clip-ViT-B-32-vision/resolve/main/model.onnx"
_MODEL_DIR = Path(settings.covers_dir).parent / "models"
_MODEL_PATH = _MODEL_DIR / "clip-vit-b32-vision.onnx"
_DOWNLOAD_TIMEOUT = 300  # секунд — модель ~350 МБ

# Препроцессинг CLIP
_INPUT_SIZE = 224
_MEAN = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32)
_STD = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32)


class CoverMatcher:
    """Лениво-инициализируемый синглтон. Эмбеддит изображения, считает косинус."""

    _instance: "CoverMatcher | None" = None
    _lock = asyncio.Lock()

    def __init__(self) -> None:
        self._session = None  # onnxruntime.InferenceSession
        self._input_name: str | None = None
        self._output_name: str | None = None

    @classmethod
    async def get(cls) -> "CoverMatcher":
        """Глобальный синглтон с ленивой загрузкой модели (thread-safe)."""
        if cls._instance is not None and cls._instance._session is not None:
            return cls._instance
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            if cls._instance._session is None:
                await asyncio.to_thread(cls._instance._load)
        return cls._instance

    # ---- загрузка модели ----

    def _ensure_model_file(self) -> None:
        if _MODEL_PATH.exists() and _MODEL_PATH.stat().st_size > 1_000_000:
            return
        _MODEL_DIR.mkdir(parents=True, exist_ok=True)
        tmp = _MODEL_PATH.with_suffix(".onnx.tmp")
        logger.info("Скачиваю CLIP ONNX модель в %s ...", _MODEL_PATH)
        with httpx.stream("GET", _MODEL_URL, timeout=_DOWNLOAD_TIMEOUT, follow_redirects=True) as r:
            r.raise_for_status()
            with open(tmp, "wb") as f:
                for chunk in r.iter_bytes(chunk_size=1 << 20):
                    f.write(chunk)
        tmp.rename(_MODEL_PATH)
        logger.info("CLIP ONNX модель загружена (%.1f МБ)", _MODEL_PATH.stat().st_size / 1e6)

    def _load(self) -> None:
        import onnxruntime as ort

        self._ensure_model_file()
        opts = ort.SessionOptions()
        # Память > скорость: скан обложки редкий, а модель резидентна навсегда
        # в процессе (инцидент 07-10: CLIP держал ~350MB + арены ~200MB → 2 воркера
        # × CLIP = OOM на 2GB). Флаги режут резидентный overhead ONNX:
        # - enable_cpu_mem_arena=False: не предвыделять большую арену (2-3× модели);
        # - enable_mem_pattern=False: не пре-планировать аллокации;
        # - intra_op_num_threads=1: одна thread-local арена вместо N;
        # - BASIC вместо ENABLE_ALL: без layout-оптимизаций, что держат лишние копии.
        opts.intra_op_num_threads = 1
        opts.enable_cpu_mem_arena = False
        opts.enable_mem_pattern = False
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
        self._session = ort.InferenceSession(
            str(_MODEL_PATH), sess_options=opts, providers=["CPUExecutionProvider"]
        )
        self._input_name = self._session.get_inputs()[0].name
        self._output_name = self._session.get_outputs()[0].name
        logger.info(
            "CLIP сессия готова: input=%s output=%s", self._input_name, self._output_name
        )

    # ---- препроцессинг ----

    @staticmethod
    def _preprocess(image_bytes: bytes) -> np.ndarray:
        """bytes JPEG/PNG -> float32 [1,3,224,224] по канону CLIP."""
        img = Image.open(BytesIO(image_bytes)).convert("RGB")
        # resize по короткой стороне до 224, затем center-crop 224
        w, h = img.size
        scale = _INPUT_SIZE / min(w, h)
        new_w, new_h = round(w * scale), round(h * scale)
        img = img.resize((new_w, new_h), Image.BICUBIC)
        left = (new_w - _INPUT_SIZE) // 2
        top = (new_h - _INPUT_SIZE) // 2
        img = img.crop((left, top, left + _INPUT_SIZE, top + _INPUT_SIZE))

        arr = np.asarray(img, dtype=np.float32) / 255.0  # HWC 0..1
        arr = (arr - _MEAN) / _STD
        arr = arr.transpose(2, 0, 1)  # CHW
        return arr[None, ...].astype(np.float32)  # [1,3,224,224]

    # ---- инференс ----

    def _embed_sync(self, image_bytes: bytes) -> np.ndarray | None:
        try:
            x = self._preprocess(image_bytes)
        except Exception as e:  # битый/неподдерживаемый файл
            logger.warning("preprocess failed: %s", e)
            return None
        out = self._session.run([self._output_name], {self._input_name: x})[0]
        vec = out[0].astype(np.float32)
        norm = np.linalg.norm(vec)
        if norm == 0:
            return None
        return vec / norm  # L2-нормализованный -> косинус = dot

    async def embed(self, image_bytes: bytes) -> np.ndarray | None:
        """Эмбеддинг одного изображения (нормализованный 512-вектор) или None."""
        return await asyncio.to_thread(self._embed_sync, image_bytes)

    async def embed_many(self, items: list[bytes]) -> list[np.ndarray | None]:
        """Эмбеддинг батча (последовательно в одном потоке — CPU-bound)."""
        def _run() -> list[np.ndarray | None]:
            return [self._embed_sync(b) for b in items]

        return await asyncio.to_thread(_run)

    @staticmethod
    def cosine(a: np.ndarray, b: np.ndarray) -> float:
        """Косинус между уже L2-нормализованными векторами."""
        return float(np.dot(a, b))
