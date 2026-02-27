# Фича: Папки в коллекции

**Ветка**: `redesign/v2`
**Статус**: Готов к реализации

---

## Ключевой инсайт: бэкенд уже готов

Модель `Collection` в бэкенде — это и есть "папки". Всё CRUD-API уже реализовано:
- `GET /collections/` — список папок
- `POST /collections/` — создать папку
- `PUT /collections/{id}` — переименовать
- `DELETE /collections/{id}` — удалить
- `POST /collections/{id}/items` — добавить пластинку (`discogs_id` или `record_id`)
- `DELETE /collections/{id}/items/{item_id}` — удалить из папки

**Семантическая модель:**
- `sort_order = 1` (первая коллекция) = **"Вся коллекция"** — главный список, таб "Моё"
- Остальные коллекции (`sort_order > 1`) = **Папки** — отдельные организационные группы
- Пластинка может быть в главной коллекции И в папке одновременно (две `CollectionItem` строки с одним `record_id`)
- Удаление папки не удаляет пластинки из главной коллекции (CASCADE только по папке)

---

## Затронутые файлы

| # | Файл | Что меняется |
|---|------|-------------|
| 1 | `assets/images/folder-placeholder.png` | Сохранить переданный логотип (виниловый персонаж) |
| 2 | `lib/api.ts` | Добавить 3 метода: `addRecordToFolder`, `renameCollection`, `deleteCollection` |
| 3 | `lib/store.ts` | Расширить `CollectionState` — добавить `folders`, 4 actions |
| 4 | `components/FolderPickerModal.tsx` | Новый компонент — поп-ап выбора папки |
| 5 | `app/(tabs)/collection.tsx` | Секция "Папки", кнопка "В папку" в selection footer |
| 6 | `app/record/[id].tsx` | Пункт "Добавить в папку" в ActionSheet |
| 7 | `app/folder/[id].tsx` | Новый экран — содержимое папки + rename/delete |
| 8 | `app/_layout.tsx` | Зарегистрировать маршрут `/folder/[id]` |

---

## Шаг 1: assets

Скопировать изображение маскота из:
```
Вертушка/Design/Logo/винил_папка.png → Вертушка/Mobile/assets/images/folder-placeholder.png
```

---

## Шаг 2: `lib/api.ts` — добавить 3 метода

```typescript
// Добавить пластинку (по внутреннему record_id) в папку
async addRecordToFolder(collectionId: string, recordId: string): Promise<CollectionItem> {
  const response = await this.client.post<CollectionItem>(
    `/collections/${collectionId}/items`,
    { record_id: recordId }
  );
  return response.data;
}

// Переименовать коллекцию/папку
async renameCollection(id: string, name: string): Promise<Collection> {
  const response = await this.client.put<Collection>(`/collections/${id}`, { name });
  return response.data;
}

// Удалить коллекцию/папку
async deleteCollection(id: string): Promise<void> {
  await this.client.delete(`/collections/${id}`);
}
```

> `createCollection` и `getCollections` в `api.ts` уже существуют — их не трогаем.

---

## Шаг 3: `lib/store.ts` — расширить `CollectionState`

### Новые поля состояния

```typescript
interface CollectionState {
  // ... существующие поля ...
  folders: Collection[];  // коллекции с sort_order > 1

  // Новые actions
  fetchFolders: () => Promise<void>;
  createFolder: (name: string) => Promise<Collection>;
  renameFolder: (id: string, name: string) => Promise<void>;
  deleteFolder: (id: string) => Promise<void>;
  addItemsToFolder: (folderId: string, collectionItemIds: string[]) => Promise<void>;
}
```

### Реализация новых actions

```typescript
// Вычисляется из collections — те, что не defaultCollection
fetchFolders: async () => {
  const { collections, defaultCollection } = get();
  const folders = collections.filter(c => c.id !== defaultCollection?.id);
  set({ folders });
},

createFolder: async (name) => {
  const collection = await api.createCollection({ name });
  await get().fetchCollections();
  await get().fetchFolders();
  return collection;
},

renameFolder: async (id, name) => {
  await api.renameCollection(id, name);
  await get().fetchCollections();
  await get().fetchFolders();
},

deleteFolder: async (id) => {
  await api.deleteCollection(id);
  await get().fetchCollections();
  await get().fetchFolders();
},

// itemIds = CollectionItem.id (строки), нужны record.id внутри
addItemsToFolder: async (folderId, collectionItemIds) => {
  const { collectionItems } = get();
  const items = collectionItems.filter(item => collectionItemIds.includes(item.id));
  await Promise.all(
    items.map(item => api.addRecordToFolder(folderId, item.record_id))
  );
  // Обновляем счётчики папок
  await get().fetchCollections();
  await get().fetchFolders();
},
```

**Важно:** В `fetchCollections` добавить вызов `fetchFolders` в конце:
```typescript
fetchCollections: async () => {
  // ...существующая логика...
  set({ collections, defaultCollection, isLoading: false });
  // НОВОЕ: сразу вычисляем folders
  const folders = collections.filter(c => c.id !== (defaultCollection?.id));
  set({ folders });
},
```

---

## Шаг 4: `components/FolderPickerModal.tsx` — новый компонент

### Что делает

Поп-ап (Modal) для выбора папки. Открывается из:
1. Footer в режиме выделения (collection.tsx)
2. ActionSheet на экране пластинки (record/[id].tsx)

### Props

```typescript
interface FolderPickerModalProps {
  visible: boolean;
  onClose: () => void;
  onSelectFolder: (folderId: string) => void;  // callback после выбора
}
```

### Структура UI

```
┌─────────────────────────────────────┐
│  Выбрать папку                      │ ← заголовок + крестик
├─────────────────────────────────────┤
│  ┌───────┐  ┌───────┐  ┌───────┐   │
│  │  img  │  │  img  │  │  img  │   │ ← ScrollView горизонтально
│  │  Джаз │  │  Рок  │  │  Soul │   │
│  │  12 🎵│  │  8 🎵 │  │  4 🎵 │   │
│  └───────┘  └───────┘  └───────┘   │
├─────────────────────────────────────┤
│  [+ Создать новую папку]            │ ← кнопка снизу
└─────────────────────────────────────┘
```

### Логика создания новой папки

- Нажатие на "Создать новую папку" → показывает `Alert.prompt` (iOS) с текстовым полем
- После ввода имени: `createFolder(name)` → автоматически открывает созданную папку (выбирает её)

### Карточка папки

```typescript
// Каждая карточка папки:
// - Image: assets/images/folder-placeholder.png (одно изображение для всех)
// - Название: folder.name (1 строка, обрезать)
// - Счётчик: folder.items_count + " пл."
// - Tap → onSelectFolder(folder.id)
// Размер карточки: 100x130, margin: 8
```

---

## Шаг 5: `app/(tabs)/collection.tsx` — изменения

### 5.1 Секция "Папки" в заголовке

В `CollectionHeader`, **после SegmentedControl** (когда `activeTab === 'collection'`), добавить:

```typescript
{activeTab === 'collection' && folders.length > 0 && (
  <View style={styles.foldersSection}>
    <Text style={styles.foldersSectionTitle}>Папки</Text>
    <ScrollView horizontal showsHorizontalScrollIndicator={false}>
      {/* Кнопка создать новую папку */}
      <TouchableOpacity style={styles.newFolderCard} onPress={handleCreateFolder}>
        <Ionicons name="add" size={32} color={Colors.textMuted} />
        <Text style={styles.newFolderText}>Новая</Text>
      </TouchableOpacity>
      {folders.map(folder => (
        <TouchableOpacity
          key={folder.id}
          style={styles.folderCard}
          onPress={() => router.push(`/folder/${folder.id}`)}
        >
          <Image source={require('../../assets/images/folder-placeholder.png')} style={styles.folderImage} />
          <Text style={styles.folderName} numberOfLines={1}>{folder.name}</Text>
          <Text style={styles.folderCount}>{folder.items_count} пл.</Text>
        </TouchableOpacity>
      ))}
    </ScrollView>
  </View>
)}

{/* Кнопка создать первую папку (когда папок нет) */}
{activeTab === 'collection' && folders.length === 0 && (
  <TouchableOpacity style={styles.createFirstFolder} onPress={handleCreateFolder}>
    <Ionicons name="folder-outline" size={20} color={Colors.textMuted} />
    <Text style={styles.createFirstFolderText}>Создать папку</Text>
  </TouchableOpacity>
)}
```

### 5.2 Кнопка "В папку" в selection footer

В `selectionFooter`, **когда `activeTab === 'collection'`**, добавить кнопку рядом с "Удалить":

```typescript
// В selectionFooter — НОВАЯ кнопка (только для вкладки "Моё")
{activeTab === 'collection' && (
  <TouchableOpacity
    style={styles.footerButton}
    onPress={() => setShowFolderPicker(true)}
    disabled={selectedItems.size === 0}
  >
    <Ionicons
      name="folder-outline"
      size={24}
      color={selectedItems.size > 0 ? Colors.royalBlue : Colors.textMuted}
    />
    <Text style={[styles.footerButtonText, selectedItems.size === 0 && styles.footerButtonTextDisabled]}>
      В папку {selectedItems.size > 0 && `(${selectedItems.size})`}
    </Text>
  </TouchableOpacity>
)}
```

### 5.3 Новые state и handlers

```typescript
const [showFolderPicker, setShowFolderPicker] = useState(false);
const { folders, fetchFolders, createFolder, addItemsToFolder } = useCollectionStore();

const handleAddToFolder = async (folderId: string) => {
  try {
    await addItemsToFolder(folderId, Array.from(selectedItems));
    setShowFolderPicker(false);
    setSelectedItems(new Set());
    setIsSelectionMode(false);
  } catch {
    Alert.alert('Ошибка', 'Не удалось добавить в папку');
  }
};

const handleCreateFolder = () => {
  Alert.prompt(
    'Новая папка',
    'Введите название папки',
    async (name) => {
      if (!name?.trim()) return;
      await createFolder(name.trim());
    },
    'plain-text'
  );
};
```

### 5.4 Добавить FolderPickerModal в return

```typescript
<FolderPickerModal
  visible={showFolderPicker}
  onClose={() => setShowFolderPicker(false)}
  onSelectFolder={handleAddToFolder}
/>
```

---

## Шаг 6: `app/record/[id].tsx` — добавить в ActionSheet

### 6.1 Новый state

```typescript
const [showFolderPicker, setShowFolderPicker] = useState(false);
const { folders, addItemsToFolder } = useCollectionStore();
```

### 6.2 Новый action в `getActionSheetActions()`

```typescript
if (recordStatus.status === 'in_collection') {
  actions.push({
    label: 'Добавить в папку',
    icon: 'folder-outline',
    onPress: () => setShowFolderPicker(true),
  });
  // ...существующие actions...
}
```

### 6.3 Handler

```typescript
const handleAddRecordToFolder = async (folderId: string) => {
  const status = getRecordStatus();
  if (!status.collectionItemId) return;
  try {
    await addItemsToFolder(folderId, [status.collectionItemId]);
    setShowFolderPicker(false);
    Alert.alert('Готово!', 'Пластинка добавлена в папку');
  } catch {
    Alert.alert('Ошибка', 'Не удалось добавить в папку');
  }
};
```

### 6.4 Добавить FolderPickerModal в return

```typescript
<FolderPickerModal
  visible={showFolderPicker}
  onClose={() => setShowFolderPicker(false)}
  onSelectFolder={handleAddRecordToFolder}
/>
```

---

## Шаг 7: `app/folder/[id].tsx` — новый экран

### Что делает
- Отображает все пластинки конкретной папки
- Заголовок с именем папки
- Три точки → ActionSheet с "Переименовать" и "Удалить папку"
- Поддержка selection mode для удаления из папки

### Структура

```typescript
export default function FolderScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [folder, setFolder] = useState<Collection | null>(null);
  const [items, setItems] = useState<CollectionItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [showOptions, setShowOptions] = useState(false);

  const { renameFolder, deleteFolder, fetchFolders } = useCollectionStore();

  // loadFolder: GET /collections/{id} → items
  // handleRename: Alert.prompt → renameFolder → обновить состояние
  // handleDelete: Alert confirm → deleteFolder → router.back()
  // handleRemoveItem: DELETE /collections/{id}/items/{item_id}
}
```

### ActionSheet options для папки

```
Переименовать папку   [pencil-outline]
Удалить папку         [trash-outline]  ← destructive
```

---

## Шаг 8: `app/_layout.tsx` — зарегистрировать маршрут

```typescript
// Добавить в Stack.Navigator:
<Stack.Screen name="folder/[id]" options={{ headerShown: false }} />
```

---

## Порядок реализации

```
1. assets/images/folder-placeholder.png — сохранить изображение

2. lib/api.ts
   - addRecordToFolder(collectionId, recordId)
   - renameCollection(id, name)
   - deleteCollection(id)

3. lib/store.ts
   - folders state
   - fetchFolders() — добавить в конец fetchCollections
   - createFolder(name)
   - renameFolder(id, name)
   - deleteFolder(id)
   - addItemsToFolder(folderId, itemIds)

4. components/FolderPickerModal.tsx — новый компонент

5. app/(tabs)/collection.tsx
   - Импорт folders, createFolder, addItemsToFolder из store
   - Секция "Папки" в CollectionHeader
   - Кнопка "В папку" в selectionFooter
   - State + handlers
   - FolderPickerModal

6. app/record/[id].tsx
   - "Добавить в папку" в ActionSheet
   - FolderPickerModal

7. app/folder/[id].tsx — новый экран

8. app/_layout.tsx — маршрут folder/[id]
```

---

## Проверка корректности и ограничения

### ✅ Что корректно

- **Бэкенд**: `POST /collections/{id}/items` поддерживает `record_id` (UUID) — строки 274-279 в `collections.py`. При добавлении `record_id`, который уже в дефолтной коллекции (не в вишлисте), вишлист-чек не сработает ложно — всё чисто.
- **Дубликаты в папке**: Если пластинка уже в папке, создастся ещё одна `CollectionItem` строка. Нужно добавить проверку на стороне клиента перед вызовом `addRecordToFolder`.
- **Удаление папки**: `DELETE /collections/{id}` CASCADE удаляет только `CollectionItem` строки этой папки. Пластинки в главной коллекции (дефолтной) не затрагиваются — это корректно.
- **Sort order**: Дефолтная коллекция (`sort_order = 1`) не попадает в список папок, поскольку фильтруем по `id !== defaultCollection.id`.
- **Alert.prompt**: Нативный iOS диалог — подходит для создания/переименования папки. Не требует доп. зависимостей.

### ⚠️ Ограничения

- **Одно изображение для всех папок** — кастомные обложки папок не реализуются в этой итерации. Все папки показывают `folder-placeholder.png`.
- **`Alert.prompt` — только iOS**. Для Android нужен кастомный модальный `TextInput`. Если приложение ориентировано на iOS — ок. Если нет — заменить на отдельный модальный компонент для ввода имени.
- **`addItemsToFolder` делает N запросов** (по одному на пластинку). При большом выделении (20+ пластинок) можно добавить batch-endpoint на бэкенде в будущем. Для текущего use case (несколько пластинок) — приемлемо.
- **Папка внутри `/folder/[id]` загружает данные через `GET /collections/{id}`** — это отдельный запрос, не из store. Данные между экранами не синхронизируются автоматически. При удалении из папки нужно вызвать `fetchFolders()` из store.

### 🚫 Что не трогаем

- Логика вишлиста — без изменений
- `removeFromCollection` / `removeFromWishlist` — без изменений
- `defaultCollection` / `fetchCollectionItems` — без изменений
- Таб "Хочу" — папки показываются только на вкладке "Моё"

---

## Проверочный список

- [ ] Папки отображаются в секции над списком пластинок (вкладка "Моё")
- [ ] Кнопка "Новая папка" создаёт папку через Alert.prompt с именем
- [ ] Нажатие на папку открывает экран `/folder/[id]` со списком пластинок
- [ ] В экране папки: трёхточечное меню → "Переименовать" и "Удалить"
- [ ] Переименование обновляет название в заголовке и в секции папок
- [ ] Удаление папки: подтверждение → router.back() → папка исчезает из списка
- [ ] В режиме выделения (collection.tsx) появляется кнопка "В папку" рядом с "Удалить"
- [ ] Кнопка "В папку" открывает FolderPickerModal с горизонтальным скроллом
- [ ] В FolderPickerModal можно создать новую папку и сразу выбрать её
- [ ] На экране пластинки (ActionSheet) появляется "Добавить в папку" (только если пластинка в коллекции)
- [ ] После добавления в папку: `items_count` папки увеличивается
- [ ] Placeholder-изображение (`folder-placeholder.png`) отображается на карточках папок
- [ ] Удаление папки не удаляет пластинки из таба "Моё"
