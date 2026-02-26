/**
 * Экран детальной информации о пластинке — Blue Gradient Edition
 */
import { useEffect, useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  Image,
  ActivityIndicator,
  Alert,
  TouchableOpacity,
} from 'react-native';
import { useLocalSearchParams, useRouter, useFocusEffect } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { LinearGradient } from 'expo-linear-gradient';
import { BlurView } from 'expo-blur';
import { Header } from '../../components/Header';
import { GradientText } from '../../components/GradientText';
import { FolderPickerModal } from '../../components/FolderPickerModal';
import { Button, Card, ActionSheet, ActionSheetAction } from '../../components/ui';
import { api } from '../../lib/api';
import { useCollectionStore } from '../../lib/store';
import { VinylRecord, CollectionItem } from '../../lib/types';
import { Colors, Typography, Spacing, BorderRadius, Gradients } from '../../constants/theme';

function getFormatDisplayInfo(format?: string): { label: string; verb: string } {
  if (!format) return { label: 'Винил', verb: 'добавлен' };
  const f = format.toLowerCase();
  if (f.includes('cassette')) return { label: 'Кассета', verb: 'добавлена' };
  if (f.includes('box set')) return { label: 'Бокс-сет', verb: 'добавлен' };
  if (f.includes('cd')) return { label: 'CD', verb: 'добавлен' };
  return { label: 'Винил', verb: 'добавлен' };
}

const handleArtistNavigation = async (artistName: string, router: ReturnType<typeof useRouter>) => {
  try {
    const response = await api.searchArtists(artistName, 1, 1);
    if (response.results.length > 0) {
      router.push(`/artist/${response.results[0].artist_id}`);
    }
  } catch {
    // Silently fail — artist search is best-effort
  }
};

export default function RecordDetailScreen() {
  const { id, folderId, folderItemId } = useLocalSearchParams<{ id: string; folderId?: string; folderItemId?: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [record, setRecord] = useState<VinylRecord | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showActionSheet, setShowActionSheet] = useState(false);
  const [showFolderPicker, setShowFolderPicker] = useState(false);

  const {
    addToCollection,
    addToWishlist,
    removeFromCollection,
    removeFromWishlist,
    moveToCollection,
    collectionItems,
    wishlistItems,
    fetchCollectionItems,
    fetchWishlistItems,
    fetchCollections,
    addItemsToFolder,
  } = useCollectionStore();

  useEffect(() => {
    loadRecord();
  }, [id]);

  // Загружаем и обновляем коллекцию/вишлист при фокусе (включая первый mount)
  useFocusEffect(
    useCallback(() => {
      fetchCollections()
        .then(() => fetchCollectionItems())
        .catch(() => {});
      fetchWishlistItems().catch(() => {});
    }, [fetchCollections, fetchCollectionItems, fetchWishlistItems])
  );

  const getRecordStatus = (): {
    status: import('@/lib/types').RecordStatus;
    copiesCount: number;
    collectionItemId: string | null;
    wishlistItemId: string | null;
  } => {
    if (!record) {
      return { status: 'not_added', copiesCount: 0, collectionItemId: null, wishlistItemId: null };
    }

    const discogsId = record.discogs_id;
    const recordId = record.id;

    const collectionCopies = collectionItems.filter(
      (item) => item.record.discogs_id === discogsId || item.record.id === recordId
    );

    const wishlistItem = wishlistItems.find(
      (item) => item.record.discogs_id === discogsId || item.record.id === recordId
    );

    if (collectionCopies.length > 0) {
      return {
        status: 'in_collection' as const,
        copiesCount: collectionCopies.length,
        collectionItemId: collectionCopies[0].id,
        wishlistItemId: null,
      };
    }

    if (wishlistItem) {
      return {
        status: 'in_wishlist' as const,
        copiesCount: 0,
        collectionItemId: null,
        wishlistItemId: wishlistItem.id,
      };
    }

    return { status: 'not_added' as const, copiesCount: 0, collectionItemId: null, wishlistItemId: null };
  };

  const loadRecord = async () => {
    if (!id) return;

    setIsLoading(true);
    setError(null);

    try {
      // Определяем формат id: UUID или Discogs ID (число)
      const isUUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id);
      const data = isUUID
        ? await api.getRecord(id)
        : await api.getRecordByDiscogsId(id);
      setRecord(data);
    } catch (err) {
      setError('Не удалось загрузить информацию о пластинке');
    } finally {
      setIsLoading(false);
    }
  };

  const handleAddToCollection = async () => {
    if (!record) return;

    const recordStatus = getRecordStatus();

    // Если пластинка уже в вишлисте - переносим атомарно
    if (recordStatus.status === 'in_wishlist' && recordStatus.wishlistItemId) {
      try {
        await moveToCollection(recordStatus.wishlistItemId);
        // Немедленно обновляем UI - критически важно для правильного отображения кнопок
        await Promise.all([
          fetchCollectionItems(),
          fetchWishlistItems(),
        ]);
        Alert.alert('Готово!', 'Винил перенесён в коллекцию');
      } catch (error: any) {
        const message = error?.response?.data?.detail || error?.message || 'Не удалось перенести в коллекцию';
        Alert.alert('Ошибка', message);
      }
      return;
    }

    // Иначе просто добавляем в коллекцию
    const discogsId = String(record.discogs_id || id);
    if (!discogsId) {
      Alert.alert('Ошибка', 'Не найден идентификатор пластинки');
      return;
    }

    try {
      await addToCollection(discogsId);
      // addToCollection уже обновляет оба списка
      const fmt = getFormatDisplayInfo(record?.format_type);
      Alert.alert('Готово!', `${fmt.label} ${fmt.verb} в коллекцию`);
    } catch (error: any) {
      const message = error?.response?.data?.detail || error?.message || 'Не удалось добавить в коллекцию';
      Alert.alert('Ошибка', message);
    }
  };

  const handleAddToWishlist = async () => {
    if (!record) return;

    const discogsId = String(record.discogs_id || id);

    if (!discogsId) {
      Alert.alert('Ошибка', 'Не найден идентификатор пластинки');
      return;
    }

    try {
      await addToWishlist(discogsId);
      const fmt = getFormatDisplayInfo(record?.format_type);
      Alert.alert('Готово!', `${fmt.label} ${fmt.verb} в список желаний`);
    } catch (error: any) {
      const message = error?.response?.data?.detail || error?.message || 'Не удалось добавить в список желаний';
      Alert.alert('Ошибка', message);
    }
  };

  const handleRemoveFromCollection = async () => {
    const status = getRecordStatus();
    if (!status.collectionItemId) return;

    Alert.alert(
      'Удалить из коллекции?',
      `"${record?.title}" будет удалена из вашей коллекции`,
      [
        { text: 'Отмена', style: 'cancel' },
        {
          text: 'Удалить',
          style: 'destructive',
          onPress: async () => {
            try {
              await removeFromCollection(status.collectionItemId!);
              Alert.alert('Готово!', 'Винил удалён из коллекции');
            } catch (error: any) {
              Alert.alert('Ошибка', 'Не удалось удалить из коллекции');
            }
          },
        },
      ]
    );
  };

  const handleRemoveFromWishlist = async () => {
    const status = getRecordStatus();
    if (!status.wishlistItemId) return;

    Alert.alert(
      'Удалить из списка?',
      `"${record?.title}" будет удалена из списка желаний`,
      [
        { text: 'Отмена', style: 'cancel' },
        {
          text: 'Удалить',
          style: 'destructive',
          onPress: async () => {
            try {
              await removeFromWishlist(status.wishlistItemId!);
              Alert.alert('Готово!', 'Винил удалён из списка желаний');
            } catch (error: any) {
              Alert.alert('Ошибка', 'Не удалось удалить из списка');
            }
          },
        },
      ]
    );
  };

  const handleRemoveFromFolder = async () => {
    if (!folderId || !folderItemId) return;

    Alert.alert(
      'Убрать из папки?',
      `"${record?.title}" будет убрана из папки`,
      [
        { text: 'Отмена', style: 'cancel' },
        {
          text: 'Убрать',
          style: 'destructive',
          onPress: async () => {
            try {
              await api.removeFromCollection(folderId, folderItemId);
              await fetchCollections();
              Alert.alert('Готово!', 'Винил убран из папки');
              router.back();
            } catch {
              Alert.alert('Ошибка', 'Не удалось убрать из папки');
            }
          },
        },
      ]
    );
  };

  const handleAddRecordToFolder = async (folderId: string) => {
    const status = getRecordStatus();
    if (!status.collectionItemId || !record) return;
    try {
      const folderData = await api.getCollection(folderId);
      const alreadyInFolder = (folderData.items || []).some(
        (i: CollectionItem) => i.record_id === record.id
      );
      if (alreadyInFolder) {
        setShowFolderPicker(false);
        Alert.alert('Уже есть', 'Эта пластинка уже в этой папке');
        return;
      }
      await addItemsToFolder(folderId, [status.collectionItemId]);
      setShowFolderPicker(false);
      const fmt = getFormatDisplayInfo(record?.format_type);
      Alert.alert('Готово!', `${fmt.label} ${fmt.verb} в папку`);
    } catch {
      Alert.alert('Ошибка', 'Не удалось добавить в папку');
    }
  };

  const getActionSheetActions = (): ActionSheetAction[] => {
    const recordStatus = getRecordStatus();
    const actions: ActionSheetAction[] = [];

    if (recordStatus.status === 'in_collection') {
      // Добавить в папку
      actions.push({
        label: 'Добавить в папку',
        icon: 'folder-outline',
        onPress: () => setShowFolderPicker(true),
      });

      if (folderId && folderItemId) {
        // Открыли из папки — показываем «Убрать из папки»
        actions.push({
          label: 'Убрать из папки',
          icon: 'folder-open-outline',
          onPress: handleRemoveFromFolder,
          destructive: true,
        });
      } else {
        // Открыли из основной коллекции — показываем «Удалить из коллекции»
        actions.push({
          label: 'Удалить',
          icon: 'trash-outline',
          onPress: handleRemoveFromCollection,
          destructive: true,
        });
      }
    }

    return actions;
  };

  if (isLoading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color={Colors.royalBlue} />
      </View>
    );
  }

  if (error || !record) {
    return (
      <View style={styles.container}>
        <Header title="Ошибка" showBack showProfile={false} />
        <View style={styles.centered}>
          <Ionicons name="alert-circle-outline" size={64} color={Colors.textMuted} />
          <Text style={styles.errorText}>{error || 'Винил не найден'}</Text>
          <Button title="Назад" onPress={() => router.back()} variant="outline" />
        </View>
      </View>
    );
  }

  const imageUrl = record.cover_image_url || record.thumb_image_url;

  return (
    <View style={styles.container}>
      <Header title="" showBack showProfile={false} />

      <ScrollView
        contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + 100 }]}
        showsVerticalScrollIndicator={false}
      >
        {/* Обложка */}
        <View style={styles.coverContainer}>
          {imageUrl ? (
            <Image source={{ uri: imageUrl }} style={styles.cover} resizeMode="cover" />
          ) : (
            <View style={[styles.cover, styles.coverPlaceholder]}>
              <Ionicons name="disc-outline" size={80} color={Colors.textMuted} />
            </View>
          )}
        </View>

        {/* Основная информация */}
        <View style={styles.infoSection}>
          <Text style={styles.title}>{record.title}</Text>

          <TouchableOpacity
            style={styles.artistCard}
            onPress={() => record.artist_id
              ? router.push(`/artist/${record.artist_id}`)
              : handleArtistNavigation(record.artist, router)
            }
            activeOpacity={0.7}
          >
            <LinearGradient
              colors={Gradients.blue}
              start={{ x: 0, y: 0 }}
              end={{ x: 1, y: 1 }}
              style={styles.artistAvatarBorder}
            >
              {record.artist_thumb_image_url ? (
                <Image
                  source={{ uri: record.artist_thumb_image_url }}
                  style={styles.artistAvatar}
                />
              ) : (
                <View style={styles.artistAvatarPlaceholder}>
                  <Ionicons name="person" size={24} color={Colors.textMuted} />
                </View>
              )}
            </LinearGradient>
            <Text style={styles.artistName}>{record.artist}</Text>
          </TouchableOpacity>

          <View style={styles.metaRow}>
            {record.year ? (
              <View style={styles.metaItem}>
                <Ionicons name="calendar-outline" size={16} color={Colors.textSecondary} />
                <Text style={styles.metaText}>{record.year}</Text>
              </View>
            ) : null}
            {record.format_type ? (
              <View style={styles.metaItem}>
                <Ionicons name="disc-outline" size={16} color={Colors.textSecondary} />
                <Text style={styles.metaText}>{getFormatDisplayInfo(record.format_type).label}</Text>
              </View>
            ) : null}
            {record.country ? (
              <View style={styles.metaItem}>
                <Ionicons name="globe-outline" size={16} color={Colors.textSecondary} />
                <Text style={styles.metaText}>{record.country}</Text>
              </View>
            ) : null}
          </View>
        </View>

        {/* Лейбл и каталог */}
        {(record.label || record.catalog_number) && (
          <Card variant="flat" style={styles.card}>
            <Text style={styles.cardTitle}>Издание</Text>
            {record.label && (
              <View style={styles.detailRow}>
                <Text style={styles.detailLabel}>Лейбл</Text>
                <Text style={styles.detailValue}>{record.label}</Text>
              </View>
            )}
            {record.catalog_number && (
              <View style={styles.detailRow}>
                <Text style={styles.detailLabel}>Каталожный №</Text>
                <Text style={styles.detailValue}>{record.catalog_number}</Text>
              </View>
            )}
          </Card>
        )}

        {/* Жанр */}
        {(record.genre || record.style) && (
          <Card variant="flat" style={styles.card}>
            <Text style={styles.cardTitle}>Жанр</Text>
            {record.genre && <Text style={styles.genreText}>{record.genre}</Text>}
            {record.style && (
              <Text style={styles.styleText}>{record.style}</Text>
            )}
          </Card>
        )}

        {/* Цена */}
        {(() => {
          const rubPrice = record.estimated_price_median_rub || record.estimated_price_min_rub;
          const usdPrice = record.estimated_price_median || record.estimated_price_min;
          if (!rubPrice && !usdPrice) return null;

          return (
            <Card variant="flat" style={styles.card}>
              <Text style={[styles.cardTitle, { textAlign: 'center' }]}>Примерная стоимость</Text>

              {rubPrice ? (
                <View style={styles.priceContainer}>
                  {record.estimated_price_min_rub && record.estimated_price_median_rub ? (
                    <View style={styles.priceItem}>
                      <Text style={styles.priceLabel}>от</Text>
                      <Text style={styles.priceValue}>
                        {Math.round(record.estimated_price_min_rub).toLocaleString('ru-RU')} ₽
                      </Text>
                    </View>
                  ) : null}
                  <View style={styles.priceItem}>
                    <Text style={styles.priceLabel}>{record.estimated_price_median_rub ? '~' : 'от'}</Text>
                    <GradientText style={styles.priceMedian}>
                      {Math.round(rubPrice).toLocaleString('ru-RU')} ₽
                    </GradientText>
                  </View>
                  {record.estimated_price_max_rub ? (
                    <View style={styles.priceItem}>
                      <Text style={styles.priceLabel}>до</Text>
                      <Text style={styles.priceValue}>
                        {Math.round(record.estimated_price_max_rub).toLocaleString('ru-RU')} ₽
                      </Text>
                    </View>
                  ) : null}
                </View>
              ) : null}

              {usdPrice != null ? (
                <Text style={styles.priceNote}>
                  Discogs: ${Number(usdPrice).toFixed(2)}
                  {record.usd_rub_rate ? ` · курс ${Number(record.usd_rub_rate).toFixed(1)} ₽` : ''}
                  {record.ru_markup ? ` · × ${record.ru_markup}` : ''}
                </Text>
              ) : null}
            </Card>
          );
        })()}

        {/* Треклист */}
        {record.tracklist && record.tracklist.length > 0 && (
          <Card variant="flat" style={styles.card}>
            <Text style={styles.cardTitle}>Треклист</Text>
            {record.tracklist.map((track, index) => (
              <View key={index} style={styles.trackRow}>
                <Text style={styles.trackPosition}>{track.position || index + 1}</Text>
                <Text style={styles.trackTitle} numberOfLines={1}>
                  {track.title}
                </Text>
                {track.duration && (
                  <Text style={styles.trackDuration}>{track.duration}</Text>
                )}
              </View>
            ))}
          </Card>
        )}
      </ScrollView>

      {/* Кнопки действий */}
      {(() => {
        const recordStatus = getRecordStatus();

        // ========== СТАТУС: В КОЛЛЕКЦИИ ==========
        if (recordStatus.status === 'in_collection') {
          return (
            <BlurView intensity={60} tint="light" style={[styles.actionsContainer, { paddingBottom: insets.bottom + Spacing.md }]}>
              <View style={styles.addedButtonContainer}>
                <View style={styles.addedButton}>
                  <Ionicons name="checkmark-circle" size={20} color={Colors.textSecondary} />
                  <Text style={styles.addedButtonText}>
                    {recordStatus.copiesCount > 1
                      ? `Добавлено (${recordStatus.copiesCount})`
                      : 'Добавлено'
                    }
                  </Text>
                </View>
                <TouchableOpacity
                  style={styles.moreButton}
                  onPress={() => setShowActionSheet(true)}
                >
                  <Ionicons name="ellipsis-vertical" size={24} color={Colors.background} />
                </TouchableOpacity>
              </View>
            </BlurView>
          );
        }

        // ========== СТАТУС: В ВИШЛИСТЕ ==========
        if (recordStatus.status === 'in_wishlist') {
          return (
            <BlurView intensity={60} tint="light" style={[styles.actionsContainer, { paddingBottom: insets.bottom + Spacing.md }]}>
              <Button
                title="Добавить"
                onPress={handleAddToCollection}
                style={styles.actionButton}
              />
              <TouchableOpacity
                style={[styles.actionButton, styles.removeButton]}
                onPress={handleRemoveFromWishlist}
              >
                <Text style={styles.removeButtonText}>Удалить</Text>
              </TouchableOpacity>
            </BlurView>
          );
        }

        // ========== СТАТУС: НЕ ДОБАВЛЕНА ==========
        return (
          <BlurView intensity={60} tint="light" style={[styles.actionsContainer, { paddingBottom: insets.bottom + Spacing.md }]}>
            <Button
              title="Добавить"
              onPress={handleAddToCollection}
              style={styles.actionButton}
            />
            <Button
              title="В вишлист"
              onPress={handleAddToWishlist}
              variant="outline"
              style={{ ...styles.actionButton, backgroundColor: Colors.surface }}
            />
          </BlurView>
        );
      })()}

      {/* ActionSheet для действий с пластинкой в коллекции */}
      <ActionSheet
        visible={showActionSheet}
        actions={getActionSheetActions()}
        onClose={() => setShowActionSheet(false)}
      />

      <FolderPickerModal
        visible={showFolderPicker}
        onClose={() => setShowFolderPicker(false)}
        onSelectFolder={handleAddRecordToFolder}
        selectedRecordIds={record ? [record.id] : []}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  centered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: Spacing.lg,
  },
  errorText: {
    ...Typography.body,
    color: Colors.textSecondary,
    textAlign: 'center',
    marginVertical: Spacing.lg,
  },
  content: {
    padding: Spacing.md,
  },
  coverContainer: {
    alignItems: 'center',
    marginBottom: Spacing.lg,
  },
  cover: {
    width: '100%',
    aspectRatio: 1,
    borderRadius: 24,
  },
  coverPlaceholder: {
    backgroundColor: Colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
  },
  infoSection: {
    marginBottom: Spacing.lg,
  },
  artistCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.lg,
    padding: Spacing.sm,
    marginBottom: Spacing.md,
    gap: Spacing.sm,
  },
  artistAvatarBorder: {
    width: 52,
    height: 52,
    borderRadius: 26,
    padding: 2,
  },
  artistAvatar: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: Colors.surface,
  },
  artistAvatarPlaceholder: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: Colors.surface,
    justifyContent: 'center',
    alignItems: 'center',
  },
  artistName: {
    ...Typography.body,
    color: Colors.text,
    fontWeight: '500',
    flex: 1,
  },
  title: {
    fontSize: 36,
    fontFamily: 'Inter_800ExtraBold',
    lineHeight: 42,
    letterSpacing: -1,
    color: Colors.deepNavy,
    marginBottom: Spacing.md,
  },
  metaRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.md,
  },
  metaItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.xs,
  },
  metaText: {
    ...Typography.bodySmall,
    color: Colors.textSecondary,
  },
  card: {
    marginBottom: Spacing.md,
  },
  cardTitle: {
    ...Typography.h4,
    color: Colors.deepNavy,
    marginBottom: Spacing.sm,
  },
  detailRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: Spacing.xs,
  },
  detailLabel: {
    ...Typography.bodySmall,
    color: Colors.textSecondary,
  },
  detailValue: {
    ...Typography.bodySmall,
    color: Colors.text,
    fontWeight: '500',
  },
  genreText: {
    ...Typography.body,
    color: Colors.text,
  },
  styleText: {
    ...Typography.bodySmall,
    color: Colors.textSecondary,
    marginTop: Spacing.xs,
  },
  priceContainer: {
    flexDirection: 'row',
    justifyContent: 'space-around',
  },
  priceItem: {
    alignItems: 'center',
  },
  priceLabel: {
    ...Typography.caption,
    color: Colors.textSecondary,
    marginBottom: Spacing.xs,
  },
  priceValue: {
    ...Typography.h4,
    color: Colors.text,
  },
  priceMedian: {
    ...Typography.h4,
    fontFamily: 'Inter_700Bold',
  },
  priceNote: {
    ...Typography.caption,
    color: Colors.textMuted,
    textAlign: 'center' as const,
    marginTop: Spacing.sm,
  },
  trackRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: Spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: Colors.divider,
  },
  trackPosition: {
    ...Typography.caption,
    color: Colors.textMuted,
    width: 30,
  },
  trackTitle: {
    ...Typography.body,
    color: Colors.text,
    flex: 1,
  },
  trackDuration: {
    ...Typography.caption,
    color: Colors.textSecondary,
    marginLeft: Spacing.sm,
  },
  actionsContainer: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    flexDirection: 'row',
    padding: Spacing.md,
    backgroundColor: Colors.glassBg,
    gap: Spacing.sm,
    overflow: 'hidden',
  },
  actionButton: {
    flex: 1,
  },
  addedButtonContainer: {
    flex: 1,
    flexDirection: 'row',
    gap: Spacing.sm,
    alignItems: 'center',
  },
  addedButton: {
    flex: 1,
    height: 56,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: Spacing.sm,
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.md,
  },
  addedButtonText: {
    ...Typography.button,
    color: Colors.textSecondary,
  },
  moreButton: {
    width: 56,
    height: 56,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: Colors.royalBlue,
    borderRadius: BorderRadius.md,
  },
  removeButton: {
    flex: 1,
    height: 56,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.md,
  },
  removeButtonText: {
    ...Typography.button,
    color: Colors.text,
  },
});
