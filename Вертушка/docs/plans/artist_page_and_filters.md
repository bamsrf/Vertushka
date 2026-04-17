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

### `_guess_release_type` — правила

```python
@staticmethod
def _guess_release_type(format_str: str | None) -> str | None:
    if not format_str:
        return "album"   # дефолт — никогда не возвращать None
    fmt = format_str.lower()
    if "single" in fmt:
        return "single"
    if "ep" in fmt or "mini" in fmt:
        return "ep"
    if "album" in fmt or "lp" in fmt or "compilation" in fmt:
        return "album"
    return "album"       # fallback — тоже album
```

**Ключевое правило: дефолт всегда `"album"`, никогда `None`.**  
Иначе релизы без чёткого формата не попадут ни в один фильтр.

### Формат из Search API

```python
formats = item.get("format", [])          # ["CD", "Album"] или ["Vinyl", "Single"]
format_str = ", ".join(formats) if formats else None
release_type = self._guess_release_type(format_str)
```

Search API возвращает `format` как **список строк** (не строку). Объединяем через `", "` перед передачей в `_guess_release_type`.

### Три фильтра на экране артиста (Mobile)

```typescript
type ReleaseFilter = 'album' | 'ep' | 'single';

const FILTERS: { key: ReleaseFilter; label: string }[] = [
  { key: 'album', label: 'Альбомы' },
  { key: 'ep',    label: 'EP'      },
  { key: 'single', label: 'Синглы' },
];
```

**Нет фильтра "Другое"** — Search API всегда возвращает `format[]`, поэтому `release_type` никогда не бывает `null` у реальных данных.

### `matchesFilter` — логика на мобиле

```typescript
const matchesFilter = (master: MasterSearchResult, filter: ReleaseFilter): boolean => {
  if (!master.release_type) return filter === 'album';  // страховка на случай null
  return master.release_type === filter;
};
```

Если `release_type` всё же `null` (старый кэш) — относим к Альбомам.

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
ssh deploy@85.198.85.12 'redis-cli --scan --pattern "artist_masters:*" | xargs redis-cli del'
```

---

## 6. Что нельзя менять без понимания последствий

| Что | Почему нельзя |
|-----|--------------|
| Вернуть `/artists/{id}/releases` | Нет `format[]` → фильтры сломаются; нет `cover_image` → пиксели |
| Убрать проверку `api-img.discogs.com` в `_thumb_to_cover` | Подписанные URL истекают, изображения будут битыми |
| Сделать дефолт `_guess_release_type` = `None` | Релизы без формата не попадут ни в один фильтр |
| Передавать сырой `format` (список) напрямую | `_guess_release_type` ожидает строку, не список |
| Добавить фильтр "Другое" | Он всегда будет пустым — Search API заполняет `format[]` |
