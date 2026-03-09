/**
 * Экран профиля (модальный) — Blue Gradient Edition
 */
import { useCallback, useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Alert,
  ScrollView,
  Share,
  ActionSheetIOS,
  Platform,
  ActivityIndicator,
} from 'react-native';
import { Image } from 'expo-image';
import ReanimatedSwipeable from 'react-native-gesture-handler/ReanimatedSwipeable';
import Reanimated, { SharedValue, useAnimatedStyle, interpolate } from 'react-native-reanimated';
import { File, Paths } from 'expo-file-system';
import * as Sharing from 'expo-sharing';
import * as Clipboard from 'expo-clipboard';
import { LinearGradient } from 'expo-linear-gradient';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useAuthStore, useCollectionStore, useOnboardingStore } from '../lib/store';
import { CollectionTab, GiftGivenItem } from '../lib/types';
import { Button } from '../components/ui';
import { AnimatedGradientText } from '../components/AnimatedGradientText';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { api } from '../lib/api';
import { Colors, Typography, Spacing, BorderRadius, Shadows } from '../constants/theme';

function SwipeDeleteAction({ drag, onPress }: { drag: SharedValue<number>; onPress: () => void }) {
  const animatedStyle = useAnimatedStyle(() => ({
    opacity: interpolate(Math.abs(drag.value), [0, 60], [0, 1]),
  }));

  return (
    <Reanimated.View style={[styles.swipeAction, animatedStyle]}>
      <TouchableOpacity style={styles.swipeActionButton} onPress={onPress}>
        <Ionicons name="close-circle" size={22} color={Colors.background} />
      </TouchableOpacity>
    </Reanimated.View>
  );
}

export default function ProfileScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { user, logout } = useAuthStore();
  const { collectionItems, wishlistItems, setActiveTab } = useCollectionStore();
  const onboarding = useOnboardingStore();

  const handleClose = () => {
    router.back();
  };

  const handleLogout = () => {
    Alert.alert(
      'Выйти из аккаунта?',
      'Вы уверены, что хотите выйти?',
      [
        { text: 'Отмена', style: 'cancel' },
        {
          text: 'Выйти',
          style: 'destructive',
          onPress: async () => {
            await logout();
            router.replace('/(auth)/login');
          },
        },
      ]
    );
  };

  const handleStatPress = (tab: CollectionTab) => {
    setActiveTab(tab);
    router.dismiss();
    router.navigate('/(tabs)/collection');
  };

  const [copied, setCopied] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [givenGifts, setGivenGifts] = useState<GiftGivenItem[]>([]);
  const [giftsLoading, setGiftsLoading] = useState(true);

  const loadGivenGifts = useCallback(async () => {
    try {
      const data = await api.getMyGivenGifts();
      setGivenGifts(data);
    } catch {
      // Не блокируем профиль
    } finally {
      setGiftsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadGivenGifts();
  }, [loadGivenGifts]);

  const handleCancelGift = useCallback((gift: GiftGivenItem) => {
    Alert.alert(
      'Отменить бронирование?',
      `${gift.record.artist} — ${gift.record.title}`,
      [
        { text: 'Нет', style: 'cancel' },
        {
          text: 'Отменить',
          style: 'destructive',
          onPress: async () => {
            try {
              await api.cancelGiftBooking(gift.id, gift.cancel_token);
              setGivenGifts(prev => prev.filter(g => g.id !== gift.id));
            } catch {
              Alert.alert('Ошибка', 'Не удалось отменить бронирование');
            }
          },
        },
      ]
    );
  }, []);

  const profileUrl = user ? `https://vinyl-vertushka.ru/@${user.username}` : '';

  const handleCopyLink = useCallback(async () => {
    await Clipboard.setStringAsync(profileUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [profileUrl]);

  const handleShareProfile = useCallback(async () => {
    try {
      await Share.share({
        message: `Моя коллекция винила: ${profileUrl}`,
        url: profileUrl,
      });
    } catch {
      // Пользователь отменил
    }
  }, [profileUrl]);

  const handleExport = useCallback(async (type: 'collection' | 'wishlist') => {
    setExporting(true);
    try {
      const csvData = type === 'collection'
        ? await api.exportCollectionCSV()
        : await api.exportWishlistCSV();

      const filename = type === 'collection'
        ? 'vertushka_collection.csv'
        : 'vertushka_wishlist.csv';

      const file = new File(Paths.cache, filename);
      file.create({ overwrite: true });
      file.write(csvData);

      await Sharing.shareAsync(file.uri, {
        mimeType: 'text/csv',
        dialogTitle: type === 'collection' ? 'Экспорт коллекции' : 'Экспорт вишлиста',
        UTI: 'public.comma-separated-values-text',
      });
    } catch {
      Alert.alert('Ошибка', 'Не удалось экспортировать данные');
    } finally {
      setExporting(false);
    }
  }, []);

  const handleExportPress = useCallback(() => {
    const options = ['Коллекция (CSV)', 'Вишлист (CSV)', 'Отмена'];
    const cancelButtonIndex = 2;

    if (Platform.OS === 'ios') {
      ActionSheetIOS.showActionSheetWithOptions(
        { options, cancelButtonIndex, title: 'Экспорт данных' },
        (buttonIndex) => {
          if (buttonIndex === 0) handleExport('collection');
          else if (buttonIndex === 1) handleExport('wishlist');
        },
      );
    } else {
      Alert.alert('Экспорт данных', 'Выберите что экспортировать', [
        { text: 'Коллекция (CSV)', onPress: () => handleExport('collection') },
        { text: 'Вишлист (CSV)', onPress: () => handleExport('wishlist') },
        { text: 'Отмена', style: 'cancel' },
      ]);
    }
  }, [handleExport]);

  const stats = [
    {
      label: 'В коллекции',
      value: collectionItems.length,
      icon: 'disc-outline' as const,
      tab: 'collection' as CollectionTab,
    },
    {
      label: 'В списке желаний',
      value: wishlistItems.length,
      icon: 'heart-outline' as const,
      tab: 'wishlist' as CollectionTab,
    },
  ];

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      {/* Editorial header */}
      <View style={styles.header}>
        <AnimatedGradientText style={Typography.display}>Профиль</AnimatedGradientText>
        <TouchableOpacity onPress={handleClose} style={styles.closeButton}>
          <Ionicons name="close" size={28} color={Colors.deepNavy} />
        </TouchableOpacity>
      </View>

      <ScrollView
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
      >
        {/* Аватар и имя */}
        <View style={styles.profileSection}>
          <View style={styles.avatarContainer}>
            {user?.avatar_url ? (
              <Image source={user.avatar_url} style={styles.avatar} cachePolicy="disk" />
            ) : (
              <LinearGradient
                colors={[Colors.royalBlue, Colors.periwinkle]}
                style={styles.avatarPlaceholder}
              >
                <Ionicons name="disc" size={48} color={Colors.background} />
              </LinearGradient>
            )}
          </View>

          <Text style={styles.displayName}>
            {user?.display_name || user?.username || 'Пользователь'}
          </Text>
          <Text style={styles.email}>{user?.email}</Text>
        </View>

        {/* Статистика */}
        <View style={styles.statsContainer}>
          {stats.map((stat, index) => (
            <TouchableOpacity
              key={index}
              style={[styles.statCard, Shadows.lg]}
              onPress={() => handleStatPress(stat.tab)}
              activeOpacity={0.7}
            >
              <Ionicons name={stat.icon} size={24} color={Colors.royalBlue} />
              <Text style={styles.statValue}>{stat.value}</Text>
              <Text style={styles.statLabel}>{stat.label}</Text>
            </TouchableOpacity>
          ))}
        </View>

        {/* Ссылка на профиль */}
        <View style={[styles.linkCard, Shadows.sm]}>
          <Text style={styles.linkLabel}>Ваш профиль</Text>
          <Text style={styles.linkUrl}>{profileUrl}</Text>
          <View style={styles.linkActions}>
            <TouchableOpacity style={styles.linkButton} onPress={handleCopyLink}>
              <Ionicons name={copied ? "checkmark-outline" : "copy-outline"} size={18} color={Colors.royalBlue} />
              <Text style={styles.linkButtonText}>{copied ? 'Скопировано' : 'Копировать'}</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.linkButton} onPress={handleShareProfile}>
              <Ionicons name="share-outline" size={18} color={Colors.royalBlue} />
              <Text style={styles.linkButtonText}>Поделиться</Text>
            </TouchableOpacity>
          </View>
        </View>

        {/* Секция «Я дарю» */}
        {giftsLoading ? (
          <View style={[styles.giftsCard, Shadows.sm]}>
            <ActivityIndicator size="small" color={Colors.royalBlue} style={{ marginVertical: Spacing.md }} />
          </View>
        ) : givenGifts.length === 0 ? (
          <LinearGradient
            colors={[Colors.royalBlue + '08', Colors.periwinkle + '12']}
            style={styles.giftsBanner}
          >
            <View style={styles.giftsBannerRow}>
              <View style={styles.giftsBannerIcon}>
                <Ionicons name="gift-outline" size={24} color={Colors.royalBlue} />
              </View>
              <View style={styles.giftsBannerTextContainer}>
                <Text style={styles.giftsBannerTitle}>Дари друзьям музыку</Text>
                <Text style={styles.giftsBannerSubtitle}>
                  Забронируй пластинку из вишлиста друга — он не узнает, кто дарит
                </Text>
              </View>
            </View>
          </LinearGradient>
        ) : (
          <View style={[styles.giftsCard, Shadows.sm]}>
            <View style={styles.giftsCardHeader}>
              <Ionicons name="gift-outline" size={18} color={Colors.royalBlue} />
              <Text style={styles.giftsCardTitle}>Я дарю</Text>
              <Text style={styles.giftsCardCount}>{givenGifts.length}</Text>
            </View>
            <ScrollView
              horizontal
              showsHorizontalScrollIndicator={false}
              contentContainerStyle={styles.giftsScrollContent}
            >
              {givenGifts.map((gift) => (
                <ReanimatedSwipeable
                  key={gift.id}
                  friction={2}
                  rightThreshold={40}
                  renderRightActions={(_progress: SharedValue<number>, drag: SharedValue<number>) => (
                    <SwipeDeleteAction drag={drag} onPress={() => handleCancelGift(gift)} />
                  )}
                  containerStyle={styles.swipeableContainer}
                >
                  <TouchableOpacity
                    style={styles.giftCard}
                    activeOpacity={0.7}
                    onPress={() => router.push(`/record/${gift.record.id}`)}
                  >
                    {gift.record.cover_image_url ? (
                      <Image
                        source={gift.record.cover_image_url}
                        style={styles.giftCardCover}
                        contentFit="cover"
                        cachePolicy="disk"
                      />
                    ) : (
                      <View style={[styles.giftCardCover, styles.giftCardCoverPlaceholder]}>
                        <Ionicons name="disc-outline" size={24} color={Colors.textMuted} />
                      </View>
                    )}
                    <Text style={styles.giftCardTitle} numberOfLines={1}>
                      {gift.record.title}
                    </Text>
                    <Text style={styles.giftCardArtist} numberOfLines={1}>
                      {gift.record.artist}
                    </Text>
                    <View style={styles.giftCardRecipient}>
                      {gift.for_user.avatar_url ? (
                        <Image source={gift.for_user.avatar_url} style={styles.giftCardAvatar} cachePolicy="disk" />
                      ) : (
                        <View style={[styles.giftCardAvatar, styles.giftCardAvatarPlaceholder]}>
                          <Ionicons name="person" size={8} color={Colors.background} />
                        </View>
                      )}
                      <Text style={styles.giftCardRecipientName} numberOfLines={1}>
                        для @{gift.for_user.username}
                      </Text>
                    </View>
                    <View style={[
                      styles.giftCardStatus,
                      gift.status === 'completed' && styles.giftCardStatusCompleted,
                    ]}>
                      <View style={[
                        styles.giftCardStatusDot,
                        { backgroundColor: gift.status === 'completed' ? Colors.success : Colors.royalBlue },
                      ]} />
                      <Text style={[
                        styles.giftCardStatusText,
                        { color: gift.status === 'completed' ? Colors.success : Colors.royalBlue },
                      ]}>
                        {gift.status === 'completed' ? 'Вручено' : 'Активно'}
                      </Text>
                    </View>
                  </TouchableOpacity>
                </ReanimatedSwipeable>
              ))}
            </ScrollView>
          </View>
        )}

        {/* Настройки */}
        <View style={styles.settingsSection}>
          <Text style={styles.sectionTitle}>Настройки</Text>

          <TouchableOpacity
            style={styles.settingsItem}
            onPress={() => router.push('/settings/edit-profile')}
          >
            <Ionicons name="person-outline" size={24} color={Colors.royalBlue} />
            <Text style={styles.settingsItemText}>Редактировать профиль</Text>
            <Ionicons name="chevron-forward" size={20} color={Colors.textMuted} />
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.settingsItem}
            onPress={() => router.push('/settings/share-profile')}
          >
            <Ionicons name="globe-outline" size={24} color={Colors.royalBlue} />
            <Text style={styles.settingsItemText}>Настройки профиля</Text>
            <Ionicons name="chevron-forward" size={20} color={Colors.textMuted} />
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.settingsItem}
            onPress={handleExportPress}
            disabled={exporting}
          >
            {exporting ? (
              <ActivityIndicator size="small" color={Colors.royalBlue} />
            ) : (
              <Ionicons name="download-outline" size={24} color={Colors.royalBlue} />
            )}
            <Text style={styles.settingsItemText}>Экспорт данных</Text>
            <Ionicons name="chevron-forward" size={20} color={Colors.textMuted} />
          </TouchableOpacity>

          <TouchableOpacity style={styles.settingsItem}>
            <Ionicons name="notifications-outline" size={24} color={Colors.royalBlue} />
            <Text style={styles.settingsItemText}>Уведомления</Text>
            <Ionicons name="chevron-forward" size={20} color={Colors.textMuted} />
          </TouchableOpacity>

          <TouchableOpacity style={styles.settingsItem}>
            <Ionicons name="help-circle-outline" size={24} color={Colors.royalBlue} />
            <Text style={styles.settingsItemText}>Помощь</Text>
            <Ionicons name="chevron-forward" size={20} color={Colors.textMuted} />
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.settingsItem}
            onPress={async () => {
              await AsyncStorage.removeItem('@vertushka:onboarding_complete');
              await onboarding.checkOnboarding();
              router.dismiss();
            }}
          >
            <Ionicons name="refresh-outline" size={24} color={Colors.warning} />
            <Text style={styles.settingsItemText}>Запустить онбординг</Text>
            <Ionicons name="chevron-forward" size={20} color={Colors.textMuted} />
          </TouchableOpacity>
        </View>

        {/* Кнопка выхода */}
        <View style={styles.logoutSection}>
          <Button
            title="Выйти из аккаунта"
            onPress={handleLogout}
            variant="outline"
            fullWidth
          />
        </View>

        {/* Версия */}
        <Text style={styles.version}>Вертушка v1.0.0</Text>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-end',
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm,
  },
  closeButton: {
    padding: Spacing.xs,
  },
  content: {
    padding: Spacing.lg,
  },
  profileSection: {
    alignItems: 'center',
    marginBottom: Spacing.xl,
  },
  avatarContainer: {
    marginBottom: Spacing.md,
  },
  avatar: {
    width: 100,
    height: 100,
    borderRadius: 50,
  },
  avatarPlaceholder: {
    width: 100,
    height: 100,
    borderRadius: 50,
    alignItems: 'center',
    justifyContent: 'center',
  },
  displayName: {
    ...Typography.h2,
    color: Colors.deepNavy,
    marginBottom: Spacing.xs,
  },
  email: {
    ...Typography.body,
    color: Colors.textSecondary,
  },
  statsContainer: {
    flexDirection: 'row',
    gap: Spacing.md,
    marginBottom: Spacing.xl,
  },
  statCard: {
    flex: 1,
    backgroundColor: Colors.background,
    borderRadius: BorderRadius.lg,
    padding: Spacing.md,
    alignItems: 'center',
  },
  statValue: {
    fontSize: 36,
    fontFamily: 'Inter_800ExtraBold',
    lineHeight: 42,
    color: Colors.deepNavy,
    marginTop: Spacing.sm,
  },
  statLabel: {
    ...Typography.caption,
    color: Colors.textSecondary,
    textAlign: 'center',
  },
  linkCard: {
    backgroundColor: Colors.background,
    borderRadius: BorderRadius.lg,
    padding: Spacing.lg,
    marginBottom: Spacing.xl,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  linkLabel: {
    ...Typography.caption,
    color: Colors.textSecondary,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: Spacing.xs,
  },
  linkUrl: {
    ...Typography.bodyBold,
    color: Colors.royalBlue,
    marginBottom: Spacing.md,
  },
  linkActions: {
    flexDirection: 'row',
    gap: Spacing.md,
  },
  linkButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.xs,
    paddingVertical: Spacing.sm,
    paddingHorizontal: Spacing.md,
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.md,
  },
  linkButtonText: {
    ...Typography.buttonSmall,
    color: Colors.royalBlue,
  },
  settingsSection: {
    marginBottom: Spacing.xl,
    gap: Spacing.sm,
  },
  sectionTitle: {
    ...Typography.h4,
    color: Colors.deepNavy,
    marginBottom: Spacing.sm,
  },
  settingsItem: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: Spacing.md,
    backgroundColor: Colors.background,
    borderRadius: BorderRadius.lg,
    gap: Spacing.md,
    ...Shadows.sm,
  },
  settingsItemText: {
    ...Typography.body,
    color: Colors.text,
    flex: 1,
  },
  logoutSection: {
    marginBottom: Spacing.lg,
  },
  version: {
    ...Typography.caption,
    color: Colors.textMuted,
    textAlign: 'center',
  },
  // Секция «Я дарю»
  giftsCard: {
    backgroundColor: Colors.background,
    borderRadius: BorderRadius.lg,
    padding: Spacing.md,
    marginBottom: Spacing.xl,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  giftsCardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.xs,
    marginBottom: Spacing.md,
  },
  giftsCardTitle: {
    ...Typography.bodyBold,
    color: Colors.deepNavy,
    flex: 1,
  },
  giftsCardCount: {
    ...Typography.caption,
    color: Colors.textSecondary,
    backgroundColor: Colors.surface,
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 10,
    overflow: 'hidden',
  },
  giftsBanner: {
    borderRadius: BorderRadius.lg,
    padding: Spacing.lg,
    marginBottom: Spacing.xl,
    borderWidth: 1,
    borderColor: Colors.royalBlue + '15',
  },
  giftsBannerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.md,
  },
  giftsBannerIcon: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: Colors.royalBlue + '12',
    alignItems: 'center',
    justifyContent: 'center',
  },
  giftsBannerTextContainer: {
    flex: 1,
  },
  giftsBannerTitle: {
    ...Typography.bodyBold,
    color: Colors.deepNavy,
    marginBottom: 2,
  },
  giftsBannerSubtitle: {
    ...Typography.caption,
    color: Colors.textSecondary,
    lineHeight: 18,
  },
  giftsScrollContent: {
    gap: Spacing.md,
  },
  swipeableContainer: {
    overflow: 'visible',
  },
  giftCard: {
    width: 140,
    backgroundColor: Colors.background,
    borderRadius: BorderRadius.lg,
    padding: Spacing.sm,
  },
  giftCardCover: {
    width: '100%',
    aspectRatio: 1,
    borderRadius: BorderRadius.md,
    marginBottom: Spacing.sm,
  },
  giftCardCoverPlaceholder: {
    backgroundColor: Colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
  },
  giftCardTitle: {
    ...Typography.bodyBold,
    fontSize: 13,
    color: Colors.deepNavy,
    lineHeight: 16,
  },
  giftCardArtist: {
    ...Typography.caption,
    fontSize: 12,
    color: Colors.textSecondary,
    marginBottom: Spacing.sm,
  },
  giftCardRecipient: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    marginBottom: Spacing.xs,
  },
  giftCardAvatar: {
    width: 16,
    height: 16,
    borderRadius: 8,
  },
  giftCardAvatarPlaceholder: {
    backgroundColor: Colors.royalBlue,
    alignItems: 'center',
    justifyContent: 'center',
  },
  giftCardRecipientName: {
    ...Typography.caption,
    fontSize: 11,
    color: Colors.royalBlue,
    flex: 1,
  },
  giftCardStatus: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  giftCardStatusCompleted: {
    opacity: 0.8,
  },
  giftCardStatusDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
  },
  giftCardStatusText: {
    ...Typography.caption,
    fontSize: 11,
  },
  swipeAction: {
    justifyContent: 'center',
    alignItems: 'center',
    width: 56,
  },
  swipeActionButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: Colors.error,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
