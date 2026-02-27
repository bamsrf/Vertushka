# План улучшения поиска в Вертушке (MVP iOS)

**Дата:** 31 января 2026
**Scope:** Master releases + История поиска + Фильтры + Артисты
**Оценка:** ~815 строк кода

---

## Этапы реализации

### Этап 1: Master Releases (убрать дубликаты)
**Оценка:** ~350 строк | **Приоритет:** Высокий

#### Архитектура
```
Поиск (type=master) → MasterSearchResult { master_id, main_release_id }
↓
Клик → /master/{master_id} (НОВЫЙ ЭКРАН)
↓
Страница мастера: обложка, название, список versions
↓
Клик на version → /record/{release_id} (существующий экран)
↓
addToCollection(release_id) → сохраняет конкретное издание
```

#### Backend
| Файл | Изменения |
|------|-----------|
| `app/schemas/record.py` | Добавить `MasterSearchResult`, `MasterRelease`, `MasterVersion` |
| `app/services/discogs.py` | Добавить методы: `search_masters()`, `get_master()`, `get_master_versions()` |
| `app/api/records.py` | Новые endpoints: `GET /masters/search`, `GET /masters/{id}`, `GET /masters/{id}/versions` |

#### Mobile
| Файл | Изменения |
|------|-----------|
| `lib/types.ts` | Добавить типы `MasterSearchResult`, `MasterRelease`, `MasterVersion` |
| `lib/api.ts` | Методы `searchMasters()`, `getMaster()`, `getMasterVersions()` |
| `lib/store.ts` | Обновить search store для работы с мастерами |
| `app/(tabs)/search.tsx` | Изменить навигацию: клик → `/master/{id}` |
| `app/master/[id].tsx` | **НОВЫЙ ЭКРАН**: обложка, инфо, список versions |
| `components/VersionCard.tsx` | **НОВЫЙ**: карточка издания (страна, год, лейбл, формат) |

**Важно:** `app/record/[id].tsx` остаётся **БЕЗ ИЗМЕНЕНИЙ** — он работает с release_id

---

### Этап 2: История поиска
**Оценка:** ~60 строк | **Приоритет:** Высокий

#### Mobile
| Файл | Изменения |
|------|-----------|
| `lib/store.ts` | Добавить `searchHistory: string[]` + AsyncStorage persist |
| `app/(tabs)/search.tsx` | Компонент "Вы искали ранее" под строкой поиска |

**Логика:**
- Хранить последние 20 запросов
- Показывать когда поле пустое, скрывать при результатах
- Возможность удалить отдельный элемент или очистить всё

---

### Этап 3: Фильтры
**Оценка:** ~115 строк | **Приоритет:** Средний

#### Backend
| Файл | Изменения |
|------|-----------|
| `app/services/discogs.py` | Передать `format`, `country` в Discogs API |

#### Mobile
| Файл | Изменения |
|------|-----------|
| `lib/types.ts` | Расширить `SearchFilters`: добавить `format`, `country` |
| `lib/api.ts` | Передать новые параметры |
| `app/(tabs)/search.tsx` | Кнопка "Фильтры" + BottomSheet с выбором |

**UI фильтров (BottomSheet):**
- Формат: Vinyl, CD, Cassette, All
- Страна: US, UK, Japan, Germany, All
- Год: диапазон или конкретный

---

### Этап 4: Поиск артистов + страница артиста
**Оценка:** ~280 строк | **Приоритет:** Высокий

#### Backend
| Файл | Изменения |
|------|-----------|
| `app/schemas/record.py` | Добавить `Artist`, `ArtistSearchResult` |
| `app/services/discogs.py` | Методы: `search_artists()`, `get_artist()`, `get_artist_releases()` |
| `app/api/records.py` | Endpoints: `GET /artists/search`, `GET /artists/{id}`, `GET /artists/{id}/releases` |

#### Mobile
| Файл | Изменения |
|------|-----------|
| `lib/types.ts` | Типы `Artist`, `ArtistSearchResult` |
| `lib/api.ts` | Методы `searchArtists()`, `getArtist()`, `getArtistReleases()` |
| `app/(tabs)/search.tsx` | Табы "Релизы | Артисты" |
| `app/artist/[id].tsx` | **НОВЫЙ ЭКРАН**: фото, имя, профиль, список релизов |
| `components/ArtistCard.tsx` | **НОВЫЙ**: карточка артиста для поиска |
| `components/RecordCard.tsx` | Кликабельное имя артиста → `/artist/{id}` |

---

### Этап 5: Polish
**Оценка:** ~10 строк | **Приоритет:** Низкий

| Файл | Изменения |
|------|-----------|
| `components/RecordCard.tsx` | Убрать ограничение `numberOfLines` или добавить "развернуть" |

---

## Новые файлы (создать)

### Mobile
```
Mobile/
├── app/
│   ├── master/
│   │   └── [id].tsx          # Страница мастера с версиями
│   └── artist/
│       └── [id].tsx          # Страница артиста
└── components/
    ├── VersionCard.tsx       # Карточка издания
    └── ArtistCard.tsx        # Карточка артиста
```

---

## API Endpoints (новые)

### Masters
```
GET /api/masters/search?q={query}&page=1&per_page=20
→ { results: MasterSearchResult[], total, page, per_page }

GET /api/masters/{master_id}
→ MasterRelease { master_id, title, artist, year, main_release_id, images }

GET /api/masters/{master_id}/versions?page=1&per_page=50
→ { results: MasterVersion[], total, page, per_page }
```

### Artists
```
GET /api/artists/search?q={query}&page=1&per_page=20
→ { results: ArtistSearchResult[], total, page, per_page }

GET /api/artists/{artist_id}
→ Artist { id, name, profile, images }

GET /api/artists/{artist_id}/releases?page=1&per_page=50
→ { releases: Release[], total, page, per_page }
```

---

## Типы TypeScript (новые)

```typescript
// Master Releases
interface MasterSearchResult {
  master_id: string;
  title: string;
  artist: string;
  year?: number;
  main_release_id: string;
  cover_image_url?: string;
  thumb_image_url?: string;
}

interface MasterRelease {
  master_id: string;
  title: string;
  artist: string;
  year?: number;
  main_release_id: string;
  genres?: string[];
  styles?: string[];
  cover_image_url?: string;
}

interface MasterVersion {
  release_id: string;
  title: string;
  label?: string;
  catalog_number?: string;
  country?: string;
  year?: number;
  format?: string;
  thumb_image_url?: string;
}

// Artists
interface ArtistSearchResult {
  artist_id: string;
  name: string;
  thumb_image_url?: string;
}

interface Artist {
  artist_id: string;
  name: string;
  profile?: string;
  images?: string[];
}

// Расширенные фильтры
interface SearchFilters {
  artist?: string;
  year?: number;
  label?: string;
  genre?: string;
  format?: string;   // NEW
  country?: string;  // NEW
}
```

---

## Pydantic схемы (новые)

```python
# app/schemas/record.py

class MasterSearchResult(BaseModel):
    master_id: str
    title: str
    artist: str
    year: int | None = None
    main_release_id: str
    cover_image_url: str | None = None
    thumb_image_url: str | None = None

class MasterVersion(BaseModel):
    release_id: str
    title: str
    label: str | None = None
    catalog_number: str | None = None
    country: str | None = None
    year: int | None = None
    format: str | None = None
    thumb_image_url: str | None = None

class MasterRelease(BaseModel):
    master_id: str
    title: str
    artist: str
    year: int | None = None
    main_release_id: str
    genres: list[str] = []
    styles: list[str] = []
    cover_image_url: str | None = None

class ArtistSearchResult(BaseModel):
    artist_id: str
    name: str
    thumb_image_url: str | None = None

class Artist(BaseModel):
    artist_id: str
    name: str
    profile: str | None = None
    images: list[str] = []
```

---

## Верификация (чеклист)

После реализации проверить:

- [ ] Поиск "Pink Floyd" → уникальные альбомы, без дубликатов
- [ ] Клик на альбом → страница мастера с версиями
- [ ] Клик на версию → страница релиза с треклистом
- [ ] Добавить в коллекцию конкретное издание
- [ ] История поиска сохраняется между сессиями
- [ ] Очистка истории работает
- [ ] Фильтры работают (формат=Vinyl, страна=US)
- [ ] Табы "Релизы | Артисты" переключаются
- [ ] Поиск артиста → переход на страницу → список релизов
- [ ] Клик на имя артиста из RecordCard → страница артиста
- [ ] Длинные названия не обрезаются некрасиво

---

## Отложено на v2

- **Рекомендации** на основе жанров коллекции (~90 строк)
  - Собрать genres/styles из коллекции
  - Поиск по топ-3 жанрам
  - Исключить уже добавленные
  - Показывать на пустом экране поиска
