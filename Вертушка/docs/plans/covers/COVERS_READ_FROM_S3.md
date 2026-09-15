# Чтение обложек из бакета (трек A, финальный шаг)

Статус: готово к выкату. Ветка `feat/covers-serve-from-s3`.
Предыстория: [COVERS_S3_IMGPROXY_MILESTONE.md](COVERS_S3_IMGPROXY_MILESTONE.md) —
там описан dual-write, который уже работает с 28.08.2026.

## Зачем

Dual-write сделал бакет вечным слоем, но **раздача осталась дисковой**:
imgproxy читал `local:///covers/…`, а legacy-путь `/covers/{id}.jpg` nginx
отдавал прямо с тома. Из-за этого локальный файл был обязателен для показа, и
LRU-эвикция превращалась в круговорот «удалили ночью → скачали обратно днём».

Замеры 14.09.2026 (прод):

| Метрика | Значение |
|---|---|
| LRU в 03:00 | удалено 34 860 файлов, освобождено 3.39 ГБ |
| Диск в 22:50 того же дня | 48 597 файлов, 5.59 ГБ при лимите 4 ГБ |
| Диск сервера | 85% занято (32 из 37 ГБ) |
| В бакете | 83 755 объектов, 9.56 ГБ |
| Исходящий трафик Beget за месяц | 39.76 ГБ — втрое больше объёма бакета |
| Доля запросов мимо imgproxy (`/covers/{id}.jpg`) | 6 677 из 8 311 за сутки (80%) |

То есть за месяц содержимое бакета выкачивалось обратно на тот же сервер
примерно трижды — только чтобы вернуть на диск то, что с него стёрли.

## Что меняется

1. **imgproxy получает второй источник — S3.** Локальный остаётся: imgproxy
   выбирает источник по схеме в URL, так что `local://` продолжает работать.
2. **Роут ресайза** `/covers/w/{w}/{id}.jpg` читает `s3://…` вместо `local:///`.
3. **Legacy-роут** `/covers/{id}.jpg` получает промежуточную ступень:
   `диск → бакет (imgproxy raw) → старый фолбэк в FastAPI`.
   `raw:1` отдаёт исходные байты потоком, без перекодирования — мастер остаётся
   бит-в-бит прежним (на него смотрит зум карточки).
4. **LRU** переводится с крона 03:00 на интервал в 2 часа: теперь выселение
   дёшево, потому что не требует обратной закачки.

Новых сервисов нет. Новых учёток нет. Ключи — те же, что у бэкенда.

## Проверка ДО выката

### 1. Конфиг nginx — одноразовым контейнером

Битый `nginx.conf` роняет весь сайт, а `deploy.sh` пересоздаёт nginx **до**
гейта `nginx -t`. Поэтому валидируем отдельно, не трогая боевой контейнер:

```bash
cd ~/vertushka/Вертушка/Backend && docker run --rm \
  -v "$PWD/nginx/nginx.conf:/etc/nginx/nginx.conf:ro" \
  --entrypoint sh nginx:alpine -c '
    mkdir -p /etc/nginx/conf.d /var/cache/nginx_covers /srv/money
    echo "set \$api_upstream http://api:8000;" > /etc/nginx/active_upstream.conf
    : > /etc/nginx/money.htpasswd
    { printf "map \$http_cookie \$money_setcookie { default \"\"; }\n";
      printf "map \$http_cookie \$money_ok { default 1; }\n"; } > /etc/nginx/money_auth.conf
    apk add --no-cache openssl >/dev/null 2>&1
    for d in $(grep -oE "/etc/letsencrypt/live/[a-z0-9.-]+" /etc/nginx/nginx.conf | sort -u); do
      mkdir -p "$d"
      openssl req -x509 -newkey rsa:2048 -nodes -keyout "$d/privkey.pem" \
        -out "$d/fullchain.pem" -days 1 -subj "/CN=test" >/dev/null 2>&1
      cp "$d/fullchain.pem" "$d/chain.pem"
    done
    nginx -t'
```

Ожидаем `syntax is ok` / `test is successful`. Сертификаты и money-переменные
здесь заглушки: они живут вне гита, и без них тест падает по окружению, а не
по конфигу.

### 2. imgproxy против живого бакета — тоже отдельным контейнером

Порт слушает только на localhost, боевой `vertushka_imgproxy` не трогается:

```bash
cd ~/vertushka/Вертушка/Backend
set -a && . <(grep -E "^S3_(ENDPOINT_URL|REGION|BUCKET_COVERS|ACCESS_KEY_ID|SECRET_ACCESS_KEY)=" .env.prod) && set +a
docker run --rm -d --name imgproxy_probe -p 127.0.0.1:18080:8080 \
  -e IMGPROXY_ALLOW_UNSAFE_URL=1 -e IMGPROXY_USE_S3=true \
  -e IMGPROXY_S3_ENDPOINT="$S3_ENDPOINT_URL" -e IMGPROXY_S3_REGION="${S3_REGION:-ru-1}" \
  -e IMGPROXY_S3_ENDPOINT_USE_PATH_STYLE=true \
  -e AWS_ACCESS_KEY_ID="$S3_ACCESS_KEY_ID" -e AWS_SECRET_ACCESS_KEY="$S3_SECRET_ACCESS_KEY" \
  darthsim/imgproxy:v3.27
sleep 5
B="$S3_BUCKET_COVERS"
curl -s -o /dev/null -w "raw:    %{http_code} %{size_download}B %{content_type}\n" \
  "http://127.0.0.1:18080/insecure/raw:1/plain/s3://$B/covers/1000312.jpg"
curl -s -H "Accept: image/webp" -o /dev/null -w "resize: %{http_code} %{size_download}B %{content_type}\n" \
  "http://127.0.0.1:18080/insecure/rs:fit:300:0:0/plain/s3://$B/covers/1000312.jpg@webp"
curl -s -o /dev/null -w "нет ключа: %{http_code} (ждём 404)\n" \
  "http://127.0.0.1:18080/insecure/raw:1/plain/s3://$B/covers/999999999999.jpg"
docker rm -f imgproxy_probe
```

Прогон 14.09.2026 дал: `raw: 200 95319B image/jpeg`, `resize: 200 5154B
image/webp` (39 мс), `нет ключа: 404`. 404 важен не меньше двухсотки: именно его
перехватывает `error_page` и уводит в старую лестницу.

## Проверка ПОСЛЕ выката

```bash
# 1. Обложка, которой заведомо нет на диске (проверить, что её там нет —
#    через любой id, стёртый последней LRU):
curl -sI "https://api.vinyl-vertushka.ru/covers/1000312.jpg" | grep -iE "^(HTTP|x-cache-status|content-type|content-length)"
# ждём: HTTP 200, image/jpeg, X-Cache-Status: MISS (второй раз — HIT)

# 2. Ресайз:
curl -sI -H "Accept: image/webp" "https://api.vinyl-vertushka.ru/covers/w/300/1000312.jpg" | grep -iE "^(HTTP|x-cache-status|content-type)"
# ждём: HTTP 200, image/webp

# 3. Заведомо несуществующая — старая лестница жива:
curl -sI "https://api.vinyl-vertushka.ru/covers/999999999999.jpg" | head -1
# ждём: 302 на внешний источник либо 404 — но НЕ 500

# 4. Через сутки: диск должен перестать пилить
df -h / | tail -1
docker logs vertushka_scheduler --since 24h 2>&1 | grep "LRU cleanup"
# ждём 12 прогонов вместо одного, каждый — мелкий
```

Красный флаг: если в логах api резко выросло число
`s3_covers: restore … упал` — значит nginx почему-то не доходит до бакета и
всё свалилось на старый путь. Откат — `git revert` + `deploy.sh`.

## Что НЕ входит

- Раздача напрямую с домена бакета (CDN, свой поддомен). Сейчас трафик всё
  равно идёт через наш nginx — но уже с кэшем деривативов и без записи на диск.
- Уменьшение `COVERS_MAX_CACHE_MB`. После выката кэш и так перестанет
  разрастаться; снижать лимит имеет смысл отдельным шагом, по замеру.
