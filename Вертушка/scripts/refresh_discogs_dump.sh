#!/usr/bin/env bash
# Обновление локального дамп-индекса Discogs: свежие описания форматов + новинки.
#
# ЗАПУСКАТЬ НЕ НА ПРОДЕ. data.discogs.com встречает прод-сервер JS-челленджем
# Cloudflare (IP дата-центра) — curl получает 403 и HTML вместо гигабайтов.
# Поэтому дамп качается и парсится на машине с «обычным» IP, а на прод уезжает
# только CSV.gz: два порядка меньше, и прод-диску (свободно ~3 ГБ) не больно.
#
# Что делает:
#   1. находит свежайший releases-дамп на data.discogs.com;
#   2. качает (~10.4 ГБ, ~40 мин), если ещё не скачан;
#   3. спрашивает у прода max(discogs_id) и вытаскивает две выгрузки:
#      formats_*.csv.gz (полные описания формата) и new_*.csv.gz (релизы,
#      которых в индексе нет);
#   4. заливает обе на прод и грузит;
#   5. чистит за собой.
#
# Каденс: раз в 2 месяца. Чаще смысла нет — дамп месячный, а дельта за месяц
# мелкая; реже — новинки заметно отстают.
#
# Использование:
#   scripts/refresh_discogs_dump.sh                 # полный цикл
#   KEEP_DUMP=1 scripts/refresh_discogs_dump.sh     # не удалять дамп после
#   DUMP_DATE=20260701 scripts/refresh_discogs_dump.sh  # конкретный дамп
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$REPO_ROOT/Backend"
WORK_DIR="${WORK_DIR:-$HOME/.cache/vertushka-discogs}"
PROD="${PROD:-deploy@85.198.85.12}"
PSQL="docker exec vertushka_db psql -U vertushka_user -d vertushka -t -A"

mkdir -p "$WORK_DIR"
cd "$WORK_DIR"

log() { printf '%s  %s\n' "$(date +%H:%M:%S)" "$*"; }

# --- 1. какой дамп берём -----------------------------------------------------
YEAR="$(date +%Y)"
if [[ -n "${DUMP_DATE:-}" ]]; then
  STAMP="$DUMP_DATE"
else
  # Страница-листинг отдаёт ссылки вида ?download=data%2F2026%2Fdiscogs_20260801_releases.xml.gz
  STAMP="$(curl -sL "https://data.discogs.com/?prefix=data/$YEAR/" \
    | grep -oE 'discogs_[0-9]{8}_releases\.xml\.gz' \
    | grep -oE '[0-9]{8}' | sort -u | tail -1)"
fi
[[ -n "$STAMP" ]] || { echo "не нашёл дамп на data.discogs.com" >&2; exit 1; }
ISO="${STAMP:0:4}-${STAMP:4:2}-${STAMP:6:2}"
DUMP="discogs_${STAMP}_releases.xml.gz"
log "дамп: $DUMP ($ISO)"

# --- 2. скачиваем ------------------------------------------------------------
verify_dump() {
  # Сервер отдаёт файл chunked и БЕЗ Content-Length, поэтому curl завершается
  # с кодом 0 даже когда соединение оборвалось на середине: «успешная»
  # загрузка может оказаться огрызком. Единственная надёжная проверка —
  # официальный SHA-256 из CHECKSUM.txt рядом с дампом.
  local want
  want="$(curl -sL "https://data.discogs.com/?download=data%2F$YEAR%2Fdiscogs_${STAMP}_CHECKSUM.txt" \
    | awk -v f="$DUMP" '$2 == f {print $1}')"
  if [[ -z "$want" ]]; then
    log "ВНИМАНИЕ: не нашёл контрольную сумму для $DUMP — проверить нечем"
    return 0
  fi
  log "считаю sha256 (~2 мин)..."
  local got
  got="$(shasum -a 256 "$1" | awk '{print $1}')"
  [[ "$got" == "$want" ]] || { log "sha256 не сошёлся: $got != $want"; return 1; }
  log "sha256 совпал"
}

if [[ -s "$DUMP" ]]; then
  log "уже скачан ($(du -h "$DUMP" | cut -f1)), пропускаю"
else
  log "качаю ~10.4 ГБ, это ~40 минут..."
  # Докачки нет: на Range-запрос сервер отвечает 200 с полным телом, без
  # Accept-Ranges. Поэтому `curl -C -` бесполезен — качаем в .part и
  # переименовываем только после успешной проверки суммы, чтобы обрыв не
  # оставил огрызок, который следующий прогон примет за готовый файл.
  # 11.2 ГБ одним потоком без права на ошибку — обрывы тут норма, не исключение.
  # Наблюдалось: rc=92 (HTTP/2 stream INTERNAL_ERROR у Cloudflare на ~5 ГБ),
  # rc=28 (просадка скорости), rc=56 (recv failure сразу после оборванной
  # попытки — похоже на троттлинг, потому пауза между заходами).
  #   --http1.1        — лечит класс rc=92;
  #   --speed-time 300 — не убивать закачку из-за минутной просадки;
  #   --no-progress-meter — иначе прогресс-бар забивает лог launchd.
  for attempt in 1 2 3 4 5 6; do
    log "попытка $attempt"
    curl -fL --http1.1 --no-progress-meter --speed-limit 50000 --speed-time 300 \
      -o "$DUMP.part" "https://data.discogs.com/?download=data%2F$YEAR%2F$DUMP" \
      || log "curl rc=$?"
    if verify_dump "$DUMP.part"; then
      mv "$DUMP.part" "$DUMP"
      break
    fi
    rm -f "$DUMP.part"
    log "битая загрузка, пауза 60с"
    sleep 60
  done
  [[ -s "$DUMP" ]] || { echo "не смог скачать дамп за 6 попыток" >&2; exit 1; }
fi

# --- 3. извлекаем ------------------------------------------------------------
SINCE_ID="$(ssh "$PROD" "$PSQL -c 'SELECT max(discogs_id) FROM discogs_releases_index;'" | tr -d '[:space:]')"
[[ "$SINCE_ID" =~ ^[0-9]+$ ]] || { echo "не смог узнать max(discogs_id): '$SINCE_ID'" >&2; exit 1; }
log "max(discogs_id) на проде: $SINCE_ID"

log "парсю дамп (~15 мин)..."
(cd "$BACKEND" && python -m app.scripts.extract_release_formats \
  --file "$WORK_DIR/$DUMP" --out-dir "$WORK_DIR" --dump-date "$ISO" --since-id "$SINCE_ID")

# --- 4. заливаем -------------------------------------------------------------
for f in "formats_${STAMP}.csv.gz" "new_${STAMP}.csv.gz"; do
  [[ -s "$f" ]] || { log "нет $f — пропускаю"; continue; }
  log "загружаю $f ($(du -h "$f" | cut -f1))"
  # -O: macOS 15 гонит scp через sftp, и тот падает «no such directory» на
  # путях вида host:/tmp/ — старый протокол работает.
  scp -O "$f" "$PROD:/tmp/$f"
  ssh "$PROD" "docker cp /tmp/$f vertushka_api:/tmp/ && rm /tmp/$f"
done

if ssh "$PROD" "docker exec vertushka_api test -f /tmp/formats_${STAMP}.csv.gz"; then
  log "гружу описания форматов"
  ssh "$PROD" "docker exec vertushka_api python -m app.scripts.load_release_formats \
    --file /tmp/formats_${STAMP}.csv.gz --dump-date $ISO"
fi
if ssh "$PROD" "docker exec vertushka_api test -f /tmp/new_${STAMP}.csv.gz"; then
  log "гружу новые релизы"
  ssh "$PROD" "docker exec vertushka_api python -m app.scripts.load_new_releases \
    --file /tmp/new_${STAMP}.csv.gz --dump-date $ISO"
fi

# --- 5. уборка ---------------------------------------------------------------
ssh "$PROD" "docker exec vertushka_api sh -c 'rm -f /tmp/formats_*.csv.gz /tmp/new_*.csv.gz'"
# Обложки/классификация кэшируются — иначе свежие данные всплывут только через сутки.
ssh "$PROD" "docker exec vertushka_redis redis-cli --scan --pattern 'artist_masters:*' \
  | xargs -r docker exec -i vertushka_redis redis-cli del" >/dev/null || true

ssh "$PROD" "$PSQL -c \"SELECT 'релизов: ' || count(*) FROM discogs_releases_index;\" \
  -c \"SELECT 'с полным форматом: ' || count(*) FROM discogs_release_formats;\""

if [[ -z "${KEEP_DUMP:-}" ]]; then
  log "удаляю дамп"
  rm -f "$DUMP"
fi
log "готово"
