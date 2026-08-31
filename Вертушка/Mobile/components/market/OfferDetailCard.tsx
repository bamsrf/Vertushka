/**
 * OfferDetailCard — большая карточка оффера в bottom-sheet «Все варианты».
 *
 * Содержит: обложку 64×64, store header (logo+name), цену 17pt/800w,
 * мета-строку (format · vinyl-color (dot+name) · year), артикул mono 11pt,
 * condition-чип (M/NM/VG+), опц. бейдж «АЛТ», CTA «КУПИТЬ НА САЙТЕ →».
 *
 * Highlighted-вариант — для подсветки самого дешёвого / выбранного.
 *
 * Источник: screens-drawer-b.jsx (OfferDetailCard атом) +
 *           docs/plans/market/MARKET_AND_PRICE_DRAWER.md §2.3.
 */
import React from 'react';
import {
  ActivityIndicator,
  Image,
  Pressable,
  StyleSheet,
  Text,
  View,
  type StyleProp,
  type ViewStyle,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';

import { Icon } from '../ui/Icon';
import { Gradients } from '../../constants/theme';
import { formatPrice } from '../HotStockTag';
import StoreLogo, { getStoreName } from './StoreLogo';
import { ms } from '../../lib/responsive';

export interface OfferDetailData {
  listingId: string;
  storeSlug: string;
  storeName?: string;

  // Карточка пластинки
  coverUrl?: string | null;
  artist?: string;
  title?: string;

  // Параметры листинга
  priceRub: number;
  format?: string | null;        // LP / 2xLP / CD / ...
  vinylColor?: string | null;    // «Red», «Pink Marble», ...
  year?: number | null;
  catalogNumber?: string | null; // SKU/артикул
  /** «M»/«NM»/«VG+»/null. Если null — поле не рендерится. */
  condition?: string | null;
  /** true если другой pressing того же мастера, не тот что в вишлисте. */
  isAlt?: boolean;
  /** discogs_id записи к которой матчен листинг. Для alt-cards — это
   *  ДРУГОЙ pressing того же master_id. Парент использует для
   *  router.push(`/record/${recordDiscogsId}`) при onCardPress. */
  recordDiscogsId?: string | null;
}

interface OfferDetailCardProps {
  data: OfferDetailData;
  /** Подсветить (самый дешёвый или selected). Ember-border + glow. */
  highlighted?: boolean;
  /** Тап на «КУПИТЬ» — родитель делает POST /offers/{id}/click + Linking.openURL. */
  onBuyPress: () => void;
  /** Тап на корпус карточки (обложка/название/мета) — обычно navigation
   *  к detail-экрану записи. Для alt-version это критично — юзер хочет
   *  увидеть полную инфу о другом прессинге. */
  onCardPress?: () => void;
  /** Активен loading-state на CTA (чтобы юзер не тапнул дважды). */
  buyLoading?: boolean;
  style?: StyleProp<ViewStyle>;
}

const VINYL_COLOR_TO_HEX: Record<string, string> = {
  black: '#1A1A1A',
  red: '#E53935',
  pink: '#EC407A',
  blue: '#5780F0',
  green: '#43A047',
  yellow: '#FBC02D',
  orange: '#FB8C00',
  purple: '#8E24AA',
  white: '#F5F5F5',
  clear: '#E0E0E0',
};

function colorHex(name?: string | null): string {
  if (!name) return '#5780F0';
  const key = name.toLowerCase().split(/\s+/)[0]; // «Pink Marble» → «pink»
  return VINYL_COLOR_TO_HEX[key] ?? '#5780F0';
}

function isCommonFormat(format: string): boolean {
  // LP / Vinyl — стандартный пресс, не несёт дополнительной инфы кроме
  // того что юзер уже видит из record header'а. Скрываем чтобы не
  // дублировать («LP к чему?»). 2xLP, CD, Cassette, Box Set оставляем.
  const f = format.trim().toLowerCase();
  return f === 'lp' || f === 'vinyl';
}

function colorLabel(name?: string | null): string {
  if (!name) return '';
  // Переводим простые англ. цвета в русские для UI; multi-word оставляем как есть
  const map: Record<string, string> = {
    black: 'Чёрный',
    red: 'Красный',
    pink: 'Розовый',
    blue: 'Синий',
    green: 'Зелёный',
    yellow: 'Жёлтый',
    orange: 'Оранжевый',
    purple: 'Фиолетовый',
    white: 'Белый',
    clear: 'Прозрачный',
  };
  return map[name.toLowerCase()] ?? name;
}

export function OfferDetailCard({
  data,
  highlighted = false,
  onBuyPress,
  onCardPress,
  buyLoading = false,
  style,
}: OfferDetailCardProps) {
  // Wrap card body в Pressable если есть onCardPress (alt-version навигация).
  // CTA «Купить» внутри — оба тапа работают независимо благодаря nested Pressable.
  const CardWrap = onCardPress ? Pressable : View;
  const cardProps = onCardPress
    ? { onPress: onCardPress, accessibilityRole: 'button' as const }
    : {};

  return (
    <CardWrap
      {...cardProps}
      style={[
        styles.card,
        highlighted && styles.cardHighlighted,
        style,
      ]}
    >
      <View style={styles.topRow}>
        <View style={styles.coverWrap}>
          {data.coverUrl ? (
            <Image source={{ uri: data.coverUrl }} style={styles.cover} resizeMode="cover" />
          ) : (
            <View style={[styles.cover, styles.coverPlaceholder]} />
          )}
        </View>

        <View style={styles.info}>
          {/* Store header row */}
          <View style={styles.storeRow}>
            <StoreLogo slug={data.storeSlug} size={20} radius={4} />
            <Text style={styles.storeName} numberOfLines={1}>
              {data.storeName ?? getStoreName(data.storeSlug) ?? data.storeSlug}
            </Text>
            {data.isAlt && (
              <View style={styles.altBadge}>
                <Text style={styles.altBadgeText}>АЛТ</Text>
              </View>
            )}
          </View>

          <Text style={styles.price}>{formatPrice(data.priceRub)}</Text>

          {/* Meta: format · color · year.
              Format показываем ТОЛЬКО если нестандартный (2xLP/Box/CD/Cassette)
              — голый «LP» / «Vinyl» дублирует record.format_type, юзер жаловался
              на «LP к чему?» в OfferRow. Цвет винила выделяем как chip — это
              ценная инфа (лимитка/пресс), не «непонятная подпись». */}
          <View style={styles.metaRow}>
            {data.format && !isCommonFormat(data.format) && (
              <Text style={styles.metaText}>{data.format}</Text>
            )}
            {data.vinylColor && (
              <View style={styles.colorChip}>
                <View
                  style={[
                    styles.colorDot,
                    { backgroundColor: colorHex(data.vinylColor) },
                  ]}
                />
                <Text style={styles.colorLabel}>{colorLabel(data.vinylColor)} винил</Text>
              </View>
            )}
            {data.year != null && (
              <>
                {(data.vinylColor || (data.format && !isCommonFormat(data.format))) && (
                  <View style={styles.metaDot} />
                )}
                <Text style={styles.metaText}>{data.year}</Text>
              </>
            )}
          </View>

          {/* SKU */}
          {data.catalogNumber && (
            <Text style={styles.sku}>Артикул: {data.catalogNumber}</Text>
          )}

          {/* Condition chip */}
          {data.condition && (
            <View style={styles.conditionRow}>
              <View style={styles.conditionChip}>
                <Text style={styles.conditionText}>{data.condition}</Text>
              </View>
              <Text style={styles.conditionDesc}>
                {data.condition === 'M' && 'Mint · запечатанная'}
                {data.condition === 'NM' && 'Near Mint · отличное'}
                {data.condition === 'VG+' && 'Very Good Plus'}
              </Text>
            </View>
          )}
        </View>
      </View>

      {/* CTA */}
      <Pressable
        onPress={onBuyPress}
        disabled={buyLoading}
        accessibilityRole="button"
        accessibilityLabel={`Купить на сайте ${data.storeName ?? data.storeSlug} за ${formatPrice(data.priceRub)}`}
      >
        <LinearGradient
          colors={Gradients.hotStock}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 1 }}
          style={[
            styles.cta,
            {
              shadowColor: '#E85A2A',
              shadowOffset: { width: 0, height: 0 },
              shadowOpacity: 0.20,
              shadowRadius: 18,
            },
          ]}
        >
          {buyLoading ? (
            <ActivityIndicator color="#FFFFFF" size="small" />
          ) : (
            <>
              <Text style={styles.ctaLabel}>Купить на сайте</Text>
              <Icon name="arrow-up-right" size={12} color="onBrand" />
            </>
          )}
        </LinearGradient>
      </Pressable>
    </CardWrap>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#FFFFFF',
    borderRadius: 16,
    padding: 14,
    borderWidth: 1,
    borderColor: '#ECEEF7',
    gap: 12,
    // Лёгкая base-shadow
    shadowColor: 'rgba(11,20,56,0.10)',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 1,
    shadowRadius: 8,
    elevation: 2,
  },
  cardHighlighted: {
    borderWidth: 1.5,
    borderColor: '#E85A2A',
    shadowColor: 'rgba(232,90,42,0.20)',
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 1,
    shadowRadius: 18,
  },
  topRow: {
    flexDirection: 'row',
    gap: 12,
  },
  coverWrap: {
    width: 64,
    height: 64,
    borderRadius: 8,
    overflow: 'hidden',
    backgroundColor: '#F0F2FA',
  },
  cover: {
    width: '100%',
    height: '100%',
  },
  coverPlaceholder: {
    backgroundColor: '#F0F2FA',
  },
  info: {
    flex: 1,
    minWidth: 0,
  },
  storeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 4,
  },
  storeName: {
    fontFamily: 'Inter_600SemiBold',
    fontSize: ms(12),
    fontWeight: '600',
    color: '#0E121C',
    includeFontPadding: false,
  },
  altBadge: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 6,
    backgroundColor: 'rgba(232,90,42,0.10)',
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: 'rgba(232,90,42,0.30)',
  },
  altBadgeText: {
    fontFamily: 'Inter_800ExtraBold',
    fontSize: 9,
    fontWeight: '800',
    color: '#B8431B',
    letterSpacing: 1,
    includeFontPadding: false,
  },
  price: {
    fontFamily: 'Inter_800ExtraBold',
    fontSize: ms(17),
    fontWeight: '800',
    color: '#0E121C',
    letterSpacing: -0.3,
    fontVariant: ['tabular-nums'],
    marginBottom: 4,
    includeFontPadding: false,
  },
  metaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    flexWrap: 'wrap',
  },
  metaText: {
    fontFamily: 'Inter_400Regular',
    fontSize: ms(11.5),
    color: '#4D5263',
    includeFontPadding: false,
  },
  metaDot: {
    width: 2,
    height: 2,
    borderRadius: 1,
    backgroundColor: '#C4CAD6',
  },
  colorChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 9999,
    backgroundColor: 'rgba(232,90,42,0.08)',
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: 'rgba(232,90,42,0.25)',
  },
  colorLabel: {
    fontFamily: 'Inter_700Bold',
    fontSize: 11,
    fontWeight: '700',
    color: '#0E121C',
    letterSpacing: -0.1,
    includeFontPadding: false,
  },
  colorDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: 'rgba(0,0,0,0.10)',
  },
  sku: {
    marginTop: 6,
    fontFamily: 'Inter_500Medium',
    fontSize: 10.5,
    color: '#9A9EBF',
    letterSpacing: 0.2,
    includeFontPadding: false,
  },
  conditionRow: {
    marginTop: 6,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  conditionChip: {
    paddingHorizontal: 7,
    paddingVertical: 2,
    borderRadius: 5,
    backgroundColor: '#E2F1E7',
  },
  conditionText: {
    fontFamily: 'Inter_800ExtraBold',
    fontSize: 9.5,
    fontWeight: '800',
    color: '#2A7A4E',
    letterSpacing: 0.5,
    includeFontPadding: false,
  },
  conditionDesc: {
    fontFamily: 'Inter_400Regular',
    fontSize: 10,
    color: '#6B7080',
    includeFontPadding: false,
  },
  cta: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    paddingHorizontal: 14,
    paddingVertical: 12,
    borderRadius: 9999,
  },
  ctaLabel: {
    fontFamily: 'Inter_800ExtraBold',
    fontSize: ms(12),
    fontWeight: '800',
    color: '#FFFFFF',
    letterSpacing: 0.6,
    textTransform: 'uppercase',
    includeFontPadding: false,
  },
});

export default OfferDetailCard;
