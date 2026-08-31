/**
 * HotStockTag — pill-индикатор «в наличии» с 6 состояниями × 3 размерами.
 *
 * Центральный визуальный примитив раздела «Маркет» и Hot Stock UX
 * (см. docs/plans/market/MARKET_AND_PRICE_DRAWER.md §2.2 + atoms.jsx из Design Claude
 * handoff). Концепция: холодный мир коллекции встречает огонь — но только
 * когда что-то реально доступно к покупке. Ember-glow = «лампочка открыто».
 *
 * Состояния:
 *   - inStock      — солидный gradient + glow (1 листинг exact-match)
 *   - inStockMulti — тот же gradient + «от 4 990 ₽» (≥2 листинга)
 *   - lastOne      — = inStock + микро-надпись «1 экз.» сверху
 *   - altVersion   — outline + disc-mono + «· альт.» (другой пресс мастера)
 *   - preorder     — outline + ember-точка + «· предзаказ»
 *   - none         — возвращает null
 *
 * Размеры: sm (для list-row), md (default, compact/expanded), lg (hero).
 *
 * Использование:
 *   <HotStockTag variant="inStock" price={4990} />
 *   <HotStockTag variant="inStockMulti" price={4890} size="lg" />
 *   <HotStockTag variant="lastOne" price={5990} size="md" />
 *   <HotStockTag variant="altVersion" price={5490} />
 *   <HotStockTag variant="preorder" price={6490} />
 *   <HotStockTag variant="none" />   // → null
 *
 * Защита от инфляции токена (где НЕ показывать) — на стороне родителя:
 * см. RecordCard.tsx правила в docs/plans/market/OFFERS_UX.md §2.8.
 */

import React from 'react';
import {
  Pressable,
  StyleSheet,
  Text,
  View,
  type StyleProp,
  type ViewStyle,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';

import { Icon } from './ui/Icon';
import { Gradients, Shadows } from '../constants/theme';

export type HotStockVariant =
  | 'inStock'
  | 'inStockMulti'
  | 'lastOne'
  | 'altVersion'
  | 'preorder'
  | 'none';

export type HotStockSize = 'sm' | 'md' | 'lg';

interface HotStockTagProps {
  variant: HotStockVariant;
  price: number;            // в рублях, целое
  size?: HotStockSize;      // default 'md'
  showArrow?: boolean;      // default: true для md/lg, false для sm
  showShadow?: boolean;     // default true; false для transition/preview-кадров
  showDisc?: boolean;       // default true
  /**
   * 0..1, для transition-моков: насколько «гореть» (1 = полный glow + полный ember
   * в gradient'е, 0 = gradient почти без ember + без glow). Используется в
   * MarketBackground transition (см. docs/plans/market/MARKET_AND_PRICE_DRAWER.md §1.3).
   */
  emberAmount?: number;
  onPress?: () => void;
  hitSlop?: number;         // default 12
  style?: StyleProp<ViewStyle>;
  testID?: string;
}

// ────────────────────────────────────────────────────────────────────────
// Spec из atoms.jsx Design Claude — те же числа, чтобы pixel-perfect match.
// ────────────────────────────────────────────────────────────────────────

const SIZES: Record<HotStockSize, {
  fontSize: number;
  paddingV: number;
  paddingH: number;
  gap: number;
  iconSize: number;
  arrowSize: number;
  outlineBorderWidth: number;
}> = {
  sm: { fontSize: 11, paddingV: 3, paddingH: 8,  gap: 4, iconSize: 11, arrowSize: 9,  outlineBorderWidth: 1 },
  md: { fontSize: 13, paddingV: 5, paddingH: 10, gap: 6, iconSize: 13, arrowSize: 11, outlineBorderWidth: 1 },
  lg: { fontSize: 16, paddingV: 7, paddingH: 14, gap: 7, iconSize: 16, arrowSize: 14, outlineBorderWidth: 1 },
};

const SUFFIX_FONT_DELTA = -1; // suffix (« · альт.» / « · предзаказ») на 1pt мельче

// ────────────────────────────────────────────────────────────────────────
// formatPrice: «4 990 ₽», «12 500 ₽» — NBSP-разделители тысяч.
// Mono-numerals в Text fontVariant ниже гарантируют что цифры не дрожат.
// ────────────────────────────────────────────────────────────────────────

export function formatPrice(n: number): string {
  const rounded = Math.round(n).toString();
  // NBSP ( ) каждые 3 цифры справа
  const withSep = rounded.replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
  return `${withSep} ₽`;
}

// ────────────────────────────────────────────────────────────────────────

export function HotStockTag({
  variant,
  price,
  size = 'md',
  showArrow,
  showShadow = true,
  showDisc = true,
  emberAmount = 1,
  onPress,
  hitSlop = 12,
  style,
  testID,
}: HotStockTagProps) {
  if (variant === 'none') return null;

  const sz = SIZES[size];
  const isOutline = variant === 'altVersion' || variant === 'preorder';
  const arrowDefault = size !== 'sm';
  const arrow = showArrow ?? arrowDefault;
  const ember = Math.max(0, Math.min(1, emberAmount));

  const priceStr = formatPrice(price);
  const displayPrice = variant === 'inStockMulti' ? `от ${priceStr}` : priceStr;
  const suffix = variant === 'altVersion' ? ' · альт.' : variant === 'preorder' ? ' · предзаказ' : null;

  // ── Solid gradient (inStock / inStockMulti / lastOne) ─────────────────
  // Outer LinearGradient как fill + 0.5dp glass-hairline border + ember glow.
  // Shadow.glowEmber берётся из theme.ts и масштабируется emberAmount'ом
  // через shadowOpacity/shadowRadius для transition-моков.
  const solidPill = (
    <LinearGradient
      colors={Gradients.hotStock}
      locations={[0, 0.55 - ember * 0.05, 1]}
      start={{ x: 0, y: 0 }}
      end={{ x: 1, y: 1 }}
      style={[
        styles.pill,
        {
          paddingVertical: sz.paddingV,
          paddingHorizontal: sz.paddingH,
          gap: sz.gap,
          borderWidth: 0.5,
          borderColor: 'rgba(255,255,255,0.18)',
        },
        showShadow && ember > 0 ? {
          ...Shadows.glowEmber,
          shadowOpacity: 0.45 * ember,
          shadowRadius: 24 * ember,
        } : null,
      ]}
    >
      {showDisc && (
        <Icon name="disc" size={sz.iconSize} color="onBrand" weight="duotone" />
      )}
      <Text style={[styles.price, { fontSize: sz.fontSize, color: '#FFFFFF' }]}>
        {displayPrice}
      </Text>
      {arrow && (
        <Icon
          name="arrow-up-right"
          size={sz.arrowSize}
          // Чуть менее заметная стрелка чем сам ценник.
          color="onBrand"
          style={{ opacity: 0.85 }}
        />
      )}
    </LinearGradient>
  );

  // ── Outline (altVersion / preorder) ──────────────────────────────────
  // Gradient-border trick в RN: внешний LinearGradient = «бордюр»,
  // внутренний View чуть меньше на (borderWidth × 2) с тёмным fill = «inset».
  // Для altVersion ещё inset = rgba(255,255,255,0.06) glass.
  const outlinePill = (
    <LinearGradient
      colors={Gradients.hotStockOutline}
      start={{ x: 0, y: 0 }}
      end={{ x: 1, y: 1 }}
      style={[
        styles.pillOuter,
        { padding: sz.outlineBorderWidth }, // gradient-border ширина
      ]}
    >
      <View
        style={[
          styles.pill,
          {
            paddingVertical: sz.paddingV - sz.outlineBorderWidth,
            paddingHorizontal: sz.paddingH - sz.outlineBorderWidth,
            gap: sz.gap,
            backgroundColor: 'rgba(255,255,255,0.06)',
            borderRadius: 9999,
          },
        ]}
      >
        {showDisc && variant === 'altVersion' && (
          // disc-mono — упрощённая иконка без duotone. Используем `disc` (HERO
          // duotone) с opacity, чтобы получить визуально «mono»-эффект без
          // отдельной иконки в registry.
          <Icon
            name="disc"
            size={sz.iconSize}
            color="onBrand"
            weight="regular"
            style={{ opacity: 0.8 }}
          />
        )}
        {showDisc && variant === 'preorder' && (
          // Ember-точка диаметром 6dp с тонким glow вместо disc.
          <View
            style={{
              width: 6,
              height: 6,
              borderRadius: 3,
              backgroundColor: '#E85A2A',
              ...Shadows.glowEmber,
              shadowOpacity: 0.6,
              shadowRadius: 8,
            }}
          />
        )}
        <Text
          style={[
            styles.price,
            {
              fontSize: sz.fontSize,
              color: variant === 'preorder' ? '#FFFFFF' : 'rgba(255,255,255,0.92)',
            },
          ]}
        >
          {displayPrice}
        </Text>
        {suffix && (
          <Text
            style={[
              styles.suffix,
              {
                fontSize: sz.fontSize + SUFFIX_FONT_DELTA,
                color: 'rgba(255,255,255,0.6)',
              },
            ]}
          >
            {suffix}
          </Text>
        )}
        {arrow && variant === 'preorder' && (
          <Icon
            name="arrow-up-right"
            size={sz.arrowSize - 1}
            color="onBrand"
            style={{ opacity: 0.6 }}
          />
        )}
      </View>
    </LinearGradient>
  );

  const pill = isOutline ? outlinePill : solidPill;

  // ── lastOne wrapper: микро-надпись «1 экз.» 9pt uppercase сверху ─────
  const content = variant === 'lastOne' ? (
    <View style={styles.lastOneWrap}>
      <Text style={styles.lastOneLabel}>1 экз.</Text>
      {pill}
    </View>
  ) : (
    pill
  );

  // ── Wrap в Pressable если нужен tap ──────────────────────────────────
  if (onPress) {
    return (
      <Pressable
        onPress={onPress}
        hitSlop={hitSlop}
        accessibilityRole="button"
        accessibilityLabel={getA11yLabel(variant, price)}
        testID={testID}
        style={style}
      >
        {content}
      </Pressable>
    );
  }

  return (
    <View
      accessibilityRole="text"
      accessibilityLabel={getA11yLabel(variant, price)}
      testID={testID}
      style={style}
    >
      {content}
    </View>
  );
}

// ────────────────────────────────────────────────────────────────────────

function getA11yLabel(variant: HotStockVariant, price: number): string {
  const priceStr = formatPrice(price);
  switch (variant) {
    case 'inStock':
      return `В наличии за ${priceStr}. Нажмите чтобы перейти к предложениям`;
    case 'inStockMulti':
      return `В наличии от ${priceStr} в нескольких магазинах`;
    case 'lastOne':
      return `Последний экземпляр — в наличии за ${priceStr}`;
    case 'altVersion':
      return `Нет этого пресса, но есть альтернативная версия того же альбома за ${priceStr}`;
    case 'preorder':
      return `Доступен предзаказ от ${priceStr}`;
    default:
      return '';
  }
}

// ────────────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  pillOuter: {
    alignSelf: 'flex-start',
    borderRadius: 9999,
  },
  pill: {
    alignSelf: 'flex-start',
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: 9999,
  },
  price: {
    fontWeight: '700',
    fontFamily: 'Inter_700Bold',
    letterSpacing: -0.2,
    fontVariant: ['tabular-nums'],
    lineHeight: undefined, // лень определять явно — pill высота уже задана padding'ом
    includeFontPadding: false,
  },
  suffix: {
    fontWeight: '600',
    fontFamily: 'Inter_600SemiBold',
    fontVariant: ['tabular-nums'],
    letterSpacing: -0.1,
    includeFontPadding: false,
  },
  lastOneWrap: {
    alignItems: 'center',
    alignSelf: 'flex-start',
    gap: 3,
  },
  lastOneLabel: {
    fontFamily: 'Inter_700Bold',
    fontSize: 9,
    fontWeight: '700',
    color: '#FFD9C8',
    letterSpacing: 1.2,
    textTransform: 'uppercase',
    // textShadow в RN — через шахту shadowColor + shadowRadius на родителе.
    // Здесь просто warm-tinted color, glow эффект даёт сам gradient pill снизу.
    includeFontPadding: false,
  },
});

// ────────────────────────────────────────────────────────────────────────
// summaryToHotStock — компьютер variant'а из RecordOffersSummary.
//
// Правила взяты из MARKET_AND_PRICE_DRAWER.md §1.15 (комментарий к
// RecordOffersSummary в Backend/app/schemas/offer.py). Один SQL Mobile
// делает на сетку карточек, потом мапит результат в карточки.
//
// Также применяет правила «когда НЕ показывать» (OFFERS_UX.md §2.8):
//   - `rarityContext === 'collection'` → не показываем 'inStock'/'inStockMulti'
//     (у юзера уже эта пластинка) — только альтернативная версия как апселл.
//   - `compact` карточка в сетке → не показываем 'preorder' и 'altVersion'
//     (defer в hero-моменты на детальном экране).
// ────────────────────────────────────────────────────────────────────────

interface HotStockSummaryLike {
  in_stock_count: number;
  preorder_count: number;
  alt_version_count: number;
  min_price_rub: string | number | null;
  min_price_alt_rub: string | number | null;
  has_last_one: boolean;
}

export interface ResolvedHotStock {
  variant: HotStockVariant;
  price: number;
}

export interface HotStockContextHints {
  /** Где рендерится карточка. Влияет на «когда НЕ показывать» (OFFERS_UX.md §2.8). */
  context?: 'search' | 'wishlist' | 'collection' | 'market' | 'detail';
  /** Карточка в сетке (compact). Не показываем preorder/altVersion. */
  isGrid?: boolean;
}

export function summaryToHotStock(
  summary: HotStockSummaryLike | null | undefined,
  hints: HotStockContextHints = {},
): ResolvedHotStock | null {
  if (!summary) return null;

  const { context = 'search', isGrid = false } = hints;
  const minPrice = toNumber(summary.min_price_rub);
  const minPriceAlt = toNumber(summary.min_price_alt_rub);

  // ── Защита от инфляции токена ────────────────────────────────────────
  const inCollection = context === 'collection';

  // 1. inStock / inStockMulti (главный «огонь»)
  if (summary.in_stock_count > 0 && minPrice !== null) {
    // В коллекции «купить то, что уже есть» — не показываем
    if (inCollection) {
      // Fallthrough на altVersion если она есть, иначе ничего
      if (summary.alt_version_count > 0 && minPriceAlt !== null) {
        return { variant: 'altVersion', price: minPriceAlt };
      }
      return null;
    }
    if (summary.has_last_one) {
      return { variant: 'lastOne', price: minPrice };
    }
    return {
      variant: summary.in_stock_count === 1 ? 'inStock' : 'inStockMulti',
      price: minPrice,
    };
  }

  // 2. altVersion (другой пресс мастера) — не на главной/сетке поиска
  if (summary.alt_version_count > 0 && minPriceAlt !== null) {
    if (isGrid && context !== 'wishlist' && context !== 'market') return null;
    return { variant: 'altVersion', price: minPriceAlt };
  }

  // 3. preorder — только на детальном экране, не в сетках
  if (summary.preorder_count > 0 && minPrice !== null) {
    if (isGrid) return null;
    return { variant: 'preorder', price: minPrice };
  }

  return null;
}

function toNumber(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined) return null;
  const n = typeof value === 'number' ? value : parseFloat(value);
  return Number.isFinite(n) ? n : null;
}

export default HotStockTag;
