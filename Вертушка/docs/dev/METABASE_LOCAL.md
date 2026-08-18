# Metabase поверх боевой БД (локально)

> Статус: **ACTIVE** · Создан 2026-08-18
> Конфиг: [Backend/docker-compose.metabase.yml](../../Backend/docker-compose.metabase.yml) ·
> Обёртка: [Backend/scripts/metabase_local.sh](../../Backend/scripts/metabase_local.sh)

Дашборд по пользователям, коллекциям и пластинкам. Metabase крутится на маке,
боевую БД читает через SSH-туннель под read-only ролью. VPS не тратит ни
памяти, ни диска — в мае Metabase сняли с прода именно из-за 1.8 ГБ диска.

## Запуск

Всё уже настроено (2026-08-18): роль на проде создана, Metabase поднят, база
подключена, дашборды собраны. В обычный день нужно только это:

```bash
cd Backend && bash scripts/metabase_local.sh up
```

Дальше `http://localhost:3000`. Логин и пароль печатает
`bash scripts/metabase_local.sh creds` — они лежат в `Backend/.env.metabase`
(chmod 600, в `.gitignore`).

## Готовые дашборды

| Дашборд | Что внутри |
|---|---|
| **Люди** — `/dashboard/2` | счётчики: живых аккаунтов, заходили за 7 и за 30 дней, новых за 30 дней. Таблица «Все пользователи» — никнейм, имя, email, staff-флаг, откуда пришёл, дата регистрации, когда был онлайн, сколько пластинок и на какую сумму, вишлист, подписчики. Плюс «Кто давно не заходил» (14+ дней или ни разу) |
| **Пластинки и коллекции** — `/dashboard/3` | счётчики: пластинок в коллекциях, суммарная стоимость, позиций в вишлистах, релизов в каталоге. Таблицы: топ-50 пластинок по спросу, коллекции по людям, вишлисты |

Карточки написаны нативным SQL поверх аналитических view, так что правятся
прямо в Metabase без оглядки на его метаданные.

## Что смотреть

Аналитический слой уже лежит в боевой БД — миграция
[20260505_analytics_layer.py](../../Backend/alembic/versions/20260505_analytics_layer.py).
В Metabase эти view видны как обычные таблицы.

| View | Про что |
|---|---|
| `v_user_overview` | строка на пользователя: email, username, display_name, signup_source, last_seen_at, размер и стоимость коллекции, вишлист, подарки, подписчики |
| `v_user_activity_buckets` | флаги is_dau / is_wau / is_mau / is_churned_30d |
| `v_collection_overview`, `v_top_records`, `v_collection_value_history` | пластинки: коллекции, топ релизов, динамика стоимости |
| `v_wishlist_overview`, `v_gift_funnel`, `v_gift_anti_fraud` | вишлисты и подарочная воронка |
| `v_social_overview`, `v_profile_views_top` | подписки и просмотры профиля |
| `mv_dau_wau_mau_daily`, `mv_signup_funnel_daily`, `mv_gift_funnel_daily` | суточные срезы |

Обычные `v_*` считаются на лету и всегда свежие. Три `mv_*` — снапшоты, их
обновляет [refresh_analytics.sh](../../Backend/scripts/refresh_analytics.sh),
и **в прод-crontab он не прописан**, так что данные в них соответствуют
последнему ручному запуску. Чтобы обновлялись раз в час:

```bash
ssh deploy@85.198.85.12 'crontab -l | { cat; echo "0 * * * * cd ~/vertushka/Вертушка/Backend && bash scripts/refresh_analytics.sh >> /var/log/vertushka_analytics.log 2>&1"; } | crontab -'
```

## Почему так, а не иначе

**Туннель отдельным контейнером.** Боевой Postgres слушает только
`127.0.0.1:5432` на VPS. Контейнер Metabase не видит loopback мака, а пробросить
порт на `0.0.0.0` хоста нельзя — прод-база оказалась бы открыта всей Wi-Fi сети.
Внутри compose-сети порт не публикуется вовсе.

**Роль `metabase_ro`.** Только `SELECT`, пароль в `Backend/.env.metabase`
(chmod 600, в `.gitignore`). SQL-редактор Metabase физически не может ничего
удалить в боевой базе.

**Порт 3000 на loopback.** Админка показывает email'ы пользователей — наружу
она не смотрит. Если понадобится доступ с телефона, это отдельная задача:
поддомен, сертификат и правка nginx.

## Тестовый аккаунт

Отдельного флага у пользователей нет — только `is_staff`
([user.py:109](../../Backend/app/models/user.py:109)). Все `v_*` считают всех
живых пользователей, поэтому тестовый аккаунт подмешивается в DAU и воронки.
Честно исключить его — это поле `is_test` в `users` плюс `WHERE NOT is_test`
во view. Наполнить аккаунт живой коллекцией умеет
[seed_demo_account.py](../../Backend/scripts/seed_demo_account.py).
