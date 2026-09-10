/**
 * Нижний отступ контента под системную панель и плавающий GlassTabBar.
 *
 * Зачем один хук: до него каждый экран считал клиренс сам — хардкод 100/112/
 * 120/160 «под iOS» (home indicator 34 + пилюля 60 + воздух). На Android под
 * edge-to-edge `insets.bottom` — это высота системной панели (жесты ~24dp,
 * 3-кнопочная навигация 48dp), и пилюля висит над ней (`GlassTabBar`), так что
 * фиксированные числа не доставали: последний ряд списка, подсказка внизу
 * Поиска и т.п. уезжали под панель.
 *
 * Инвариант iOS (ANDROID_PORT_PLAN §2): все формулы на iOS сворачиваются в
 * прежние константы — пилюля там прибита к `bottom: 28`, футпринт 28 + 60 = 88,
 * и экраны передают `extra` так, чтобы итог совпал с тем, что было
 * (112 = 88 + 24, 120 = 88 + 32 и т.д.). Это проверяется тестом
 * `__tests__/useBottomContentInset.test.ts`.
 */
import { Platform } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

/** Высота пилюли GlassTabBar (`styles.blurContainer.height`). */
export const TAB_BAR_PILL_HEIGHT = 60;

/** iOS: пилюля прибита к `bottom: 28` (`GlassTabBar` → `styles.container`). */
const TAB_BAR_IOS_BOTTOM = 28;

/**
 * Android: минимальный зазор до нижней кромки, если система не отдала инсет
 * (жестовая панель «скрыта» на некоторых прошивках), и воздух над панелью.
 */
const TAB_BAR_ANDROID_MIN_INSET = 16;
const TAB_BAR_ANDROID_GAP = 12;

/** Отступ пилюли от нижней кромки экрана. Единственный источник для GlassTabBar. */
export function tabBarBottomOffset(insetBottom: number): number {
  if (Platform.OS === 'ios') return TAB_BAR_IOS_BOTTOM;
  return Math.max(insetBottom, TAB_BAR_ANDROID_MIN_INSET) + TAB_BAR_ANDROID_GAP;
}

/** Футпринт пилюли: от нижней кромки экрана до её верхнего края. iOS = 88. */
export function tabBarFootprint(insetBottom: number): number {
  return tabBarBottomOffset(insetBottom) + TAB_BAR_PILL_HEIGHT;
}

interface BottomContentInsetOptions {
  /** Экран лежит внутри табов — учитывать пилюлю GlassTabBar, не только панель. */
  tabBar?: boolean;
  /** Воздух сверх обязательного клиренса. */
  extra?: number;
}

/**
 * Сколько нужно `paddingBottom` у `contentContainerStyle`, чтобы последний
 * элемент списка можно было доскроллить над панелью (и пилюлей, если есть).
 *
 *   tabBar: false → insets.bottom + extra   (стековые экраны)
 *   tabBar: true  → футпринт пилюли + extra (экраны в табах)
 */
export function useBottomContentInset({ tabBar = false, extra = 0 }: BottomContentInsetOptions = {}): number {
  const insets = useSafeAreaInsets();
  const base = tabBar ? tabBarFootprint(insets.bottom) : insets.bottom;
  return base + extra;
}
