import re
import time
import httpx
from bs4 import BeautifulSoup
from dataclasses import dataclass


BASE_URL = "https://yandex.ru/jobs"
LISTING_URL = f"{BASE_URL}/vacancies/"

PROFESSIONS = [
    "product-manager",
    "project-manager",
    "project-manager-business",
]


@dataclass
class Vacancy:
    title: str
    slug: str
    service: str
    work_format: str
    cities: str
    grade: str
    url: str


_http_client = None


def get_client() -> httpx.Client:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.Client(
            follow_redirects=True,
            timeout=30,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
            },
        )
    return _http_client


def fetch_page(url: str, retries: int = 2) -> str:
    client = get_client()
    for attempt in range(retries + 1):
        resp = client.get(url)
        resp.raise_for_status()
        text = resp.text
        # Check for valid vacancy page (not a captcha or generic page)
        if "vacancies" in url and "/vacancies/" in url and url.count("/") > 4:
            if 'og:title' in text or 'serviceName' in text:
                return text
            # Possibly rate-limited, retry after delay
            if attempt < retries:
                time.sleep(2 + attempt * 2)
                continue
        return text
    return text


def decode_rsc_chunk(raw: str) -> str:
    """Decode a raw RSC chunk, handling \\uXXXX and \\\" escapes."""
    def replace_unicode_escape(m: re.Match) -> str:
        return chr(int(m.group(1), 16))

    result = re.sub(r'\\u([0-9a-fA-F]{4})', replace_unicode_escape, raw)
    result = result.replace('\\"', '"').replace('\\n', '\n').replace('\\/', '/')
    return result


def parse_rsc_text(html: str) -> str:
    """Extract readable text from Next.js RSC payload embedded in script tags."""
    texts = []
    for match in re.finditer(r'self\.__next_f\.push\(\[1,"(.+?)"\]\)', html, re.DOTALL):
        chunk = decode_rsc_chunk(match.group(1))
        texts.append(chunk)
    return "\n".join(texts)


def extract_vacancy_slugs(html: str) -> list[str]:
    """Extract vacancy URL slugs from the listing page."""
    pattern = r'/jobs/vacancies/([\w\-]+-\d+)'
    slugs = list(dict.fromkeys(re.findall(pattern, html)))
    return slugs


def parse_listing_page(html: str) -> dict[str, dict]:
    """Parse vacancy cards from the listing page HTML + RSC payload."""
    slugs = extract_vacancy_slugs(html)
    rsc_text = parse_rsc_text(html)
    full_text = html + "\n" + rsc_text

    vacancies = {}
    for slug in slugs:
        vacancies[slug] = {
            "slug": slug,
            "url": f"{BASE_URL}/vacancies/{slug}",
        }

    return vacancies


def parse_vacancy_page(html: str, slug: str) -> Vacancy:
    """Parse a single vacancy detail page to extract all fields."""
    rsc_text = parse_rsc_text(html)
    full_text = html + "\n" + rsc_text

    soup = BeautifulSoup(html, "html.parser")

    # Title: try og:title, then <title>, then RSC payload, then slug
    title = ""
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = og_title["content"]
    elif soup.title:
        title = soup.title.string or ""
    # Clean up common suffixes (Russian and English variants)
    title = re.sub(r"\s*[—–-]\s*работа в компании Яндекс.*$", "", title)
    title = re.sub(r"\s*[—–-]\s*work in the company Yandex.*$", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s*[—–-]\s*Яндекс.*$", "", title)
    title = re.sub(r"\s*in Yandex$", "", title, flags=re.IGNORECASE)
    title = re.sub(r"^Vacancy\s*[«\"]", "", title)
    title = re.sub(r"[»\"]\s*$", "", title)
    title = title.replace("Вакансия «", "").replace("» в Яндексе", "")
    title = title.replace("Вакансия ", "").strip(" «»")

    # If title is too short or generic, try extracting from RSC data
    if not title or title in ("Яндекс", "Yandex", ""):
        # Look for the vacancy title in RSC payload
        title_match = re.search(r'"title"\s*:\s*"([^"]{10,})"', full_text)
        if title_match:
            title = title_match.group(1)
        else:
            # Last resort: humanize slug
            title = slug.rsplit("-", 1)[0].replace("-", " ").capitalize()

    # Service/department — extract from RSC payload or page text
    og_desc = soup.find("meta", property="og:description")
    desc_text = og_desc["content"] if og_desc and og_desc.get("content") else ""
    service = extract_service(desc_text, full_text, html)

    # Work format
    work_format = extract_work_format(full_text)

    # Cities
    cities = extract_cities(full_text)

    # Grade/experience
    grade = extract_grade(full_text)

    return Vacancy(
        title=title.strip(),
        slug=slug,
        service=service,
        work_format=work_format,
        cities=cities,
        grade=grade,
        url=f"{BASE_URL}/vacancies/{slug}",
    )


def extract_service(desc_text: str, full_text: str, raw_html: str) -> str:
    """Extract service/department name from RSC data or page text."""
    # Best source: serviceName from MVPHeaderProps in RSC payload (decoded)
    match = re.search(r'"serviceName"\s*:\s*"([^"]+)"', full_text)
    if match:
        return match.group(1)

    # Try raw HTML (serviceName may be in unicode-escaped form)
    raw_match = re.search(r'"serviceName"\\?:\s*\\?"([^"\\]+(?:\\.[^"\\]*)*)"', raw_html)
    if raw_match:
        name = raw_match.group(1)
        name = decode_rsc_chunk(name)
        return name

    # Fallback: try og:description patterns
    for pattern in [
        r'(?:подразделени|направлени|команд|юните|отдел)\w*\s+[«"]([^»"]+)[»"]',
        r'(?:в\s+)(Яндекс\s+\w+|Yandex\s+\w+)',
    ]:
        m = re.search(pattern, desc_text)
        if m:
            return m.group(1).strip()

    return "Не указано"


def extract_work_format(text: str) -> str:
    """Extract work format from text."""
    text_lower = text.lower()
    if "удалённ" in text_lower or "удаленн" in text_lower or "remote" in text_lower:
        return "Удалённая работа"
    if "гибридн" in text_lower or "hybrid" in text_lower:
        return "Гибрид"
    if "офис" in text_lower or "office" in text_lower:
        return "Офис"
    return "Не указано"


def extract_cities(text: str) -> str:
    """Extract cities from text."""
    cities = [
        "Москва", "Санкт-Петербург", "Екатеринбург", "Новосибирск",
        "Казань", "Нижний Новгород", "Ростов-на-Дону", "Краснодар",
        "Воронеж", "Пермь", "Минск", "Алматы", "Ташкент",
        "Белград", "Стамбул", "Ереван", "Тбилиси", "Иннополис",
        "Симферополь", "Саратов",
    ]
    found = [c for c in cities if c in text]
    return ", ".join(found) if found else "Не указано"


def extract_grade(text: str) -> str:
    """Extract grade/experience level from text."""
    text_lower = text.lower()

    # Check for explicit level ranges like "от «Специалист» до «Старший»"
    match = re.search(r'от\s+[«"](.+?)[»"]\s+до\s+[«"](.+?)[»"]', text)
    if match:
        return f"{match.group(1)} — {match.group(2)}"

    # Check for single level mention
    level_match = re.search(
        r'уровн\w+\s+квалификации\s+[«"](.+?)[»"]', text
    )
    if level_match:
        return level_match.group(1)

    # Check for experience years
    exp_match = re.search(r'(\d+)[+]?\s*(?:лет|год[а]?)\s*опыт', text_lower)
    if exp_match:
        return f"от {exp_match.group(1)} лет"

    # Keywords
    if "стажёр" in text_lower or "стажер" in text_lower or "intern" in text_lower:
        return "Стажёр"
    if "руководител" in text_lower or "lead" in text_lower or "head" in text_lower:
        return "Руководитель"
    if "старший" in text_lower or "senior" in text_lower or "ведущий" in text_lower:
        return "Senior"
    if "junior" in text_lower or "младший" in text_lower:
        return "Junior"

    return "Не указано"


def fetch_vacancies() -> list[Vacancy]:
    """Fetch all vacancies for project/product management professions."""
    all_vacancies: dict[str, Vacancy] = {}

    for profession in PROFESSIONS:
        url = f"{LISTING_URL}?professions={profession}"
        try:
            html = fetch_page(url)
        except Exception as e:
            print(f"Error fetching {profession}: {e}")
            continue

        slugs = extract_vacancy_slugs(html)
        for slug in slugs:
            if slug in all_vacancies:
                continue
            try:
                time.sleep(1)  # Rate limit: 1 req/sec
                detail_html = fetch_page(f"{BASE_URL}/vacancies/{slug}")
                vacancy = parse_vacancy_page(detail_html, slug)
                all_vacancies[slug] = vacancy
            except Exception as e:
                print(f"Error parsing vacancy {slug}: {e}")

    return list(all_vacancies.values())


if __name__ == "__main__":
    vacancies = fetch_vacancies()
    for v in vacancies:
        print(f"\n{'='*60}")
        print(f"Title:   {v.title}")
        print(f"Service: {v.service}")
        print(f"Format:  {v.work_format}")
        print(f"Cities:  {v.cities}")
        print(f"Grade:   {v.grade}")
        print(f"URL:     {v.url}")
