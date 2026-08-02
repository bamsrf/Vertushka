#!/usr/bin/env python3
"""
Наполнение демо-аккаунта для ревью App Store (Guideline 2.1).

Ревьюер заходит по email+паролю и должен увидеть живое приложение, а не
пустые экраны: пустая коллекция читается как «не работает» и приносит
реджект. Скрипт добавляет пластинки в коллекцию и вишлист через тот же
публичный API, которым пользуется мобильное приложение.

**Пароль скрипт не придумывает и никуда не сохраняет.** Он берётся из
переменной окружения и живёт только в App Store Connect — файлу в
репозитории такому значению не место.

Идемпотентен: если аккаунт уже есть, скрипт логинится и добирает недостающее.
Повторный запуск ничего не ломает и не плодит дубли.

Запуск:
    DEMO_EMAIL=review@vinyl-vertushka.store \\
    DEMO_PASSWORD='...' \\
    python scripts/seed_demo_account.py

Проверить результат:
    DEMO_EMAIL=... DEMO_PASSWORD=... python scripts/presubmit_check.py
"""
from __future__ import annotations

import argparse
import os
import sys
import time

import httpx

DEFAULT_BASE_URL = "https://api.vinyl-vertushka.ru"
DEFAULT_USERNAME = "vertushka_demo"
TIMEOUT = 60.0  # поиск может ходить в Discogs на холодном кэше

# Витрина: узнаваемая классика, которая гарантированно есть в Discogs и
# хорошо выглядит на скриншотах. Первые — в коллекцию, последние — в вишлист.
COLLECTION_QUERIES = [
    "Pink Floyd The Dark Side of the Moon",
    "Miles Davis Kind of Blue",
    "The Beatles Abbey Road",
    "Led Zeppelin IV",
    "Nirvana Nevermind",
    "Radiohead OK Computer",
    "Daft Punk Discovery",
    "David Bowie Hunky Dory",
    "Fleetwood Mac Rumours",
    "The Velvet Underground & Nico",
    "Кино Группа крови",
    "Аквариум Радио Африка",
    "Joy Division Unknown Pleasures",
    "Portishead Dummy",
    "Massive Attack Mezzanine",
]

WISHLIST_QUERIES = [
    "The Beach Boys Pet Sounds",
    "Talking Heads Remain in Light",
    "Аквариум Синий альбом",
    "Boards of Canada Music Has the Right to Children",
    "Джо Дассен Les Champs-Élysées",
]

GREEN, RED, YELLOW, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[0m"


def ok(msg: str) -> None:
    print(f"{GREEN}  ✓{RESET} {msg}")


def warn(msg: str) -> None:
    print(f"{YELLOW}  !{RESET} {msg}")


def die(msg: str) -> None:
    print(f"{RED}  ✗{RESET} {msg}")
    sys.exit(1)


class Session:
    """HTTP-сессия с автопродлением токена.

    Access-токен живёт 30 минут, а полный засев легко занимает дольше: каждый
    поиск на холодном кэше Discogs может тянуться десятки секунд. Когда токен
    протухает посреди прогона, запросы начинают отдавать 401 — и скрипт
    молча добирается до конца, добавив половину. Именно так первый запуск
    дал 11 пластинок из 15 и пустой вишлист.

    Поэтому на каждый 401 — перелогин и одна повторная попытка.
    """

    def __init__(self, client: httpx.Client, base: str, email: str, password: str, username: str):
        self.client = client
        self.base = base
        self.email = email
        self.password = password
        self.username = username
        self.token: str | None = None

    def login_or_register(self) -> None:
        response = self.client.post(
            f"{self.base}/api/auth/login",
            json={"email": self.email, "password": self.password},
        )
        if response.status_code == 200:
            self.token = response.json()["access_token"]
            ok("демо-аккаунт существует, вошли")
            return

        if response.status_code not in (400, 401, 404):
            die(f"логин упал неожиданно: {response.status_code} {response.text[:200]}")

        print("  аккаунта нет — регистрирую")
        response = self.client.post(
            f"{self.base}/api/auth/register",
            json={"email": self.email, "username": self.username, "password": self.password},
        )
        if response.status_code != 201:
            die(f"регистрация не прошла: {response.status_code} {response.text[:300]}")

        self.token = response.json()["access_token"]
        ok(f"аккаунт создан: {self.email} / @{self.username}")

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        response = self.client.request(
            method, f"{self.base}{path}", headers=self._headers(), **kwargs
        )
        if response.status_code == 401:
            warn("токен протух — перелогиниваюсь")
            self.login_or_register()
            response = self.client.request(
                method, f"{self.base}{path}", headers=self._headers(), **kwargs
            )
        return response

    def get(self, path: str, **kwargs) -> httpx.Response:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs) -> httpx.Response:
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs) -> httpx.Response:
        return self.request("PUT", path, **kwargs)


def find_release(session: Session, query: str) -> str | None:
    """Discogs ID первого подходящего результата поиска."""
    try:
        response = session.get("/api/records/search", params={"q": query, "per_page": 5})
    except Exception as exc:
        warn(f"поиск «{query}» упал: {exc}")
        return None

    if response.status_code == 429:
        # Лимит поиска — 40/мин. Ждём окно и пробуем ещё раз, иначе засев
        # молча недосчитается пластинок.
        warn("уперлись в лимит поиска, жду 60с")
        time.sleep(60)
        response = session.get("/api/records/search", params={"q": query, "per_page": 5})

    if response.status_code != 200:
        warn(f"поиск «{query}»: {response.status_code}")
        return None

    results = response.json().get("results") or []
    for item in results:
        discogs_id = item.get("discogs_id") or item.get("id")
        if discogs_id:
            return str(discogs_id)

    warn(f"ничего не найдено: «{query}»")
    return None


def ensure_collection(session: Session) -> str:
    """ID основной коллекции (создаём, если её ещё нет)."""
    response = session.get("/api/collections/")
    if response.status_code != 200:
        die(f"не удалось прочитать коллекции: {response.status_code}")

    collections = response.json()
    if collections:
        return collections[0]["id"]

    created = session.post("/api/collections/", json={"name": "Моя коллекция"})
    if created.status_code != 201:
        die(f"не удалось создать коллекцию: {created.status_code} {created.text[:200]}")
    return created.json()["id"]


def seed_collection(session: Session, collection_id: str) -> tuple[int, int]:
    added, failed = 0, 0
    for query in COLLECTION_QUERIES:
        discogs_id = find_release(session, query)
        if not discogs_id:
            failed += 1
            continue

        response = session.post(
            f"/api/collections/{collection_id}/items",
            json={"discogs_id": discogs_id, "condition": "Very Good Plus (VG+)"},
        )
        if response.status_code == 201:
            added += 1
            ok(f"в коллекцию: {query}")
        elif response.status_code in (400, 409):
            print(f"    уже в коллекции: {query}")
        else:
            failed += 1
            warn(f"не добавилось «{query}»: {response.status_code} {response.text[:150]}")
    return added, failed


def seed_wishlist(session: Session) -> tuple[int, int]:
    added, failed = 0, 0
    for priority, query in enumerate(WISHLIST_QUERIES):
        discogs_id = find_release(session, query)
        if not discogs_id:
            failed += 1
            continue

        response = session.post(
            "/api/wishlists/items",
            json={"discogs_id": discogs_id, "priority": min(priority, 10)},
        )
        if response.status_code == 201:
            added += 1
            ok(f"в вишлист: {query}")
        elif response.status_code in (400, 409):
            print(f"    уже в вишлисте: {query}")
        else:
            failed += 1
            warn(f"не добавилось «{query}»: {response.status_code} {response.text[:150]}")
    return added, failed


def set_profile(session: Session) -> None:
    response = session.put(
        "/api/users/me",
        json={
            "display_name": "Демо-коллекционер",
            "bio": "Демонстрационный аккаунт для проверки приложения.",
        },
    )
    if response.status_code == 200:
        ok("профиль заполнен")
    else:
        warn(f"профиль не обновился: {response.status_code} {response.text[:150]}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Наполнить демо-аккаунт для App Store review")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--username", default=os.environ.get("DEMO_USERNAME", DEFAULT_USERNAME))
    args = parser.parse_args()

    email = os.environ.get("DEMO_EMAIL")
    password = os.environ.get("DEMO_PASSWORD")
    if not (email and password):
        die(
            "нужны DEMO_EMAIL и DEMO_PASSWORD в окружении.\n"
            "     Пароль задаёшь ты — он поедет в App Store Connect и не должен "
            "оказаться в репозитории."
        )
    if len(password) < 8:
        die("пароль короче 8 символов — бэкенд не примет")

    base = args.base_url.rstrip("/")
    print(f"Наполняю демо-аккаунт на {base}\n")

    with httpx.Client(timeout=TIMEOUT) as client:
        session = Session(client, base, email, password, args.username)
        session.login_or_register()

        set_profile(session)

        print("\nКоллекция:")
        collection_id = ensure_collection(session)
        in_collection, failed_collection = seed_collection(session, collection_id)

        print("\nВишлист:")
        in_wishlist, failed_wishlist = seed_wishlist(session)

    print(f"\n{GREEN}Готово{RESET}: +{in_collection} в коллекцию, +{in_wishlist} в вишлист")

    failed = failed_collection + failed_wishlist
    if failed:
        print(
            f"{YELLOW}Не добавилось: {failed}{RESET} — запусти скрипт ещё раз, "
            f"он идемпотентен и доберёт недостающее"
        )

    print("\nДальше:")
    print("  1. Проверить: venv/bin/python scripts/presubmit_check.py")
    print("  2. Занести email и пароль в ASC → App Review Information")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
