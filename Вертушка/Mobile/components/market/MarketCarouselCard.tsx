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
 * + docs/plans/MARKET_AND_PRICE_DRAWER.md §1.9.
 */
import React, { useEffect, useRef, useState } from 'react';
import {
  Image,
  Pressable,
  StyleSheet,
  Text,
  View,
  type StyleProp,
  type ViewStyle,
} from 'react-native';

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

// Один отложенный ретрай: первый запрос `/covers/{id}.jpg` бьёт в nginx
// @covers_fallback → 302 + фоновое зеркалирование. Повтор через 3с обычно
// попадает уже в готовый локальный файл. После — плейсхолдер.
const RETRY_DELAY_MS = 3000;

export function MarketCarouselCard({
  data,
  width = 132,
  onPress,
  style,
}: MarketCarouselCardProps) {
  const [failed, setFailed] = useState(false);
  const [retry, setRetry] = useState(0);
  const retriedRef = useRef(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    // Новый URL — сбрасываем состояние ретрая.
    retriedRef.current = false;
    setFailed(false);
    setRetry(0);
  }, [data.coverUrl]);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const handleError = () => {
    if (!retriedRef.current) {
      retriedRef.current = true;
      timerRef.current = setTimeout(() => setRetry((n) => n + 1), RETRY_DELAY_MS);
      return;
    }
    setFailed(true);
  };

  const showImage = data.coverUrl && !failed;
  const uri = retry > 0 ? `${data.coverUrl}?r=${retry}` : data.coverUrl;

  const content = (
    <View style={[{ width }, style]}>
      <View style={[styles.coverWrap, { width, height: width }]}>
        {showImage ? (
          <Image
            source={{ uri: uri as string }}
            style={styles.cover}
            resizeMode="cover"
            onError={handleError}
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
