# Аудит безопасности перед релизом — Вертушка

> **Дата:** 2026-08-14 · **Ветка:** `fix/crawl-breaker-threshold` · **Метод:** ручной обзор кода
> (Backend `app/api`, `app/services`, `app/web`, `app/models`, nginx, compose, Mobile `lib/`).
>
> **Дополняет, а не заменяет** [APPSTORE_PRERELEASE_AUDIT.md](APPSTORE_PRERELEASE_AUDIT.md) — тот про
> соответствие гайдлайнам Apple (метаданные, demo-аккаунт, iPad, права на данные). Этот — про **код**:
> что сломается или чем воспользуются, когда придут живые юзеры.
> Функциональные баги UI живут в [../BUGS.md](../BUGS.md) и здесь не дублируются.

---

## Резюме

Фундамент крепкий и это видно по коду: `token_version` реально проверяется и в `/refresh`,
и в `get_current_user`, и в WS-хендшейке; ревокация сессий рабочая. Токены на клиенте лежат в
`expo-secure-store`, а не в `AsyncStorage`. IDOR в проверенных местах закрыт — `user_photos`,
`collections`, `messages` везде сверяют владельца. Редиректор `/go/` намеренно не принимает URL
из query. Cascade-удаление на уровне БД расставлено по всем 18 таблицам с FK на `users.id`.
Rate-limit сведён в один инстанс. Секреты не в git. SQL с f-строками везде подставляет только
whitelist-значения, параметры идут через bind.

**Но есть 3 блокера**, каждый из которых — не «теоретический риск», а работающая цепочка:

1. **Stored XSS на публичном профиле** — доставляется любому, кто откроет расшаренную ссылку.
2. **`POST /api/records/` splat'ит вход в модель** — обход модерации UGC (тот самый Guideline 1.2,
   ради которого писался весь `reports.py`), плюс открытый редирект и SSRF из одного поля.
3. **Удалённые аккаунты никогда не вычищаются** — джоба существует, но нигде не запущена.

Плюс пачка устаревших зависимостей с прямо достижимыми CVE (unauth DoS через multipart).

| Уровень | Кол-во | Смысл | Статус |
|---|---|---|---|
| 🔴 Блокер | 3 | Не сабмитить | ✅ закрыты |
| 🟠 Высокий | 4 | До открытия на публику | ✅ закрыты |
| 🟡 Средний | 7 | Первые две недели | ✅ закрыты (S9 — частично) |
| ⚪ Гигиена | 6 | Бэклог | ✅ S14, S15, S16, S17, S19 · ⏳ S18 |

**Итог на 2026-08-14: закрыто 19 из 20.** Регресс — 133 теста в
`Backend/tests/test_security_hardening.py`, весь набор 599 зелёных.

Что осталось и почему:

- **S9 — наполовину.** Из access-лога токен убран, но `error_log` пишет строку
  запроса целиком и в nginx не настраивается. Закрывается только ticket-схемой.
- **S18 (`--workers 1`) — намеренно не трогали.** Это потолок пропускной
  способности, а не уязвимость, и для запуска он корректен: именно он делает
  in-memory rate-limit честным. Переход на несколько воркеров ТРЕБУЕТ сначала
  вынести лимиты в Redis, иначе каждый воркер получит свой счётчик.
- **CSP с `'unsafe-inline'`.** Снятие требует переписать 14 инлайновых
  обработчиков в шаблонах — отдельная задача.
- **Обложки user-записей при удалении аккаунта.** Решение продуктовое: запись
  переживает автора (`SET NULL`), удалять её обложку — оставить битую карточку
  в каталоге. Подробности в §S3.

> **Статус (2026-08-14).** Закрыты все блокеры и весь высокий риск, кроме S20 —
> тот правится текстом политики, не кодом. Регресс — 103 теста в
> `Backend/tests/test_security_hardening.py`, весь набор 554 зелёных.
> Описания ниже сохранены как есть: они объясняют, что было сломано и почему
> фикс выглядит именно так.
>
> - **S1** — `Markup(...).format()` в `web/routes.py`, `|safe` убран из шаблона.
>   При правке нашлась третья точка инъекции — `genre` через `_genre_label()`.
> - **S2** — `POST /api/records/` удалён, добавлен `app/utils/url_guard.py`,
>   подключён в обе закачки `cover_storage` и во все 302 `api/covers.py`.
> - **S3** — джоба `purge_deleted_users` заведена в планировщике (04:30),
>   добавлено удаление `uploads/user_photos/{user_id}` и аватара. Обложки
>   user-записей оставлены намеренно (запись переживает автора, `SET NULL`).
> - **S4** — подняты `fastapi` 0.109→0.115 (starlette 0.35→0.41),
>   `python-multipart` 0.0.6→0.0.20, `pillow` 10.2→11.1, `aiohttp` 3.9.1→3.11.11,
>   `jinja2` 3.1.3→3.1.5, `lxml` 5.1→5.3. `python-jose` заменён на `PyJWT 2.10.1`.
>   `playwright` НЕ тронут — см. поправку в §S4.
> - **S5** — `assert_secrets_ok()` в `main.py` до создания приложения.
> - **S6** — `services/blocking.py`, применён в `follow_user`,
>   `upsert_notification` и `block_user` (рвёт Follow/FollowRequest).

---

## 🔴 Блокеры

### S1. Stored XSS на публичном профиле

**Где:** [`app/web/templates/public_profile.html:962`](../../Backend/app/web/templates/public_profile.html)
+ [`app/web/routes.py:576-598`](../../Backend/app/web/routes.py)

Шаблон рендерит fun-stats через `|safe`, отключая автоэкранирование Jinja:

```jinja
<span class="text">{{ stat.html|safe }}</span>
```

А `stat.html` собирается f-строками, в которые подставляются **поля из БД**:

```python
"html": f"Топ-артист: <b>{artist_name}</b>",          # routes.py:583
"html": f"Самая старая: <b>{oldest[0]}</b>{suffix}",  # routes.py:592  ← suffix = artist
```

`artist_name` и `suffix` приходят из `Record.artist` (запросы на `routes.py:440-488`,
без фильтра по `moderation_status`).

**Цепочка эксплуатации:**

1. Юзер создаёт 2 записи с `artist = "<svg/onload=...>"` — `UserRecordCreate.artist` это
   `str = Field(..., max_length=500)`, никакой санитизации ([`schemas/record.py:368`](../../Backend/app/schemas/record.py)).
2. Кладёт их в коллекцию → артист становится топ-артистом (порог `cnt >= 2`).
3. Включает публичный профиль, шарит `https://vinyl-vertushka.ru/@username`.
4. Payload исполняется у каждого, кто открыл ссылку.

Обрезка до 22/18 символов **не спасает** — она режет длину, а не смысл. В 18 символов влезает
`<base href=//x.ru>` (перехватывает все относительные URL страницы), в 22 — `<script src=//x.ru>`.

**Почему это больно именно здесь.** Домен `vinyl-vertushka.ru` — это не только профили: на нём
живут `/privacy`, `/terms` и страницы подтверждения/отмены бронирования подарка
(`/confirm/{booking_id}`, `/cancel/{booking_id}`) с email дарителя. Сессионных кук там нет
(мобилка ходит с Bearer), так что угон сессии не грозит — но остаются дефейс, редирект на
малварь и **фишинг с настоящего домена** («войдите в Вертушку, чтобы посмотреть коллекцию»).
Публичный профиль по замыслу расшаривается в винильных сообществах — то есть у payload'а
встроенный канал доставки.

**Фикс.** Убрать `|safe`. Разложить статистику на структуру и дать Jinja экранировать:

```python
# routes.py — вместо "html": f"Топ-артист: <b>{artist_name}</b>"
{"icon": "👑", "prefix": "Топ-артист: ", "value": artist_name, "suffix": ""}
```

```jinja
{# public_profile.html #}
<span class="text">{{ stat.prefix }}<b>{{ stat.value }}</b>{{ stat.suffix }}</span>
```

Если переписывать все 15 строк не хочется — минимальный вариант: обернуть каждую
интерполяцию в `markupsafe.escape()` и оставить `|safe` только для собственной разметки.
Первый вариант лучше: он не оставляет грабель на следующего, кто добавит стат.

**Проверка:** артист `<svg onload=alert(1)>` → открыть публичный профиль → в DOM должно быть
`&lt;svg onload=alert(1)&gt;`, алерта нет.

---

### S2. `POST /api/records/` — mass assignment: обход модерации + открытый редирект + SSRF

**Где:** [`app/api/records.py:2111-2126`](../../Backend/app/api/records.py)

```python
@router.post("/", response_model=RecordResponse, status_code=201)
async def create_record(record_data: RecordCreate, current_user: User = Depends(get_current_user), ...):
    record = Record(**record_data.model_dump())   # ← весь вход splat'ом в модель
    db.add(record)
```

Ни одного поля не фильтруется и ни одно не проставляется сервером. Дефолты модели
([`models/record.py:31,41,50`](../../Backend/app/models/record.py)):
`source="discogs"`, `moderation_status="approved"`, `created_by_user_id=NULL`.

Отсюда три разных последствия одного бага:

**(а) Обход модерации UGC.** Рядом живёт правильный путь — `POST` с `UserRecordCreate`
(`records.py:1605`), который ставит `source='user'`, `moderation_status='pending'` и гонит запись
через `admin.py` → approve/reject. Этот эндпоинт всё это **обходит**: запись рождается сразу
`approved`, с `source='discogs'` (то есть выглядит как каноничная запись Discogs) и **без автора**
— `created_by_user_id=NULL`.

Последнее ломает и модерацию постфактум: `reports._resolve_target_user_id()`
([`reports.py:97`](../../Backend/app/api/reports.py)) для `target_type='record'` возвращает
`rec.created_by_user_id` — то есть `None`. **Забанить автора такой записи по жалобе физически
нечем.** Вся конструкция вокруг Guideline 1.2 обходится одним POST'ом.

**(б) Открытый редирект на API-домене.** `RecordCreate.cover_image_url` — свободная строка
([`schemas/record.py:29`](../../Backend/app/schemas/record.py)). Дальше:

```python
# app/api/covers.py:133 — публичный эндпоинт, без авторизации
return RedirectResponse(url=record.cover_image_url, status_code=302)
```

`https://api.vinyl-vertushka.ru/covers/store/<uuid>` → 302 куда угодно. Ровно та дыра, которую
`/go/{click_id}` в `web/routes.py:1007` аккуратно закрывает с комментарием «это мгновенно
превратило бы наш домен в инструмент фишинга» — и которая здесь открыта настежь.

**(в) SSRF.** Тот же URL уходит в фоновую закачку (`covers.py:128`):

```python
# app/services/cover_storage.py:461 (и точно такой же вызов на строке 230)
async with httpx.AsyncClient(timeout=_DOWNLOAD_TIMEOUT, follow_redirects=True) as client:
    resp = await client.get(image_url)      # ← ни схемы, ни хоста не проверяем
```

Внутри docker-сети досягаемы `http://redis:6379`, `http://imgproxy:8080`, `postgres:5432`,
и метаданные хостера. Слепой SSRF (ответ падает в файл обложки, ошибки глотаются), но рабочий.
`follow_redirects=True` означает, что аллоу-лист только на входной URL обойдётся редиректом —
проверять надо на каждом хопе.

**Фикс — три отдельных, все нужны:**

1. **Закрыть эндпоинт.** Он дублирует `UserRecordCreate` и не должен быть публичным. Либо
   удалить, либо повесить `Depends(require_staff)`. Если он нужен клиенту — переписать на явное
   присвоение полей с `source='user'`, `moderation_status='pending'`,
   `created_by_user_id=current_user.id`, и **не** брать `cover_image_url` из запроса.
2. **Аллоу-лист хостов для закачки обложек** в `cover_storage`: только `https`, только известные
   CDN (Discogs, Deezer, iTunes, Yandex, CAA, домены магазинов из `stores`). Проверять
   на каждом редиректе (`follow_redirects=False` + ручной цикл), резолвить хост и отбрасывать
   приватные диапазоны (10/8, 172.16/12, 192.168/16, 127/8, 169.254/16, ::1, fc00::/7).
3. **`covers.py:133`** — редиректить только на URL, прошедший тот же аллоу-лист; иначе 404.

**Проверка:** `POST /api/records/` с `{"cover_image_url": "http://redis:6379/"}` → 403/422;
`GET /covers/store/{id}` на записи с внешним URL → 404, не 302.

---

### S3. Удалённые аккаунты не вычищаются никогда

**Где:** [`app/scripts/purge_deleted_users.py`](../../Backend/app/scripts/purge_deleted_users.py)
· [`app/api/users.py:431`](../../Backend/app/api/users.py)

`DELETE` аккаунта — мягкое: ставит `deleted_at` и `scheduled_purge_at = now + 30 дней`.
Скрипт финальной вычистки написан, в докстринге сказано «запуск через cron раз в сутки».

**Этот cron нигде не заведён.** Проверено: в `main.py` среди ~30 задач APScheduler его нет,
в `app/tasks/` нет, в `Makefile`, `docker-compose.prod.yml` и `scripts/*.sh` — тоже
(в отличие от `backfill_snapshot.sh` и `harden_disk.sh`, где host-crontab прописан явно).

**Последствия:**
- Guideline **5.1.1(v)**: удаление аккаунта обязано удалять данные. Сейчас через 30 дней ничего не
  происходит — данные лежат вечно. Ревьюер это не увидит, но обещание в UI и в privacy-политике
  расходится с реальностью.
- 152-ФЗ / GDPR: то же самое, но с юридическим весом.
- Мусор: `email` и `username` остаются заняты уникальными индексами, юзер не может
  перерегистрироваться на свой же email.

**Хорошая новость:** сам purge отработает, когда его запустят — DB-level
`ondelete="CASCADE"` расставлен на всех 18 таблицах с FK на `users.id` (проверено), падения на
FK-constraint не будет.

**Фикс:**

```python
# app/main.py — рядом с остальными задачами, в блоке IS_SCHEDULER
from app.scripts.purge_deleted_users import purge
scheduler.add_job(purge, 'cron', hour=4, minute=30, id='purge_deleted_users',
                  max_instances=1, coalesce=True)
```

**И отдельно — файлы на диске.** `purge()` удаляет только строки БД. Фотографии пластинок
лежат в `uploads/user_photos/{user_id}/*.jpg` и переживают вычистку. Это самая чувствительная
часть UGC (фото из дома пользователя). Добавить в `purge()` перед `session.delete(user)`:

```python
import shutil
shutil.rmtree(Path("uploads") / "user_photos" / str(user.id), ignore_errors=True)
```

**Проверка:** удалить тестовый аккаунт, руками отмотать `scheduled_purge_at` в прошлое,
прогнать джобу → строки нет, папки нет, email снова свободен для регистрации.

---

## 🟠 Высокий риск

### S4. Зависимости с достижимыми CVE

`requirements.txt` пинит версии начала 2024-го. Не абстрактная «гигиена» — часть уязвимостей
достижима неаутентифицированным запросом.

| Пакет | Сейчас | CVE | Достижимо? |
|---|---|---|---|
| `python-multipart` | 0.0.6 | CVE-2024-24762 (ReDoS в разборе `Content-Type`), CVE-2024-53981 (DoS логами) | **Да.** Любой POST с multipart. Unauth DoS одним запросом |
| `fastapi` → `starlette` | 0.109.0 → <0.36 | CVE-2024-47874 (DoS: multipart без лимита памяти) | **Да.** `user_photos` принимает файлы |
| `python-jose` | 3.3.0 | CVE-2024-33663 (algorithm confusion), CVE-2024-33664 (DoS через JWE-бомбу) | **Да.** `/auth/apple` и `/auth/google` декодируют произвольную строку от клиента |
| `pillow` | 10.2.0 | CVE-2024-28219 (переполнение буфера в `_imagingcms`) | **Да.** Обрабатываем чужие картинки |
| `aiohttp` | 3.9.1 | CVE-2024-23334, -27306, -30251, -52304 | Частично — используется как клиент в скрейперах |
| `jinja2` | 3.1.3 | CVE-2024-34064, -56201, -56326 (побег из песочницы) | Нет — шаблоны свои. Бампнуть заодно |
| `playwright` | 1.41.2 | Chromium ~Jan-2024, с тех пор десятки RCE | **Нет** — см. поправку ниже |

> **Поправка к строке про playwright (проверено 2026-08-14).** Первоначальная
> оценка «headless-Chromium рендерит чужие HTML» не подтвердилась: `Dockerfile`
> ставит только pip-пакет и **не выполняет `playwright install`**, то есть
> бинарников браузера в образе нет вообще. Отдельного контейнера с браузером в
> `docker-compose.prod.yml` тоже нет. Значит Chromium-поверхности не существует,
> и бамп пакета сам по себе ничего не закрывает — версия оставлена как есть,
> чтобы не ловить изменения API ради нулевой выгоды.
>
> Побочное наблюдение, уже не про безопасность: в планировщике зарегистрированы
> `weekly_full_crawl_browser` и `daily_incremental_crawl_browser`, а
> `BrowserPool._ensure_started` ловит только `ImportError` (пакет отсутствует) —
> отсутствие самого браузера прилетит уже из `chromium.launch()`. Похоже, эти
> джобы падают каждый запуск. Стоит проверить на проде: либо ставить браузер в
> образ, либо снимать джобы с расписания.

**Фикс:**

```
python-multipart==0.0.20
fastapi==0.115.6          # тянет starlette>=0.40
pillow==11.1.0
aiohttp==3.11.11
jinja2==3.1.5
playwright==1.49.1        # + playwright install chromium в Dockerfile
```

`python-jose` — отдельная история: проект фактически заброшен (3.3.0 — последний релиз).
Правильный ход — миграция на `PyJWT`. Затрагивает `utils/security.py` (4 функции) и
`api/auth.py` (Apple/Google верификация, reset-токен). Работы на полдня, но это единственная
библиотека на критическом пути аутентификации.

> Между бампом FastAPI 0.109→0.115 breaking changes минимальны, но прогнать `pytest` обязательно —
> в `tests/` уже 38 файлов, они это поймают.

---

### S5. JWT-секрет по умолчанию `change-me-in-production`

**Где:** [`app/config.py:20,25`](../../Backend/app/config.py)

```python
secret_key: str = Field(default="change-me-in-production", alias="SECRET_KEY")
jwt_secret_key: str = Field(default="change-me-in-production", alias="JWT_SECRET_KEY")
```

Если `JWT_SECRET_KEY` не доедет до контейнера — опечатка в `.env`, потерянная переменная при
пересборке, новый инстанс с чистым окружением — приложение **молча стартует с публично известным
секретом**. Дальше кто угодно подписывает себе токен на любой `sub` и `tv`, включая
`is_staff`-аккаунт. Полный обход аутентификации, и ни одного признака в логах.

Это не гипотеза про «а вдруг»: `.env` не в git (правильно), значит на проде он собирается руками,
и именно там такие переменные и теряются.

**Фикс** — падать на старте, а не работать в дырявом режиме:

```python
# app/config.py, в конце Settings
@model_validator(mode="after")
def _forbid_default_secrets(self):
    if not self.debug:
        for name in ("jwt_secret_key", "secret_key"):
            v = getattr(self, name)
            if v == "change-me-in-production" or len(v) < 32:
                raise ValueError(f"{name.upper()} не задан или слишком короткий — прод не стартует")
    return self
```

Заодно проверить, что текущий прод-секрет длиннее 32 байт и был сгенерён случайно
(`openssl rand -hex 32`), а не придуман.

---

### S6. Блокировка работает только в личках

**Где:** [`app/services/messaging.py:34`](../../Backend/app/services/messaging.py) (проверка есть)
vs [`app/api/users.py:826`](../../Backend/app/api/users.py) (проверки нет)

`UserBlock` проверяется двусторонне и корректно — но **только** в переписке. `follow_user()`
про блокировки не знает вообще: заблокированный пользователь по-прежнему может

- подписаться на вас (или прислать follow-request на приватный профиль),
- **прислать вам пуш** — `create_notification()` дёргается на follow/follow_request без фильтра,
- видеть публичный профиль, коллекцию и вишлист.

Для юзера «заблокировать» означает «этот человек исчез». Здесь он исчезает из одного экрана из
четырёх и продолжает присылать уведомления. Это и жалоба в саппорт на второй неделе, и риск по
Guideline 1.2 при ревью флоу блокировки, и просто плохо.

**Фикс:** вынести существующую проверку из `messaging.py` в общий хелпер и применить в
`follow_user`, `create_follow_request`, `create_notification` и в резолве публичного профиля:

```python
# app/services/blocking.py
async def is_blocked_either_way(db, a_id: UUID, b_id: UUID) -> bool: ...
```

Минимум для релиза — `follow_user` и `create_notification`. Скрытие профиля от заблокированного
можно донести следующим релизом.

---

### S20. OpenAI не заявлен в политике конфиденциальности

**Где:** [`app/web/templates/privacy.html`](../../Backend/app/web/templates/privacy.html) §3 и §7
vs [`app/services/openai_vision.py:66`](../../Backend/app/services/openai_vision.py)

Распознавание обложки отправляет снимок пользователя в OpenAI:

```python
"url": f"data:image/jpeg;base64,{image_base64}",   # openai_vision.py:66
```

В §3 «Передача данных третьим лицам» перечислены Discogs, Apple/Google, Expo Push,
Amplitude, Яндекс.Метрика и магазины-партнёры. **OpenAI в списке нет.** §7 «Камера и
галерея» говорит, что доступ к камере нужен «для распознавания обложек», умалчивая, что
кадр уходит стороннему обработчику в США.

При этом §5 отдельно оговаривает трансграничную передачу для Amplitude («это трансграничная
передача») — то есть механика в политике описана правильно, просто для одного из получателей
её забыли применить. И §5 утверждает, что фотографии хранятся «на сервере в Российской
Федерации», что для скан-кадра неточно: он туда не попадает вовсе, но по пути пересекает
границу.

Задевает Guideline 5.1.1 (нераскрытая передача третьим лицам), App Privacy в App Store
Connect и 152-ФЗ в части трансграничной передачи.

**Фикс** — текстовый, кода не требует. В §3 добавить пункт вида: «OpenAI — распознавание
обложки по фотографии. Передаётся только сам кадр, без имени, email и содержимого коллекции;
снимок не сохраняется ни у нас, ни для обучения моделей». В §7 — одну фразу, что кадр
уходит на распознавание внешнему сервису. В App Store Connect убедиться, что
«Photos or Videos» помечены как передаваемые третьей стороне.

> Перед публикацией текста стоит свериться с актуальными условиями OpenAI по хранению
> и обучению на данных API — формулировка «не используется для обучения» должна
> соответствовать вашему тарифу, иначе политика опять разойдётся с реальностью.

---

## 🟡 Средний риск

### S7. Код сброса пароля генерится небезопасным PRNG

[`app/api/auth.py:746`](../../Backend/app/api/auth.py) — `code = f"{random.randint(0, 999999):06d}"`.

`random` — это Mersenne Twister, детерминированный и предсказуемый по наблюдаемым выходам.
Для кода, который единственный стоит между чужим email и захватом аккаунта, нужен CSPRNG.
В `utils/security.py` `secrets` уже импортирован — рядом лежит правильный инструмент.

```python
import secrets
code = f"{secrets.randbelow(1_000_000):06d}"
```

### S8. Перечисление зарегистрированных email

Два независимых канала, оба в [`auth.py`](../../Backend/app/api/auth.py):

**Тайминг в `/forgot-password/` (строка 741).** Ответ всегда одинаковый — комментарий в коде
именно про это. Но при существующем аккаунте выполняются `hash_password(code)` (bcrypt, ~200 мс)
и `await send_reset_code_email(...)` (сетевой вызов Resend). При несуществующем — мгновенный
возврат. Разница на порядок, измеряется без статистики.

**Разные тексты ошибок в `/verify-reset-code/` (строки 774 и 799).** Нет аккаунта → «Неверный или
просроченный код». Аккаунт есть → «Неверный код. **Осталось попыток: 2**». Прямой оракул.

**Фикс:**
- `/forgot-password/`: отправку письма — в `asyncio.create_task()` (как уже сделано в
  `_touch_last_seen`), а bcrypt выполнять и в ветке «юзера нет», по фиктивному хешу.
- `/verify-reset-code/`: один текст на все ветки; счётчик попыток отдавать только после
  успешной аутентификации кода — либо не отдавать вовсе.

### S9. Access-токен в query-строке WebSocket → в логи nginx

[`app/api/messages.py:1213`](../../Backend/app/api/messages.py) — `async def messages_ws(websocket, token: str = Query(...))`.

Сама проверка сделана правильно (тип токена, `is_active`, `token_version` — всё на месте). Проблема
не в валидации, а в транспорте: nginx по умолчанию пишет полную строку запроса в `access.log`.
То есть **валидные access-токены оседают на диске открытым текстом**, попадают в ротацию, бэкапы
и в любой сборщик логов.

Браузерный WS не умеет кастомные заголовки — обходной путь через query легитимен. Лечится на
уровне лога:

```nginx
# в http {} — отдельный формат без query-строки для WS-локации
log_format ws_safe '$remote_addr - [$time_local] "$request_method $uri" $status $body_bytes_sent';
location /api/messages/ws { access_log /var/log/nginx/ws.log ws_safe; ... }
```

Более чистое решение на потом — одноразовый короткоживущий ticket: `POST /api/messages/ws-ticket`
отдаёт UUID с TTL 30 с в Redis, WS принимает его вместо access-токена.

> **Что сделано и что осталось (2026-08-14).** Отдельный `log_format ws_safe` с `$uri`
> вместо `$request` и свой `location = /api/messages/ws` — из access-лога токен ушёл.
> **Но это половина решения:** формат настраивается только у `access_log`, а `error_log`
> пишет строку запроса целиком, и в nginx это не конфигурируется. При любой ошибке
> (429, недоступный апстрим, разрыв соединения) токен по-прежнему попадёт в `error.log`.
> Проверено на throwaway-контейнере: в записи `limiting requests` видно
> `request: "POST /api/auth/login HTTP/2.0"` — то есть `$request` как есть.
> Полностью закрывает только ticket-схема выше; оставлено в бэклоге.

### S10. Загрузка фото: чтение до проверки размера, нет защиты от bomb, нет квоты

[`app/api/user_photos.py:113`](../../Backend/app/api/user_photos.py):

```python
raw = await file.read()                                   # ← весь файл в память
if len(raw) > _MAX_FILE_MB * 1024 * 1024:                 # ← проверка ПОСЛЕ
```

`client_max_body_size 10M` в nginx ограничивает ущерб, так что это не катастрофа — но проверять
после чтения всё равно неправильно, и лимит nginx легко потерять при переносе конфига.

Серьёзнее — три соседних пробела:

- **Decompression bomb.** `Image.open(...).convert("RGB")` на 2-килобайтном PNG, который
  разворачивается в 30000×30000. Pillow по умолчанию только предупреждает. Нужно явно:
  `Image.MAX_IMAGE_PIXELS = 40_000_000` и ловить `Image.DecompressionBombError`.
- **Нет квоты.** Ни на число фото у юзера, ни на объём. 10 МБ × безлимит = диск кончается.
  Учитывая, что `harden_disk.sh` в репозитории существует, тема живая.
- **Нет чистки при удалении аккаунта** — см. S3.

```python
# читаем с потолком, не доверяя nginx
raw = await file.read(_MAX_FILE_MB * 1024 * 1024 + 1)
if len(raw) > _MAX_FILE_MB * 1024 * 1024:
    raise HTTPException(413, ...)
```

Квота: `SELECT count(*) FROM user_record_photos WHERE user_id = :u` перед вставкой, потолок ~200.

### S11. nginx: заголовки безопасности теряются в `/covers/`, CSP нет нигде

[`Backend/nginx/nginx.conf`](../../Backend/nginx/nginx.conf)

Классическая грабля `add_header`: директива в `location` **отменяет все унаследованные** из
`server`. В блоках `location /covers/` и `location ~ "^/covers/w/..."` объявлены свои
`add_header` (Cache-Control, Vary, X-Cache-Status) — значит `X-Frame-Options`,
`X-Content-Type-Options`, `HSTS` и `X-XSS-Protection` там **не отдаются**. Для картинок урон
невелик, но дыра в HSTS на домене — уже не мелочь: один HTTP-ответ без заголовка даёт окно для
downgrade.

Отдельно: **`Content-Security-Policy` нет ни на одном блоке.** На `vinyl-vertushka.ru` отдаётся
HTML с пользовательскими данными — то есть ровно та поверхность, где CSP является вторым
рубежом после S1.

**Фикс:**

```nginx
# в http {} — один раз
map $host $sec_headers { default "1"; }   # или просто продублировать add_header в location

# в каждом location, где есть свой add_header — повторить набор:
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

# на server{} основного домена — CSP
add_header Content-Security-Policy "default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; script-src 'self'; frame-ancestors 'none'; base-uri 'self'" always;
```

`base-uri 'self'` отдельно ценен — он гасит `<base href>`-вектор из S1.

> Проверять конфиг **throwaway-контейнером**, не `exec` в работающий nginx — см. заметку
> про stale inode в памяти проекта. Битый конфиг роняет весь сайт, потому что deploy
> пересоздаёт nginx до гейта `nginx -t`.

### S12. Reset-токен переиспользуется в течение 10 минут

[`auth.py:812`](../../Backend/app/api/auth.py) выдаёт JWT `type: "reset"` с TTL 10 минут.
`reset_password` его проверяет, но **не помечает израсходованным** и не кладёт в него `tv`.
После смены пароля `token_version` инкрементируется — но это убивает access/refresh, а на сам
reset-токен не влияет. Утёкший токен (скриншот, лог, прокси) остаётся рабочим все 10 минут
даже после использования.

**Фикс:** добавить в payload `jti` (`secrets.token_urlsafe(16)`), после успешного сброса писать
`jti` в Redis с TTL 10 мин и отклонять повтор. Либо проще — вложить в токен `tv` на момент
выдачи и сверять: после первой смены пароля `tv` разъедется и токен умрёт сам.

### S13. Rate-limit: в памяти процесса, и большая часть surface не покрыта

`slowapi` держит счётчики в памяти воркера ([`utils/rate_limit.py`](../../Backend/app/utils/rate_limit.py) —
ограничение задокументировано честно). Следствия: лимиты **обнуляются на каждом деплое**, и на
время blue-green-перекрытия удваиваются. На уровне nginx `limit_req`/`limit_conn` **нет вообще**.

Покрыто сейчас: auth (7 эндпоинтов), records (2), offers (1), messages (2), `/go/l/` (1).
Не покрыто ничего из этого:

- `GET /@{username}` и `GET /api/profile/public/{username}` — публичные, без лимита →
  перебор юзернеймов и выкачивание всех публичных коллекций;
- создание user-записей (после фикса S2 это единственный путь UGC внутрь);
- follow / follow-request — спам-подписки и пуши;
- операции с вишлистом.

**Фикс — два уровня.** На nginx общий потолок (переживает деплой, стоит дёшево):

```nginx
limit_req_zone $binary_remote_addr zone=api_general:10m rate=30r/s;
limit_req_zone $binary_remote_addr zone=api_write:10m rate=2r/s;
# в location / :  limit_req zone=api_general burst=60 nodelay;
```

В приложении — точечно `@limiter.limit` на четыре пункта выше. Там, где важен точный потолок,
уже есть правильный образец — `services/quota.py` на Redis для vision-скана.

---

## ⚪ Гигиена

**S14. PII в логах и Sentry.** `auth.py:857` — `logger.info("password_reset", extra={..., "email": user.email})`.
`get_current_user` (`auth.py:276`) кладёт email и username в скоуп Sentry на **каждый**
аутентифицированный запрос, при том что `send_default_pii=False`. Глобальный обработчик
(`main.py:321`) отправляет `str(exc)` в Telegram — текст исключения может содержать данные юзера.
GlitchTip self-hosted, так что за периметр не уходит, но App Privacy это всё равно касается.
Оставить в Sentry только `id`; из лога сброса убрать email (есть `user_id`).

**S15. `X-XSS-Protection: 1; mode=block`** — заголовок устарел, в некоторых браузерах сам был
вектором. Текущая рекомендация — `0` либо не отдавать. Заменяется на CSP из S11.

**S16. `proxy_set_header Connection "upgrade"` безусловно** в `location /` (nginx.conf) — ставится
на все запросы, а не только на WS-апгрейд. Ломает keepalive к апстриму. Стандартное решение —
`map $http_upgrade $connection_upgrade { default upgrade; '' close; }`.

**S17. `/health` публичен** и отдаёт состояние БД и Redis. `/health/covers` — метрики покрытия.
Не секрет, но лишняя разведка. Закрыть на nginx по `allow`/`deny` или вынести на отдельный порт.

**S18. `--workers 1`** в обоих API-контейнерах (`docker-compose.prod.yml:34,127`) — потолок по CPU.
Для запуска нормально (и это то, что делает in-memory rate-limit корректным), но при росте
упрётесь. Переход на несколько воркеров **потребует** сначала вынести rate-limit в Redis.

**S19. `passlib==1.7.4`** не обновлялся с 2020 и известен несовместимостью с `bcrypt>=4.1`
(падает на чтении `bcrypt.__about__`). Сейчас связка запинена и работает, но при первом же
неаккуратном `pip install -U` сломается. Плюс passlib молча обрезает пароль до 72 байт —
`UserCreate.password` разрешает 100 символов, значит хвост игнорируется без предупреждения.
Либо ограничить пароль 72 символами, либо перейти на `bcrypt` напрямую.

---

## Что проверено и оказалось в порядке

Чтобы не перепроверять второй раз:

- **Ревокация сессий работает end-to-end.** `token_version` сверяется в `get_current_user`
  (`auth.py:260`), в `/refresh` (`auth.py:492`) и в WS-хендшейке (`messages.py:1239`). Смена
  пароля инкрементирует `tv` — все старые токены умирают. Реализовано аккуратно.
- **IDOR не найден.** `user_photos`, `collections`, `messages`, `wishlists` везде проверяют
  владельца до действия. `_get_collection_item()` — образцовый пример.
- **SQL-инъекций нет.** f-строки в SQL встречаются часто, но подставляют только whitelist:
  `order_clause` из двух литералов, имена таблиц из констант, `ORDER BY` направление из
  тернарника. Пользовательский ввод везде идёт через bind-параметры (`:q`, `:mid`).
- **Открытый редирект в `/go/` закрыт осознанно** и с комментарием, объясняющим почему.
- **Токены на клиенте — в `expo-secure-store`**, не в `AsyncStorage`. В `AsyncStorage` только
  coach-marks и настройки маркета.
- **Секретов в git нет.** `.env` покрыт корневым `.gitignore` (вместе с `*.p8`, `*.pem`, `*.p12`,
  `*.mobileprovision`). Проверено `git check-ignore` и `git ls-files`.
- **DB-cascade полный** — `ondelete` проставлен на всех 18 таблицах с FK на `users.id`.
- **Postgres не наружу** — `127.0.0.1:5432:5432`. Redis портов не публикует вовсе.
- **Rate-limit сведён в один инстанс** — прошлое расхождение двух хранилищ починено и
  задокументировано.
- **CORS узкий** — один origin, не `*`.
- **Стектрейсы наружу не текут** — глобальный обработчик отдаёт `{"detail": "Internal server error"}`.
- **`/api/docs` выключен** при `debug=false`.

---

## Порядок работ

**Перед сабмитом (блокеры + высокий):**

| # | Что | Оценка |
|---|---|---|
| 1 | S1 — убрать `\|safe`, экранировать fun-stats | 1 ч |
| 2 | S2 — закрыть `POST /api/records/`, аллоу-лист для закачки обложек | 3 ч |
| 3 | S3 — зарегистрировать purge в scheduler + чистка файлов | 1 ч |
| 4 | S5 — валидатор секретов на старте | 30 мин |
| 5 | S4 — бамп зависимостей (кроме `python-jose`) + прогон `pytest` | 2 ч |
| 6 | S6 — блокировка в follow и уведомлениях | 2 ч |

**Первые две недели после релиза:** S7, S8, S9, S10, S11, S13, миграция `python-jose` → `PyJWT`.

**Бэклог:** S12, S14–S19.

---

## Регресс-проверка перед сабмитом

```
□ артист `<svg onload=alert(1)>` → публичный профиль → в DOM экранировано, алерта нет
□ POST /api/records/ {"cover_image_url":"http://redis:6379/"} → 403/422
□ GET /covers/store/{id} с внешним URL → 404 (не 302)
□ удалить аккаунт → отмотать scheduled_purge_at → прогнать purge → строк нет, папки нет,
  email свободен для повторной регистрации
□ поднять контейнер без JWT_SECRET_KEY → падает на старте с внятной ошибкой
□ заблокировать юзера → он не может подписаться и не присылает пуш
□ pip-audit / safety на обновлённом requirements.txt → чисто
□ curl -I https://vinyl-vertushka.ru/covers/1.jpg → HSTS и X-Content-Type-Options на месте
□ nginx -t в throwaway-контейнере ДО деплоя
□ pytest — весь набор зелёный после бампа FastAPI
```

---

## Мониторинг после релиза

Инфраструктура алармов уже есть (`services/alerts.py` в Telegram, пороги в `config.py`).
Что стоит добавить под эти находки:

- всплеск 401 на `/api/auth/*` — брутфорс или сломанная ревокация;
- ненулевой счётчик 403 от нового гейта на `POST /api/records/` — кто-то щупает S2;
- рост `uploads/user_photos` быстрее N МБ/сутки — квота из S10 не работает;
- ежедневная строка в логе от `purge_deleted_users` — тишина означает, что джоба снова отвалилась.
