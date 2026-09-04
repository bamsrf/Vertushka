# Чеклист апгрейда Expo SDK / React Native

> Родился из апгрейда SDK 54 → 57 (04.09.2026): RN 0.86 удалил
> `StyleSheet.absoluteFillObject`, спред `...absoluteFillObject` молча давал
> `{}` — оверлеи теряли `position: absolute` и вставали в поток. Симптомы
> выглядели как три несвязанных бага (невидимая камера, сжатый экран,
> наезжающий винил), часы диагностики. `npx tsc --noEmit` находил корень
> за минуту — но никто его не запустил.

## Порядок

1. **Чистая точка**: закоммитить WIP, апгрейд — в отдельной ветке
   (`chore/expo-NN`), одним коммитом. Откат = переключение ветки.
2. `npx expo install expo@^NN` → `npx expo install --fix` (дважды, до
   «Dependencies are up to date» в `--check`).
3. **`npx tsc --noEmit` — СРАЗУ после установки, до запуска приложения.**
   Это главный шаг. Удалённые/переименованные API (`absoluteFillObject`,
   `allowsFullscreen`, сузившиеся типы reanimated/linear-gradient) в
   рантайме падают МОЛЧА — undefined вместо ошибки. tsc называет их
   поимённо. Ошибки разбирать до нуля, а не «потом»: type-ошибка после
   мажорного апгрейда — это с большой вероятностью рантайм-баг, а не
   косметика.
4. Сверить нативные версии с Expo Go/dev-client:
   `expo/bundledNativeModules.json` против установленных (svg, reanimated,
   worklets, screens, camera, image).
5. Форс-сборка бандла без телефона: взять `launchAsset.url` из манифеста
   (`curl -H "expo-platform: ios" localhost:8081/`) и скачать — HTTP 200
   и мегабайты JS, а не JSON с ошибкой.
6. Прогон на устройстве: смотреть не только «работает», а именно оверлеи,
   абсолютное позиционирование, камеру, анимации входа/выхода.

## Грабли SDK 57 конкретно (чтобы не открывать заново)

- `StyleSheet.absoluteFillObject` удалён → `StyleSheet.absoluteFill`
  (теперь это обычный объект, годится и для спреда).
- `expo-router` 6: прямые импорты `@react-navigation/*` запрещены
  (`useIsFocused` → из `expo-router`, `BottomTabBarProps` →
  `expo-router/js-tabs`), сам пакет из deps убрать.
- reanimated 4.5: `FadeIn.withInitialValues` принимает только `{opacity}` —
  сдвиги делать кастомным entering-worklet.
- expo-linear-gradient 15: `colors` — tuple минимум из двух
  (`readonly [ColorValue, ColorValue, ...]`), `string[]` не проходит.
- expo-video 3: `allowsFullscreen` → `fullscreenOptions={{enable: false}}`;
  сам expo-video появился в Expo Go 57 — ветки «модуля нет в Go» начинают
  исполняться иначе.
- react-native-svg 15.15: `dominantBaseline` выпилен из типов (native его
  никогда не поддерживал).
- Локальные нативные модули: проверить, что `expo-modules-core` остался
  в дереве — апгрейд может его выкинуть.
- phosphor-react-native 3.0.6: в tarball нет `index.d.ts` → ambient-типы
  в `Mobile/types/phosphor-react-native.d.ts`.
