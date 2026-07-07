#!/bin/bash
# Ежедневный снапшот заполняемости обложек. Пишет строку в
# ~/vertushka/backfill_daily.log. Ставится в host-crontab (см. низ файла).
# Читать: ssh deploy@85.198.85.12 'cat ~/vertushka/backfill_daily.log'
set -e
cd ~/vertushka/Вертушка/Backend

OUT=$(docker compose -f docker-compose.prod.yml exec -T db sh -c 'psql -tA -U "$POSTGRES_USER" -d vertushka' <<'SQL'
WITH m AS (
  SELECT master_id, bool_and(cover_image_url IS NULL) AS an
  FROM discogs_releases_index WHERE master_id IS NOT NULL AND master_id<>0
  GROUP BY master_id
)
SELECT 'masters_covered='||
  count(*) FILTER (WHERE NOT an OR EXISTS(SELECT 1 FROM discogs_master_covers mc WHERE mc.master_id=m.master_id))
  ||'/'||count(*) FROM m;
SELECT 'index_rows_covered='||count(*) FILTER (WHERE cover_image_url IS NOT NULL)||'/'||count(*)
  FROM discogs_releases_index;
SELECT 'backfill_masters_done='||count(*) FILTER (WHERE done)||'/'||count(*) FROM cover_backfill_masters;
SELECT 'deezer_covers='||count(*) FROM discogs_master_covers WHERE source='deezer';
SQL
)

TS=$(date -u +%Y-%m-%dT%H:%MZ)
echo "$TS | $(echo $OUT | tr '\n' ' ')" >> ~/vertushka/backfill_daily.log

# --- Установка крона (один раз, вручную) ---
# crontab -l 2>/dev/null | grep -q backfill_snapshot || \
#   (crontab -l 2>/dev/null; echo "7 9 * * * bash ~/vertushka/Вертушка/Backend/scripts/backfill_snapshot.sh") | crontab -
