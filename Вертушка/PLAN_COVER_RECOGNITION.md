# Распознавание обложки пластинки через GPT-4o-mini Vision

## Контекст
Сейчас приложение умеет находить пластинки только по штрихкоду. Но не на всех пластинках есть штрихкод. Нужна возможность сфотографировать обложку и найти пластинку визуально — как в Record Scanner. On-device ML не подходит (ML Kit не знает альбомов), поэтому используем GPT-4o-mini Vision (~$0.003/запрос) на бэкенде.

## Архитектура
```
Mobile: фото обложки → base64 → POST /records/scan/cover/
Backend: получает base64 → GPT-4o-mini Vision → {artist, album} → Discogs search → результаты
Mobile: показывает результаты в том же модале что и штрихкод
```

## Файлы

### Backend (создать/изменить)

| Файл | Действие |
|------|----------|
| `Backend/app/config.py` | Добавить `openai_api_key` |
| `Backend/app/services/openai_vision.py` | **Новый** — сервис распознавания обложки |
| `Backend/app/schemas/record.py` | Добавить `CoverScanRequest`, `CoverScanResponse` |
| `Backend/app/api/records.py` | Добавить `POST /records/scan/cover/` |

### Mobile (изменить)

| Файл | Действие |
|------|----------|
| `Mobile/lib/types.ts` | Добавить `ScanMode`, `CoverScanResponse` |
| `Mobile/lib/api.ts` | Добавить `scanCover()` метод |
| `Mobile/lib/store.ts` | Расширить `useScannerStore` — режим, `searchByCover()` |
| `Mobile/app/(tabs)/index.tsx` | Переключатель режимов, кнопка затвора, фото |

### Зависимости
- `expo-image-manipulator` — ресайз + сжатие фото перед отправкой
- Новых Python-зависимостей НЕТ (httpx уже есть)

---

## Пошаговый план

### Фаза 1: Backend

#### 1.1 config.py
Добавить поле в `Settings`:
```python
openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
```

#### 1.2 services/openai_vision.py (новый файл)
- Класс `OpenAIVisionService` с методом `recognize_cover(image_base64: str) -> dict[str, str]`
- Использует `httpx.AsyncClient` напрямую (без openai SDK)
- POST на `https://api.openai.com/v1/chat/completions`, модель `gpt-4o-mini`
- Промпт: "Identify artist and album from this vinyl cover photo. Return JSON: {artist, album}"
- `detail: "low"` — дешевле, достаточно для обложек (85 токенов на изображение)
- Парсинг JSON из ответа (с обработкой markdown code fences)
- Кастомный `CoverRecognitionError` для ошибок

#### 1.3 schemas/record.py
```python
class CoverScanRequest(BaseModel):
    image_base64: str  # Base64-encoded JPEG

class CoverScanResponse(BaseModel):
    recognized_artist: str
    recognized_album: str
    results: list[RecordSearchResult]
```

#### 1.4 api/records.py — POST /records/scan/cover/
- Принимает `CoverScanRequest` (JSON body)
- Валидация размера base64 (макс 10MB)
- Вызывает `OpenAIVisionService.recognize_cover()` → получает artist + album
- Ищет в Discogs через `DiscogsService.search(query, artist=artist)`
- Возвращает `CoverScanResponse` с распознанным текстом + результатами
- Ошибки: 422 (не распознано), 503 (сервис недоступен), 413 (слишком большое фото)

### Фаза 2: Mobile

#### 2.1 Установить expo-image-manipulator
```bash
cd Вертушка/Mobile && npx expo install expo-image-manipulator
```

#### 2.2 types.ts
```typescript
export type ScanMode = 'barcode' | 'cover';
export interface CoverScanResponse {
  recognized_artist: string;
  recognized_album: string;
  results: RecordSearchResult[];
}
```

#### 2.3 api.ts
Метод `scanCover(imageBase64: string): Promise<CoverScanResponse>` — POST на `/records/scan/cover/`

#### 2.4 store.ts — расширить useScannerStore
- Новые поля: `scanMode`, `recognizedInfo: {artist, album} | null`
- Новые действия: `setScanMode()`, `searchByCover(imageBase64)`
- `searchByCover` вызывает `api.scanCover()`, сохраняет результаты и recognizedInfo

#### 2.5 app/(tabs)/index.tsx — UI
- **SegmentedControl** (компонент уже есть) с табами "Штрихкод" / "Обложка"
- Подзаголовок меняется в зависимости от режима
- В режиме "Обложка":
  - Рамка квадратная (aspect ratio 1:1) вместо прямоугольной
  - Barcode scanning отключён (`onBarcodeScanned={undefined}`)
  - Кнопка затвора внизу (круг 72px, стиль iOS камеры)
- `cameraRef` для `takePictureAsync()`
- `handleTakePhoto`: фото → ресайз 1024px, JPEG 50% → base64 → searchByCover
- В модале результатов: баннер "Распознано: Artist — Album" (если cover mode)

---

## Верификация
1. Backend: запустить локально, тест `POST /records/scan/cover/` с base64 фото обложки через curl
2. Mobile: переключить на "Обложка", сфотографировать обложку, проверить что результаты появляются
3. Проверить что режим "Штрихкод" работает как раньше (регрессия)
4. Проверить ошибки: нераспознанная обложка, нет интернета, фото не обложки
