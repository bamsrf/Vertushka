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

# Сборка обоих сервисов из общего Dockerfile.
# api и scheduler — один образ под капотом, разница только в IS_SCHEDULER env var.
# Если билдить только api — scheduler застрянет на старом образе.
echo "🔨 Собираю Docker образы (api + scheduler)..."
docker compose -f docker-compose.prod.yml build api scheduler

# Применение миграций ДО подъёма новой версии — если миграция упадёт,
# прод-контейнер останется на старой версии и старой схеме (no downtime).
echo "📊 Применяю миграции базы данных..."
docker compose -f docker-compose.prod.yml run --rm -e PYTHONPATH=/app api alembic upgrade head

# Поднимаем зависимости (db, redis, nginx, metabase) — те что не пересобирали.
echo "🐳 Поднимаю зависимости..."
docker compose -f docker-compose.prod.yml up -d

# Принудительный пересоздание api и scheduler — гарантия что контейнеры
# подхватят свежесобранный образ. Без этого compose иногда не замечает смену
# image hash и оставляет контейнер на предыдущем (тогда диск пухнет: новый
# образ лежит, старый держится живым контейнером).
# --no-deps — не трогать db/redis/nginx, они уже подняты.
echo "♻️  Принудительно пересоздаю api и scheduler с новым образом..."
docker compose -f docker-compose.prod.yml up -d --force-recreate --no-deps api scheduler

# Healthcheck — ждём пока api действительно поднимется (до ~60 сек).
echo "❤️  Проверяю /health..."
HEALTH_URL="https://api.vinyl-vertushka.ru/health"
HEALTHY=false
for i in $(seq 1 30); do
    if curl -fsS --max-time 3 "$HEALTH_URL" > /dev/null 2>&1; then
        HEALTHY=true
        echo "   ✅ api отвечает (попытка $i)"
        break
    fi
    sleep 2
done

if [ "$HEALTHY" != "true" ]; then
    echo -e "${YELLOW}⚠️  Healthcheck не прошёл за 60 секунд. Проверь логи: docker compose -f docker-compose.prod.yml logs api${NC}"
    docker compose -f docker-compose.prod.yml ps
    exit 1
fi

# Очистка старых образов и build cache.
# image prune -f — снимает dangling-образы (старая версия backend-api после пересборки).
# builder prune — режет аккумулированный кэш слоёв старше 72h, верхний потолок 500 МБ.
# Без --volumes / --all — данные пользователей не трогаются.
echo "🧹 Очищаю старые Docker образы и build cache..."
docker image prune -f
docker builder prune -f --filter "until=72h" --reserved-space 500MB

echo -e "${GREEN}✅ Деплой завершён успешно!${NC}"

# Авто-резюм bulk-backfill обложек (Deezer). Рестарт api при деплое убивает
# фоновый процесс; backfill resumable (worklist done-флаги + checkpoint), поэтому
# просто поднимаем заново, если он не запущен. Скрипт сам мгновенно выходит,
# когда весь хвост пройден — повторный запуск безвреден.
if docker compose -f docker-compose.prod.yml exec -T api sh -c 'grep -lq backfill_covers /proc/*/cmdline 2>/dev/null'; then
    echo "🎨 backfill обложек уже крутится"
else
    echo "🎨 Поднимаю backfill обложек (Deezer, resumable)..."
    # python -u — иначе stdout буферизуется и лог «молчит» часами (httpx заглушён).
    docker compose -f docker-compose.prod.yml exec -T -d api sh -c 'python -u -m app.scripts.backfill_covers_deezer --kind both --batch 300 >> /app/uploads/backfill_covers.log 2>&1'
fi

# Показать статус
echo ""
echo "📊 Статус контейнеров:"
docker compose -f docker-compose.prod.yml ps
