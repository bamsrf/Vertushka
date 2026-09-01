#!/usr/bin/env python3
"""
Пресабмит-проверка перед отправкой билда в App Store.

Прогоняет ту часть чек-листа ревьюера, которую можно проверить машиной:
живость API, консистентность remote config, доступность юридических страниц
и наполненность демо-аккаунта. Остальное (скриншоты, атрибуция в UI,
возрастной рейтинг) проверяется глазами — см. APPSTORE_PRERELEASE_AUDIT.md.

Главная ловушка, ради которой это написано: `min_supported_version` на
сервере выше, чем `version` в app.json. Тогда force-update gate покажет
стену «обновитесь» ВСЕМ, включая ревьюера, который в ответ пришлёт реджект
по Guideline 2.1. Проверить глазами это невозможно — цифры лежат в разных
местах и меняются в разное время.

Запуск:
    python scripts/presubmit_check.py
    python scripts/presubmit_check.py --base-url https://api.vinyl-vertushka.ru

Проверки демо-аккаунта (опционально, но это 🔴 пункт плана):
    DEMO_EMAIL=review@... DEMO_PASSWORD=... python scripts/presubmit_check.py

Код возврата: 0 — можно сабмитить, 1 — есть провалы.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx

DEFAULT_BASE_URL = "https://api.vinyl-vertushka.ru"
APP_JSON = Path(__file__).resolve().parents[2] / "Mobile" / "app.json"
TIMEOUT = 15.0

# Демо-коллекция должна выглядеть как живая, иначе ревьюер увидит пустой
# экран и решит, что приложение не работает (Guideline 2.1).
MIN_DEMO_RECORDS = 10
MIN_DEMO_WISHLIST = 3

GREEN, RED, YELLOW, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[0m"

failures: list[str] = []
warnings: list[str] = []


def ok(message: str) -> None:
    print(f"{GREEN}  ✓{RESET} {message}")


def fail(message: str) -> None:
    failures.append(message)
    print(f"{RED}  ✗{RESET} {message}")


def warn(message: str) -> None:
    warnings.append(message)
    print(f"{YELLOW}  !{RESET} {message}")


def section(title: str) -> None:
    print(f"\n{title}")


def parse_version(value: str) -> tuple[int, ...] | None:
    parts = value.strip().split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return None
    return tuple(int(p) for p in parts)


def read_app_version() -> str | None:
    try:
        with APP_JSON.open(encoding="utf-8") as fh:
            return json.load(fh)["expo"]["version"]
    except Exception as exc:
        warn(f"не удалось прочитать версию из {APP_JSON}: {exc}")
        return None


def check_health(client: httpx.Client, base_url: str) -> None:
    section("API живо")
    try:
        response = client.get(f"{base_url}/health")
    except Exception as exc:
        fail(f"/health недоступен: {exc}")
        return

    if response.status_code != 200:
        fail(f"/health вернул {response.status_code}")
        return

    body = response.json()
    ok(f"/health: {body.get('status')}")
    if body.get("db") != "connected":
        fail(f"БД: {body.get('db')}")


def check_remote_config(client: httpx.Client, base_url: str) -> None:
    section("Remote config")
    try:
        response = client.get(f"{base_url}/api/config/")
    except Exception as exc:
        fail(f"/api/config/ недоступен: {exc}")
        return

    if response.status_code != 200:
        fail(f"/api/config/ вернул {response.status_code}")
        return

    config = response.json()

    missing = {"min_supported_version", "store_url", "update_message", "flags"} - set(config)
    if missing:
        fail(f"в /api/config/ нет полей: {', '.join(sorted(missing))}")
        return
    ok("контракт /api/config/ полный")

    # Главная проверка: гейт не должен закрывать сабмитируемый билд.
    min_version = config["min_supported_version"]
    app_version = read_app_version()
    if app_version:
        parsed_min, parsed_app = parse_version(min_version), parse_version(app_version)
        if parsed_min is None:
            fail(f"min_supported_version некорректна: {min_version!r}")
        elif parsed_app is None:
            fail(f"версия в app.json некорректна: {app_version!r}")
        elif parsed_app < parsed_min:
            fail(
                f"ФОРС-АПДЕЙТ ЗАБЛОКИРУЕТ РЕВЬЮЕРА: app.json={app_version} < "
                f"min_supported_version={min_version}. Приложение покажет стену "
                f"«обновитесь» и получит реджект по Guideline 2.1"
            )
        else:
            ok(f"версии согласованы: app.json={app_version} ≥ min={min_version}")

    disabled = [name for name, enabled in config["flags"].items() if not enabled]
    if disabled:
        fail(
            f"выключены рубильником: {', '.join(disabled)}. Ревьюер увидит 503 "
            f"вместо фичи — включить перед сабмитом"
        )
    else:
        ok(f"все фичи включены ({len(config['flags'])})")


def check_legal_pages(client: httpx.Client) -> None:
    section("Юридические страницы (Guideline 5.1.1)")
    for name, url in (
        ("Privacy Policy", "https://vinyl-vertushka.ru/privacy"),
        ("Terms of Use", "https://vinyl-vertushka.ru/terms"),
    ):
        try:
            response = client.get(url, follow_redirects=True)
        except Exception as exc:
            fail(f"{name} ({url}) недоступна: {exc}")
            continue

        if response.status_code == 200:
            ok(f"{name} отдаётся ({url})")
        else:
            fail(f"{name} вернула {response.status_code} ({url})")


def check_demo_account(client: httpx.Client, base_url: str) -> None:
    section("Демо-аккаунт для ревью (Guideline 2.1)")

    email, password = os.environ.get("DEMO_EMAIL"), os.environ.get("DEMO_PASSWORD")
    if not (email and password):
        warn("DEMO_EMAIL / DEMO_PASSWORD не заданы — проверки пропущены")
        return

    try:
        response = client.post(
            f"{base_url}/api/auth/login", json={"email": email, "password": password}
        )
    except Exception as exc:
        fail(f"логин демо-аккаунта упал: {exc}")
        return

    if response.status_code != 200:
        fail(
            f"демо-аккаунт не логинится по email+паролю ({response.status_code}). "
            f"У ревьюера нет доступа к Apple/Discogs-входу — только пароль"
        )
        return
    ok("демо-аккаунт логинится по email+паролю")

    token = response.json().get("access_token")
    if not token:
        fail("логин прошёл, но access_token не вернулся")
        return

    headers = {"Authorization": f"Bearer {token}"}

    for label, path, minimum, counter in (
        ("коллекция", "/api/collections/", MIN_DEMO_RECORDS, _count_collection_records),
        ("вишлист", "/api/wishlists/", MIN_DEMO_WISHLIST, _count_wishlist_items),
    ):
        try:
            data = client.get(f"{base_url}{path}", headers=headers).json()
        except Exception as exc:
            warn(f"не удалось прочитать {label}: {exc}")
            continue

        count = counter(data)
        if count is None:
            warn(f"{label}: не удалось посчитать элементы, проверь глазами")
        elif count < minimum:
            fail(
                f"{label} демо-аккаунта: {count} (нужно ≥{minimum}). Пустой экран "
                f"у ревьюера читается как «приложение не работает»"
            )
        else:
            ok(f"{label} демо-аккаунта наполнена: {count}")


def _count_collection_records(payload) -> int | None:
    """Пластинок во всех коллекциях.

    `GET /api/collections/` отдаёт список КОЛЛЕКЦИЙ (папок), а не пластинок —
    считать `len()` значило бы получить 1 вместо пятнадцати. Суммируем
    items_count по всем папкам.
    """
    if not isinstance(payload, list):
        return None
    total = 0
    for collection in payload:
        if not isinstance(collection, dict):
            return None
        total += collection.get("items_count") or 0
    return total


def _count_wishlist_items(payload) -> int | None:
    """`GET /api/wishlists/` отдаёт один вишлист с вложенным items."""
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        return len(payload["items"])
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Пресабмит-проверка перед App Store")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    print(f"Пресабмит-проверка: {base_url}")

    with httpx.Client(timeout=TIMEOUT) as client:
        check_health(client, base_url)
        check_remote_config(client, base_url)
        check_legal_pages(client)
        check_demo_account(client, base_url)

    print()
    if failures:
        print(f"{RED}СТОП: {len(failures)} провал(ов) — сабмитить нельзя{RESET}")
        for item in failures:
            print(f"  · {item}")
    else:
        print(f"{GREEN}Машинные проверки пройдены{RESET}")

    if warnings:
        print(f"{YELLOW}Предупреждений: {len(warnings)}{RESET}")
        for item in warnings:
            print(f"  · {item}")

    print(
        "\nОстальное — глазами: скриншоты, атрибуция Discogs в UI, возрастной "
        "рейтинг, Content Rights.\nСм. docs/plans/appstore/APPSTORE_PRERELEASE_AUDIT.md"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
