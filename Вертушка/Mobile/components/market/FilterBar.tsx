/**
 * FilterBar — «аккордеон» фильтров Маркета (заменяет FormatChips).
 *
 * Свёрнуто: горизонтальный ряд категорий [Формат] [Жанр] [Особенности] со
 * счётчиками активного + кнопка «Сбросить» (когда есть активные). Тап по
 * категории разворачивает ЕЁ: соседи скрываются, вместо них — опции категории
 * (скроллятся вбок), слева «✕» для сворачивания. Формат — одиночный выбор,
 * Жанр/Особенности — мультивыбор.
 *
 * Плавность «общее ↔ частное»: Reanimated layout-анимации — LinearTransition на
 * ряду (сохранившиеся чипы плавно переезжают), FadeIn.delay(i*…)/FadeOut на
 * входящих/уходящих (staggered появление опций).
 *
 * Data-driven: жанры и особенности приходят из /market/facets (только те, что
 * реально в наличии, со счётчиками). Если у категории нет опций — не рисуем её.
 */
import React, { useMemo, useState } from 'react';
import {
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
  type StyleProp,
  type ViewStyle,
} from 'react-native';
import Animated, { FadeIn, FadeOut, LinearTransition } from 'react-native-reanimated';
import { LinearGradient } from 'expo-linear-gradient';

import { Icon, type IconName } from '../ui/Icon';
import { Gradients, MarketPalette } from '../../constants/theme';
import type {
  MarketFilters,
  MarketFacetsResponse,
  MarketFormatFilter,
} from '../../lib/types';
import { EMPTY_MARKET_FILTERS, hasActiveFilters } from '../../lib/types';

type CatKey = 'format' | 'genre' | 'feature';

interface Category {
  key: CatKey;
  label: string;
  icon: IconName;
  multi: boolean;
  options: { key: string; label: string }[];
}

const FORMAT_OPTIONS: { key: MarketFormatFilter | 'all'; label: string }[] = [
  { key: 'all', label: 'Все' },
  { key: 'vinyl', label: 'Винил' },
  { key: 'cd', label: 'CD' },
  { key: 'cassette', label: 'Кассеты' },
];

const DUR_MORPH = 220;

interface FilterBarProps {
  filters: MarketFilters;
  onChange: (next: MarketFilters) => void;
  /** Доступные жанры/особенности из /market/facets. null → ещё не загружено. */
  facets: MarketFacetsResponse | null;
  style?: StyleProp<ViewStyle>;
}

export function FilterBar({ filters, onChange, facets, style }: FilterBarProps) {
  const [expanded, setExpanded] = useState<CatKey | null>(null);

  // Категории строим из фасетов: формат всегда, жанр/особенности — только если
  // есть что показать (иначе пустой чип, ведущий в никуда).
  const categories = useMemo<Category[]>(() => {
    const cats: Category[] = [
      { key: 'format', label: 'Формат', icon: 'disc', multi: false, options: FORMAT_OPTIONS as any },
    ];
    if (facets?.genres.length) {
      cats.push({
        key: 'genre',
        label: 'Жанр',
        icon: 'music-notes',
        multi: true,
        options: facets.genres.map((g) => ({ key: g.key, label: g.label })),
      });
    }
    if (facets?.features.length) {
      cats.push({
        key: 'feature',
        label: 'Особенности',
        icon: 'sparkle',
        multi: true,
        options: facets.features.map((f) => ({ key: f.key, label: f.label })),
      });
    }
    return cats;
  }, [facets]);

  const countFor = (key: CatKey): number => {
    if (key === 'format') return filters.format !== 'all' ? 1 : 0;
    if (key === 'genre') return filters.genres.length;
    return filters.features.length;
  };

  const isOptionActive = (cat: Category, optKey: string): boolean => {
    if (cat.key === 'format') return filters.format === optKey;
    if (cat.key === 'genre') return filters.genres.includes(optKey);
    return filters.features.includes(optKey);
  };

  const toggleOption = (cat: Category, optKey: string) => {
    if (cat.key === 'format') {
      onChange({ ...filters, format: optKey as MarketFormatFilter | 'all' });
      return;
    }
    const field = cat.key === 'genre' ? 'genres' : 'features';
    const cur = filters[field];
    const next = cur.includes(optKey)
      ? cur.filter((k) => k !== optKey)
      : [...cur, optKey];
    onChange({ ...filters, [field]: next });
  };

  const activeCat = expanded ? categories.find((c) => c.key === expanded) ?? null : null;

  return (
    <ScrollView
      horizontal
      showsHorizontalScrollIndicator={false}
      contentContainerStyle={styles.row}
      style={[styles.scroll, style]}
      keyboardShouldPersistTaps="handled"
    >
      {activeCat ? (
        <>
          <Chip
            key="__back"
            label={activeCat.label}
            icon={activeCat.icon}
            variant="back"
            onPress={() => setExpanded(null)}
            index={0}
          />
          <Animated.View
            key="__divider"
            style={styles.divider}
            entering={FadeIn.duration(140)}
            exiting={FadeOut.duration(100)}
          />
          {activeCat.options.map((opt, i) => (
            <Chip
              key={`${activeCat.key}:${opt.key}`}
              label={opt.label}
              active={isOptionActive(activeCat, opt.key)}
              onPress={() => toggleOption(activeCat, opt.key)}
              index={i + 1}
            />
          ))}
        </>
      ) : (
        <>
          {categories.map((cat, i) => {
            const n = countFor(cat.key);
            return (
              <Chip
                key={cat.key}
                label={cat.label}
                icon={cat.icon}
                active={n > 0}
                badge={n > 0 ? n : undefined}
                chevron
                onPress={() => setExpanded(cat.key)}
                index={i}
              />
            );
          })}
          {hasActiveFilters(filters) && (
            <Chip
              key="__reset"
              label="Сбросить"
              icon="x"
              variant="reset"
              onPress={() => onChange(EMPTY_MARKET_FILTERS)}
              index={categories.length}
            />
          )}
        </>
      )}
    </ScrollView>
  );
}

// ────────────────────────────────────────────────────────────────────────

interface ChipProps {
  label: string;
  icon?: IconName;
  active?: boolean;
  badge?: number;
  chevron?: boolean;
  variant?: 'default' | 'back' | 'reset';
  onPress: () => void;
  /** Порядковый индекс — для staggered появления при морфе. */
  index: number;
}

function Chip({ label, icon, active, badge, chevron, variant = 'default', onPress, index }: ChipProps) {
  const isBack = variant === 'back';
  const isReset = variant === 'reset';
  const showEmber = active && !isBack && !isReset;

  const wrapExtra =
    isBack ? styles.chipBack : isReset ? styles.chipReset : active ? null : styles.chipInactive;

  return (
    <Animated.View
      entering={FadeIn.duration(160).delay(index * 35)}
      exiting={FadeOut.duration(120)}
      layout={LinearTransition.duration(DUR_MORPH)}
    >
      <Pressable onPress={onPress} hitSlop={6} style={[styles.chip, wrapExtra]}>
        {showEmber && (
          <LinearGradient
            colors={Gradients.hotStock}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 1 }}
            style={[StyleSheet.absoluteFill, { borderRadius: 9999 }]}
          />
        )}
        {icon ? (
          <Icon
            name={icon}
            size={14}
            color={showEmber || isBack ? 'onBrand' : isReset ? 'secondary' : active ? 'onBrand' : 'secondary'}
            style={{ opacity: showEmber || isBack || active ? 1 : 0.75 }}
          />
        ) : null}
        <Text style={[styles.label, (showEmber || isBack) && styles.labelActive, isReset && styles.labelReset]}>
          {label}
        </Text>
        {badge !== undefined && (
          <View style={styles.badge}>
            <Text style={styles.badgeText}>{badge}</Text>
          </View>
        )}
        {chevron && (
          <Icon name="chevron-down" size={14} color={active ? 'onBrand' : 'secondary'} style={{ opacity: 0.85 }} />
        )}
        {isBack && <Icon name="x" size={14} color="onBrand" style={{ opacity: 0.9 }} />}
      </Pressable>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  scroll: {
    flexGrow: 0,
  },
  row: {
    paddingHorizontal: 20,
    paddingTop: 14,
    paddingBottom: 12,
    gap: 8,
    flexDirection: 'row',
    alignItems: 'center',
  },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 9999,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: 'transparent',
  },
  chipInactive: {
    backgroundColor: 'rgba(255,255,255,0.06)',
    borderColor: MarketPalette.chrome.border,
  },
  chipBack: {
    backgroundColor: 'rgba(255,255,255,0.12)',
    borderColor: 'rgba(255,255,255,0.2)',
  },
  chipReset: {
    backgroundColor: 'transparent',
    borderColor: 'rgba(255,255,255,0.14)',
  },
  divider: {
    width: 1,
    height: 22,
    backgroundColor: 'rgba(255,255,255,0.12)',
    marginHorizontal: 2,
    alignSelf: 'center',
  },
  label: {
    fontFamily: 'Inter_600SemiBold',
    fontSize: 12.5,
    fontWeight: '600',
    color: 'rgba(255,255,255,0.78)',
    includeFontPadding: false,
  },
  labelActive: {
    color: '#FFFFFF',
    fontFamily: 'Inter_700Bold',
    fontWeight: '700',
  },
  labelReset: {
    color: 'rgba(255,255,255,0.6)',
  },
  badge: {
    minWidth: 16,
    height: 16,
    paddingHorizontal: 4,
    borderRadius: 9999,
    backgroundColor: 'rgba(255,255,255,0.9)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  badgeText: {
    fontFamily: 'Inter_700Bold',
    fontSize: 10.5,
    fontWeight: '700',
    color: '#B5401C',
    includeFontPadding: false,
  },
});

export default FilterBar;
