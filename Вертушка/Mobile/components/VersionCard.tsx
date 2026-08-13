/**
 * Карточка версии (издания) мастер-релиза
 */
import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
} from 'react-native';
import { Image } from 'expo-image';
import { Icon } from '@/components/ui';
import { Colors, Typography, BorderRadius, Shadows, Spacing } from '../constants/theme';
import { MasterVersion } from '../lib/types';
import { resolveMediaUrl, sizedCoverUrl } from '../lib/api';
import { RarityAura, TierCoverEffects, TierEdgeStrip, TierLabel, pickRarityTier } from './RarityAura';

interface VersionCardProps {
  version: MasterVersion;
  onPress?: () => void;
}

// Ноготь строки — 80×80pt (styles.imageContainer), на 3x это 240px ⇒ ступень 320.
// Раньше строка тянула мастер целиком: страница из 29 версий = 29×~84 КБ вместо
// 29×~15 КБ, причём ради картинки в 80 точек.
const ROW_COVER_PX = 80 * 3;

export function VersionCard({ version, onPress }: VersionCardProps) {
  const imageUrl = sizedCoverUrl(
    resolveMediaUrl(version.cover_image_url || version.thumb_image_url),
    ROW_COVER_PX,
  );
  const rarityTier = pickRarityTier(version, 'search');

  const inner = (
    <TouchableOpacity
      style={[styles.container, rarityTier ? styles.containerNoMargin : Shadows.sm]}
      onPress={onPress}
      activeOpacity={0.9}
      disabled={!onPress}
    >
      {/* Градиент-полоса тира на левом крае карточки */}
      <TierEdgeStrip tier={rarityTier} radius={BorderRadius.md} />

      {/* Обложка */}
      <View style={styles.imageContainer}>
        {imageUrl ? (
          <Image
            source={imageUrl}
            style={styles.image}
            contentFit="cover"
            cachePolicy="memory-disk"
          />
        ) : (
          <View style={styles.placeholderImage}>
            <Icon name="disc-outline" size={32} color={Colors.textMuted} />
          </View>
        )}
        <TierCoverEffects tier={rarityTier} radius={0} />
      </View>

      {/* Информация */}
      <View style={styles.info}>
        <Text style={styles.title} numberOfLines={1}>
          {version.title}
        </Text>

        {!!(version.country || version.year) && (
          <View style={styles.meta}>
            {!!version.country && (
              <View style={styles.metaRow}>
                <Icon name="location-outline" size={14} color={Colors.textMuted} />
                <Text style={styles.metaText}>{version.country}</Text>
              </View>
            )}
            {!!version.year && (
              <View style={styles.metaRow}>
                <Icon name="calendar-outline" size={14} color={Colors.textMuted} />
                <Text style={styles.metaText}>{version.year}</Text>
              </View>
            )}
          </View>
        )}

        {version.label && (
          <View style={styles.metaRow}>
            <Icon name="business-outline" size={14} color={Colors.textMuted} />
            <Text style={styles.metaText} numberOfLines={1}>
              {version.label}
              {version.catalog_number && ` • ${version.catalog_number}`}
            </Text>
          </View>
        )}

        {version.format && (
          <View style={styles.metaRow}>
            <Icon name="disc" size={14} color={Colors.textMuted} />
            <Text style={styles.metaText}>{version.format}</Text>
          </View>
        )}

        {rarityTier && (
          <View style={styles.metaRow}>
            <TierLabel tier={rarityTier} />
          </View>
        )}
      </View>

      {/* Иконка перехода */}
      {onPress && (
        <View style={styles.chevron}>
        </View>
      )}
    </TouchableOpacity>
  );

  if (!rarityTier) return inner;
  return (
    <RarityAura tier={rarityTier} radius={BorderRadius.md} style={styles.rarityWrap}>
      {inner}
    </RarityAura>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: Colors.background,
    borderRadius: BorderRadius.md,
    overflow: 'hidden',
    marginBottom: Spacing.sm,
    flexDirection: 'row',
    alignItems: 'center',
  },
  imageContainer: {
    width: 80,
    height: 80,
    backgroundColor: Colors.surface,
  },
  image: {
    width: '100%',
    height: '100%',
  },
  placeholderImage: {
    width: '100%',
    height: '100%',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: Colors.surface,
  },
  info: {
    flex: 1,
    padding: Spacing.sm,
    gap: Spacing.xs,
  },
  title: {
    ...Typography.bodySmall,
    fontWeight: '600',
    color: Colors.text,
  },
  meta: {
    flexDirection: 'row',
    gap: Spacing.sm,
  },
  metaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  metaText: {
    ...Typography.caption,
    color: Colors.textMuted,
  },
  chevron: {
    paddingRight: Spacing.sm,
  },
  containerNoMargin: {
    marginBottom: 0,
  },
  rarityWrap: {
    marginTop: 6,
    marginBottom: Spacing.md,
  },
});

export default VersionCard;
