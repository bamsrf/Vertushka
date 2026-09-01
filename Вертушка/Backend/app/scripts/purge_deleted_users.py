"""Окончательное удаление аккаунтов, помеченных на удаление.

`DELETE /api/users/me` ставит `deleted_at` и `scheduled_purge_at = now + 30д` —
это окно на «передумал». Здесь окно закрывается: строки уходят из БД, файлы —
с диска.

Запускается джобой APScheduler (`purge_deleted_users` в main.py, 04:30 в
scheduler-контейнере). Раньше здесь стояло «запуск через cron раз в сутки», но
этот cron нигде не был заведён — то есть вычистка не происходила вообще и
обещание «удалим через 30 дней» не выполнялось. См.
docs/plans/appstore/SECURITY_AUDIT_PRERELEASE.md §S3.

Ручной прогон (например, чтобы разобрать накопившееся):
  docker compose exec api python -m app.scripts.purge_deleted_users
"""
import asyncio
import logging
import shutil
from datetime import datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from app.database import async_session_maker, engine
from app.models.user import User
from app.services import apple_auth
from app.services.secret_crypto import decrypt_secret

logger = logging.getLogger(__name__)

# Пути относительные, в контейнере CWD=/app. Держать в синхронизации с
# app/api/user_photos.py::_photo_dir и app/api/users.py::upload_avatar —
# если там появится настройка, сюда приедет она же.
_USER_PHOTOS_ROOT = Path("uploads") / "user_photos"
_AVATARS_ROOT = Path("uploads") / "avatars"

# ЧЕГО ЗДЕСЬ НАМЕРЕННО НЕТ: обложки user-записей (uploads/covers/user_{record_id}.jpg).
# У Record.created_by_user_id стоит ondelete='SET NULL', то есть сама запись
# переживает удаление автора и остаётся в общем каталоге — одобренная
# user-запись это уже справочные данные, на неё ссылаются чужие коллекции.
# Удалять её обложку значило бы оставить в каталоге битую карточку. Если
# продуктово решим, что записи должны уходить вместе с автором, — менять надо
# каскад в модели, а не дочищать файлы здесь.


def _drop_user_files(user_id: UUID) -> int:
    """Удаляет файлы юзера с диска. Возвращает число удалённых файлов.

    Каскады в БД чистят строки, но JPEG'и лежат на диске и переживали бы
    удаление аккаунта — а это самое чувствительное из UGC: снимки, сделанные
    дома у человека, и портрет в аватаре.
    """
    removed = 0

    photo_dir = _USER_PHOTOS_ROOT / str(user_id)
    if photo_dir.exists():
        removed += sum(1 for p in photo_dir.rglob("*") if p.is_file())
        shutil.rmtree(photo_dir, ignore_errors=True)

    # Аватар — плоский файл {user_id}.jpg, см. users.py::upload_avatar.
    avatar = _AVATARS_ROOT / f"{user_id}.jpg"
    if avatar.exists():
        avatar.unlink(missing_ok=True)
        removed += 1

    return removed


async def purge() -> int:
    """Вычищает всех, у кого истекло окно. Возвращает число удалённых аккаунтов."""
    async with async_session_maker() as session:
        result = await session.execute(
            select(User).where(
                User.deleted_at.isnot(None),
                User.scheduled_purge_at <= datetime.utcnow(),
            )
        )
        users = result.scalars().all()

        if not users:
            logger.info("purge_deleted_users: нечего вычищать")
            return 0

        # id собираем ДО удаления: после commit объекты отвязаны от сессии.
        doomed = [(u.id, u.username) for u in users]

        for user in users:
            logger.info(
                "purge_deleted_users: удаляю %s (%s), deleted_at=%s",
                user.username, user.id, user.deleted_at,
            )
            # Последняя попытка отозвать доступ Apple: при удалении аккаунта
            # мы уже пробовали, но Apple мог быть недоступен. Дальше строка
            # исчезнет вместе с токеном — второго шанса не будет.
            if user.apple_refresh_token:
                token = decrypt_secret(user.apple_refresh_token)
                if token:
                    revoked = await apple_auth.revoke_refresh_token(token)
                    logger.info(
                        "purge_deleted_users: apple revoke %s → %s",
                        user.username, revoked,
                    )
            await session.delete(user)  # ondelete=CASCADE в БД уберёт связанные строки

        await session.commit()

    # Файлы — строго ПОСЛЕ успешного commit. Обратный порядок означал бы, что
    # откат транзакции оставит живой аккаунт без фотографий; осиротевшая папка
    # при падении после commit — куда меньшая беда, и её видно по логу.
    total_files = 0
    for user_id, username in doomed:
        try:
            total_files += _drop_user_files(user_id)
        except Exception:
            logger.warning(
                "purge_deleted_users: не удалось удалить файлы %s (%s)",
                username, user_id, exc_info=True,
            )

    logger.info(
        "purge_deleted_users: удалено аккаунтов=%d, файлов=%d", len(doomed), total_files,
    )
    return len(doomed)


async def main():
    try:
        await purge()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    # basicConfig только для ручного запуска. На уровне модуля он затирал бы
    # JSON-хендлер, который main.py ставит на root-логгер.
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(main())
