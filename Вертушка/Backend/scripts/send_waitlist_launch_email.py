"""Рассылка ссылки на App Store по waitlist — то самое обещанное письмо.

Кнопка «Попробовать приложение Вертушка» на публичном профиле до релиза
открывала модалку и складывала email в `waitlist_entries` с обещанием:
«никакого спама, только один email с релизом». Скрипт это обещание закрывает.

Идемпотентность: адрес, у которого хоть одна строка с `notified_at`, из
выборки выпадает. Отметка ставится сразу после успешной отправки и
коммитится по одному письму — обрыв посередине не приводит к дублям.

Запуск (сначала всегда --dry-run, потом тест на себя, потом всем):
    ./scripts/send_waitlist_launch_email.sh --dry-run
    ./scripts/send_waitlist_launch_email.sh --only me@example.com --force
    ./scripts/send_waitlist_launch_email.sh
"""
import argparse
import asyncio
import logging
from datetime import datetime

from sqlalchemy import func, select, update

from app.config import get_settings
from app.database import async_session_maker
from app.models.waitlist import WaitlistEntry
from app.services.notifications import send_email

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("waitlist-launch")

SUBJECT = "Вертушка вышла в App Store"


def build_html(store_url: str) -> str:
    return f"""
    <div style="font-family:'Helvetica Neue',Arial,sans-serif;max-width:520px;margin:0 auto;background:#F5F0EA;border-radius:16px;overflow:hidden;">
      <div style="background:#1B1D26;padding:28px 32px;">
        <span style="color:#ffffff;font-size:18px;font-weight:700;letter-spacing:2px;">ВЕРТУШКА</span>
      </div>
      <div style="padding:32px;">
        <h1 style="margin:0 0 12px;color:#1B1D26;font-size:24px;font-weight:700;line-height:1.25;">
          Мы в App Store
        </h1>
        <p style="margin:0 0 24px;color:#5A5F7A;font-size:15px;line-height:1.6;">
          Ты оставил(а) почту на чьём-то публичном профиле в Вертушке — мы обещали
          написать один раз, когда приложение появится в сторе. Это то самое письмо.
        </p>
        <div style="text-align:center;margin-bottom:28px;">
          <a href="{store_url}" style="display:inline-block;background:#3B4BF5;color:#ffffff;font-size:15px;font-weight:600;text-decoration:none;padding:14px 32px;border-radius:999px;">
            Скачать в App Store
          </a>
        </div>
        <div style="background:#ffffff;border-radius:12px;padding:20px 24px;margin-bottom:24px;border:1px solid rgba(27,29,38,0.08);">
          <p style="margin:0 0 12px;color:#1B1D26;font-size:14px;font-weight:600;">Что внутри</p>
          <p style="margin:0 0 8px;color:#5A5F7A;font-size:14px;line-height:1.6;">
            — Коллекция и вишлист: добавляешь пластинку по фото обложки или поиском по Discogs.
          </p>
          <p style="margin:0 0 8px;color:#5A5F7A;font-size:14px;line-height:1.6;">
            — Оценка: сколько стоит собранное и как меняется в цене.
          </p>
          <p style="margin:0;color:#5A5F7A;font-size:14px;line-height:1.6;">
            — Публичный профиль — такой же, как тот, с которого ты сюда пришёл(а).
          </p>
        </div>
        <p style="margin:0;color:#9096A6;font-size:13px;line-height:1.6;">
          Android ещё в работе — адрес остаётся в списке, напишем, когда выйдем
          в Google Play. Других писем не будет.
        </p>
      </div>
      <div style="padding:16px 32px 24px;border-top:1px solid rgba(27,29,38,0.08);">
        <p style="margin:0;color:#9096A6;font-size:12px;">Вертушка — твоя коллекция винила · vinyl-vertushka.ru</p>
      </div>
    </div>
    """


async def _pending_emails(session, limit: int | None) -> list[str]:
    """Адреса, которым письмо ещё не уходило, в порядке подписки.

    Один человек мог подписаться с нескольких профилей — строк несколько,
    письмо одно. Поэтому отсекаем по email целиком, а не по строке.
    """
    already_sent = select(WaitlistEntry.email).where(WaitlistEntry.notified_at.isnot(None))
    query = (
        select(WaitlistEntry.email)
        .where(~WaitlistEntry.email.in_(already_sent))
        .group_by(WaitlistEntry.email)
        .order_by(func.min(WaitlistEntry.created_at))
    )
    if limit:
        query = query.limit(limit)
    return list((await session.execute(query)).scalars().all())


async def _mark_sent(session, email: str) -> None:
    await session.execute(
        update(WaitlistEntry)
        .where(WaitlistEntry.email == email, WaitlistEntry.notified_at.is_(None))
        .values(notified_at=datetime.utcnow())
    )
    await session.commit()


async def main() -> None:
    parser = argparse.ArgumentParser(description="Рассылка ссылки на стор по waitlist")
    parser.add_argument("--dry-run", action="store_true", help="показать список и выйти")
    parser.add_argument("--only", help="отправить только на этот адрес (тест на себе)")
    parser.add_argument(
        "--force", action="store_true",
        help="игнорировать notified_at (только вместе с --only)",
    )
    parser.add_argument("--limit", type=int, help="отправить не больше N писем за прогон")
    parser.add_argument(
        "--delay", type=float, default=0.6,
        help="пауза между письмами, сек (Resend по умолчанию держит 2 rps)",
    )
    args = parser.parse_args()

    if args.force and not args.only:
        parser.error("--force разрешён только вместе с --only")

    settings = get_settings()
    store_url = settings.app_store_url
    if not store_url:
        log.error("APP_STORE_URL пуст — рассылать нечего")
        return
    html = build_html(store_url)
    log.info("store_url=%s from=%s", store_url, settings.email_from or "(EMAIL_FROM не задан!)")

    async with async_session_maker() as session:
        if args.only:
            targets = [args.only.strip().lower()]
            if not args.force:
                pending = await _pending_emails(session, None)
                if targets[0] not in pending:
                    log.warning("%s не в списке или уже получил письмо — нужен --force", targets[0])
                    return
        else:
            targets = await _pending_emails(session, args.limit)

        log.info("к отправке: %d адресов", len(targets))
        if args.dry_run:
            for email in targets:
                log.info("  dry-run → %s", email)
            return

        sent = failed = 0
        for i, email in enumerate(targets, 1):
            ok = await send_email(email, SUBJECT, html)
            if ok:
                await _mark_sent(session, email)
                sent += 1
            else:
                failed += 1
                log.error("не отправлено: %s", email)
            if i % 25 == 0:
                log.info("прогресс: %d/%d (ошибок %d)", i, len(targets), failed)
            if i < len(targets):
                await asyncio.sleep(args.delay)

        log.info("готово: отправлено %d, ошибок %d", sent, failed)
        if failed:
            log.info("неотправленные остались без notified_at — повторный запуск их доберёт")


if __name__ == "__main__":
    asyncio.run(main())
