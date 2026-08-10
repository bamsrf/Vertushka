/**
 * StoreLogo — лого магазина с monogram-fallback.
 *
 * Используется:
 *   - В header витрины магазина в Маркете (44×44, MARKET_AND_PRICE_DRAWER.md §1.9)
 *   - На экране витрины одного магазина `/market/store/[slug]` (64×64, §1.12)
 *   - В bottom-sheet деталей оффера (24×24, §2.3 OfferDetailCard)
 *
 * Fallback: если PNG отсутствует (юзер ещё не положил в assets/store-logos/) —
 * рендерим monogram-бейдж из первой буквы названия магазина в круге
 * `brand.cobaltDeep`. UI не ломается до момента когда ассеты появятся.
 *
 * Источник: store-logo.jsx из Design Claude handoff + MARKET_AND_PRICE_DRAWER.md §1.14.
 */
import React from 'react';
import {
  Image,
  StyleSheet,
  Text,
  View,
  type ImageSourcePropType,
  type StyleProp,
  type ViewStyle,
} from 'react-native';

// Реестр магазинов: slug → метаданные + (опционально) bundled-asset.
// Когда юзер положит PNG в Mobile/assets/store-logos/{slug}.png —
// раскомментировать соответствующую `require(...)` строку.
//
// ВАЖНО: require должен быть статическим (Metro bundler не умеет динамические
// require), поэтому каждый магазин — отдельная строка.
const STORE_REGISTRY: Record<string, {
  name: string;
  monogram: string;
  bgColor: string;            // фон под лого (для логотипов с прозрачностью)
  logoSource?: ImageSourcePropType;
}> = {
  korobkavinyla: {
    name: 'Коробка Винила',
    monogram: 'К',
    bgColor: '#E85A2A',
    logoSource: require('../../assets/store-logos/korobkavinyla.png'),
  },
  plastinka_com: {
    name: 'Plastinka.com',
    monogram: 'P',
    bgColor: '#FFFFFF',
    logoSource: require('../../assets/store-logos/plastinka_com.png'),
  },
  vinyl_ru: {
    name: 'Vinyl.ru',
    monogram: 'V',
    bgColor: '#000000',
    logoSource: require('../../assets/store-logos/vinyl_ru.png'),
  },
  stoprobotvinyl: {
    name: 'Stoprobot Vinyl',
    monogram: 'S',
    bgColor: '#1B1B1B',
    logoSource: require('../../assets/store-logos/stoprobotvinyl.png'),
  },
  found: {
    name: 'Found',
    monogram: 'F',
    bgColor: '#FFFFFF',
    logoSource: require('../../assets/store-logos/found.png'),
  },
  doctorhead: {
    name: 'Dr.Head',
    monogram: 'D',
    bgColor: '#01ADFF',
    logoSource: require('../../assets/store-logos/doctorhead.png'),
  },
  skifmusic: {
    name: 'Скифмьюзик',
    monogram: 'С',
    bgColor: '#F5B335',
    logoSource: require('../../assets/store-logos/skifmusic.png'),
  },
  rotaryrecords: {
    name: 'Rotary Records',
    monogram: 'R',
    bgColor: '#FFFFFF',
    logoSource: require('../../assets/store-logos/rotaryrecords.png'),
  },
};

interface StoreLogoProps {
  /** Slug магазина (соответствует `stores.slug` в БД и parser_class в коде). */
  slug: string;
  /** Размер квадрата в pt. Default 44. */
  size?: number;
  /**
   * Border-radius. Default size * 0.18 (~8dp для 44, ~12dp для 64) —
   * мягкий скруглённый квадрат, как у мерч-логотипов брендов.
   */
  radius?: number;
  style?: StyleProp<ViewStyle>;
  /** Override имени магазина (если slug нет в реестре). Для unknown-fallback. */
  fallbackName?: string;
}

export function StoreLogo({
  slug,
  size = 44,
  radius,
  style,
  fallbackName,
}: StoreLogoProps) {
  const info = STORE_REGISTRY[slug];
  const resolvedRadius = radius ?? Math.round(size * 0.18);

  // Unknown slug — generic «?»-monogram в нейтральном cobaltDeep.
  if (!info) {
    return (
      <View
        style={[
          styles.container,
          {
            width: size,
            height: size,
            borderRadius: resolvedRadius,
            backgroundColor: '#11225C',
          },
          style,
        ]}
        accessibilityRole="image"
        accessibilityLabel={fallbackName || 'Неизвестный магазин'}
      >
        <Text style={[styles.monogram, { fontSize: size * 0.42 }]}>
          {fallbackName?.[0]?.toUpperCase() ?? '?'}
        </Text>
      </View>
    );
  }

  // Bundled-asset есть — рендерим Image, иначе monogram-fallback в bgColor.
  if (info.logoSource) {
    return (
      <View
        style={[
          styles.container,
          {
            width: size,
            height: size,
            borderRadius: resolvedRadius,
            backgroundColor: info.bgColor,
            overflow: 'hidden',
          },
          style,
        ]}
        accessibilityRole="image"
        accessibilityLabel={info.name}
      >
        <Image
          source={info.logoSource}
          style={{ width: '100%', height: '100%' }}
          resizeMode="contain"
        />
      </View>
    );
  }

  return (
    <View
      style={[
        styles.container,
        {
          width: size,
          height: size,
          borderRadius: resolvedRadius,
          backgroundColor: info.bgColor,
        },
        style,
      ]}
      accessibilityRole="image"
      accessibilityLabel={info.name}
    >
      <Text
        style={[
          styles.monogram,
          {
            fontSize: size * 0.42,
            // На светлом bg (Plastinka.com) — тёмный текст, на тёмном — белый.
            color: isLightBg(info.bgColor) ? '#0E121C' : '#FFFFFF',
          },
        ]}
      >
        {info.monogram}
      </Text>
    </View>
  );
}

// Простая эвристика: если bg «светлее» средне-серого — текст тёмный.
function isLightBg(hex: string): boolean {
  const h = hex.replace('#', '');
  if (h.length < 6) return false;
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  // YIQ luma — стандартный пороговый алгоритм для контраста.
  const luma = (r * 299 + g * 587 + b * 114) / 1000;
  return luma > 160;
}

const styles = StyleSheet.create({
  container: {
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
    // Лёгкая тень + внутренняя стеклянная hairline — даёт «брендовое»
    // ощущение «вырезанной марки», даже когда внутри monogram.
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.18,
    shadowRadius: 8,
    elevation: 3,
  },
  monogram: {
    fontFamily: 'Inter_800ExtraBold',
    fontWeight: '800',
    color: '#FFFFFF',
    includeFontPadding: false,
  },
});

/** Хелпер: достать display-имя магазина по slug (для подписей в карусели). */
export function getStoreName(slug: string): string | undefined {
  return STORE_REGISTRY[slug]?.name;
}

export default StoreLogo;
