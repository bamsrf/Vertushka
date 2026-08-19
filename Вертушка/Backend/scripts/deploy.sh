#!/bin/bash
# ===========================================
# Скрипт деплоя Вертушка API
# ===========================================

set -e  # Остановить при ошибке

# Цвета для вывода
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}🚀 Начинаю деплой Вертушка API...${NC}"

# Перейти в директорию проекта
cd ~/vertushka

# Сохранить локальные изменения перед pull (если есть)
if ! git diff-index --quiet HEAD --; then
    echo "💾 Сохраняю локальные изменения..."
    git stash push -m "Auto-stash before deploy $(date +%Y-%m-%d_%H:%M:%S)"
    STASHED=true
else
    STASHED=false
fi

# Получить последние изменения
echo "📥 Получаю обновления из git..."
git pull

# Попытаться применить сохранённые изменения обратно (если были)
if [ "$STASHED" = true ]; then
    echo "🔄 Пытаюсь применить сохранённые изменения..."
    if git stash pop 2>/dev/null; then
        echo "✅ Локальные изменения успешно применены"
    else
        echo "⚠️  Не удалось автоматически применить локальные изменения (возможны конфликты)"
        echo "   Используйте 'git stash list' и 'git stash show' для просмотра"
    fi
fi

# Перейти в Backend
cd Вертушка/Backend

# Pre-flight: проверить что есть достаточно места для билда.
# Билд распаковывает слои + промежуточные стадии — нужно >1 ГБ свободного,
# иначе docker умирает с "no space left on device" посередине пересоздания
# контейнера, и api остаётся в нерабочем состоянии.
AVAIL_MB=$(df -BM / | awk 'NR==2 {print $4}' | tr -dc '0-9')
echo "💾 Свободно на /: ${AVAIL_MB} МБ"
if [ "$AVAIL_MB" -lt 1000 ]; then
    echo -e "${YELLOW}⚠️  Свободного места <1000 МБ. Освобождаю build cache и dangling образы...${NC}"
    docker buildx prune -af 2>&1 | tail -1
    docker image prune -f 2>&1 | tail -1
    AVAIL_MB=$(df -BM / | awk 'NR==2 {print $4}' | tr -dc '0-9')
    echo "   После очистки: ${AVAIL_MB} МБ"
    if [ "$AVAIL_MB" -lt 1000 ]; then
        echo -e "${YELLOW}❌ Всё равно мало места. Деплой остановлен. Проверь: df -h / && docker system df${NC}"
        exit 1
    fi
fi

# ===========================================================================
# BLUE-GREEN ДЕПЛОЙ API (zero-downtime)
# ===========================================================================
# Один образ, два цвета-контейнера (vertushka_api_blue / _green). В покое активен
# один. Деплой поднимает второй, ждёт его healthy, переключает nginx graceful
# reload'ом, гасит старый. Если новый цвет не поднялся — nginx НЕ переключается,
# старый продолжает обслуживать → безопасный авто-rollback.
#
# ВАЖНО про миграции: они применяются ДО подъёма нового цвета и работают на живой
# схеме, которую в момент перекрытия читает ещё и СТАРЫЙ цвет. Поэтому миграции
# обязаны быть backward-compatible (только additive: nullable-колонки, новые
# таблицы/индексы; без DROP/RENAME/NOT NULL без дефолта). Breaking-изменение —
# отдельным двухфазным деплоем.
COMPOSE="docker compose -f docker-compose.prod.yml"
STATE_FILE="nginx/.active_color"
UPSTREAM_FILE="nginx/active_upstream.conf"

echo "🔨 Собираю Docker образ (api + scheduler)..."
$COMPOSE build api-blue scheduler   # api-blue и api-green делят image vertushka_api:latest

echo "📊 Применяю миграции базы данных (backward-compatible)..."
$COMPOSE run --rm -e PYTHONPATH=/app api-blue alembic upgrade head

# --- Одноразовый cutover со старой single-api схемы -------------------------
# Если ещё жив легаси-контейнер vertushka_api (до перехода на blue-green) —
# переводим стенд на api-blue и пересоздаём nginx (нужно, чтобы подхватить новый
# volume-mount active_upstream.conf; reload'а недостаточно).
if docker inspect vertushka_api >/dev/null 2>&1; then
    echo "🔀 Первый переход на blue-green: поднимаю api-blue..."
    $COMPOSE --profile blue up -d --no-deps api-blue
    printf 'set $api_upstream http://vertushka_api_blue:8000;\n' > "$UPSTREAM_FILE"
    # Ждём healthy нового контейнера ПЕРЕД тем как трогать nginx/легаси.
    CUT_OK=false
    for i in $(seq 1 45); do
        st=$(docker inspect -f '{{.State.Health.Status}}' vertushka_api_blue 2>/dev/null || echo "starting")
        if [ "$st" = "healthy" ]; then CUT_OK=true; break; fi
        sleep 2
    done
    if [ "$CUT_OK" != "true" ]; then
        # Не трогаем nginx и НЕ сносим легаси — прод остаётся на старом api.
        echo -e "${YELLOW}❌ api-blue не поднялся. Cutover прерван, прод остаётся на легаси vertushka_api.${NC}"
        echo "   Логи: $COMPOSE logs api-blue"
        $COMPOSE --profile blue stop api-blue 2>/dev/null || true
        rm -f "$UPSTREAM_FILE.tmp" 2>/dev/null || true
        # active_upstream.conf вернём к blue-дефолту из git на следующем pull;
        # старый nginx его ещё не читает (mount появится только при recreate).
        exit 1
    fi
    echo "blue" > "$STATE_FILE"
    echo "🔁 Пересоздаю nginx (подхватить mount active_upstream.conf)..."
    $COMPOSE up -d --force-recreate nginx
    echo "🗑  Сношу легаси-контейнер vertushka_api..."
    docker rm -f vertushka_api 2>/dev/null || true   # -f форс-удаляет запущенный
    ACTIVE="blue"
else
    # --- Штатный blue↔green свитч ------------------------------------------
    ACTIVE=$(cat "$STATE_FILE" 2>/dev/null || echo "blue")
    [ "$ACTIVE" = "blue" ] && TARGET="green" || TARGET="blue"
    echo "🎯 Активен: $ACTIVE → поднимаю новый цвет: $TARGET"

    # Поднимаем зависимости на случай, если что-то легло (db/redis/nginx/scheduler).
    # Цвета profile-gated → этот `up -d` их не трогает.
    $COMPOSE up -d

    $COMPOSE --profile "$TARGET" up -d --no-deps --force-recreate "api-$TARGET"

    echo "❤️  Жду healthy у api-$TARGET (до ~90 сек)..."
    HEALTHY=false
    for i in $(seq 1 45); do
        st=$(docker inspect -f '{{.State.Health.Status}}' "vertushka_api_$TARGET" 2>/dev/null || echo "starting")
        if [ "$st" = "healthy" ]; then
            HEALTHY=true
            echo "   ✅ api-$TARGET healthy (попытка $i)"
            break
        fi
        sleep 2
    done

    if [ "$HEALTHY" != "true" ]; then
        echo -e "${YELLOW}❌ api-$TARGET не поднялся. НЕ переключаю трафик — прод остаётся на $ACTIVE.${NC}"
        echo "   Логи: $COMPOSE logs api-$TARGET"
        $COMPOSE --profile "$TARGET" stop "api-$TARGET" 2>/dev/null || true
        exit 1
    fi

    echo "🔀 Переключаю nginx на $TARGET..."
    printf 'set $api_upstream http://vertushka_api_%s:8000;\n' "$TARGET" > "$UPSTREAM_FILE"
    if ! docker exec vertushka_nginx nginx -t 2>/dev/null; then
        echo -e "${YELLOW}❌ nginx -t не прошёл после свитча. Откатываю upstream на $ACTIVE.${NC}"
        printf 'set $api_upstream http://vertushka_api_%s:8000;\n' "$ACTIVE" > "$UPSTREAM_FILE"
        $COMPOSE --profile "$TARGET" stop "api-$TARGET" 2>/dev/null || true
        exit 1
    fi
    docker exec vertushka_nginx nginx -s reload
    echo "$TARGET" > "$STATE_FILE"

    echo "⏳ Дренаж in-flight запросов на $ACTIVE (5с)..."
    sleep 5
    $COMPOSE --profile "$ACTIVE" stop "api-$ACTIVE"
    ACTIVE="$TARGET"
fi

# Scheduler — единственный, не за nginx, краткий простой допустим.
echo "♻️  Пересоздаю scheduler..."
$COMPOSE up -d --force-recreate --no-deps scheduler

# Внешний healthcheck через nginx — финальная страховка после переключения.
echo "❤️  Проверяю /health снаружи..."
HEALTH_URL="https://api.vinyl-vertushka.ru/health"
HEALTHY=false
for i in $(seq 1 30); do
    if curl -fsS --max-time 3 "$HEALTH_URL" > /dev/null 2>&1; then
        HEALTHY=true
        echo "   ✅ api отвечает через nginx (попытка $i), активный цвет: $ACTIVE"
        break
    fi
    sleep 2
done

if [ "$HEALTHY" != "true" ]; then
    echo -e "${YELLOW}⚠️  Внешний healthcheck не прошёл за 60с. Активный цвет: $ACTIVE. Логи: $COMPOSE logs api-$ACTIVE${NC}"
    $COMPOSE ps
    exit 1
fi

# Очистка старых образов и build cache.
# image prune -f — снимает dangling-образы (старая версия backend-api после пересборки).
#
# builder prune БЕЗ фильтра until. Раньше стояло `--filter "until=72h"`, и это
# не работало вообще: деплой пересобирает образы, кэш слоёв создаётся заново,
# и записей старше трёх суток попросту не остаётся. Скрипт исправно рапортовал
# «Total reclaimed space: 0B» при 5.9 ГБ накопленного кэша — проверено 18.08.2026,
# ручной прогон без фильтра освободил все 5.897 ГБ и снял диск с 77% до 63%.
#
# --reserved-space оставляет рабочий набор, чтобы следующая сборка не шла с нуля:
# слои одного нашего образа весят ~1.2 ГБ, поэтому 2 ГБ хватает на последнюю.
# Без --volumes / --all — данные пользователей не трогаются.
echo "🧹 Очищаю старые Docker образы и build cache..."
docker image prune -f
docker builder prune -f --reserved-space 2GB

echo -e "${GREEN}✅ Деплой завершён успешно!${NC}"

# Авто-резюм bulk-backfill обложек (Deezer). ГЕЙТ: по умолчанию ВЫКЛ.
# 2GB-коробка тесная (metabase/api/scheduler/db/redis), backfill в 6 потоков
# добивал её в swap-thrash (инцидент 07-10). Включать осознанно после
# стабилизации: BACKFILL_ENABLED=1 bash scripts/deploy.sh.
# backfill resumable (worklist done-флаги + checkpoint) — старт заново безопасен.
# Bulk-backfill обложек (Deezer) теперь ведёт APScheduler-джоба в scheduler
# (main.py, id=cover_backfill_deezer, каждые 2 мин) — надёжнее detached
# `docker exec -d`, который не переживал деплой и путал детект самоматчем.
# Деплой ничего не запускает: джоба поднимается со scheduler-контейнером сама.
# ГЕЙТ = маркер /app/uploads/.backfill_enabled (volume uploads_data). Включить:
#   docker compose -f docker-compose.prod.yml exec -T scheduler touch /app/uploads/.backfill_enabled
# Выключить: тем же путём rm.
if docker compose -f docker-compose.prod.yml exec -T scheduler test -f /app/uploads/.backfill_enabled 2>/dev/null; then
    echo "🎨 backfill обложек ВКЛ (маркер есть) — ведёт APScheduler-джоба"
else
    echo "🎨 backfill обложек ОТКЛ (нет маркера .backfill_enabled)"
fi

# Показать статус
echo ""
echo "📊 Статус контейнеров:"
docker compose -f docker-compose.prod.yml ps
