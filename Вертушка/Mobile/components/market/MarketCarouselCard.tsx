/**
 * MarketCarouselCard — карточка пластинки в горизонтальной витрине магазина.
 *
 * Геометрия по дизайну: 132dp ширина (108dp обложка опционально). Мета-строка:
 * «2024 · LP · ◉ 4 990 ₽» через MiniPriceBadge.
 *
 * Используется в StoreCarousel. Текст белый/полупрозрачный — рендерится
 * поверх market-фона.
 *
 * Источник: record-card.jsx variant 'carousel' из Design Claude handoff
 * + docs/plans/market/MARKET_AND_PRICE_DRAWER.md §1.9.
 */
import React from 'react';
import {
  PixelRatio,
  Pressable,
  StyleSheet,
  Text,
  View,
  type StyleProp,
  type ViewStyle,
} from 'react-native';
import { Image } from 'expo-image';

import { sizedCoverUrl } from '../../lib/api';
import { useCoverSource } from '../../lib/coverRetry';

import MiniPriceBadge from '../MiniPriceBadge';
import { ms } from '../../lib/responsive';

export interface MarketCarouselCardData {
  /** Уникальный ID (record_id из БД). */
  id: string;
  artist: string;
  title: string;
  year?: number | null;
  /** Нормализованный формат: 'LP' / '2xLP' / 'CD' / 'Cassette' / 'Box Set' / etc. */
  format?: string | null;
  /** URL обложки (records.cover_image_url, либо image_url из raw_payload листинга). */
  coverUrl?: string | null;
  /** Минимальная цена среди листингов в этом магазине для этого release'а. */
  priceRub: number;
}

interface MarketCarouselCardProps {
  data: MarketCarouselCardData;
  width?: number;
  onPress?: () => void;
  style?: StyleProp<ViewStyle>;
}

export function MarketCarouselCard({
  data,
  width = 132,
  onPress,
  style,
}: MarketCarouselCardProps) {
  // Нарезка под фактический слот вместо мастера. Карусель рисует плитку в
  // 132pt, а мост отдавал мастер 1000px — замер 15.09.2026: 331 399 байт
  // против 28 806 у ступени 320. Десять плиток ряда — 3.3 МБ вместо 290 КБ.
  const imageUrl = sizedCoverUrl(
    data.coverUrl ?? undefined,
    Math.ceil(width * PixelRatio.get()),
  );
  // Общий ретрай вместо самодельного. Прежний дописывал `?r=N` прямо в URI, и
  // для клиента это была ДРУГАЯ картинка: дисковый кэш дробился, а успешный
  // повтор не переиспользовался. Хук держит cacheKey исходным и умеет откат
  // на прямой внешний URL.
  const cover = useCoverSource(imageUrl, data.coverUrl ?? undefined);
  const showImage = !!cover.source;

  const content = (
    <View style={[{ width }, style]}>
      <View style={[styles.coverWrap, { width, height: width }]}>
        {showImage ? (
          <Image
            source={cover.source}
            style={styles.cover}
            contentFit="cover"
            transition={120}
            cachePolicy="memory-disk"
            onLoad={cover.onLoad}
            onError={cover.onError}
          />
        ) : (
          <View style={[styles.cover, styles.coverPlaceholder]} />
        )}
      </View>
      <View style={styles.textBlock}>
        <Text style={styles.artist} numberOfLines={1}>
          {data.artist.toUpperCase()}
        </Text>
        <Text style={styles.title} numberOfLines={1}>
          {data.title}
        </Text>
        <View style={styles.metaRow}>
          <Text style={styles.meta} numberOfLines={1}>
            {data.year ? `${data.year}` : ''}
            {data.year && data.format ? ' · ' : ''}
            {data.format || ''}
          </Text>
          {(data.year || data.format) && (
            <View style={styles.metaDot} />
          )}
          <MiniPriceBadge price={data.priceRub} size={10} color="#FFFFFF" />
        </View>
      </View>
    </View>
  );

  if (onPress) {
    return (
      <Pressable
        onPress={onPress}
        accessibilityRole="button"
        accessibilityLabel={`${data.artist} — ${data.title}, ${data.priceRub} рублей`}
      >
        {content}
      </Pressable>
    );
  }
  return content;
}

const styles = StyleSheet.create({
  coverWrap: {
    borderRadius: 12,
    overflow: 'hidden',
    backgroundColor: 'rgba(255,255,255,0.06)',
    // Тень глубже чем у обычной карточки — мы на тёмном фоне.
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.30,
    shadowRadius: 18,
    elevation: 6,
  },
  cover: {
    width: '100%',
    height: '100%',
  },
  coverPlaceholder: {
    backgroundColor: 'rgba(255,255,255,0.10)',
  },
  textBlock: {
    marginTop: 8,
  },
  artist: {
    fontFamily: 'Inter_600SemiBold',
    fontSize: 9,
    fontWeight: '600',
    color: 'rgba(255,255,255,0.65)',
    letterSpacing: 0.3,
    marginBottom: 2,
    includeFontPadding: false,
  },
  title: {
    fontFamily: 'Inter_700Bold',
    fontSize: ms(11.5),
    fontWeight: '700',
    color: '#FFFFFF',
    lineHeight: ms(14),
    marginBottom: 4,
    includeFontPadding: false,
  },
  metaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    // Ограничиваем строку шириной карточки — иначе длинный формат + цена
    // переполняют контейнер и наезжают на соседнюю карточку карусели.
    overflow: 'hidden',
  },
  meta: {
    fontFamily: 'Inter_400Regular',
    fontSize: 10,
    color: 'rgba(255,255,255,0.55)',
    includeFontPadding: false,
    // Год·формат ужимается с многоточием, цена остаётся целой.
    flexShrink: 1,
  },
  metaDot: {
    width: 2,
    height: 2,
    borderRadius: 1,
    backgroundColor: 'rgba(255,255,255,0.40)',
  },
});

export default MarketCarouselCard;
