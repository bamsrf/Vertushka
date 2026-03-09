/**
 * Экран оценки стоимости коллекции
 * Анимированная шкала + бегущие цифры + самая дорогая пластинка
 */
import { useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  ActivityIndicator,
} from 'react-native';
import { Image } from 'expo-image';
import { useRouter } from 'expo-router';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withTiming,
  withDelay,
  withRepeat,
  useDerivedValue,
  Easing,
  runOnJS,
} from 'react-native-reanimated';
import { Header } from '../../components/Header';
import { useCollectionStore } from '../../lib/store';
import { CollectionItem } from '../../lib/types';
import { Colors, Typography, Spacing, BorderRadius, Shadows } from '../../constants/theme';


function formatRub(value: number): string {
  return Math.round(value).toLocaleString('ru-RU');
}

function formatUsd(value: number): string {
  return `$${value.toFixed(0)}`;
}

function AnimatedValue({ targetValue, prefix = '', suffix = '' }: {
  targetValue: number;
  prefix?: string;
  suffix?: string;
}) {
  const progress = useSharedValue(0);
  const displayValue = useDerivedValue(() => {
    return Math.round(progress.value * targetValue);
  });

  useEffect(() => {
    progress.value = 0;
    progress.value = withDelay(
      300,
      withTiming(1, { duration: 2000, easing: Easing.out(Easing.cubic) })
    );
  }, [targetValue]);

  // We need to use a state-based approach since AnimatedText isn't available
  const [display, setDisplay] = React.useState('0');

  useDerivedValue(() => {
    const val = Math.round(progress.value * targetValue);
    runOnJS(setDisplay)(val.toLocaleString('ru-RU'));
  });

  return (
    <Text style={styles.animatedValueText}>
      {prefix}{display}{suffix}
    </Text>
  );
}

import React from 'react';

export default function CollectionValueScreen() {
  const router = useRouter();
  const { stats, isLoadingStats, fetchStats, collectionItems, defaultCollection } = useCollectionStore();

  const barWidth = useSharedValue(0);
  const gradientShift = useSharedValue(0);

  useEffect(() => {
    fetchStats();
    gradientShift.value = 0;
    gradientShift.value = withRepeat(
      withTiming(1, { duration: 4000, easing: Easing.inOut(Easing.ease) }),
      -1,
      true,
    );
  }, []);

  useEffect(() => {
    if (stats && stats.total_estimated_value_rub) {
      barWidth.value = 0;
      barWidth.value = withDelay(
        200,
        withTiming(1, { duration: 2000, easing: Easing.out(Easing.cubic) })
      );
    }
  }, [stats]);

  const barAnimatedStyle = useAnimatedStyle(() => ({
    width: `${barWidth.value * 100}%`,
  }));

  const gradientSlideStyle = useAnimatedStyle(() => ({
    transform: [{ translateX: -gradientShift.value * 200 }],
  }));


  // Сортируем items по цене для списка
  const sortedByPrice = React.useMemo(() => {
    return [...collectionItems]
      .filter(item => item.estimated_price_rub)
      .sort((a, b) => (b.estimated_price_rub || 0) - (a.estimated_price_rub || 0));
  }, [collectionItems]);

  const renderItem = useCallback(({ item, index }: { item: CollectionItem; index: number }) => {
    const record = item.record;
    return (
      <TouchableOpacity
        style={styles.listItem}
        onPress={() => router.push(`/record/${record.id}`)}
        activeOpacity={0.7}
      >
        <Text style={styles.listRank}>#{index + 1}</Text>
        <Image
          source={record.thumb_image_url || record.cover_image_url}
          style={styles.listThumb}
          contentFit="cover"
          cachePolicy="disk"
        />
        <View style={styles.listInfo}>
          <Text style={styles.listTitle} numberOfLines={1}>{record.title}</Text>
          <Text style={styles.listArtist} numberOfLines={1}>{record.artist}</Text>
        </View>
        <Text style={styles.listPrice}>
          ~{formatRub(item.estimated_price_rub || 0)} ₽
        </Text>
      </TouchableOpacity>
    );
  }, []);

  if (isLoadingStats) {
    return (
      <View style={styles.container}>
        <Header title="Оценка стоимости" showBack showProfile={false} />
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={Colors.royalBlue} />
          <Text style={styles.loadingText}>Подсчитываем стоимость...</Text>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <Header title="Оценка стоимости" showBack showProfile={false} />

      <FlatList
        data={sortedByPrice}
        keyExtractor={(item) => item.id}
        renderItem={renderItem}
        contentContainerStyle={styles.listContent}
        ListHeaderComponent={
          <View>
            {/* Основной блок стоимости */}
            <View style={styles.valueCard}>
              <View style={styles.valueGradient}>
                <Animated.View style={[styles.gradientSlider, gradientSlideStyle]}>
                  <LinearGradient
                    colors={['#2D3E8F', '#4A6FDB', '#6B5EC2', '#5B3FA0', '#8B4DA8', '#C75895', '#8B4DA8', '#5B3FA0']}
                    start={{ x: 0, y: 0 }}
                    end={{ x: 1, y: 0.5 }}
                    style={StyleSheet.absoluteFill}
                  />
                </Animated.View>
                <Text style={styles.valueLabel}>Примерная стоимость</Text>

                {/* Анимированная шкала */}
                <View style={styles.barContainer}>
                  <Animated.View style={[styles.barFill, barAnimatedStyle]}>
                    <LinearGradient
                      colors={['rgba(255,255,255,0.9)', 'rgba(255,255,255,0.6)']}
                      start={{ x: 0, y: 0 }}
                      end={{ x: 1, y: 0 }}
                      style={styles.barGradient}
                    />
                  </Animated.View>
                </View>

                {/* Бегущие цифры */}
                <AnimatedValue
                  targetValue={stats?.total_estimated_value_rub || 0}
                  prefix="~"
                  suffix=" ₽"
                />

                {/* Справочно в USD */}
                {stats?.total_estimated_value_median && (
                  <Text style={styles.usdValue}>
                    {formatUsd(stats.total_estimated_value_median)} на Discogs
                  </Text>
                )}
              </View>
            </View>

            {/* Детали */}
            <View style={styles.detailsRow}>
              <View style={styles.detailItem}>
                <Text style={styles.detailLabel}>Курс ЦБ</Text>
                <Text style={styles.detailValue}>
                  {stats?.usd_rub_rate ? `${stats.usd_rub_rate.toFixed(2)} ₽/$` : '—'}
                </Text>
              </View>
              <View style={styles.detailItem}>
                <Text style={styles.detailLabel}>Наценка РФ</Text>
                <Text style={styles.detailValue}>×{stats?.ru_markup || 1.7}</Text>
              </View>
              <View style={styles.detailItem}>
                <Text style={styles.detailLabel}>Оценено</Text>
                <Text style={styles.detailValue}>
                  {stats?.records_with_price || 0} из {stats?.total_records || 0}
                </Text>
              </View>
            </View>

            {/* Самая дорогая */}
            {stats?.most_expensive && (
              <TouchableOpacity
                style={styles.expensiveCard}
                onPress={() => router.push(`/record/${stats.most_expensive!.id}`)}
                activeOpacity={0.7}
              >
                <View style={styles.expensiveBadge}>
                  <Ionicons name="trophy" size={14} color={Colors.warning} />
                  <Text style={styles.expensiveBadgeText}>Самая дорогая</Text>
                </View>
                <View style={styles.expensiveContent}>
                  <Image
                    source={stats.most_expensive.thumb_image_url || stats.most_expensive.cover_image_url}
                    style={styles.expensiveImage}
                    contentFit="cover"
                    cachePolicy="disk"
                  />
                  <View style={styles.expensiveInfo}>
                    <Text style={styles.expensiveTitle} numberOfLines={1}>
                      {stats.most_expensive.title}
                    </Text>
                    <Text style={styles.expensiveArtist} numberOfLines={1}>
                      {stats.most_expensive.artist}
                    </Text>
                    <Text style={styles.expensivePrice}>
                      ~{formatRub(stats.most_expensive_price_rub || 0)} ₽
                    </Text>
                  </View>
                  <Ionicons name="chevron-forward" size={20} color={Colors.textMuted} />
                </View>
              </TouchableOpacity>
            )}

            {/* Заголовок списка */}
            {sortedByPrice.length > 0 && (
              <Text style={styles.sectionTitle}>По стоимости</Text>
            )}
          </View>
        }
        ListEmptyComponent={
          <View style={styles.emptyContainer}>
            <Ionicons name="pricetag-outline" size={48} color={Colors.textMuted} />
            <Text style={styles.emptyText}>
              Нет пластинок с оценкой стоимости
            </Text>
          </View>
        }
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    gap: Spacing.md,
  },
  loadingText: {
    ...Typography.body,
    color: Colors.textSecondary,
  },
  listContent: {
    padding: Spacing.md,
    paddingBottom: 100,
  },

  // Value card
  valueCard: {
    borderRadius: BorderRadius.lg,
    overflow: 'hidden',
    marginBottom: Spacing.md,
    ...Shadows.lg,
  },
  valueGradient: {
    padding: Spacing.lg,
    alignItems: 'center',
    overflow: 'hidden',
  },
  gradientSlider: {
    position: 'absolute',
    top: 0,
    bottom: 0,
    left: -200,
    right: -200,
  },
  valueLabel: {
    ...Typography.bodySmall,
    color: 'rgba(255,255,255,0.8)',
    marginBottom: Spacing.md,
  },
  barContainer: {
    width: '100%',
    height: 8,
    borderRadius: 4,
    backgroundColor: 'rgba(255,255,255,0.2)',
    marginBottom: Spacing.lg,
    overflow: 'hidden',
  },
  barFill: {
    height: '100%',
    borderRadius: 4,
    overflow: 'hidden',
  },
  barGradient: {
    flex: 1,
    borderRadius: 4,
  },
  animatedValueText: {
    fontSize: 40,
    fontFamily: 'Inter_800ExtraBold',
    color: '#FFFFFF',
    letterSpacing: -1,
    lineHeight: 48,
  },
  usdValue: {
    ...Typography.bodySmall,
    color: 'rgba(255,255,255,0.7)',
    marginTop: Spacing.xs,
  },

  // Details row
  detailsRow: {
    flexDirection: 'row',
    gap: Spacing.sm,
    marginBottom: Spacing.lg,
  },
  detailItem: {
    flex: 1,
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.sm,
    padding: Spacing.md,
    alignItems: 'center',
  },
  detailLabel: {
    ...Typography.caption,
    color: Colors.textMuted,
    marginBottom: Spacing.xs,
  },
  detailValue: {
    ...Typography.bodyBold,
    color: Colors.text,
  },

  // Most expensive card
  expensiveCard: {
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.md,
    padding: Spacing.md,
    marginBottom: Spacing.lg,
    ...Shadows.sm,
  },
  expensiveBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.xs,
    marginBottom: Spacing.sm,
  },
  expensiveBadgeText: {
    ...Typography.caption,
    color: Colors.warning,
    fontFamily: 'Inter_600SemiBold',
  },
  expensiveContent: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.md,
  },
  expensiveImage: {
    width: 56,
    height: 56,
    borderRadius: BorderRadius.sm,
    backgroundColor: Colors.surfaceHover,
  },
  expensiveInfo: {
    flex: 1,
  },
  expensiveTitle: {
    ...Typography.bodyBold,
    color: Colors.text,
  },
  expensiveArtist: {
    ...Typography.bodySmall,
    color: Colors.textSecondary,
  },
  expensivePrice: {
    ...Typography.bodyBold,
    color: Colors.royalBlue,
    marginTop: 2,
  },

  // Section
  sectionTitle: {
    ...Typography.h4,
    color: Colors.text,
    marginBottom: Spacing.md,
  },

  // List items
  listItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: Spacing.sm,
    gap: Spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: Colors.divider,
  },
  listRank: {
    ...Typography.bodyBold,
    color: Colors.textMuted,
    width: 30,
    textAlign: 'center',
  },
  listThumb: {
    width: 44,
    height: 44,
    borderRadius: 8,
    backgroundColor: Colors.surfaceHover,
  },
  listInfo: {
    flex: 1,
  },
  listTitle: {
    ...Typography.bodySmall,
    color: Colors.text,
    fontFamily: 'Inter_600SemiBold',
  },
  listArtist: {
    ...Typography.caption,
    color: Colors.textSecondary,
  },
  listPrice: {
    ...Typography.bodyBold,
    color: Colors.royalBlue,
  },

  // Empty
  emptyContainer: {
    alignItems: 'center',
    paddingVertical: Spacing.xxl,
    gap: Spacing.md,
  },
  emptyText: {
    ...Typography.body,
    color: Colors.textMuted,
    textAlign: 'center',
  },
});
