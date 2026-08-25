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
#   3. читает водяной знак прошлого дампа (discogs_dump_state), снимает с прода
#      список записей без жанра и вытаскивает три выгрузки: formats_*.csv.gz
#      (полные описания формата), new_*.csv.gz (релизы, которых в индексе нет)
#      и genres_*.csv.gz (жанры/стили для records с пустым genre);
#   4. заливает все на прод и грузит;
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

# Имя API-контейнера спрашиваем у прода, а не зашиваем: деплой сине-зелёный, и
# контейнер называется vertushka_api_blue или vertushka_api_green по очереди.
# Захардкоженный vertushka_api ронял заливку на `docker cp` с «No such container».
API_CONTAINER="${API_CONTAINER:-$(ssh "$PROD" 'docker ps --format "{{.Names}}" | grep -E "^vertushka_api(_(blue|green))?$" | head -1')}"
[[ -n "$API_CONTAINER" ]] || { echo "не нашёл запущенный API-контейнер на проде" >&2; exit 1; }
log "API-контейнер на проде: $API_CONTAINER"

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
# Отметка берётся из discogs_dump_state, а НЕ из max(discogs_id) по индексу.
# В индекс пишет и живой путь (upsert_release_into_index): стоило юзеру открыть
# в приложении свежую пластинку, и её id задирал отметку — следующая дельта
# отрезала всё до неё. Так в августе 2026 потерялось 721 515 id: майский дамп
# кончился на 37 220 946, отметку поставила живая строка 37 942 461, и в дыре
# осело 298 строк вместо сотен тысяч.
SINCE_ID="$(ssh "$PROD" "$PSQL -c 'SELECT max(max_release_id) FROM discogs_dump_state;'" | tr -d '[:space:]')"
[[ "$SINCE_ID" =~ ^[0-9]+$ ]] || { echo "не смог прочитать водяной знак из discogs_dump_state: '$SINCE_ID' (миграция 20260814_dump_state применена?)" >&2; exit 1; }
log "водяной знак прошлого дампа: $SINCE_ID"

# Список записей, которым нужен жанр. Жанровые чипы Маркета фильтруют по
# records.genre, а заполнялся он только живым Discogs API — у карточек, которые
# кто-то открыл руками. Склад магазинов матчер создаёт из дампа, где колонок
# genre/style нет вовсе, так что на 25.08.2026 жанр был у ~390 карточек из ~30
# тысяч. Фильтруем выгрузку списком, а не тащим жанры всех 19M релизов: на
# прод-диске свободно ~3 ГБ, полная таблица жанров (~0.9 ГБ) туда не влезет.
IDS_FILE="$WORK_DIR/genre_ids_${STAMP}.txt"
ssh "$PROD" "$PSQL -c \"SELECT discogs_id FROM records WHERE discogs_id ~ '^[0-9]+\$' AND merged_into_id IS NULL AND (genre IS NULL OR btrim(genre) = '');\"" > "$IDS_FILE"
IDS_COUNT="$(wc -l < "$IDS_FILE" | tr -d '[:space:]')"
log "записей без жанра на проде: $IDS_COUNT"

log "парсю дамп (~15 мин)..."
EXTRA_ARGS=()
# Пустой список — не повод падать: жанры у всех, кого мы знаем, уже стоят.
# Но и запускать выгрузку не надо, иначе extractor честно ругнётся на пустоту.
[[ "$IDS_COUNT" -gt 0 ]] && EXTRA_ARGS+=(--ids-file "$IDS_FILE")
(cd "$BACKEND" && python -m app.scripts.extract_release_formats \
  --file "$WORK_DIR/$DUMP" --out-dir "$WORK_DIR" --dump-date "$ISO" --since-id "$SINCE_ID" \
  "${EXTRA_ARGS[@]}")

# --- 4. заливаем -------------------------------------------------------------
for f in "formats_${STAMP}.csv.gz" "new_${STAMP}.csv.gz" "genres_${STAMP}.csv.gz"; do
  [[ -s "$f" ]] || { log "нет $f — пропускаю"; continue; }
  log "загружаю $f ($(du -h "$f" | cut -f1))"
  # -O: macOS 15 гонит scp через sftp, и тот падает «no such directory» на
  # путях вида host:/tmp/ — старый протокол работает.
  scp -O "$f" "$PROD:/tmp/$f"
  ssh "$PROD" "docker cp /tmp/$f $API_CONTAINER:/tmp/ && rm /tmp/$f"
done

if ssh "$PROD" "docker exec $API_CONTAINER test -f /tmp/formats_${STAMP}.csv.gz"; then
  log "гружу описания форматов"
  ssh "$PROD" "docker exec $API_CONTAINER python -m app.scripts.load_release_formats \
    --file /tmp/formats_${STAMP}.csv.gz --dump-date $ISO"
fi
if ssh "$PROD" "docker exec $API_CONTAINER test -f /tmp/new_${STAMP}.csv.gz"; then
  log "гружу новые релизы"
  ssh "$PROD" "docker exec $API_CONTAINER python -m app.scripts.load_new_releases \
    --file /tmp/new_${STAMP}.csv.gz --dump-date $ISO"
fi
# Жанры грузим ПОСЛЕ новых релизов: у только что приехавшей строки индекса
# записи в records ещё нет, но если она появится следующим матчем — жанр ей
# добудет уже следующий прогон. Порядок в обратную сторону не даёт ничего.
if ssh "$PROD" "docker exec $API_CONTAINER test -f /tmp/genres_${STAMP}.csv.gz"; then
  log "гружу жанры"
  ssh "$PROD" "docker exec $API_CONTAINER python -m app.scripts.load_release_genres \
    --file /tmp/genres_${STAMP}.csv.gz"
fi

# --- 5. уборка ---------------------------------------------------------------
ssh "$PROD" "docker exec $API_CONTAINER sh -c 'rm -f /tmp/formats_*.csv.gz /tmp/new_*.csv.gz /tmp/genres_*.csv.gz'"
rm -f "$IDS_FILE"
# Обложки/классификация кэшируются — иначе свежие данные всплывут только через сутки.
ssh "$PROD" "docker exec vertushka_redis redis-cli --scan --pattern 'artist_masters:*' \
  | xargs -r docker exec -i vertushka_redis redis-cli del" >/dev/null || true

ssh "$PROD" "$PSQL -c \"SELECT 'релизов: ' || count(*) FROM discogs_releases_index;\" \
  -c \"SELECT 'с полным форматом: ' || count(*) FROM discogs_release_formats;\" \
  -c \"SELECT 'записей с жанром: ' || count(*) FROM records WHERE btrim(coalesce(genre,'')) <> '';\""

if [[ -z "${KEEP_DUMP:-}" ]]; then
  log "удаляю дамп"
  rm -f "$DUMP"
fi
log "готово"
