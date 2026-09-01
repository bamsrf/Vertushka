/**
 * MarketHeader — заголовок «МАРКЕТ ◉» с двумя режимами.
 *
 * Режимы:
 *   - 'hero'   — большой заголовок 40pt RubikMonoOne + ember underline +
 *                subtitle. Дефолт, виден когда юзер только вошёл в Маркет.
 *   - 'sticky' — компактный 17pt sticky-bar высотой 110 (54 safe-area + 56 content),
 *                background BlurView 24 поверх market-фона. Появляется когда
 *                юзер скроллит внутри Маркета (sticky pinned at top).
 *
 * Переход между режимами анимируется через cross-fade в родителе
 * (MarketScreen или search.tsx), driven by scrollY interpolation.
 *
 * Источник: screens-market.jsx из Design Claude handoff (ScreenMarketFull
 * stickyHeader prop) + docs/plans/market/MARKET_AND_PRICE_DRAWER.md §1.6.
 */
import React from 'react';
import { Platform, Pressable, StyleSheet, Text, View, type StyleProp, type ViewStyle } from 'react-native';
import { BlurView } from 'expo-blur';

import { Icon } from '../ui/Icon';
import { MarketPalette } from '../../constants/theme';
import { ms } from '../../lib/responsive';

/**
 * Оптическое выравнивание disc-иконки с капителями «МАРКЕТ».
 *
 * Подбирать сдвиг на глаз бесполезно: он зависит от того, где внутри line-box
 * лежит baseline, а это считается из метрик шрифта и различается по платформам.
 * Метрики RubikMonoOne-Regular (upem 1000): ascender 932, descender −306,
 * capHeight 700.
 */
const HERO_FONT_SIZE = 40;
const HERO_LINE_HEIGHT = 40;
const HERO_DISC_SIZE = 30;

const RUBIK_ASCENT = 0.932 * HERO_FONT_SIZE;   // 37.28
const RUBIK_DESCENT = 0.306 * HERO_FONT_SIZE;  // 12.24
const RUBIK_CAP = 0.700 * HERO_FONT_SIZE;      // 28.00

/**
 * Позиция baseline от верха line-box:
 *   • iOS (TextKit): при lineHeight меньше натурального (37.28 + 12.24 = 49.52)
 *     строка поджимается сверху, baseline = lineHeight − descent = 27.76;
 *   • Android (CustomLineHeightSpan): разница распределяется поровну сверху и
 *     снизу, baseline = (lineHeight − (ascent + descent)) / 2 + ascent = 32.52.
 */
const HERO_BASELINE =
  Platform.OS === 'ios'
    ? HERO_LINE_HEIGHT - RUBIK_DESCENT
    : (HERO_LINE_HEIGHT - (RUBIK_ASCENT + RUBIK_DESCENT)) / 2 + RUBIK_ASCENT;

/**
 * У titleRow alignItems:'center', значит центр иконки сейчас совпадает с
 * центром line-box. Нужный сдвиг = центр капителей − центр line-box.
 * Иконка (Phosphor VinylRecord) отрисована по центру своего бокса, поэтому
 * центр бокса = визуальный центр пластинки. Итог: −6 (iOS) / −1.5 (Android).
 */
const HERO_DISC_OFFSET =
  Math.round(((HERO_BASELINE - RUBIK_CAP / 2) - HERO_LINE_HEIGHT / 2) * 2) / 2;

interface MarketHeaderProps {
  mode?: 'hero' | 'sticky';
  /** Подзаголовок «В наличии сейчас · 4 магазина · 5 437 шт.» */
  subtitle?: string;
  /** Top padding под safe-area. Default 70 (hero) / 54 (sticky). */
  paddingTop?: number;
  /** Тап по иконке поиска в sticky-режиме (фокусирует input в маркете). */
  onSearchPress?: () => void;
  style?: StyleProp<ViewStyle>;
}

export function MarketHeader({
  mode = 'hero',
  subtitle,
  paddingTop,
  onSearchPress,
  style,
}: MarketHeaderProps) {
  if (mode === 'sticky') {
    return (
      <BlurView
        intensity={24}
        tint="dark"
        style={[
          styles.stickyContainer,
          { paddingTop: paddingTop ?? 54 },
          style,
        ]}
      >
        <View style={styles.stickyContent}>
          <View style={styles.titleRow}>
            <Text style={styles.stickyTitle}>МАРКЕТ</Text>
            <Icon name="disc" size={16} color="accent" weight="duotone" />
          </View>
          <View style={{ flex: 1 }} />
          {onSearchPress && (
            <Pressable
              onPress={onSearchPress}
              hitSlop={12}
              accessibilityRole="button"
              accessibilityLabel="Поиск в Маркете"
            >
              <Icon name="magnifying-glass" size={20} color="onBrand" />
            </Pressable>
          )}
        </View>
      </BlurView>
    );
  }

  // hero
  return (
    <View
      style={[
        styles.heroContainer,
        { paddingTop: paddingTop ?? 70 },
        style,
      ]}
    >
      <View style={styles.titleRow}>
        <Text style={styles.heroTitle}>МАРКЕТ</Text>
        <Icon
          name="disc"
          size={HERO_DISC_SIZE}
          color="accent"
          weight="duotone"
          style={styles.heroDiscIcon}
        />
      </View>
      <View style={styles.underline} />
      {subtitle && (
        <Text style={styles.subtitle}>{subtitle}</Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  // ── HERO ─────────────────────────────────────────────────────────────
  heroContainer: {
    paddingHorizontal: 20,
  },
  heroTitle: {
    // RubikMonoOne — display font из theme.ts (T.type.heroTitle.font)
    fontFamily: 'RubikMonoOne-Regular',
    fontSize: HERO_FONT_SIZE,
    letterSpacing: -0.5,
    lineHeight: HERO_LINE_HEIGHT,
    color: MarketPalette.chrome.textPrimary,
    includeFontPadding: false,
    // textShadow в RN — через text-shadow props. Лёгкая dark подложка чтобы
    // заголовок не сливался с яркими peach-углами фона.
    textShadowColor: 'rgba(0,0,0,0.30)',
    textShadowOffset: { width: 0, height: 2 },
    textShadowRadius: 24,
  },
  heroDiscIcon: {
    // Центр пластинки на оптическом центре капителей «МАРКЕТ».
    // Значение выведено из метрик шрифта — см. HERO_DISC_OFFSET выше.
    transform: [{ translateY: HERO_DISC_OFFSET }],
  },
  underline: {
    width: 56,
    height: 1.5,
    backgroundColor: '#E85A2A',
    marginTop: 8,
    // glow ember
    shadowColor: '#E85A2A',
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.8,
    shadowRadius: 10,
    elevation: 0,
  },
  subtitle: {
    fontFamily: 'Inter_500Medium',
    fontSize: ms(13),
    fontWeight: '500',
    color: MarketPalette.chrome.textSecondary,
    marginTop: 14,
  },
  // ── STICKY ───────────────────────────────────────────────────────────
  stickyContainer: {
    position: 'absolute',
    top: 0, left: 0, right: 0,
    height: 110,
    zIndex: 30,
    backgroundColor: 'rgba(14,7,38,0.55)',
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: MarketPalette.chrome.borderSoft,
    justifyContent: 'flex-end',
    paddingBottom: 0,
  },
  stickyContent: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 10,
    height: 56,
    gap: 10,
  },
  stickyTitle: {
    fontFamily: 'Inter_800ExtraBold',
    fontSize: ms(17),
    fontWeight: '800',
    color: MarketPalette.chrome.textPrimary,
    letterSpacing: -0.3,
    includeFontPadding: false,
  },
  // ── Shared ───────────────────────────────────────────────────────────
  titleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
});

export default MarketHeader;
