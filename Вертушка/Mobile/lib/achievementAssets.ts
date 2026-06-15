/**
 * Прогрев ассетов ачивок.
 *
 * Пины открытых ачивок — локальные bundled PNG (512×512) из DESIGN_PNGS.
 * При первом маунте expo-image декодирует PNG → видимая задержка иконки.
 * А off-screen карточка шаринга (view-shot) успевает снять кадр ДО декода →
 * пустой пин на шере.
 *
 * Решение: один раз прогреть декод в memory-кэш expo-image заранее
 * (на маунте экрана уведомлений и экрана ачивок), а перед самим шером —
 * дождаться готовности конкретного пина (prefetchAchievementAsset).
 */
import { Image as RNImage, type ImageSourcePropType } from 'react-native';
import { Image as ExpoImage } from 'expo-image';

import { DESIGN_PNGS } from '../assets/achievements/designs';
import type { AchievementItem } from './types';

/** require-модуль → uri (dev: packager-url, prod: bundled asset uri). */
function resolveUri(source: ImageSourcePropType): string | null {
  try {
    const resolved = RNImage.resolveAssetSource(source);
    return resolved?.uri || null;
  } catch {
    return null;
  }
}

/** Грузим+декодируем uri в memory-disk кэш expo-image. */
async function warm(source: ImageSourcePropType): Promise<void> {
  const uri = resolveUri(source);
  if (!uri) return;
  try {
    await ExpoImage.prefetch(uri, 'memory-disk');
  } catch {
    // best-effort — даже без prefetch render-маунт декодирует, просто не мгновенно
  }
}

let prewarmStarted = false;

/**
 * Идемпотентный фоновой прогрев всех PNG-дизайнов открытых ачивок.
 * Вызывать на маунте экранов-точек входа (уведомления, ачивки).
 */
export function prewarmAchievementPins(): void {
  if (prewarmStarted) return;
  prewarmStarted = true;
  const sources = Object.values(DESIGN_PNGS);
  // Не блокируем UI: запускаем параллельно, ошибки глушим внутри warm().
  void Promise.all(sources.map(warm));
}

/**
 * Гарантирует готовность пина КОНКРЕТНОЙ ачивки перед снимком шер-карточки.
 * Возвращается, когда битмап в кэше (или сразу, если у ачивки нет PNG-дизайна —
 * SVG/scene рендерятся синхронно). Заменяет слепой setTimeout в handleShare.
 */
export async function prefetchAchievementAsset(item: AchievementItem): Promise<void> {
  const slug = item.icon_slug?.toLowerCase();
  if (!slug) return;
  const png = DESIGN_PNGS[slug];
  if (!png) return; // SVG-пин/scene — синхронный рендер, ждать нечего
  await warm(png);
}
