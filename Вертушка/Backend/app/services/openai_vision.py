"""
Сервис распознавания обложек винила через OpenAI Vision API (GPT-4o-mini)
"""
import json
import re
import logging

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class CoverRecognitionError(Exception):
    """Ошибка распознавания обложки"""
    pass


class OpenAIVisionService:
    """Распознавание обложки пластинки через GPT-4o-mini Vision"""

    API_URL = "https://api.openai.com/v1/chat/completions"

    def __init__(self):
        self.api_key = settings.openai_api_key

    async def recognize_cover(self, image_base64: str) -> dict[str, str]:
        """
        Отправляет фото обложки в GPT-4o-mini Vision и возвращает
        {"artist": "...", "album": "..."}.
        """
        if not self.api_key:
            raise CoverRecognitionError("OPENAI_API_KEY не настроен")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "You are a vinyl record expert analyzing a photograph of a record cover. "
                                "Identify the artist/band name and album title using ALL available clues: "
                                "text on the cover, iconic artwork, visual style, and your knowledge of famous album covers. "
                                "Even if there is no text, try to recognize the album by its artwork alone. "
                                "Return ONLY valid JSON: {\"artist\": \"...\", \"album\": \"...\"}. "
                                "If you cannot determine a field, use an empty string. "
                                "Do not include any other text, markdown, or explanation."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}",
                                "detail": "low",
                            },
                        },
                    ],
                }
            ],
            "max_tokens": 200,
            "temperature": 0.1,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(self.API_URL, json=payload, headers=headers)
            response.raise_for_status()

        data = response.json()
        content = data["choices"][0]["message"]["content"].strip()

        # Strip markdown code fences if present
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)

        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            logger.error(f"Не удалось распарсить ответ OpenAI: {content}")
            raise CoverRecognitionError(f"Не удалось распознать ответ AI")

        artist = result.get("artist", "").strip()
        album = result.get("album", "").strip()

        if not artist and not album:
            raise CoverRecognitionError("Не удалось определить исполнителя или альбом по обложке")

        logger.info(f"Распознана обложка: artist={artist}, album={album}")
        return {"artist": artist, "album": album}
