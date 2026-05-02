#!/usr/bin/env python3
"""
sync_roadmap.py — обновляет Changelog в docs/plans/ROADMAP.md
после merge PR в main.

Запуск:
  - Из GitHub Action (pull_request closed && merged):
      python scripts/sync_roadmap.py --from-event $GITHUB_EVENT_PATH
  - Локально (для отладки или ручного синка одного PR):
      python scripts/sync_roadmap.py --pr 9
  - Локально (досинхронизировать всё за период):
      python scripts/sync_roadmap.py --since 2026-04-01

Поведение:
  1. Парсит заголовок PR через conventional commits (`feat(scope): ...`).
  2. По scope определяет milestone через SCOPE_TO_MILESTONE.
  3. Дописывает строку в общий Changelog (секция 4) и в Changelog M-блока.
  4. Обновляет timestamp в шапке.
  5. Если запись уже есть (идемпотентность по PR номеру) — skip.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ROADMAP_PATH = REPO_ROOT / "ROADMAP.md"

# Маппинг conventional-commit scope → milestone code.
# Если scope не в словаре — запись попадает только в общий Changelog (секция 4).
SCOPE_TO_MILESTONE: dict[str, str] = {
    "design": "M1",
    "mascot": "M1",
    "theme": "M1",
    "ui": "M1",
    "release": "M2",
    "ios": "M2",
    "android": "M2",
    "store": "M2",
    "sentry": "M2",
    "submitted": "M3",
    "user-records": "M3",
    "import": "M4",
    "achievements": "M5",
    "achievement": "M5",
    "rarity": "M5",
    "shops": "M6",
    "ru-shops": "M6",
    "parsing": "M6",
    "affiliate": "M7",
    "partner": "M7",
    "marketplace": "M8",
    "p2p": "M8",
    "listing": "M8",
    "recommendations": "M9",
    "recs": "M9",
    "discover": "M9",
    "monetization": "M10",
    "premium": "M10",
    "analytics": "M10",
    "pricing": "M10",  # на текущем этапе RUB-pricing служит и unit-economics
}

CONVENTIONAL_RE = re.compile(r"^(?P<type>\w+)(?:\((?P<scope>[^)]+)\))?: (?P<summary>.+)$")


def run(cmd: list[str]) -> str:
    """Запустить shell-команду, вернуть stdout (stripped). Бросить при ошибке."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Command {cmd!r} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def fetch_pr_via_gh(pr_number: int) -> dict:
    """Загрузить PR через gh CLI."""
    raw = run(["gh", "pr", "view", str(pr_number), "--json", "number,title,mergedAt,url,state"])
    return json.loads(raw)


def fetch_prs_since(since_iso: str) -> list[dict]:
    """Загрузить все merged PR с указанной даты."""
    raw = run([
        "gh", "pr", "list",
        "--state", "merged",
        "--limit", "100",
        "--json", "number,title,mergedAt,url",
        "--search", f"merged:>{since_iso}",
    ])
    return json.loads(raw)


def parse_event_payload(event_path: str) -> dict | None:
    """Прочитать GitHub Actions event payload и достать PR-данные."""
    with open(event_path, encoding="utf-8") as f:
        payload = json.load(f)
    pr = payload.get("pull_request")
    if not pr:
        return None
    if not pr.get("merged"):
        return None
    return {
        "number": pr["number"],
        "title": pr["title"],
        "mergedAt": pr["merged_at"],
        "url": pr["html_url"],
    }


def detect_milestone(title: str) -> tuple[str | None, str]:
    """Вернуть (milestone_code | None, scope | '')."""
    match = CONVENTIONAL_RE.match(title)
    if not match:
        return None, ""
    scope = (match.group("scope") or "").strip().lower()
    if not scope:
        return None, ""
    primary_scope = scope.split("/")[0].split(",")[0].strip()
    return SCOPE_TO_MILESTONE.get(primary_scope), primary_scope


def format_changelog_line(pr: dict, milestone: str | None) -> str:
    """Отформатировать строку для секции Changelog."""
    date = pr["mergedAt"][:10]
    suffix = f" — _{milestone} relevant_" if milestone else ""
    return f"- **{date}** — [#{pr['number']}]({pr['url']}) {pr['title']}{suffix}"


def already_recorded(content: str, pr_number: int) -> bool:
    """Идемпотентность — проверка что #N уже есть в документе."""
    return bool(re.search(rf"#{pr_number}\b", content))


def insert_into_global_changelog(content: str, line: str, merged_at: str) -> str:
    """Добавить строку в общий Changelog (секция 4), сгруппированный по месяцам."""
    year_month_header = f"### {merged_at[:7]}"
    section_marker = "## 4. Changelog"
    section_idx = content.find(section_marker)
    if section_idx < 0:
        raise RuntimeError("Не найдена секция '## 4. Changelog' в ROADMAP.md")

    # Граница секции 4 — следующий ## заголовок верхнего уровня.
    next_section = re.search(r"\n## \d", content[section_idx + len(section_marker):])
    section_end = (
        section_idx + len(section_marker) + next_section.start()
        if next_section
        else len(content)
    )
    section = content[section_idx:section_end]

    if year_month_header in section:
        # Вставить как первую строку под заголовком месяца.
        new_section = section.replace(
            year_month_header + "\n\n",
            year_month_header + "\n\n" + line + "\n",
            1,
        )
    else:
        # Создать новый блок месяца сразу после '## 4. Changelog ...' и интро-параграфа.
        first_subsection_match = re.search(r"\n### \d{4}-\d{2}", section)
        insert_pos = first_subsection_match.start() if first_subsection_match else len(section)
        new_section = (
            section[:insert_pos]
            + f"\n\n{year_month_header}\n\n{line}\n"
            + section[insert_pos:]
        )

    return content[:section_idx] + new_section + content[section_end:]


def insert_into_milestone_changelog(content: str, milestone: str, line: str) -> str:
    """Добавить строку в Changelog конкретного M-блока."""
    milestone_re = re.compile(rf"### {milestone}\.[^\n]+\n.*?(?=\n### M\d+\.|\Z)", re.DOTALL)
    milestone_match = milestone_re.search(content)
    if not milestone_match:
        return content

    block = milestone_match.group(0)
    changelog_marker = "#### Changelog\n"
    cl_idx = block.find(changelog_marker)
    if cl_idx < 0:
        return content

    after_marker = cl_idx + len(changelog_marker)
    block_after = block[after_marker:]
    placeholder = "- _нет записей_\n"
    if placeholder in block_after:
        new_block_after = block_after.replace(placeholder, line + "\n", 1)
    else:
        new_block_after = line + "\n" + block_after

    new_block = block[:after_marker] + new_block_after
    return content[: milestone_match.start()] + new_block + content[milestone_match.end():]


def update_timestamp(content: str) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return re.sub(
        r"(\| \*\*Последнее обновление\*\* \| )\d{4}-\d{2}-\d{2}( \|)",
        rf"\g<1>{today}\g<2>",
        content,
    )


def sync_pr(pr: dict, content: str) -> tuple[str, bool]:
    """Применить один PR к содержимому. Вернуть (new_content, changed)."""
    if already_recorded(content, pr["number"]):
        return content, False

    milestone, _scope = detect_milestone(pr["title"])
    line = format_changelog_line(pr, milestone)

    new_content = insert_into_global_changelog(content, line, pr["mergedAt"])
    if milestone:
        new_content = insert_into_milestone_changelog(new_content, milestone, line)
    new_content = update_timestamp(new_content)
    return new_content, True


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync ROADMAP.md changelog from merged PRs")
    parser.add_argument("--pr", type=int, help="Sync single PR by number (uses gh CLI)")
    parser.add_argument("--from-event", help="Path to GITHUB_EVENT_PATH JSON (CI mode)")
    parser.add_argument("--since", help="Sync all merged PRs since YYYY-MM-DD (uses gh CLI)")
    parser.add_argument("--dry-run", action="store_true", help="Print result, do not write")
    args = parser.parse_args()

    prs: list[dict] = []
    if args.from_event:
        pr = parse_event_payload(args.from_event)
        if pr is None:
            print("[sync_roadmap] event has no merged PR — skipping")
            return 0
        prs = [pr]
    elif args.pr:
        prs = [fetch_pr_via_gh(args.pr)]
    elif args.since:
        prs = fetch_prs_since(args.since)
    else:
        parser.error("provide --pr, --since, or --from-event")

    if not ROADMAP_PATH.exists():
        print(f"[sync_roadmap] ROADMAP.md not found at {ROADMAP_PATH}", file=sys.stderr)
        return 1

    content = ROADMAP_PATH.read_text(encoding="utf-8")
    changed_any = False
    # Сортируем от старых к новым — чтобы новые попадали в начало секции, старые ниже.
    for pr in sorted(prs, key=lambda p: p["mergedAt"]):
        content, changed = sync_pr(pr, content)
        if changed:
            changed_any = True
            print(f"[sync_roadmap] added #{pr['number']} — {pr['title']}")
        else:
            print(f"[sync_roadmap] skipped #{pr['number']} (already recorded)")

    if not changed_any:
        print("[sync_roadmap] nothing to update")
        return 0

    if args.dry_run:
        sys.stdout.write(content)
        return 0

    ROADMAP_PATH.write_text(content, encoding="utf-8")
    print(f"[sync_roadmap] wrote {ROADMAP_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
