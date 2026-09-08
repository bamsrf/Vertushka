import {
  APP_STORE_FALLBACK_URL,
  PLAY_STORE_MARKET_URL,
  PLAY_STORE_WEB_URL,
  rateAppLabel,
  rateAppUrls,
} from '../lib/storeLinks';

describe('storeLinks (A12)', () => {
  it('подпись пункта меню по платформе', () => {
    expect(rateAppLabel('ios')).toBe('Оценить в App Store');
    expect(rateAppLabel('android')).toBe('Оценить в Google Play');
  });

  it('iOS: прежняя ветка — URL из конфига или фолбэк + action=write-review', () => {
    expect(rateAppUrls('ios', null)).toEqual([`${APP_STORE_FALLBACK_URL}?action=write-review`]);
    expect(rateAppUrls('ios', 'https://apps.apple.com/app/id1')).toEqual([
      'https://apps.apple.com/app/id1?action=write-review',
    ]);
  });

  it('Android без конфига: market:// затем веб-Play, без write-review', () => {
    const urls = rateAppUrls('android', undefined);
    expect(urls).toEqual([PLAY_STORE_MARKET_URL, PLAY_STORE_WEB_URL]);
    expect(urls.join(' ')).not.toContain('write-review');
    expect(urls.join(' ')).not.toContain('apple.com');
  });

  it('Android с platforms.android.store_url из remoteConfig — он идёт фолбэком после market://', () => {
    const cfg = 'https://play.google.com/store/apps/details?id=com.vertushka.app&hl=ru';
    expect(rateAppUrls('android', cfg)).toEqual([PLAY_STORE_MARKET_URL, cfg]);
  });

  it('Android: если в конфиге уже market://, не дублируем', () => {
    expect(rateAppUrls('android', PLAY_STORE_MARKET_URL)).toEqual([PLAY_STORE_MARKET_URL]);
  });
});
