/**
 * Карточка пластинки — Editorial Gradient Edition
 * Два варианта: compact (overlay) и expanded (card с инфо)
 */
import React, { memo, useRef, useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  Dimensions,
} from 'react-native';
import { Image } from 'expo-image';
import { LinearGradient } from 'expo-linear-gradient';
import { Icon } from '@/components/ui';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withTiming,
} from 'react-native-reanimated';
import { Colors, Typography, BorderRadius, Shadows, Spacing, Gradients } from '../constants/theme';
import { RecordSearchResult, VinylRecord, MasterSearchResult, ReleaseSearchResult, PublicProfileRecord } from '../lib/types';
import { getCoverUrl } from '../lib/api';
import { ms } from '../lib/responsive';
import { cleanArtistName } from '../lib/format';
import { RarityAura, TierCoverEffects, TierLabel, pickRarityTier, RarityContext, RarityFlags, RARITY_TIERS } from './RarityAura';
import HotStockTag, { type ResolvedHotStock } from './HotStockTag';
import { RadarIcon } from './RadarIcon';
import { OfferBadge, TileFrameGradient } from './OfferBadge';

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
  /** Where this card is rendered — drives rarity tier selection. `collection` hides "hot". */
  rarityContext?: RarityContext;
  /** Disable the rarity aura/animation wrapper — show only the inline text label. Used in grid/tile mode. */
  noRarityAura?: boolean;
  /**
   * Hot Stock indicator — рендерится в правом нижнем углу (compact),
   * в text-block (expanded) или справа (list). Передаётся уже-вычисленный
   * {variant, price} — используй summaryToHotStock(summary, hints) на родителе.
   * Если undefined/null — карточка как обычно, без pill'а.
   * См. docs/plans/MARKET_AND_PRICE_DRAWER.md §2.4 + OFFERS_UX.md §2.8.
   */
  hotStock?: ResolvedHotStock | null;
  /**
   * Wishlist tile/list режим (см. handoff/screens-wishlist-grid-v3):
   *  - `expanded` variant → corner-плашка «В ПРОДАЖЕ»/«ЕСТЬ АНАЛОГ» в правом
   *    верхнем углу обложки + gradient-рамка вокруг cover. Bottom HotStockTag
   *    скрывается. Саб-строка с ценой исчезает.
   *  - `list` variant → ТОЛЬКО для altVersion заменяет HotStockTag на
   *    OfferBadge «ЕСТЬ АНАЛОГ». Для in-stock case оставляет HotStockTag.
   */
  useOfferBadge?: boolean;
  /** Пластинка на радаре (notify_mode='subscribed') — маленький бейдж-иконка. */
  onRadar?: boolean;
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
  rarityContext = 'search',
  noRarityAura = false,
  hotStock,
  useOfferBadge = false,
  onRadar = false,
}: RecordCardProps) {
  // ── Wishlist offer-badge режим (handoff/screens-wishlist-grid-v3.jsx) ──
  // Для tile (expanded) и list — corner/inline-плашка вместо HotStockTag.
  // 'inStock' для in-stock-листингов (any variant), 'alt' для altVersion.
  const offerBadgeKind: 'inStock' | 'alt' | null = useOfferBadge && hotStock
    ? hotStock.variant === 'altVersion'
      ? 'alt'
      : hotStock.variant === 'inStock' || hotStock.variant === 'inStockMulti' || hotStock.variant === 'lastOne'
        ? 'inStock'
        : null
    : null;
  const imageUrl = getCoverUrl(record);
  // Битый URL (протухший Deezer/store-хотлинк, мёртвое зеркало) → откат на
  // иконку пластинки вместо пустого квадрата. Сброс при смене обложки
  // (FlatList переиспользует инстансы карточек).
  const [imgFailed, setImgFailed] = useState(false);
  useEffect(() => setImgFailed(false), [imageUrl]);
  const showImage = !!imageUrl && !imgFailed;
  const artistDisplay = cleanArtistName(record.artist);
  const cardWidth = size === 'large' ? width - Spacing.md * 2 : CARD_WIDTH;
  const imageHeight = size === 'large' ? cardWidth * 0.8 : CARD_WIDTH;
  const rarityTier = pickRarityTier(record as RarityFlags, rarityContext);
  const auraTier = noRarityAura ? null : rarityTier;

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
              {isSelected && <Icon name="checkmark" size={16} color={Colors.background} />}
            </View>
          </View>
        )}

        {showImage ? (
          <Image source={imageUrl} style={styles.compactImage} contentFit="cover" cachePolicy="disk" onError={() => setImgFailed(true)} />
        ) : (
          <View style={styles.compactPlaceholder}>
            <Icon name="disc-outline" size={48} color={Colors.periwinkle} />
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

        {/* Радар-бейдж — левый нижний угол обложки */}
        {onRadar && (
          <View style={styles.radarBadge} pointerEvents="none">
            <RadarIcon size={13} color="#fff" variant="on" />
          </View>
        )}

        {isBooked && !isSelectionMode && (
          <LinearGradient
            colors={[Colors.royalBlue, Colors.periwinkle]}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 0 }}
            style={styles.bookedBadge}
          >
            <Icon name="gift-outline" size={12} color={Colors.background} />
            <Text style={styles.bookedBadgeText}>Забронировано</Text>
          </LinearGradient>
        )}

        {/* Hot Stock pill — bottom-right overlay (top-right для altVersion).
            MARKET_AND_PRICE_DRAWER.md §2.4.1 — pill живёт ВНУТРИ gradient overlay,
            прижат к правому углу с offset 8dp. altVersion смещается вверх, чтобы
            не перекрывать имя/название в нижнем блоке. */}
        {hotStock && (
          <View
            pointerEvents="none"
            style={
              hotStock.variant === 'altVersion'
                ? styles.hotStockTopRight
                : styles.hotStockBottomRight
            }
          >
            <HotStockTag
              variant={hotStock.variant}
              price={hotStock.price}
              size="sm"
              showArrow={false}
              showShadow={hotStock.variant !== 'altVersion'}
            />
          </View>
        )}

        {/* Gradient overlay с текстом */}
        <LinearGradient
          colors={Gradients.overlay as [string, string]}
          style={styles.compactOverlay}
        >
          <Text style={styles.compactArtist} numberOfLines={1}>
            {artistDisplay}
          </Text>
          <Text style={styles.compactTitle} numberOfLines={2}>
            {record.title}
          </Text>
          {rarityTier && (
            <View style={[styles.compactRarity, { backgroundColor: RARITY_TIERS[rarityTier].palette[1] }]}>
              <Text style={styles.compactRarityText} numberOfLines={1}>
                {RARITY_TIERS[rarityTier].label}
              </Text>
            </View>
          )}
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

    const listInner = (
      <AnimatedPressable
        style={[
          styles.listContainer,
          auraTier === 'collectible' ? styles.cardNoMargin : Shadows.sm,
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
              {isSelected && <Icon name="checkmark" size={16} color={Colors.background} />}
            </View>
          </View>
        )}

        <View style={styles.listImageContainer}>
          {showImage ? (
            <Image source={imageUrl} style={styles.listImage} contentFit="cover" cachePolicy="disk" onError={() => setImgFailed(true)} />
          ) : (
            <View style={styles.listPlaceholder}>
              <Icon name="disc-outline" size={28} color={Colors.periwinkle} />
            </View>
          )}
          <TierCoverEffects tier={auraTier} radius={10} />
          {onRadar && (
            <View style={styles.radarBadgeList} pointerEvents="none">
              <RadarIcon size={11} color="#fff" variant="on" />
            </View>
          )}
          {isBooked && !isSelectionMode && (
            <View style={styles.listBookedBadge}>
              <Icon name="gift-outline" size={10} color={Colors.background} />
            </View>
          )}
        </View>

        <View style={styles.listInfo}>
          {onArtistPress ? (
            <Pressable onPress={() => onArtistPress(record.artist)}>
              <Text style={[styles.listArtist, styles.artistClickable]} numberOfLines={1}>
                {artistDisplay}
              </Text>
            </Pressable>
          ) : (
            <Text style={styles.listArtist} numberOfLines={1}>
              {artistDisplay}
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
            {rarityTier && (
              <>
                {((record.year != null && record.year !== 0) || formatText) && (
                  <Text style={styles.metaDot}>·</Text>
                )}
                <TierLabel tier={rarityTier} />
              </>
            )}
          </View>
        </View>

        {/* Hot Stock pill — справа вместо chevron'а. List-row компактный,
            используем size='sm' без стрелки. MARKET_AND_PRICE_DRAWER.md §2.4.3.
            Для wishlist'а с offerBadgeKind='alt' — заменяем pill на OfferBadge
            «ЕСТЬ АНАЛОГ» (вместо «· альт.» суффикса в HotStockTag). In-stock
            case остаётся как есть. */}
        {hotStock && offerBadgeKind === 'alt' ? (
          <View style={styles.listHotStock} pointerEvents="none">
            <OfferBadge kind="alt" size="sm" />
          </View>
        ) : hotStock ? (
          <View style={styles.listHotStock} pointerEvents="none">
            <HotStockTag
              variant={hotStock.variant}
              price={hotStock.price}
              size="sm"
              showArrow={false}
              showShadow={hotStock.variant !== 'altVersion'}
            />
          </View>
        ) : null}

      </AnimatedPressable>
    );

    if (!auraTier) return listInner;
    return (
      <RarityAura tier={auraTier} radius={14} style={styles.rarityWrapList}>
        {listInner}
      </RarityAura>
    );
  }

  // variant === 'expanded'
  const hasYear = record.year != null && record.year !== 0;
  const hasCountry = 'country' in record && !!record.country;
  const formatText = 'format_type' in record && record.format_type
    ? getShortFormat(record.format_type)
    : 'format' in record && record.format
      ? getShortFormat(record.format as string)
      : undefined;

  const expandedInner = (
    <AnimatedPressable
      style={[
        styles.expandedContainer,
        { width: cardWidth },
        auraTier === 'collectible' ? null : Shadows.md,
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
            {isSelected && <Icon name="checkmark" size={16} color={Colors.background} />}
          </View>
        </View>
      )}

      {(() => {
        // Cover-блок с опциональной gradient-рамкой и corner-плашкой.
        // Для wishlist tile (offerBadgeKind !== null) оборачиваем cover в
        // TileFrameGradient (2dp gradient outline) и кладём OfferBadge в
        // правый верхний угол. Для остальных случаев — обычный контейнер.
        const coverInner = (
          <View
            style={[
              styles.expandedImageContainer,
              { height: imageHeight },
              offerBadgeKind ? styles.expandedImageContainerFramed : null,
            ]}
          >
            {showImage ? (
              <Image source={imageUrl} style={styles.expandedImage} contentFit="cover" cachePolicy="disk" onError={() => setImgFailed(true)} />
            ) : (
              <View style={styles.expandedPlaceholder}>
                <Icon name="disc-outline" size={48} color={Colors.periwinkle} />
              </View>
            )}
            <TierCoverEffects tier={auraTier} radius={0} />
            {isBooked && !isSelectionMode && (
              <LinearGradient
                colors={[Colors.royalBlue, Colors.periwinkle]}
                start={{ x: 0, y: 0 }}
                end={{ x: 1, y: 0 }}
                style={styles.bookedBadge}
              >
                <Icon name="gift-outline" size={12} color={Colors.background} />
                <Text style={styles.bookedBadgeText}>Забронировано</Text>
              </LinearGradient>
            )}
            {offerBadgeKind && (
              <View style={styles.offerCornerBadge} pointerEvents="none">
                <OfferBadge kind={offerBadgeKind} size="md" />
              </View>
            )}
          </View>
        );
        return offerBadgeKind ? (
          <TileFrameGradient kind={offerBadgeKind}>{coverInner}</TileFrameGradient>
        ) : coverInner;
      })()}

      <View style={styles.expandedInfo}>
        {onArtistPress ? (
          <Pressable onPress={() => onArtistPress(record.artist)}>
            <Text style={[styles.expandedArtist, styles.artistClickable]} numberOfLines={1}>
              {artistDisplay}
            </Text>
          </Pressable>
        ) : (
          <Text style={styles.expandedArtist} numberOfLines={1}>
            {artistDisplay}
          </Text>
        )}
        <Text style={styles.expandedTitle} numberOfLines={1}>
          {record.title}
        </Text>
        <View style={styles.meta}>
          {hasYear && <Text style={styles.metaText}>{record.year}</Text>}
          {hasCountry && (
            <>
              {hasYear && <Text style={styles.metaDot}>·</Text>}
              <Text style={styles.metaText}>{(record as { country?: string }).country}</Text>
            </>
          )}
          {formatText && (
            <>
              {(hasYear || hasCountry) && <Text style={styles.metaDot}>·</Text>}
              <Text style={styles.metaText} numberOfLines={1}>{formatText}</Text>
            </>
          )}
          {rarityTier && (
            <>
              {(hasYear || hasCountry || formatText) && <Text style={styles.metaDot}>·</Text>}
              <TierLabel tier={rarityTier} />
            </>
          )}
        </View>
        {/* Hot Stock pill — отдельная строка под метой. MARKET_AND_PRICE_DRAWER.md §2.4.2:
            высота карточки не растёт критично, pill добавляет ~24dp. Если место
            не находится — fallback на compact-стиль решает родитель через variant.
            В wishlist tile-режиме (offerBadgeKind != null) скрываем — сигнал уже
            даёт corner-плашка на обложке. */}
        {hotStock && !offerBadgeKind && (
          <View style={styles.expandedHotStock} pointerEvents="none">
            <HotStockTag
              variant={hotStock.variant}
              price={hotStock.price}
              size="sm"
              showArrow={false}
              showShadow={hotStock.variant !== 'altVersion'}
            />
          </View>
        )}
      </View>

      {showActions && (
        <View style={styles.actions}>
          {onAddToCollection && (
            <Pressable style={styles.actionButton} onPress={onAddToCollection}>
              <Icon name="add-circle-outline" size={24} color={Colors.royalBlue} />
            </Pressable>
          )}
          {onAddToWishlist && (
            <Pressable style={styles.actionButton} onPress={onAddToWishlist}>
              <Icon name="heart-outline" size={24} color={Colors.softPink} />
            </Pressable>
          )}
          {onRemove && (
            <Pressable style={styles.actionButton} onPress={onRemove}>
              <Icon name="trash-outline" size={24} color={Colors.error} />
            </Pressable>
          )}
        </View>
      )}
    </AnimatedPressable>
  );

  if (!auraTier) return expandedInner;
  return (
    <RarityAura tier={auraTier} radius={16} style={styles.rarityWrapExpanded}>
      {expandedInner}
    </RarityAura>
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
    fontSize: ms(12),
    fontFamily: 'Inter_500Medium',
    color: 'rgba(255,255,255,0.85)',
    textTransform: 'uppercase',
    letterSpacing: 1,
    marginBottom: 2,
  },
  compactTitle: {
    fontSize: ms(16),
    fontFamily: 'Inter_700Bold',
    color: '#FFFFFF',
    lineHeight: ms(20),
  },
  compactRarity: {
    alignSelf: 'flex-start',
    marginTop: 6,
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 6,
  },
  compactRarityText: {
    fontSize: 10,
    fontFamily: 'Inter_700Bold',
    color: '#FFFFFF',
    letterSpacing: 0.4,
    textTransform: 'uppercase',
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
  radarBadge: {
    position: 'absolute',
    bottom: 8,
    left: 8,
    width: 24,
    height: 24,
    borderRadius: 12,
    backgroundColor: Colors.royalBlue,
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 3,
    shadowColor: '#3B4BF5',
    shadowOpacity: 0.4,
    shadowRadius: 5,
    shadowOffset: { width: 0, height: 2 },
    elevation: 3,
  },
  radarBadgeList: {
    position: 'absolute',
    bottom: 4,
    left: 4,
    width: 20,
    height: 20,
    borderRadius: 10,
    backgroundColor: Colors.royalBlue,
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 3,
  },

  // ===== EXPANDED (card) =====
  expandedContainer: {
    borderRadius: 16,
    overflow: 'hidden',
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
    height: 92,
    overflow: 'hidden',
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
    flexWrap: 'nowrap',
    height: 18,
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

  // ===== RARITY wrappers =====
  // Extra marginTop+Bottom чтобы соседние подсвеченные карточки не слипались аурами
  rarityWrapList: {
    marginTop: 6,
    marginBottom: Spacing.md,
  },
  rarityWrapExpanded: {},
  cardNoMargin: {
    marginBottom: 0,
  },
  // ── Hot Stock pill placements ───────────────────────────────────────
  // Compact variant: pill ВНУТРИ overlay в правом нижнем углу с offset 8dp.
  // pointerEvents=none на родителе — тап проваливается на саму карточку.
  hotStockBottomRight: {
    position: 'absolute',
    right: 8,
    bottom: 8,
    zIndex: 2, // выше gradient overlay
  },
  hotStockTopRight: {
    position: 'absolute',
    right: 8,
    top: 8,
    zIndex: 2,
  },
  // List variant: pill справа от текстового блока, прижата к правому краю
  // карточки. Margin-right даёт «дышание».
  listHotStock: {
    marginRight: Spacing.sm,
    alignSelf: 'center',
  },
  // Expanded variant: pill отдельной строкой под метой, выравнен по левому
  // краю (alignSelf:'flex-start' через style на pill'е).
  expandedHotStock: {
    marginTop: 6,
  },
  // Wishlist tile corner badge: top:8 right:8 поверх обложки (handoff spec).
  offerCornerBadge: {
    position: 'absolute',
    top: 8,
    right: 8,
    zIndex: 3,
  },
  // Внутренний радиус обложки внутри TileFrameGradient (внешний 14, рамка 2dp).
  expandedImageContainerFramed: {
    borderRadius: 12,
  },
});

export const RecordCard = memo(RecordCardComponent);
export default RecordCard;
