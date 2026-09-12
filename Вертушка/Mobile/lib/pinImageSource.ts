/**
 * Источник для expo-image под локальный PNG-пин ачивки.
 *
 * Почему на Android пины «пиксельные», а на iOS нет:
 * `require('./pin.png')` резолвится в `{ uri, width, height, scale }`, и
 * expo-image на Android при известных width/height ставит Glide
 * `override(width × scale, height × scale)` (SourceMap.createGlideOptions).
 * Это фиксирует размер ДЕКОДА в полный размер файла — 512² у дизайнов,
 * 2048² у egg/gift/trophy — вместо размера вью (72dp × 3 = 216px). Дальше
 * ImageView рисует 512→216 GPU-билинейно без мипмапов: каждый второй пиксель
 * пропускается, тонкие линии иллюстрации рассыпаются. iOS декодирует через
 * `imageThumbnailPixelSize` = размер вью × scale, поэтому там гладко.
 *
 * Лечение: на Android отдаём только `uri` (без width/height) → override не
 * ставится, Glide берёт размер вью и даунсемплит при декоде (QUALITY-округление:
 * 512 → 256 семплом, затем точное 216 через density-scale). Заодно egg/gift/
 * trophy перестают держать по 16 МБ ARGB в памяти на каждый инстанс.
 *
 * iOS не трогаем — возвращаем исходный require как есть.
 */
import { Image as RNImage, Platform, type ImageSourcePropType } from 'react-native';
import type { ImageSource } from 'expo-image';

export type PinImageSource = ImageSourcePropType | ImageSource;

export function pinImageSource(source: ImageSourcePropType): PinImageSource {
  if (Platform.OS !== 'android') return source;
  const resolved = RNImage.resolveAssetSource(source);
  // Dev: http://…/assets/…png?platform=android&hash=…; release: имя drawable;
  // OTA (expo-updates): file://… — все три ветки Glide понимает без width/height.
  if (!resolved?.uri) return source;
  return { uri: resolved.uri };
}
