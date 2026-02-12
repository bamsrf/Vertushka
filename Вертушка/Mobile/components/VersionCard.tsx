/**
 * Карточка версии (издания) мастер-релиза
 */
import React from 'react';
import {
  View,
  Text,
  Image,
  StyleSheet,
  TouchableOpacity,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Typography, BorderRadius, Shadows, Spacing } from '../constants/theme';
import { MasterVersion } from '../lib/types';

interface VersionCardProps {
  version: MasterVersion;
  onPress?: () => void;
}

export function VersionCard({ version, onPress }: VersionCardProps) {
  const imageUrl = version.thumb_image_url;

  return (
    <TouchableOpacity
      style={[styles.container, Shadows.sm]}
      onPress={onPress}
      activeOpacity={0.9}
      disabled={!onPress}
    >
      {/* Обложка */}
      <View style={styles.imageContainer}>
        {imageUrl ? (
          <Image
            source={{ uri: imageUrl }}
            style={styles.image}
            resizeMode="cover"
          />
        ) : (
          <View style={styles.placeholderImage}>
            <Ionicons name="disc-outline" size={32} color={Colors.textMuted} />
          </View>
        )}
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
                <Ionicons name="location-outline" size={14} color={Colors.textMuted} />
                <Text style={styles.metaText}>{version.country}</Text>
              </View>
            )}
            {!!version.year && (
              <View style={styles.metaRow}>
                <Ionicons name="calendar-outline" size={14} color={Colors.textMuted} />
                <Text style={styles.metaText}>{version.year}</Text>
              </View>
            )}
          </View>
        )}

        {version.label && (
          <View style={styles.metaRow}>
            <Ionicons name="business-outline" size={14} color={Colors.textMuted} />
            <Text style={styles.metaText} numberOfLines={1}>
              {version.label}
              {version.catalog_number && ` • ${version.catalog_number}`}
            </Text>
          </View>
        )}

        {version.format && (
          <View style={styles.metaRow}>
            <Ionicons name="disc" size={14} color={Colors.textMuted} />
            <Text style={styles.metaText}>{version.format}</Text>
          </View>
        )}
      </View>

      {/* Иконка перехода */}
      {onPress && (
        <View style={styles.chevron}>
          <Ionicons name="chevron-forward" size={20} color={Colors.textMuted} />
        </View>
      )}
    </TouchableOpacity>
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
});

export default VersionCard;
