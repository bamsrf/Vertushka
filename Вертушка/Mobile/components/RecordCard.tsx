/**
 * Карточка пластинки — Editorial Gradient Edition
 * Два варианта: compact (overlay) и expanded (card с инфо)
 */
import React, { memo, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  Dimensions,
} from 'react-native';
import { Image } from 'expo-image';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withTiming,
} from 'react-native-reanimated';
import { Colors, Typography, BorderRadius, Shadows, Spacing, Gradients } from '../constants/theme';
import { RecordSearchResult, VinylRecord, MasterSearchResult, ReleaseSearchResult, PublicProfileRecord } from '../lib/types';

const { width } = Dimensions.get('window');
const CARD_WIDTH = (width - Spacing.md * 3) / 2;

interface RecordCardProps {
  record: RecordSearchResult | VinylRecord | MasterSearchResult | ReleaseSearchResult | PublicProfileRecord;
  onPress?: () => void;
  onArtistPress?: (artistName: string) => void;
  onAddToCollection?: () => void;
  onAddToWishlist?: () => void;
  onRemove?: () => void;
  showActions?: boolean;
  size?: 'default' | 'large';
  variant?: 'compact' | 'expanded' | 'list';
  isSelectionMode?: boolean;
  isSelected?: boolean;
  onToggleSelection?: () => void;
  onLongPress?: () => void;
  isBooked?: boolean;
}

const FORMAT_TRANSLATIONS: Record<string, string> = {
  'Vinyl': 'Винил',
  'LP': 'Винил',
  'Cassette': 'Кассета',
  'Box Set': 'Бокс-сет',
};

function getFormatBadgeInfo(format?: string): { label: string; bg: string } | null {
  if (!format) return null;
  const f = format.toLowerCase();
  if (f.includes('vinyl') || f === 'lp') return { label: 'Vinyl', bg: 'rgba(59, 75, 245, 0.55)' };
  if (f.includes('cd')) return { label: 'CD', bg: 'rgba(0, 0, 0, 0.45)' };
  if (f.includes('cassette')) return { label: 'Cassette', bg: 'rgba(0, 0, 0, 0.45)' };
  if (f.includes('box set')) return { label: 'Box Set', bg: 'rgba(0, 0, 0, 0.45)' };
  if (f.includes('dvd')) return { label: 'DVD', bg: 'rgba(0, 0, 0, 0.45)' };
  if (f.includes('blu-ray')) return { label: 'Blu-ray', bg: 'rgba(0, 0, 0, 0.45)' };
  return { label: format, bg: 'rgba(0, 0, 0, 0.45)' };
}

function getShortFormat(format: string | undefined): string | undefined {
  if (!format) return undefined;

  const parts = format.split(',').map(s => s.trim()).filter(Boolean);
  if (parts.length === 0) return undefined;

  const mainFormats = ['Vinyl', 'CD', 'Cassette', 'DVD', 'Blu-ray', 'Box Set', 'LP', '7"', '12"', '10"'];
  const importantDetails = ['Album', 'Single', 'EP', 'Compilation', 'Limited Edition', 'Reissue', 'Remaster'];

  const result: string[] = [];

  const mainFormat = parts.find(p => mainFormats.some(mf => p.includes(mf)));
  if (mainFormat) {
    const translatedKey = Object.keys(FORMAT_TRANSLATIONS).find(k => mainFormat.includes(k));
    result.push(translatedKey ? FORMAT_TRANSLATIONS[translatedKey] : mainFormat);
  } else if (parts[0]) {
    result.push(parts[0]);
  }

  const detail = parts.find(p => importantDetails.some(d => p.includes(d)));
  if (detail && result.length < 2) {
    result.push(detail);
  }

  return result.join(', ') || parts[0];
}

const AnimatedPressable = Animated.createAnimatedComponent(Pressable);

function RecordCardComponent({
  record,
  onPress,
  onArtistPress,
  onAddToCollection,
  onAddToWishlist,
  onRemove,
  showActions = false,
  size = 'default',
  variant = 'expanded',
  isSelectionMode = false,
  isSelected = false,
  onToggleSelection,
  onLongPress,
  isBooked = false,
}: RecordCardProps) {
  const imageUrl = record.cover_image_url || record.thumb_image_url;
  const cardWidth = size === 'large' ? width - Spacing.md * 2 : CARD_WIDTH;
  const imageHeight = size === 'large' ? cardWidth * 0.8 : CARD_WIDTH;

  const scale = useSharedValue(1);
  const didLongPress = useRef(false);

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [{ scale: scale.value }],
  }));

  const handlePressIn = () => {
    scale.value = withTiming(0.96, { duration: 100 });
  };

  const handlePressOut = () => {
    scale.value = withTiming(1, { duration: 150 });
  };

  const handlePress = () => {
    if (didLongPress.current) {
      didLongPress.current = false;
      return;
    }
    if (isSelectionMode && onToggleSelection) {
      onToggleSelection();
    } else if (onPress) {
      onPress();
    }
  };

  const handleLongPress = () => {
    didLongPress.current = true;
    onLongPress?.();
  };

  if (variant === 'compact') {
    const formatValue = 'format_type' in record ? record.format_type
      : 'format' in record ? (record.format as string)
      : undefined;
    const formatBadge = getFormatBadgeInfo(formatValue);

    return (
      <AnimatedPressable
        style={[
          styles.compactContainer,
          { width: cardWidth, height: imageHeight },
          Shadows.md,
          isSelectionMode && isSelected && styles.containerSelected,
          animatedStyle,
        ]}
        onPress={handlePress}
        onLongPress={!isSelectionMode ? handleLongPress : undefined}
        onPressIn={handlePressIn}
        onPressOut={handlePressOut}
        disabled={isSelectionMode ? !onToggleSelection : !onPress}
      >
        {isSelectionMode && (
          <View style={styles.checkboxContainer}>
            <View style={[styles.checkbox, isSelected && styles.checkboxSelected]}>
              {isSelected && <Ionicons name="checkmark" size={16} color={Colors.background} />}
            </View>
          </View>
        )}

        {imageUrl ? (
          <Image source={imageUrl} style={styles.compactImage} contentFit="cover" cachePolicy="disk" />
        ) : (
          <View style={styles.compactPlaceholder}>
            <Ionicons name="disc-outline" size={48} color={Colors.periwinkle} />
          </View>
        )}

        {/* Год badge в правом верхнем углу */}
        {record.year != null && record.year !== 0 && (
          <View style={styles.yearBadge}>
            <Text style={styles.yearBadgeText}>{record.year}</Text>
          </View>
        )}

        {/* Формат badge в левом верхнем углу */}
        {formatBadge && (
          <View style={[styles.formatBadge, { backgroundColor: formatBadge.bg }]}>
            <Text style={styles.formatBadgeText}>{formatBadge.label}</Text>
          </View>
        )}

        {isBooked && !isSelectionMode && (
          <LinearGradient
            colors={[Colors.royalBlue, Colors.periwinkle]}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 0 }}
            style={styles.bookedBadge}
          >
            <Ionicons name="gift-outline" size={12} color={Colors.background} />
            <Text style={styles.bookedBadgeText}>Забронировано</Text>
          </LinearGradient>
        )}

        {/* Gradient overlay с текстом */}
        <LinearGradient
          colors={Gradients.overlay as [string, string]}
          style={styles.compactOverlay}
        >
          <Text style={styles.compactArtist} numberOfLines={1}>
            {record.artist}
          </Text>
          <Text style={styles.compactTitle} numberOfLines={2}>
            {record.title}
          </Text>
        </LinearGradient>
      </AnimatedPressable>
    );
  }

  // variant === 'list'
  if (variant === 'list') {
    const formatText = 'format_type' in record && record.format_type
      ? getShortFormat(record.format_type)
      : 'format' in record && record.format
        ? getShortFormat(record.format as string)
        : undefined;

    return (
      <AnimatedPressable
        style={[
          styles.listContainer,
          Shadows.sm,
          isSelectionMode && isSelected && styles.containerSelected,
          animatedStyle,
        ]}
        onPress={handlePress}
        onLongPress={!isSelectionMode ? handleLongPress : undefined}
        onPressIn={handlePressIn}
        onPressOut={handlePressOut}
        disabled={isSelectionMode ? !onToggleSelection : !onPress}
      >
        {isSelectionMode && (
          <View style={styles.listCheckboxContainer}>
            <View style={[styles.checkbox, isSelected && styles.checkboxSelected]}>
              {isSelected && <Ionicons name="checkmark" size={16} color={Colors.background} />}
            </View>
          </View>
        )}

        <View style={styles.listImageContainer}>
          {imageUrl ? (
            <Image source={imageUrl} style={styles.listImage} contentFit="cover" cachePolicy="disk" />
          ) : (
            <View style={styles.listPlaceholder}>
              <Ionicons name="disc-outline" size={28} color={Colors.periwinkle} />
            </View>
          )}
          {isBooked && !isSelectionMode && (
            <View style={styles.listBookedBadge}>
              <Ionicons name="gift-outline" size={10} color={Colors.background} />
            </View>
          )}
        </View>

        <View style={styles.listInfo}>
          {onArtistPress ? (
            <Pressable onPress={() => onArtistPress(record.artist)}>
              <Text style={[styles.listArtist, styles.artistClickable]} numberOfLines={1}>
                {record.artist}
              </Text>
            </Pressable>
          ) : (
            <Text style={styles.listArtist} numberOfLines={1}>
              {record.artist}
            </Text>
          )}
          <Text style={styles.listTitle} numberOfLines={1}>
            {record.title}
          </Text>
          <View style={styles.listMeta}>
            {record.year != null && record.year !== 0 && (
              <Text style={styles.metaText}>{record.year}</Text>
            )}
            {formatText && (
              <>
                {record.year != null && record.year !== 0 && <Text style={styles.metaDot}>·</Text>}
                <Text style={styles.metaText} numberOfLines={1}>{formatText}</Text>
              </>
            )}
          </View>
        </View>

        <Ionicons name="chevron-forward" size={16} color={Colors.textMuted} style={styles.listChevron} />
      </AnimatedPressable>
    );
  }

  // variant === 'expanded'
  return (
    <AnimatedPressable
      style={[
        styles.expandedContainer,
        { width: cardWidth },
        Shadows.md,
        isSelectionMode && isSelected && styles.containerSelected,
        animatedStyle,
      ]}
      onPress={handlePress}
      onLongPress={!isSelectionMode ? handleLongPress : undefined}
      onPressIn={handlePressIn}
      onPressOut={handlePressOut}
      disabled={isSelectionMode ? !onToggleSelection : !onPress}
    >
      {isSelectionMode && (
        <View style={styles.checkboxContainer}>
          <View style={[styles.checkbox, isSelected && styles.checkboxSelected]}>
            {isSelected && <Ionicons name="checkmark" size={16} color={Colors.background} />}
          </View>
        </View>
      )}

      <View style={[styles.expandedImageContainer, { height: imageHeight }]}>
        {imageUrl ? (
          <Image source={imageUrl} style={styles.expandedImage} contentFit="cover" cachePolicy="disk" />
        ) : (
          <View style={styles.expandedPlaceholder}>
            <Ionicons name="disc-outline" size={48} color={Colors.periwinkle} />
          </View>
        )}
        {isBooked && !isSelectionMode && (
          <LinearGradient
            colors={[Colors.royalBlue, Colors.periwinkle]}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 0 }}
            style={styles.bookedBadge}
          >
            <Ionicons name="gift-outline" size={12} color={Colors.background} />
            <Text style={styles.bookedBadgeText}>Забронировано</Text>
          </LinearGradient>
        )}
      </View>

      <View style={styles.expandedInfo}>
        {onArtistPress ? (
          <Pressable onPress={() => onArtistPress(record.artist)}>
            <Text style={[styles.expandedArtist, styles.artistClickable]} numberOfLines={1}>
              {record.artist}
            </Text>
          </Pressable>
        ) : (
          <Text style={styles.expandedArtist} numberOfLines={1}>
            {record.artist}
          </Text>
        )}
        <Text style={styles.expandedTitle} numberOfLines={2}>
          {record.title}
        </Text>
        <View style={styles.meta}>
          {record.year != null && record.year !== 0 && (
            <Text style={styles.metaText}>{record.year}</Text>
          )}
          {'country' in record && record.country && (
            <>
              {record.year != null && record.year !== 0 && <Text style={styles.metaDot}>·</Text>}
              <Text style={styles.metaText}>{record.country}</Text>
            </>
          )}
          {'format_type' in record && record.format_type && (
            <>
              {(record.year != null && record.year !== 0) || ('country' in record && record.country) ? <Text style={styles.metaDot}>·</Text> : null}
              <Text style={styles.metaText} numberOfLines={1}>{getShortFormat(record.format_type)}</Text>
            </>
          )}
          {'format' in record && record.format && !('format_type' in record) && (
            <>
              {(record.year != null && record.year !== 0) || ('country' in record && record.country) ? <Text style={styles.metaDot}>·</Text> : null}
              <Text style={styles.metaText} numberOfLines={1}>{getShortFormat(record.format)}</Text>
            </>
          )}
        </View>
      </View>

      {showActions && (
        <View style={styles.actions}>
          {onAddToCollection && (
            <Pressable style={styles.actionButton} onPress={onAddToCollection}>
              <Ionicons name="add-circle-outline" size={24} color={Colors.royalBlue} />
            </Pressable>
          )}
          {onAddToWishlist && (
            <Pressable style={styles.actionButton} onPress={onAddToWishlist}>
              <Ionicons name="heart-outline" size={24} color={Colors.softPink} />
            </Pressable>
          )}
          {onRemove && (
            <Pressable style={styles.actionButton} onPress={onRemove}>
              <Ionicons name="trash-outline" size={24} color={Colors.error} />
            </Pressable>
          )}
        </View>
      )}
    </AnimatedPressable>
  );
}

const styles = StyleSheet.create({
  // ===== COMPACT (overlay) =====
  compactContainer: {
    borderRadius: 16,
    overflow: 'hidden',
    marginBottom: Spacing.md,
    position: 'relative',
    backgroundColor: Colors.surface,
    borderWidth: 2,
    borderColor: 'transparent',
  },
  compactImage: {
    width: '100%',
    height: '100%',
  },
  compactPlaceholder: {
    width: '100%',
    height: '100%',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: Colors.surface,
  },
  compactOverlay: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    paddingHorizontal: 12,
    paddingBottom: 12,
    paddingTop: 40,
  },
  compactArtist: {
    fontSize: 12,
    fontFamily: 'Inter_500Medium',
    color: 'rgba(255,255,255,0.85)',
    textTransform: 'uppercase',
    letterSpacing: 1,
    marginBottom: 2,
  },
  compactTitle: {
    fontSize: 16,
    fontFamily: 'Inter_700Bold',
    color: '#FFFFFF',
    lineHeight: 20,
  },
  yearBadge: {
    position: 'absolute',
    top: 8,
    right: 8,
    backgroundColor: 'rgba(255,255,255,0.25)',
    borderRadius: 10,
    paddingHorizontal: 8,
    paddingVertical: 3,
  },
  yearBadgeText: {
    fontSize: 11,
    fontFamily: 'Inter_600SemiBold',
    color: '#FFFFFF',
  },
  formatBadge: {
    position: 'absolute',
    top: 8,
    left: 8,
    borderRadius: 8,
    paddingHorizontal: 7,
    paddingVertical: 3,
    zIndex: 2,
  },
  formatBadgeText: {
    fontSize: 11,
    fontFamily: 'Inter_600SemiBold',
    color: '#FFFFFF',
  },

  // ===== EXPANDED (card) =====
  expandedContainer: {
    borderRadius: 16,
    overflow: 'hidden',
    marginBottom: Spacing.md,
    position: 'relative',
    borderWidth: 2,
    borderColor: 'transparent',
    backgroundColor: '#FFFFFF',
  },
  containerSelected: {
    borderColor: Colors.royalBlue,
  },
  expandedImageContainer: {
    width: '100%',
    backgroundColor: Colors.surface,
    overflow: 'hidden',
  },
  expandedImage: {
    width: '100%',
    height: '100%',
  },
  expandedPlaceholder: {
    width: '100%',
    height: '100%',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: Colors.surface,
  },
  expandedInfo: {
    padding: 12,
    backgroundColor: '#FFFFFF',
  },
  expandedArtist: {
    ...Typography.caption,
    color: Colors.textSecondary,
    textTransform: 'uppercase',
    letterSpacing: 1,
    marginBottom: 2,
  },
  artistClickable: {
    color: Colors.royalBlue,
  },
  expandedTitle: {
    ...Typography.bodySmall,
    fontFamily: 'Inter_600SemiBold',
    color: Colors.text,
    marginBottom: Spacing.xs,
  },
  meta: {
    flexDirection: 'row',
    alignItems: 'center',
    flexWrap: 'wrap',
    maxHeight: 36,
    overflow: 'hidden',
  },
  metaText: {
    ...Typography.caption,
    color: '#999999',
  },
  metaDot: {
    ...Typography.caption,
    color: '#999999',
    marginHorizontal: 4,
  },

  // ===== LIST =====
  listContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    borderRadius: 14,
    overflow: 'hidden',
    marginBottom: Spacing.sm,
    padding: Spacing.sm,
    gap: Spacing.sm,
    position: 'relative',
    borderWidth: 2,
    borderColor: 'transparent',
  },
  listCheckboxContainer: {
    marginRight: 2,
  },
  listImageContainer: {
    width: 56,
    height: 56,
    borderRadius: 10,
    overflow: 'hidden',
    backgroundColor: Colors.surface,
    position: 'relative',
  },
  listImage: {
    width: '100%',
    height: '100%',
  },
  listPlaceholder: {
    width: '100%',
    height: '100%',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: Colors.surface,
  },
  listBookedBadge: {
    position: 'absolute',
    bottom: 2,
    right: 2,
    width: 18,
    height: 18,
    borderRadius: 9,
    backgroundColor: Colors.royalBlue,
    alignItems: 'center',
    justifyContent: 'center',
  },
  listInfo: {
    flex: 1,
    justifyContent: 'center',
    gap: 1,
  },
  listArtist: {
    ...Typography.caption,
    color: Colors.textSecondary,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
  },
  listTitle: {
    ...Typography.bodySmall,
    fontFamily: 'Inter_600SemiBold',
    color: Colors.text,
  },
  listMeta: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  listChevron: {
    marginLeft: Spacing.xs,
  },

  // ===== SHARED =====
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
    borderColor: Colors.royalBlue,
    backgroundColor: Colors.background,
    alignItems: 'center',
    justifyContent: 'center',
  },
  checkboxSelected: {
    backgroundColor: Colors.royalBlue,
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
    paddingVertical: 4,
    paddingHorizontal: Spacing.sm,
    borderRadius: BorderRadius.sm,
  },
  bookedBadgeText: {
    ...Typography.caption,
    color: Colors.background,
    fontFamily: 'Inter_600SemiBold',
  },
});

export const RecordCard = memo(RecordCardComponent);
export default RecordCard;
