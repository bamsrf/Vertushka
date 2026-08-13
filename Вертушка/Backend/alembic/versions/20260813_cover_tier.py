"""Тир обложки: records.cover_min_side + discogs_releases_index.thumb_image_url

Discogs в `/masters/{id}/versions` отдаёт по каждой версии только `thumb`
(h:150/w:150, размер запечён в подпись HMAC — увеличить нельзя, подмена `w:`
даёт 403). Функция `_thumb_to_cover` должна была апскейлить его по старой схеме
CDN (`_150.jpg` → `_500.jpg`), но нынешние URL под этот regex не подходят, и она
молча возвращала вход. В результате 150px уезжал в поле «обложка», а дальше:

1. зеркало принимало его как мастер (порога размера не было) → 150px на диске,
   imgproxy честно резал из него → деталь-экран получал апскейл ×8;
2. персист в `discogs_releases_index.cover_image_url` делал строку NOT NULL, а
   офлайн-каналы CAA (`ingest_mb_discogs_map`, `ingest_mb_barcode_covers`) пишут
   ТОЛЬКО в `IS NULL` — то есть full-1200 для этого релиза не приезжал уже
   никогда. Один и тот же механизм давал и пиксели, и вечную зависимость от
   Discogs API.

Две колонки разводят тир по местам хранения:

- `records.cover_min_side` — меньшая сторона уложенного мастера в пикселях.
  Ниже `cover_quality.MASTER_MIN_SIDE` = мелкая: годится в плейсхолдер, и
  зеркало имеет право перезаписать её лучшим источником. NULL = «не мерили»
  (все файлы до этой правки) — апгрейд их не трогает, иначе первый прогрев
  после деплоя устроил бы перекачку всех ~13K зеркал.
- `discogs_releases_index.thumb_image_url` — куда теперь складываются
  thumb-grade URL. База обложек только накапливается: мелкую ссылку не
  выбрасываем, но и в канонический слот не пускаем, поэтому `cover_image_url`
  остаётся NULL и офлайн-CAA снова может её заполнить.

Backfill данных здесь НЕ делается намеренно. Демоут уже отравленных строк и
замер размеров существующих файлов — в `scripts/heal_cover_tiers.py`: логика
определения тира живёт в `cover_quality`, дублировать её regex'ами в SQL значит
гарантировать расхождение. Плюс размеры файлов на диске SQL не видит в принципе,
а скрипт умеет батчи и dry-run.

Revision ID: 20260813_cover_tier
"""
import sqlalchemy as sa
from alembic import op

revision = "20260813_cover_tier"
down_revision = "20260812_match_attempt"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "records",
        sa.Column("cover_min_side", sa.Integer(), nullable=True),
    )
    op.add_column(
        "discogs_releases_index",
        sa.Column("thumb_image_url", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("discogs_releases_index", "thumb_image_url")
    op.drop_column("records", "cover_min_side")
