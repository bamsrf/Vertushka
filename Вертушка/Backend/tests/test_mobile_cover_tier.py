"""Клиентский выбор тира обложки — исполняем реальный код `Mobile/lib/api.ts`.

Инцидент, который сторожит файл. У релиза Discogs 12194564 (`Steel Sharpens
Steel`) лицевая обложка залита маленькой: 300×300, 19 КБ. Гейт тира честно не
пустил её в мастер-слот (300 < MASTER_MIN_SIDE), а запасной путь —
`getPlaceholderCoverUrl` — первым правилом возвращал `thumb_image_url`, не
сравнивая размеры. Деталь показывала 150×150 на 2.6 КБ, растянутые на всю
ширину экрана, при живой 300px-обложке в соседнем поле той же строки.

Вторая половина той же поломки: `source` у героя оставался пустым, и
expo-image навсегда висел в состоянии загрузки, показывая плейсхолдер. Отсюда
жалоба «обложка как будто не догрузилась» — она буквально не догружалась.

На проде в момент фикса: 1183 записи с обложкой Discogs мельче 500px, у 289 из
них thumb перебивал обложку получше.

Тест не пересказывает логику на Python — он вырезает функции из api.ts и
гоняет их под node. Пересказ разошёлся бы с оригиналом молча, а такой тест
падает ровно тогда, когда меняется поведение.
"""
import json
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

from app.services.cover_quality import MASTER_MIN_SIDE as BACKEND_MIN_SIDE

_API_TS = Path(__file__).resolve().parents[2] / "Mobile" / "lib" / "api.ts"

# Функции самодостаточны (кроме resolveMediaUrl — он стабится в прелюдии).
_WANTED = (
    "coverSideFromUrl",
    "isThumbGrade",
    "getMasterCoverUrl",
    "getPlaceholderCoverUrl",
    "getHeroCoverUrl",
)

# URL'ы настоящие, с прода: релиз 12194564.
_COVER_300 = (
    "https://i.discogs.com/dvb1scIehCY6lfrneJ5ec6RTvV6imlmf_hnDQ_XhWrY"
    "/rs:fit/g:sm/q:90/h:300/w:300/czM6Ly9kaXNjb2dz.jpeg"
)
_THUMB_150 = (
    "https://i.discogs.com/PY8eHUJy7OcAMRn5DKNBeQt9be-U6cUX0JAnCpBqNuw"
    "/rs:fit/g:sm/q:40/h:150/w:150/czM6Ly9kaXNjb2dz.jpeg"
)
_COVER_600 = "https://i.discogs.com/zzz/rs:fit/g:sm/q:90/h:600/w:600/czM6Ly9k.jpeg"
# У CAA `/front` и у магазинных CDN размера в URL нет вообще.
_COVER_UNKNOWN = "https://coverartarchive.org/release/9d8f0a/front"


def _body_start(src: str, start: int) -> int:
    """Индекс `{`, открывающей тело функции.

    Наивный «первый `{` после имени» промахивается: у наших функций объектные
    типы прямо в сигнатуре (`record: { cover_image_url?: string }`). Поэтому
    сначала дожидаемся закрытия списка параметров по скобкам-круглым.
    """
    depth = 0
    seen = False
    for i in range(start, len(src)):
        if src[i] == "(":
            depth += 1
            seen = True
        elif src[i] == ")":
            depth -= 1
        elif src[i] == "{" and seen and depth == 0:
            return i
    raise AssertionError(f"не нашёл начало тела функции с позиции {start}")


def _extract(name: str, src: str) -> str:
    """Функция целиком: от `export function NAME` до парной закрывающей скобки."""
    start = src.index(f"export function {name}")
    depth = 0
    for i in range(_body_start(src, start), len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[start : i + 1]
    raise AssertionError(f"не нашёл конец функции {name} в api.ts")


def _run_in_node(cases: list[dict], tmp_path: Path) -> list:
    src = _API_TS.read_text(encoding="utf-8")
    min_side = re.search(r"const MASTER_MIN_SIDE = (\d+);", src)
    assert min_side, "в api.ts пропал MASTER_MIN_SIDE"

    bundle = "\n\n".join(
        [
            "const resolveMediaUrl = (u: string): string => u;",
            f"const MASTER_MIN_SIDE = {min_side.group(1)};",
            *(_extract(n, src) for n in _WANTED),
            textwrap.dedent(
                """
                const cases = JSON.parse(process.argv[2]);
                console.log(JSON.stringify(cases.map((r: any) => ({
                  master: getMasterCoverUrl(r) ?? null,
                  placeholder: getPlaceholderCoverUrl(r) ?? null,
                  hero: getHeroCoverUrl(r) ?? null,
                  side: coverSideFromUrl(r.cover_image_url) ?? null,
                  thumbGrade: isThumbGrade(r.cover_image_url),
                }))));
                """
            ),
        ]
    )
    harness = tmp_path / "cover_tier.ts"
    harness.write_text(bundle, encoding="utf-8")
    out = subprocess.run(
        ["node", "--experimental-strip-types", str(harness), json.dumps(cases)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert out.returncode == 0, f"node упал:\n{out.stderr}"
    return json.loads(out.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def results(tmp_path_factory) -> list:
    if shutil.which("node") is None:
        pytest.skip("нет node — исполнить api.ts нечем")
    cases = [
        # 0. Тот самый релиз: обложка 300px, thumb 150px, зеркала нет.
        {"cover_image_url": _COVER_300, "thumb_image_url": _THUMB_150},
        # 1. Нормальный релиз: мастер 600px.
        {"cover_image_url": _COVER_600, "thumb_image_url": _THUMB_150},
        # 2. Мелкая обложка без thumb'а.
        {"cover_image_url": _COVER_300},
        # 3. Схему размера не разобрали — считать мелким нельзя.
        {"cover_image_url": _COVER_UNKNOWN, "thumb_image_url": _THUMB_150},
        # 4. Есть зеркало — оно старше всех остальных полей.
        {
            "cover_url": "/uploads/covers/abc.jpg",
            "cover_image_url": _COVER_300,
            "thumb_image_url": _THUMB_150,
        },
    ]
    return _run_in_node(cases, tmp_path_factory.mktemp("node"))


def test_threshold_matches_backend():
    """Порог один на два конца — иначе бэк и клиент спорят, что такое мастер."""
    src = _API_TS.read_text(encoding="utf-8")
    mobile = int(re.search(r"const MASTER_MIN_SIDE = (\d+);", src).group(1))
    assert mobile == BACKEND_MIN_SIDE


def test_placeholder_prefers_the_larger_small_image(results):
    """Ядро инцидента: 300px-обложка обязана победить 150px-thumb."""
    assert results[0]["placeholder"] == _COVER_300, (
        "плейсхолдер снова берёт thumb не глядя — деталь показывает 150px "
        "при живой 300px-обложке в той же строке"
    )


def test_small_cover_is_still_not_a_master(results):
    """Гейт тира не ослаб: 300px в full-size слот по-прежнему не пускаем."""
    assert results[0]["master"] is None
    assert results[0]["thumbGrade"] is True
    assert results[0]["side"] == 300


def test_hero_falls_back_to_the_best_small_image(results):
    """Без этого source пустой и expo-image вечно «грузится»."""
    assert results[0]["hero"] == _COVER_300


def test_master_grade_cover_wins_the_hero_slot(results):
    assert results[1]["master"] == _COVER_600
    assert results[1]["hero"] == _COVER_600
    assert results[1]["placeholder"] == _THUMB_150, "при живом мастере thumb — плейсхолдер"


def test_small_cover_without_thumb_still_renders(results):
    assert results[2]["placeholder"] == _COVER_300
    assert results[2]["hero"] == _COVER_300


def test_unparsed_size_is_not_treated_as_small(results):
    """У CAA `/front` размера в URL нет — рубить такое значило бы терять покрытие."""
    assert results[3]["side"] is None
    assert results[3]["thumbGrade"] is False
    assert results[3]["master"] == _COVER_UNKNOWN


def test_mirror_beats_everything(results):
    assert results[4]["master"] == "/uploads/covers/abc.jpg"
    assert results[4]["hero"] == "/uploads/covers/abc.jpg"
