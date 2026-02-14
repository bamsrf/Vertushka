/**
 * Карточка пластинки
 */
import React from 'react';
import {
  View,
  Text,
  Image,
  StyleSheet,
  TouchableOpacity,
  Dimensions,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Typography, BorderRadius, Shadows, Spacing } from '../constants/theme';
import { RecordSearchResult, VinylRecord, MasterSearchResult, ReleaseSearchResult } from '../lib/types';

const { width } = Dimensions.get('window');
const CARD_WIDTH = (width - Spacing.md * 3) / 2;

interface RecordCardProps {
  record: RecordSearchResult | VinylRecord | MasterSearchResult | ReleaseSearchResult;
  onPress?: () => void;
  onArtistPress?: (artistName: string) => void;
  onAddToCollection?: () => void;
  onAddToWishlist?: () => void;
  onRemove?: () => void;
  showActions?: boolean;
  size?: 'default' | 'large';
  isSelectionMode?: boolean;
  isSelected?: boolean;
  onToggleSelection?: () => void;
  isBooked?: boolean;
}

// Извлекает краткий формат из полной строки (первый значимый элемент)
function getShortFormat(format: string | undefined): string | undefined {
  if (!format) return undefined;

  // Разделяем по запятым и берём только первые 2-3 значимых элемента
  const parts = format.split(',').map(s => s.trim()).filter(Boolean);
  if (parts.length === 0) return undefined;

  // Основные типы носителей
  const mainFormats = ['Vinyl', 'CD', 'Cassette', 'DVD', 'Blu-ray', 'Box Set', 'LP', '7"', '12"', '10"'];
  // Важные дополнения
  const importantDetails = ['Album', 'Single', 'EP', 'Compilation', 'Limited Edition', 'Reissue', 'Remaster'];

  const result: string[] = [];

  // Добавляем основной формат (первый найденный)
  const mainFormat = parts.find(p => mainFormats.some(mf => p.includes(mf)));
  if (mainFormat) {
    result.push(mainFormat);
  } else if (parts[0]) {
    result.push(parts[0]);
  }

  // Добавляем одну важную деталь если есть
  const detail = parts.find(p => importantDetails.some(d => p.includes(d)) && !result.includes(p));
  if (detail && result.length < 2) {
    result.push(detail);
  }

  return result.join(', ') || parts[0];
}

export function RecordCard({
  record,
  onPress,
  onArtistPress,
  onAddToCollection,
  onAddToWishlist,
  onRemove,
  showActions = false,
  size = 'default',
  isSelectionMode = false,
  isSelected = false,
  onToggleSelection,
  isBooked = false,
}: RecordCardProps) {
  // Приоритет: cover_image_url для высокого качества, fallback на thumb
  const imageUrl = record.cover_image_url || record.thumb_image_url;
  const cardWidth = size === 'large' ? width - Spacing.md * 2 : CARD_WIDTH;
  const imageHeight = size === 'large' ? cardWidth * 0.8 : CARD_WIDTH;

  const handlePress = () => {
    if (isSelectionMode && onToggleSelection) {
      onToggleSelection();
    } else if (onPress) {
      onPress();
    }
  };

  return (
    <TouchableOpacity
      style={[
        styles.container,
        { width: cardWidth },
        Shadows.md,
        isSelectionMode && isSelected && styles.containerSelected,
      ]}
      onPress={handlePress}
      activeOpacity={0.9}
      disabled={isSelectionMode ? !onToggleSelection : !onPress}
    >
      {/* Чекбокс в режиме выбора */}
      {isSelectionMode && (
        <View style={styles.checkboxContainer}>
          <View
            style={[
              styles.checkbox,
              isSelected && styles.checkboxSelected,
            ]}
          >
            {isSelected && (
              <Ionicons name="checkmark" size={16} color={Colors.background} />
            )}
          </View>
        </View>
      )}

      {/* Обложка */}
      <View style={[styles.imageContainer, { height: imageHeight }]}>
        {imageUrl ? (
          <Image
            source={{ uri: imageUrl }}
            style={styles.image}
            resizeMode="cover"
          />
        ) : (
          <View style={styles.placeholderImage}>
            <Ionicons name="disc-outline" size={48} color={Colors.textMuted} />
          </View>
        )}
        {isSelectionMode && isSelected && (
          <View style={styles.selectedOverlay} />
        )}
        {isBooked && !isSelectionMode && (
          <View style={styles.bookedBadge}>
            <Ionicons name="gift-outline" size={12} color={Colors.background} />
            <Text style={styles.bookedBadgeText}>Забронировано</Text>
          </View>
        )}
      </View>

      {/* Информация */}
      <View style={styles.info}>
        {onArtistPress ? (
          <TouchableOpacity
            onPress={() => onArtistPress(record.artist)}
            activeOpacity={0.7}
          >
            <Text style={[styles.artist, styles.artistClickable]} numberOfLines={1}>
              {record.artist}
            </Text>
          </TouchableOpacity>
        ) : (
          <Text style={styles.artist} numberOfLines={1}>
            {record.artist}
          </Text>
        )}
        <Text style={styles.title} numberOfLines={2}>
          {record.title}
        </Text>
        <View style={styles.meta}>
          {record.year != null && record.year !== 0 && (
            <Text style={styles.metaText}>{record.year}</Text>
          )}
          {'country' in record && record.country && (
            <>
              {record.year != null && record.year !== 0 && <Text style={styles.metaDot}>•</Text>}
              <Text style={styles.metaText}>{record.country}</Text>
            </>
          )}
          {'format_type' in record && record.format_type && (
            <>
              {(record.year != null && record.year !== 0) || ('country' in record && record.country) ? <Text style={styles.metaDot}>•</Text> : null}
              <Text style={styles.metaText} numberOfLines={1}>{getShortFormat(record.format_type)}</Text>
            </>
          )}
          {'format' in record && record.format && !('format_type' in record) && (
            <>
              {(record.year != null && record.year !== 0) || ('country' in record && record.country) ? <Text style={styles.metaDot}>•</Text> : null}
              <Text style={styles.metaText} numberOfLines={1}>{getShortFormat(record.format)}</Text>
            </>
          )}
        </View>
      </View>

      {/* Кнопки действий */}
      {showActions && (
        <View style={styles.actions}>
          {onAddToCollection && (
            <TouchableOpacity
              style={styles.actionButton}
              onPress={onAddToCollection}
            >
              <Ionicons name="add-circle-outline" size={24} color={Colors.primary} />
            </TouchableOpacity>
          )}
          {onAddToWishlist && (
            <TouchableOpacity
              style={styles.actionButton}
              onPress={onAddToWishlist}
            >
              <Ionicons name="heart-outline" size={24} color={Colors.accent} />
            </TouchableOpacity>
          )}
          {onRemove && (
            <TouchableOpacity
              style={styles.actionButton}
              onPress={onRemove}
            >
              <Ionicons name="trash-outline" size={24} color={Colors.error} />
            </TouchableOpacity>
          )}
        </View>
      )}
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: Colors.background,
    borderRadius: BorderRadius.lg,
    overflow: 'hidden',
    marginBottom: Spacing.md,
    position: 'relative',
    borderWidth: 1,
    borderColor: Colors.border,
  },
  containerSelected: {
    borderWidth: 2,
    borderColor: Colors.primary,
  },
  checkboxContainer: {
    position: 'absolute',
    top: Spacing.sm,
    left: Spacing.sm,
    zIndex: 10,
  },
  checkbox: {
    width: 24,
    height: 24,
    borderRadius: 12,
    borderWidth: 2,
    borderColor: Colors.primary,
    backgroundColor: Colors.background,
    alignItems: 'center',
    justifyContent: 'center',
  },
  checkboxSelected: {
    backgroundColor: Colors.primary,
  },
  selectedOverlay: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(26, 26, 26, 0.3)',
  },
  imageContainer: {
    width: '100%',
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
    padding: Spacing.sm,
  },
  artist: {
    ...Typography.caption,
    color: Colors.textSecondary,
    letterSpacing: 0.5,
    marginBottom: 2,
  },
  artistClickable: {
    color: Colors.primary,
  },
  title: {
    ...Typography.bodySmall,
    fontWeight: '600',
    color: Colors.text,
    marginBottom: Spacing.xs,
  },
  meta: {
    flexDirection: 'row',
    alignItems: 'center',
    flexWrap: 'wrap',
    maxHeight: 36, // Ограничиваем высоту мета-блока (примерно 2 строки)
    overflow: 'hidden',
  },
  metaText: {
    ...Typography.caption,
    color: Colors.textMuted,
    flexShrink: 1,
  },
  metaDot: {
    ...Typography.caption,
    color: Colors.textMuted,
    marginHorizontal: 4,
  },
  actions: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    padding: Spacing.sm,
    paddingTop: 0,
    gap: Spacing.sm,
  },
  actionButton: {
    padding: Spacing.xs,
  },
  bookedBadge: {
    position: 'absolute',
    bottom: Spacing.sm,
    left: Spacing.sm,
    right: Spacing.sm,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
    backgroundColor: Colors.accent,
    paddingVertical: 4,
    paddingHorizontal: Spacing.sm,
    borderRadius: BorderRadius.sm,
  },
  bookedBadgeText: {
    ...Typography.caption,
    color: Colors.background,
    fontWeight: '600',
  },
});

export default RecordCard;
