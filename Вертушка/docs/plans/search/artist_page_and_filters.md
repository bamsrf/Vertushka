# Принципы: раздел Артист — обложки и фильтры

Этот документ фиксирует **рабочую логику** отображения обложек и работы фильтров на экране артиста. Менять эти принципы нельзя без понимания причин, изложенных ниже.

---

## 1. Почему используется Search API, а не `/artists/{id}/releases`

### Проблема с `/artists/{id}/releases`
Этот endpoint возвращает **master releases**, у которых:
- **нет поля `format`** — формат принадлежит конкретным pressings/релизам, не мастерам
- **нет `cover_image`** — только `thumb` (150px), который часто является подписанным `api-img.discogs.com` URL

Следствия:
- `_guess_release_type(None)` → всё падало в одну категорию
- Обложки 150px, пиксельные, подписанные URL истекают через ~30 мин

### Решение: `/database/search?type=master&artist=NAME`
Search API возвращает:
- **`format[]`** — массив строк (`["CD", "Album"]`, `["Vinyl", "Single"]`)
- **`cover_image`** — полноразмерный стабильный `i.discogs.com` URL
- **`thumb`** — 150px запасной вариант

**Правило: для получения релизов артиста всегда использовать Search API.**

---

## 2. Обложки: логика выбора URL

### Два типа URL в Discogs

| Тип | Пример | Стабильный? | Размер |
|-----|--------|-------------|--------|
| `i.discogs.com` CDN | `https://i.discogs.com/abc_150.jpg` | Да | Регулируется суффиксом |
| `api-img.discogs.com` signed | `https://api-img.discogs.com/...?expires=...` | Нет (~30 мин) | 150px |

### `_thumb_to_cover` — только для `i.discogs.com`

```python
@staticmethod
def _thumb_to_cover(thumb_url: str | None) -> str | None:
    if not thumb_url or "api-img.discogs.com" in thumb_url:
        return None  # подписанные URL не апскейлить — они истекут
    return re.sub(r'_\d+\.(jpg|jpeg|png)', r'_500.\1', thumb_url)
```

Замена суффикса `_150.jpg` → `_500.jpg` работает **только** для стабильных CDN URL.  
Для подписанных возвращаем `None` — лучше нет картинки, чем битая.

### Приоритет выбора обложки в `get_artist_masters`

```python
cover_image = item.get("cover_image")   # Search API: полноразмерный, стабильный
thumb       = item.get("thumb")          # запасной: 150px

final_cover = (
    cover_image
    if (cover_image and "api-img.discogs.com" not in cover_image)
    else self._thumb_to_cover(thumb)
)
```

**Порядок приоритетов:**
1. `cover_image` из Search API — если стабильный (`i.discogs.com`)
2. `_thumb_to_cover(thumb)` — если thumb стабильный `i.discogs.com` (апскейл до 500px)
3. `None` — если оба варианта подписанные/недоступные

---

## 3. Фильтры: классификация релизов

### Единственный источник правды — `app/services/release_type.py`

Правила живут в одном модуле. Локальный дамп-индекс, live Discogs и мобильный
фолбэк обязаны звать его, а не заводить свои регексы. **Раньше правила были
продублированы** в SQL-агрегатах `get_artist_masters_local`, в
`_guess_release_type` и в `_is_video` — копии разошлись (`umd` был в питоне, но
не в SQL), и каждый течь чинился точечно: это и есть механика «мешанины».

Модель: Discogs `<descriptions>` мешает три ортогональные вещи — **тип релиза**
(Album, Single, EP, Mini-Album, Maxi-Single, Compilation), **носитель/тираж**
(LP, 12", 45 RPM, Reissue, Limited Edition) и **служебное** (Promo, Sampler,
Advance, Transcription, Interview, DVD-Video). Классификатор разбирает их
именно в таком порядке: служебное → тип → носитель.

**Дефолт — `other`, не `album`.** Прежнее правило «никогда не возвращать None,
всё непонятное → album» и набивало «Альбомы» интервью-дисками, radio-сэмплерами
и transcription-катками. Замер по четырём артистам после правки правил и
ре-ингеста полных описаний:

| Артист | «Альбомы» было | стало | Сборники | EP | Синглы | Другое |
|---|---|---|---|---|---|---|
| Eminem | 46 | 16 | 13 | 1 | 87 | 81 |
| Radiohead | 52 | 19 | 8 | 12 | 61 | 110 |
| Queen | 169 | 35 | 71 | 9 | 182 | 156 |
| Daft Punk | 29 | 10 | 11 | 2 | 24 | 33 |

### Ловушки, на которые есть регресс-тесты

| Строка | Тип | Почему |
|---|---|---|
| `CD, Mini-Album` | `ep` | Подстрока «album» уводила его в альбомы (Radiohead «Airbag / How Am I Driving?») |
| `CD, Mini` | нет данных | Это 3" CD — **носитель**. По нему вся сингловая дискография Queen числилась как EP |
| `Cassette, Single Sided` | нет данных | Односторонняя кассета, не сингл. 42k строк в дампе |
| `DVD, Album` | `album` | DVD-Audio — музыкальный носитель. Видео только по явным маркерам |
| `VHS, Compilation` | `other` | Явное видео перебивает тип |
| `CD, Sampler, Promo` | `other` | Служебное проверяется раньше типа |

### Голосование по группе версий

Тип мастера — **плюрализм** по различным форматам его изданий, ничья ломается по
специфичности `ep > single > compilation > album`. Стоявший здесь `bool_or`
давал альбому приоритет над всем: у «My Iron Lung» одно `Vinyl, LP` перебивало
четыре EP-версии. Служебные версии в голосовании не участвуют, но если ВСЕ
версии служебные — группа и есть промо-материал → `other`.

### Формат из Search API

```python
formats = item.get("format", [])          # ["CD", "Album"] или ["Vinyl", "Single"]
format_str = ", ".join(formats) if formats else None
release_type = classify_format(format_str)
```

Search API возвращает `format` как **список строк** (не строку). Объединяем через `", "`.

### Четыре фильтра на экране артиста (Mobile)

```typescript
type ReleaseFilter = 'album' | 'ep' | 'single' | 'compilation';
```

`Альбомы` — только студийные и концертные (дескриптор Album/LP). Сборники,
бест-оф и микстейпы уехали в свой чип `Сборники`: раньше они сидели в
«Альбомах» вперемешку с фанатскими «Special Sampler 2003» и «Before Kid A».

`other` в чипы не попадает — такие карточки видны только без фильтра.
`matchesFilter` больше **не** приравнивает пустой `release_type` к альбому.

### Полные описания формата — `discogs_release_formats`

`format_type` в индексе несёт только **первое** описание первого формата: у
«Curtain Call (Album Sampler)» Discogs отдаёт `['Sampler','Promo','Compilation']`,
а в базе лежало `CD, Sampler`. Из-за этого 1.06M строк оставались без типового
маркера, а radio-show LP Queen («Innerview», «BBC Rock Hour-309») выглядели
альбомами — их `Transcription` терялся при ингесте.

Ре-ингест 2026-08-06 залил полные описания в отдельную таблицу
`discogs_release_formats` (8.5M строк, 747 МБ — только релизы, реально
существующие в индексе). Запрос дискографии берёт
`COALESCE(f.format_full, i.format_type)`; строки с 0–1 описанием в таблицу не
пишутся, там `format_type` и так полон. Обновляется вместе с индексом —
`scripts/refresh_discogs_dump.sh`, см.
[DISCOGS_DATA_DUMPS.md](../discogs/DISCOGS_DATA_DUMPS.md) §10.

Цена: запрос дискографии самого тяжёлого артиста (Queen, 6837 релизов) вырос с
~45 мс до ~380 мс — 6837 PK-lookup'ов в таблицу, которая не влезает в 1.9 ГБ
RAM прода. Типовой артист — 31 мс. Экран кэшируется на 300 с, так что цена
приемлемая, но при следующем упоре в latency начинать надо отсюда.

---

## 4. Имя артиста: disambig-суффикс

Discogs хранит артистов с суффиксом вида `"Prince (3)"` для устранения неоднозначности.  
Перед запросом к Search API суффикс удаляется:

```python
clean_name = re.sub(r'\s*\(\d+\)\s*$', '', artist_name).strip()
# "Prince (3)" → "Prince"
```

Без этого Search API вернёт мало или ноль результатов.

---

## 5. Кэш

| Тип | Ключ | TTL |
|-----|------|-----|
| artist_masters | `{artist_id}:search:p{page}` | 1 день (`TTL_ARTIST_MASTERS = 86400`) |

**После изменения логики обложек/фильтров — обязательно сбросить кэш:**
```bash
ssh deploy@85.198.85.12 'docker exec vertushka_redis redis-cli --scan --pattern "artist_masters:*" | xargs -r docker exec -i vertushka_redis redis-cli del'
```

Local-first путь (дамп-индекс) в Redis не кэшируется — там достаточно рестарта
API. Но выдача едет ещё через два слоя: nginx `Cache-Control: max-age=300` и
клиентский `useCacheStore.artistMasters` (TTL 5 минут, in-memory). Оба
рассасываются сами; при проверке фикса на устройстве — перезапустить приложение,
иначе увидишь старую классификацию.

---

## 6. Что нельзя менять без понимания последствий

| Что | Почему нельзя |
|-----|--------------|
| Вернуть `/artists/{id}/releases` | Нет `format[]` → фильтры сломаются; нет `cover_image` → пиксели |
| Убрать проверку `api-img.discogs.com` в `_thumb_to_cover` | Подписанные URL истекают, изображения будут битыми |
| Завести регекс типа релиза вне `release_type.py` | Копии расходятся и чинятся по одной — так и появилась мешанина в «Альбомах» |
| Вернуть дефолт «непонятное → album» | Интервью, сэмплеры, transcription-диски и DVD-концерты снова заполнят «Альбомы» |
| Считать `Mini` за EP, а `Single Sided` за сингл | Это носители (3" CD и односторонняя кассета), не типы |
| Приравнять пустой `release_type` к альбому на мобиле | Тот же дефолт, только на клиенте |
| Судить тип мастера по одному representative-формату | Он случайный: DVD-A издание уводило флагманский альбом в `other` |
