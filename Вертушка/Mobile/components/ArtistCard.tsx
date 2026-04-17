/**
 * Карточка артиста
 */
import React, { memo } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Dimensions,
} from 'react-native';
import { Image } from 'expo-image';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Typography, BorderRadius, Shadows, Spacing } from '../constants/theme';
import { ArtistSearchResult } from '../lib/types';

const { width } = Dimensions.get('window');
const CARD_WIDTH = (width - Spacing.md * 3) / 2;

interface ArtistCardProps {
  artist: ArtistSearchResult;
  onPress?: () => void;
}

function ArtistCardComponent({ artist, onPress }: ArtistCardProps) {
  // Приоритет: cover_image_url для высокого качества, fallback на thumb
  const imageUrl = artist.cover_image_url || artist.thumb_image_url;

  return (
    <TouchableOpacity
      style={[styles.container, Shadows.md]}
      onPress={onPress}
      activeOpacity={0.9}
      disabled={!onPress}
    >
      {/* Изображение артиста (круглое) */}
      <View style={styles.imageContainer}>
        {imageUrl ? (
          <Image
            source={imageUrl}
            style={styles.image}
            contentFit="cover"
            cachePolicy="disk"
          />
        ) : (
          <View style={styles.placeholderImage}>
            <Ionicons name="person-outline" size={48} color={Colors.textMuted} />
          </View>
        )}
      </View>

      {/* Имя артиста */}
      <View style={styles.info}>
        <Text style={styles.name} numberOfLines={2}>
          {artist.name}
        </Text>
      </View>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  container: {
    width: CARD_WIDTH,
    backgroundColor: Colors.background,
    borderRadius: BorderRadius.lg,
    overflow: 'hidden',
    marginBottom: Spacing.md,
    alignItems: 'center',
    paddingVertical: Spacing.md,
  },
  imageContainer: {
    width: 100,
    height: 100,
    borderRadius: 50,
    backgroundColor: Colors.surface,
    overflow: 'hidden',
    marginBottom: Spacing.sm,
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
    paddingHorizontal: Spacing.sm,
    alignItems: 'center',
  },
  name: {
    ...Typography.bodySmall,
    fontWeight: '600',
    color: Colors.text,
    textAlign: 'center',
  },
});

export const ArtistCard = memo(ArtistCardComponent);
export default ArtistCard;
