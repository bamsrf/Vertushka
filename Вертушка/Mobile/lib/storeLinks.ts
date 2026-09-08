/**
 * Ссылки на магазин приложений по платформе — для пункта «Оценить…» в профиле
 * (A12 в docs/BUGS.md: на Android светился App Store и apps.apple.com).
 *
 * Чистые функции: `os` передаётся явно, чтобы гонять оба варианта в jest.
 */
import { Platform } from 'react-native';

export const ANDROID_PACKAGE = 'com.vertushka.app';

/**
 * Куда вести на iOS, если /api/config не доехал (fail-open, см. lib/remoteConfig.ts).
 * Ровно тот адрес, что Apple отдаёт в trackViewUrl: с витриной и слагом —
 * короткие формы доезжают редиректом не везде. Зеркало Backend/app/config.py.
 */
export const APP_STORE_FALLBACK_URL =
  'https://apps.apple.com/ru/app/' +
  '%D0%B2%D0%B5%D1%80%D1%82%D1%83%D1%88%D0%BA%D0%B0-' +
  '%D0%BA%D0%BE%D0%BB%D0%BB%D0%B5%D0%BA%D1%86%D0%B8%D1%8F-' +
  '%D0%B2%D0%B8%D0%BD%D0%B8%D0%BB%D0%B0/id6774999020';

/** Deep link в приложение Play — открывает карточку сразу в маркете. */
export const PLAY_STORE_MARKET_URL = `market://details?id=${ANDROID_PACKAGE}`;
/** Веб-фолбэк, если приложения Play нет (эмулятор без GMS, кастомные прошивки). */
export const PLAY_STORE_WEB_URL = `https://play.google.com/store/apps/details?id=${ANDROID_PACKAGE}`;

export function storeName(os: string = Platform.OS): string {
  return os === 'android' ? 'Google Play' : 'App Store';
}

export function rateAppLabel(os: string = Platform.OS): string {
  return `Оценить в ${storeName(os)}`;
}

/**
 * Кандидаты для `Linking.openURL` по порядку: первый удачный выигрывает.
 *
 * iOS — прежняя ветка: канонический URL из конфига (или фолбэк) с
 * `?action=write-review`, который сразу открывает форму отзыва.
 * Android — сначала `market://` (родной Play), затем URL из конфига либо веб-Play;
 * `action=write-review` — параметр Apple, на Play его не дописываем.
 */
export function rateAppUrls(os: string = Platform.OS, storeUrl?: string | null): string[] {
  if (os === 'android') {
    const web = storeUrl || PLAY_STORE_WEB_URL;
    return web === PLAY_STORE_MARKET_URL ? [web] : [PLAY_STORE_MARKET_URL, web];
  }
  return [`${storeUrl || APP_STORE_FALLBACK_URL}?action=write-review`];
}
