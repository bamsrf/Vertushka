/**
 * StoryPickerSheet — шторка «выбери вид» перед шерингом стоимости коллекции.
 *
 * Три превью сторис (Hi-Fi / Ценник / Лейбл), выбранный вид снимается
 * view-shot'ом в PNG 1080×1920 и уходит в системный share-лист. Полноразмерная
 * копия рендерится за экраном, чтобы снимок не зависел от масштаба превью.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Modal,
  TouchableOpacity,
  Animated,
  Easing,
  Share,
  ActivityIndicator,
  Platform,
  useWindowDimensions,
} from 'react-native';
import { Image } from 'expo-image';
import * as Sharing from 'expo-sharing';
import * as Haptics from 'expo-haptics';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Icon } from '@/components/ui';
import { Colors, Typography, Spacing, BorderRadius, Shadows } from '../../constants/theme';
import {
  CollectionValueStory,
  CollectionValueStoryPreview,
  CollectionStoryData,
  CollectionStoryVariant,
  STORY_VARIANTS,
  STORY_BASE_WIDTH,
  STORY_BASE_HEIGHT,
  formatRubStory,
} from './CollectionValueStory';

interface StoryPickerSheetProps {
  visible: boolean;
  data: CollectionStoryData | null;
  onClose: () => void;
}

export function StoryPickerSheet({ visible, data, onClose }: StoryPickerSheetProps) {
  const insets = useSafeAreaInsets();
  const { width: screenWidth } = useWindowDimensions();
  const [variant, setVariant] = useState<CollectionStoryVariant>('hifi');
  const [sharing, setSharing] = useState(false);
  const shotRef = useRef<View>(null);

  // Та же анимация, что у FolderPickerModal: фон фейдится, лист выезжает снизу.
  const [mounted, setMounted] = useState(visible);
  const progress = useRef(new Animated.Value(0)).current;
  const sheetHeight = useRef(0);

  useEffect(() => {
    if (visible) {
      setMounted(true);
      Animated.timing(progress, {
        toValue: 1,
        duration: 260,
        easing: Easing.out(Easing.cubic),
        useNativeDriver: true,
      }).start();
    } else if (mounted) {
      Animated.timing(progress, {
        toValue: 0,
        duration: 200,
        easing: Easing.in(Easing.cubic),
        useNativeDriver: true,
      }).start(({ finished }) => {
        if (finished) setMounted(false);
      });
    }
  }, [visible]);

  const translateY = progress.interpolate({
    inputRange: [0, 1],
    outputRange: [sheetHeight.current || 600, 0],
  });

  const previewWidth = Math.floor((screenWidth - Spacing.lg * 2 - Spacing.sm * 2) / 3);

  const handleShare = useCallback(async () => {
    if (!data || sharing) return;
    if (Platform.OS !== 'web') {
      Haptics.selectionAsync().catch(() => {});
    }
    setSharing(true);
    const fallbackText = `Моя коллекция винила стоит ~${formatRubStory(data.totalRub)} ₽ по оценке Вертушки. https://vinyl-vertushka.ru/links`;
    try {
      // Ленивый require: нативного view-shot нет в Expo Go (см. achievements.tsx).
      const { captureRef } = require('react-native-view-shot');
      // Обложки — удалённые картинки; без готового битмапа снимок выйдет с
      // пустыми квадратами. Ждём прогрев кэша, но не дольше 2.5 с.
      const covers = data.top.map((r) => r.coverUrl).filter((u): u is string => !!u);
      await Promise.race([
        Image.prefetch(covers, 'disk').catch(() => false),
        new Promise((r) => setTimeout(r, 2500)),
      ]);
      await new Promise((r) => requestAnimationFrame(() => r(null)));
      const uri: string = await captureRef(shotRef, {
        format: 'png',
        quality: 1,
        result: 'tmpfile',
        width: STORY_BASE_WIDTH * 3,
        height: STORY_BASE_HEIGHT * 3,
      });
      if (await Sharing.isAvailableAsync()) {
        await Sharing.shareAsync(uri, { mimeType: 'image/png', dialogTitle: 'Стоимость коллекции' });
      } else {
        await Share.share({ message: fallbackText });
      }
      onClose();
    } catch {
      try {
        await Share.share({ message: fallbackText });
        onClose();
      } catch {
        // Пользователь отменил
      }
    } finally {
      setSharing(false);
    }
  }, [data, sharing, onClose]);

  if (!data) return null;

  return (
    <Modal visible={mounted} transparent animationType="none" onRequestClose={onClose}>
      <Animated.View style={[styles.overlay, { opacity: progress }]}>
        <TouchableOpacity style={StyleSheet.absoluteFill} activeOpacity={1} onPress={onClose} />
        <Animated.View
          style={[styles.sheet, { paddingBottom: insets.bottom + Spacing.lg, transform: [{ translateY }] }]}
          onStartShouldSetResponder={() => true}
          onLayout={(e) => { sheetHeight.current = e.nativeEvent.layout.height; }}
        >
          <View style={styles.handle} />
          <View style={styles.header}>
            <Text style={styles.title}>Выбери вид</Text>
            <TouchableOpacity onPress={onClose} style={styles.closeButton} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
              <Icon name="close" size={20} color={Colors.textSecondary} />
            </TouchableOpacity>
          </View>
          <Text style={styles.sectionLabel}>СТОИМОСТЬ КОЛЛЕКЦИИ</Text>

          <View style={styles.grid}>
            {STORY_VARIANTS.map((v) => {
              const selected = v.id === variant;
              return (
                <TouchableOpacity
                  key={v.id}
                  activeOpacity={0.85}
                  onPress={() => setVariant(v.id)}
                  style={styles.option}
                  accessibilityRole="radio"
                  accessibilityState={{ selected }}
                  accessibilityLabel={v.label}
                >
                  <View style={[styles.previewFrame, selected && styles.previewFrameSelected]}>
                    <CollectionValueStoryPreview variant={v.id} data={data} width={previewWidth - 4} />
                    {selected && (
                      <View style={styles.check}>
                        <Icon name="check" size={14} color="#FFFFFF" />
                      </View>
                    )}
                  </View>
                  <Text style={[styles.optionLabel, selected && styles.optionLabelSelected]}>{v.label}</Text>
                </TouchableOpacity>
              );
            })}
          </View>

          <TouchableOpacity
            style={[styles.shareButton, sharing && styles.shareButtonDisabled]}
            onPress={handleShare}
            disabled={sharing}
            activeOpacity={0.85}
            accessibilityRole="button"
            accessibilityLabel="Поделиться"
          >
            {sharing ? (
              <ActivityIndicator size="small" color="#FFFFFF" />
            ) : (
              <>
                <Icon name="share" size={18} color="#FFFFFF" />
                <Text style={styles.shareButtonText}>Поделиться</Text>
              </>
            )}
          </TouchableOpacity>
        </Animated.View>
      </Animated.View>

      {/* Полноразмерная копия для снимка — за экраном */}
      <View style={styles.offscreen} pointerEvents="none">
        <View ref={shotRef} collapsable={false} style={{ width: STORY_BASE_WIDTH, height: STORY_BASE_HEIGHT }}>
          <CollectionValueStory variant={variant} data={data} />
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    justifyContent: 'flex-end',
    backgroundColor: 'rgba(11,20,56,0.55)',
  },
  sheet: {
    backgroundColor: Colors.background,
    borderTopLeftRadius: BorderRadius.lg,
    borderTopRightRadius: BorderRadius.lg,
    paddingHorizontal: Spacing.lg,
    paddingTop: Spacing.sm,
  },
  handle: {
    alignSelf: 'center',
    width: 36,
    height: 4,
    borderRadius: 2,
    backgroundColor: Colors.border,
    marginBottom: Spacing.md,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: Spacing.sm,
  },
  title: {
    ...Typography.h1,
    color: Colors.text,
  },
  closeButton: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: Colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sectionLabel: {
    ...Typography.overline,
    color: Colors.textMuted,
    marginBottom: Spacing.md,
  },
  grid: {
    flexDirection: 'row',
    gap: Spacing.sm,
    marginBottom: Spacing.xl,
  },
  option: {
    flex: 1,
    alignItems: 'center',
    gap: Spacing.sm,
  },
  previewFrame: {
    borderRadius: BorderRadius.md,
    borderWidth: 2,
    borderColor: Colors.border,
    overflow: 'hidden',
    backgroundColor: Colors.surface,
  },
  previewFrameSelected: {
    borderColor: Colors.royalBlue,
    ...Shadows.glow,
  },
  check: {
    position: 'absolute',
    top: 8,
    right: 8,
    width: 26,
    height: 26,
    borderRadius: 13,
    backgroundColor: Colors.royalBlue,
    alignItems: 'center',
    justifyContent: 'center',
  },
  optionLabel: {
    ...Typography.bodySmall,
    color: Colors.textSecondary,
  },
  optionLabelSelected: {
    ...Typography.subhead,
    color: Colors.text,
  },
  shareButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: Spacing.sm,
    height: 52,
    borderRadius: BorderRadius.md,
    backgroundColor: Colors.royalBlue,
    ...Shadows.md,
  },
  shareButtonDisabled: {
    opacity: 0.7,
  },
  shareButtonText: {
    ...Typography.button,
    color: '#FFFFFF',
  },
  offscreen: {
    position: 'absolute',
    left: -4000,
    top: 0,
  },
});
