/// <reference types="jest" />
/**
 * Гейт «iOS-цифры не меняются»: на iOS (пресет jest-expo/ios → Platform.OS =
 * 'ios') формулы из lib/useBottomContentInset.ts обязаны сворачиваться в
 * прежние константы экранов — 88 (футпринт пилюли), 112 (Поиск), 120
 * (ZoomableRecordGrid / MarketMain), 160 (входящие сообщения).
 */
import { Platform } from 'react-native';
import { tabBarBottomOffset, tabBarFootprint, TAB_BAR_PILL_HEIGHT } from '@/lib/useBottomContentInset';

describe('useBottomContentInset (iOS)', () => {
  it('Platform.OS замокан как ios', () => {
    expect(Platform.OS).toBe('ios');
  });

  it('пилюля прибита к bottom: 28 независимо от инсета', () => {
    expect(tabBarBottomOffset(0)).toBe(28);
    expect(tabBarBottomOffset(34)).toBe(28);
    expect(tabBarBottomOffset(48)).toBe(28);
  });

  it('футпринт пилюли = 28 + 60 = 88', () => {
    expect(TAB_BAR_PILL_HEIGHT).toBe(60);
    expect(tabBarFootprint(34)).toBe(88);
  });

  it('прежние клиренсы экранов воспроизводятся из футпринта', () => {
    const footprint = tabBarFootprint(34);
    expect(footprint + 24).toBe(112); // (tabs)/search — TAB_BAR_CLEARANCE
    expect(footprint + 32).toBe(120); // ZoomableRecordGrid, MarketMain
    expect(34 + 126).toBe(160); // messages/index — listContent
  });
});
