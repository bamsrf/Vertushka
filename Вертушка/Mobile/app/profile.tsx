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
  Linking,
} from 'react-native';
import { Image } from 'expo-image';
import { File, Paths } from 'expo-file-system';
import * as Sharing from 'expo-sharing';
import * as Clipboard from 'expo-clipboard';
import { LinearGradient } from 'expo-linear-gradient';
import { useRouter } from 'expo-router';
import { Icon } from '@/components/ui';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useAuthStore, useCollectionStore, useOnboardingStore, useFollowStore, useGiftStore } from '../lib/store';
import { useMessagesStore } from '../lib/messagesStore';
import { useTourTarget } from '../lib/useTourTarget';
import { ms } from '../lib/responsive';
import { OnboardingOverlay } from '../components/OnboardingOverlay';
import { CollectionTab, GiftGivenItem } from '../lib/types';
import { Button } from '../components/ui';
import { AnimatedGradientText } from '../components/AnimatedGradientText';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as ImagePicker from 'expo-image-picker';
import { api, resolveMediaUrl } from '../lib/api';
import { cleanArtistName } from '../lib/format';
import { detectAchievementUnlocks } from '../lib/achievementsBus';
import { toast } from '../lib/toast';
import Toast from 'react-native-toast-message';
import { toastConfig } from '../components/CustomToast';
import { Colors, Typography, Spacing, BorderRadius, Shadows } from '../constants/theme';
import { AchievementsBlock } from '../components/AchievementsBlock';
import { ArchetypeChip } from '../components/ArchetypeChip';
import { ActivityCard } from '../components/notifications/ActivityCard';

function MessagesMenuItem({ onPress }: { onPress: () => void }) {
  const unread = useMessagesStore((s) => s.unread.primary + s.unread.requests);
  return (
    <TouchableOpacity style={styles.settingsItem} onPress={onPress}>
      <Icon name="chat-circle" size={24} color={Colors.royalBlue} />
      <Text style={styles.settingsItemText}>Сообщения</Text>
      {unread > 0 ? (
        <View style={styles.followReqBadge}>
          <Text style={styles.followReqBadgeTxt}>{unread > 99 ? '99+' : unread}</Text>
        </View>
      ) : null}
    </TouchableOpacity>
  );
}

function FollowRequestsMenuItem({ onPress }: { onPress: () => void }) {
  const [count, setCount] = useState(0);
  useEffect(() => {
    let cancelled = false;
    api
      .getIncomingFollowRequestsCount()
      .then((c) => {
        if (!cancelled) setCount(c);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);
  return (
    <TouchableOpacity style={styles.settingsItem} onPress={onPress}>
      <Icon name="person-add-outline" size={24} color={Colors.royalBlue} />
      <Text style={styles.settingsItemText}>Запросы на подписку</Text>
      {count > 0 ? (
        <View style={styles.followReqBadge}>
          <Text style={styles.followReqBadgeTxt}>{count > 99 ? '99+' : count}</Text>
        </View>
      ) : null}
    </TouchableOpacity>
  );
}

export default function ProfileScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const shareTarget = useTourTarget('profile-share');
  const { user, logout, setUser } = useAuthStore();
  const { collectionItems, wishlistItems, stats, setActiveTab, fetchCollectionItems, fetchWishlistItems, fetchStats } = useCollectionStore();
  const onboarding = useOnboardingStore();
  const { followers, following, fetchFollowers, fetchFollowing } = useFollowStore();
  const { given: givenGifts, isLoaded: giftsLoaded, loadAll: loadGifts } = useGiftStore();

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
  const [avatarUploading, setAvatarUploading] = useState(false);
  // §11: раздел «Мои релизы» появляется после первого ручного релиза.
  const [hasUserRecords, setHasUserRecords] = useState(false);

  useEffect(() => {
    let alive = true;
    api
      .listMyUserRecords()
      .then((recs) => {
        if (alive) setHasUserRecords(recs.length > 0);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  const pickImage = useCallback(async (source: 'library' | 'camera') => {
    const launcher = source === 'library'
      ? ImagePicker.launchImageLibraryAsync
      : ImagePicker.launchCameraAsync;

    const result = await launcher({
      mediaTypes: ['images'],
      allowsEditing: true,
      aspect: [1, 1],
      quality: 0.8,
    });

    if (result.canceled || !result.assets?.[0]) return;

    setAvatarUploading(true);
    try {
      const { avatar_url } = await api.uploadAvatar(result.assets[0].uri);
      setUser({ ...user!, avatar_url: `${avatar_url}?t=${Date.now()}` });
      // Возможный анлок A3 «Аватар»
      detectAchievementUnlocks();
    } catch {
      toast.error('Не удалось загрузить аватарку');
    } finally {
      setAvatarUploading(false);
    }
  }, [user, setUser]);

  const handleAvatarPress = useCallback(() => {
    const hasAvatar = !!user?.avatar_url;
    const options = hasAvatar
      ? ['Выбрать из галереи', 'Сделать фото', 'Удалить аватарку', 'Отмена']
      : ['Выбрать из галереи', 'Сделать фото', 'Отмена'];
    const cancelIndex = options.length - 1;
    const destructiveIndex = hasAvatar ? 2 : undefined;

    if (Platform.OS === 'ios') {
      ActionSheetIOS.showActionSheetWithOptions(
        { options, cancelButtonIndex: cancelIndex, destructiveButtonIndex: destructiveIndex },
        async (index) => {
          if (index === 0) pickImage('library');
          else if (index === 1) pickImage('camera');
          else if (hasAvatar && index === 2) {
            setAvatarUploading(true);
            try {
              await api.deleteAvatar();
              setUser({ ...user!, avatar_url: undefined as any });
            } catch {
              toast.error('Не удалось удалить аватарку');
            } finally {
              setAvatarUploading(false);
            }
          }
        },
      );
    } else {
      const buttons: any[] = [
        { text: 'Выбрать из галереи', onPress: () => pickImage('library') },
        { text: 'Сделать фото', onPress: () => pickImage('camera') },
      ];
      if (hasAvatar) {
        buttons.push({
          text: 'Удалить аватарку',
          style: 'destructive',
          onPress: async () => {
            setAvatarUploading(true);
            try {
              await api.deleteAvatar();
              setUser({ ...user!, avatar_url: undefined as any });
            } catch {
              toast.error('Не удалось удалить аватарку');
            } finally {
              setAvatarUploading(false);
            }
          },
        });
      }
      buttons.push({ text: 'Отмена', style: 'cancel' });
      Alert.alert('Аватарка', undefined, buttons);
    }
  }, [user, setUser, pickImage]);

  useEffect(() => {
    if (!giftsLoaded) loadGifts();
    fetchFollowers();
    fetchFollowing();
    fetchStats().catch(() => {});
  }, [giftsLoaded, loadGifts, fetchFollowers, fetchFollowing, fetchStats]);

  const handleGivenPress = useCallback(
    (gift: GiftGivenItem) => {
      router.push(`/gift/${gift.id}?direction=given` as any);
    },
    [router],
  );

  const handleOpenWishlistsTab = useCallback(() => {
    router.push('/settings/wishlists?tab=given' as any);
  }, [router]);

  const handleDeleteAccount = useCallback(async () => {
    try {
      await api.deleteMyAccount();
      await logout();
      router.replace('/(auth)/login');
    } catch {
      toast.error('Не удалось удалить аккаунт');
    }
  }, [logout, router]);

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
      toast.error('Не удалось экспортировать данные');
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

  const statCards = [
    {
      label: 'В коллекции',
      value: stats?.total_records ?? collectionItems.length,
      icon: 'disc-outline' as const,
      onPress: () => handleStatPress('collection'),
    },
    {
      label: 'В вишлисте',
      value: wishlistItems.length,
      icon: 'heart-outline' as const,
      onPress: () => handleStatPress('wishlist'),
    },
    {
      label: 'Подписки',
      value: following.length,
      icon: 'people-outline' as const,
      onPress: () => router.push('/social/list?tab=following' as any),
    },
    {
      label: 'Подписчики',
      value: followers.length,
      icon: 'person-add-outline' as const,
      onPress: () => router.push('/social/list?tab=followers' as any),
    },
  ];

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      {/* Editorial header */}
      <View style={styles.header}>
        <AnimatedGradientText style={Typography.heroTitle}>Профиль</AnimatedGradientText>
        <TouchableOpacity onPress={handleClose} style={styles.closeButton}>
          <Ionicons name="close" size={28} color={Colors.royalBlue} />
        </TouchableOpacity>
      </View>

      <ScrollView
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
      >
        {/* Аватар и имя */}
        <View style={styles.profileSection}>
          <TouchableOpacity style={styles.avatarContainer} onPress={handleAvatarPress} activeOpacity={0.7}>
            {user?.avatar_url ? (
              <Image source={resolveMediaUrl(user.avatar_url)} style={styles.avatar} cachePolicy="disk" />
            ) : (
              <LinearGradient
                colors={[Colors.royalBlue, Colors.periwinkle]}
                style={styles.avatarPlaceholder}
              >
                <Icon name="disc" size={48} color={Colors.background} />
              </LinearGradient>
            )}
            {avatarUploading ? (
              <View style={styles.avatarEditBadge}>
                <ActivityIndicator size="small" color={Colors.background} />
              </View>
            ) : (
              <View style={styles.avatarEditBadge}>
                <Icon name="pencil" size={14} color={Colors.background} />
              </View>
            )}
          </TouchableOpacity>

          <Text style={styles.username}>@{user?.username ?? 'username'}</Text>
          {user?.display_name ? (
            <Text style={styles.displayName}>{user.display_name}</Text>
          ) : null}
          <View style={styles.archetypeRow}>
            <ArchetypeChip />
          </View>
          <Text style={styles.email}>{user?.email}</Text>
        </View>

        {/* Статистика 2×2 */}
        <View style={styles.statsGrid}>
          {statCards.map((stat, index) => (
            <TouchableOpacity
              key={index}
              style={[styles.statCard, Shadows.lg]}
              onPress={stat.onPress}
              activeOpacity={0.7}
            >
              <Icon name={stat.icon} size={22} color={Colors.royalBlue} />
              <Text style={styles.statValue}>{stat.value}</Text>
              <Text style={styles.statLabel}>{stat.label}</Text>
            </TouchableOpacity>
          ))}
        </View>

        {/* Уведомления: лента «Ты» и «Подписки» */}
        <View style={styles.activityWrap}>
          <ActivityCard />
        </View>

        {/* Ссылка на профиль */}
        <View
          ref={shareTarget.ref}
          onLayout={shareTarget.onLayout}
          collapsable={false}
          style={[styles.linkCard, Shadows.sm]}
        >
          <Text style={styles.linkLabel}>Ваш профиль</Text>
          <Text style={styles.linkUrl} numberOfLines={1} ellipsizeMode="tail">{profileUrl}</Text>
          <View style={styles.linkActions}>
            <TouchableOpacity style={styles.linkButton} onPress={handleCopyLink}>
              <Icon name={copied ? "checkmark-outline" : "copy-outline"} size={18} color={Colors.royalBlue} />
              <Text style={styles.linkButtonText}>{copied ? 'Скопировано' : 'Копировать'}</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.linkButton} onPress={handleShareProfile}>
              <Icon name="share-outline" size={18} color={Colors.royalBlue} />
              <Text style={styles.linkButtonText}>Поделиться</Text>
            </TouchableOpacity>
          </View>
        </View>

        {/* Секция «Я дарю» */}
        {!giftsLoaded ? (
          <View style={[styles.giftsCard, Shadows.sm]}>
            <ActivityIndicator size="small" color={Colors.royalBlue} style={{ marginVertical: Spacing.md }} />
          </View>
        ) : givenGifts.length === 0 ? (
          <TouchableOpacity activeOpacity={0.85} onPress={handleOpenWishlistsTab}>
            <LinearGradient
              colors={[Colors.royalBlue + '08', Colors.periwinkle + '12']}
              style={styles.giftsBanner}
            >
              <View style={styles.giftsBannerRow}>
                <View style={styles.giftsBannerIcon}>
                  <Icon name="gift-outline" size={24} color={Colors.royalBlue} />
                </View>
                <View style={styles.giftsBannerTextContainer}>
                  <Text style={styles.giftsBannerTitle}>Дари друзьям музыку</Text>
                  <Text style={styles.giftsBannerSubtitle}>
                    Забронируй пластинку из вишлиста друга — он не узнает, кто дарит
                  </Text>
                </View>
              </View>
            </LinearGradient>
          </TouchableOpacity>
        ) : (
          <View style={[styles.giftsCard, Shadows.sm]}>
            <TouchableOpacity
              style={styles.giftsCardHeader}
              activeOpacity={0.7}
              onPress={handleOpenWishlistsTab}
            >
              <Icon name="gift-outline" size={18} color={Colors.royalBlue} />
              <Text style={styles.giftsCardTitle}>Я дарю</Text>
              <Text style={styles.giftsCardCount}>{givenGifts.length}</Text>
            </TouchableOpacity>
            <ScrollView
              horizontal
              showsHorizontalScrollIndicator={false}
              contentContainerStyle={styles.giftsScrollContent}
            >
              {givenGifts.map((gift) => (
                <TouchableOpacity
                  key={gift.id}
                  style={styles.giftCard}
                  activeOpacity={0.7}
                  onPress={() => handleGivenPress(gift)}
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
                      <Icon name="disc-outline" size={24} color={Colors.textMuted} />
                    </View>
                  )}
                  <Text style={styles.giftCardTitle} numberOfLines={1}>
                    {gift.record.title}
                  </Text>
                  <Text style={styles.giftCardArtist} numberOfLines={1}>
                    {cleanArtistName(gift.record.artist)}
                  </Text>
                  <View style={styles.giftCardRecipient}>
                    {gift.for_user.avatar_url ? (
                      <Image source={resolveMediaUrl(gift.for_user.avatar_url)} style={styles.giftCardAvatar} cachePolicy="disk" />
                    ) : (
                      <View style={[styles.giftCardAvatar, styles.giftCardAvatarPlaceholder]}>
                        <Icon name="person" size={8} color={Colors.background} />
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
              ))}
            </ScrollView>
          </View>
        )}

        {/* Ачивки */}
        <View style={styles.achievementsSection}>
          <AchievementsBlock />
        </View>

        {/* Настройки */}
        <View style={styles.settingsSection}>
          <Text style={styles.sectionTitle}>Настройки</Text>

          <TouchableOpacity
            style={styles.settingsItem}
            onPress={() => router.push('/collection/value')}
          >
            <Icon name="cash-outline" size={24} color={Colors.royalBlue} />
            <Text style={styles.settingsItemText}>Стоимость коллекции</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.settingsItem}
            onPress={() => router.push('/settings/edit-profile')}
          >
            <Icon name="person-outline" size={24} color={Colors.royalBlue} />
            <Text style={styles.settingsItemText}>Редактировать профиль</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.settingsItem}
            onPress={() => router.push('/settings/discogs' as any)}
          >
            <Icon name="disc-outline" size={24} color={Colors.royalBlue} />
            <Text style={styles.settingsItemText}>Discogs</Text>
          </TouchableOpacity>

          {hasUserRecords && (
            <TouchableOpacity
              style={styles.settingsItem}
              onPress={() => router.push('/records/mine' as any)}
            >
              <Ionicons name="create-outline" size={24} color={Colors.royalBlue} />
              <Text style={styles.settingsItemText}>Мои релизы</Text>
            </TouchableOpacity>
          )}

          <TouchableOpacity
            style={styles.settingsItem}
            onPress={handleExportPress}
            disabled={exporting}
          >
            {exporting ? (
              <ActivityIndicator size="small" color={Colors.royalBlue} />
            ) : (
              <Icon name="download-outline" size={24} color={Colors.royalBlue} />
            )}
            <Text style={styles.settingsItemText}>Экспорт данных</Text>
          </TouchableOpacity>

          <MessagesMenuItem onPress={() => router.push('/messages' as any)} />

          <TouchableOpacity
            style={styles.settingsItem}
            onPress={() => router.push('/settings/notifications')}
          >
            <Icon name="notifications-outline" size={24} color={Colors.royalBlue} />
            <Text style={styles.settingsItemText}>Уведомления</Text>
          </TouchableOpacity>

          <FollowRequestsMenuItem
            onPress={() => router.push('/social/follow-requests' as any)}
          />

          <TouchableOpacity
            style={styles.settingsItem}
            onPress={() => router.push('/settings/wishlists')}
          >
            <Icon name="gift-outline" size={24} color={Colors.royalBlue} />
            <Text style={styles.settingsItemText}>Бронирования</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.settingsItem}
            onPress={() => Linking.openURL('https://timestripe.com/boards/sX8B5Keg/')}
          >
            <Icon name="map-outline" size={24} color={Colors.royalBlue} />
            <Text style={styles.settingsItemText}>Планы Вертушки</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.settingsItem}
            onPress={() => Linking.openURL('mailto:support@vinyl-vertushka.store')}
          >
            <Icon name="help-circle-outline" size={24} color={Colors.royalBlue} />
            <Text style={styles.settingsItemText}>Помощь</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.settingsItem}
            onPress={() => router.push('/legal' as any)}
          >
            <Icon name="shield-checkmark-outline" size={24} color={Colors.royalBlue} />
            <Text style={styles.settingsItemText}>Условия и конфиденциальность</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.settingsItem}
            onPress={async () => {
              await AsyncStorage.removeItem('@vertushka:onboarding_complete');
              await onboarding.checkOnboarding();
              router.dismiss();
            }}
          >
            <Icon name="refresh-outline" size={24} color={Colors.warning} />
            <Text style={styles.settingsItemText}>Запустить онбординг</Text>
          </TouchableOpacity>

          {/* DEV: галерея иконок B2 — убрать перед релизом */}
          {__DEV__ && (
            <TouchableOpacity
              style={styles.settingsItem}
              onPress={() => router.push('/dev/icons' as any)}
            >
              <Icon name="grid-outline" size={24} color={Colors.royalBlue} />
              <Text style={styles.settingsItemText}>Icons gallery (dev)</Text>
            </TouchableOpacity>
          )}
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

        {/* Опасная зона */}
        <View style={styles.dangerSection}>
          <Text style={styles.dangerTitle}>Опасная зона</Text>
          <Text style={styles.dangerDisclaimer}>
            Аккаунт и все данные будут безвозвратно удалены через 30 дней
          </Text>
          <TouchableOpacity
            style={styles.dangerButton}
            onPress={() => {
              Alert.alert(
                'Удалить аккаунт?',
                'Ваш аккаунт, коллекция, вишлист и все данные будут удалены. В течение 30 дней можно восстановить аккаунт, войдя снова.',
                [
                  { text: 'Отмена', style: 'cancel' },
                  {
                    text: 'Удалить',
                    style: 'destructive',
                    onPress: handleDeleteAccount,
                  },
                ]
              );
            }}
          >
            <Icon name="trash-outline" size={20} color={Colors.background} />
            <Text style={styles.dangerButtonText}>Удалить аккаунт</Text>
          </TouchableOpacity>
        </View>

        {/* Версия */}
        <Text style={styles.version}>Вертушка v1.0.0</Text>
      </ScrollView>

      <OnboardingOverlay />
      <Toast config={toastConfig} topOffset={56} />
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
    // Центруем close-кнопку по вертикали относительно «Профиль»-заголовка
    // (heroTitle 40pt + lineHeight 44). При flex-end она «прилипала» к нижнему
    // краю текста и читалась как съехавшая.
    alignItems: 'center',
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
  avatarEditBadge: {
    position: 'absolute',
    bottom: 0,
    right: 0,
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: Colors.royalBlue,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 2,
    borderColor: Colors.background,
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
  username: {
    ...Typography.h2,
    color: Colors.deepNavy,
    marginBottom: 2,
    textAlign: 'center',
  },
  displayName: {
    ...Typography.body,
    color: Colors.textSecondary,
    marginBottom: Spacing.xs,
    textAlign: 'center',
  },
  email: {
    ...Typography.caption,
    color: Colors.textMuted,
    textAlign: 'center',
  },
  archetypeRow: {
    alignItems: 'center',
    marginTop: 4,
    marginBottom: 6,
  },
  statsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.sm,
    marginBottom: Spacing.xl,
  },
  statCard: {
    width: '48%' as any,
    flexGrow: 1,
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.lg,
    padding: Spacing.md,
    alignItems: 'center',
  },
  statValue: {
    fontSize: ms(28),
    fontFamily: 'Inter_800ExtraBold',
    lineHeight: ms(34),
    color: Colors.deepNavy,
    marginTop: Spacing.xs,
  },
  statLabel: {
    ...Typography.caption,
    color: Colors.textSecondary,
    textAlign: 'center',
  },
  activityWrap: {
    marginBottom: Spacing.md,
  },
  linkCard: {
    backgroundColor: Colors.surface,
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
    fontSize: ms(13),
    fontFamily: 'Inter_600SemiBold',
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
  achievementsSection: {
    marginBottom: Spacing.lg,
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
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.lg,
    gap: Spacing.md,
    ...Shadows.sm,
  },
  settingsItemText: {
    ...Typography.body,
    color: Colors.text,
    flex: 1,
  },
  followReqBadge: {
    minWidth: 22,
    height: 22,
    borderRadius: 11,
    paddingHorizontal: 6,
    backgroundColor: Colors.royalBlue,
    alignItems: 'center',
    justifyContent: 'center',
  },
  followReqBadgeTxt: {
    color: '#fff',
    fontSize: 11,
    fontWeight: '700',
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
    fontSize: ms(13),
    color: Colors.deepNavy,
    lineHeight: 16,
  },
  giftCardArtist: {
    ...Typography.caption,
    fontSize: ms(12),
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
    fontSize: ms(11),
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
  giftCardStatusReceived: {
    opacity: 1,
  },
  receivedHint: {
    ...Typography.caption,
    color: Colors.textSecondary,
    marginTop: -Spacing.xs,
    marginBottom: Spacing.sm,
  },
  giftCardStatusDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
  },
  giftCardStatusText: {
    ...Typography.caption,
    fontSize: ms(11),
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
  // Danger Zone
  dangerSection: {
    marginBottom: Spacing.xl,
    padding: Spacing.lg,
    borderRadius: BorderRadius.lg,
    borderWidth: 1,
    borderColor: Colors.error + '30',
    backgroundColor: Colors.error + '06',
  },
  dangerTitle: {
    ...Typography.h4,
    color: Colors.error,
    marginBottom: Spacing.xs,
  },
  dangerDisclaimer: {
    ...Typography.caption,
    color: Colors.textSecondary,
    marginBottom: Spacing.md,
    lineHeight: 18,
  },
  dangerButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: Spacing.sm,
    backgroundColor: Colors.error,
    borderRadius: BorderRadius.md,
    paddingVertical: Spacing.sm + 2,
    paddingHorizontal: Spacing.lg,
  },
  dangerButtonText: {
    ...Typography.buttonSmall,
    color: Colors.background,
    fontFamily: 'Inter_600SemiBold',
  },
  // Delete Modal
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: Spacing.lg,
  },
  modalContent: {
    backgroundColor: Colors.background,
    borderRadius: BorderRadius.xl,
    padding: Spacing.xl,
    width: '100%',
    maxWidth: 360,
  },
  modalTitle: {
    ...Typography.h3,
    color: Colors.error,
    marginBottom: Spacing.md,
  },
  modalText: {
    ...Typography.body,
    color: Colors.textSecondary,
    lineHeight: 22,
    marginBottom: Spacing.lg,
  },
  modalHint: {
    ...Typography.caption,
    color: Colors.textMuted,
    marginBottom: Spacing.sm,
  },
  modalInput: {
    borderWidth: 1,
    borderColor: Colors.border,
    borderRadius: BorderRadius.md,
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm + 2,
    ...Typography.body,
    color: Colors.text,
    marginBottom: Spacing.lg,
  },
  modalActions: {
    flexDirection: 'row',
    gap: Spacing.md,
  },
  modalCancelButton: {
    flex: 1,
    alignItems: 'center',
    paddingVertical: Spacing.sm + 2,
    borderRadius: BorderRadius.md,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  modalCancelText: {
    ...Typography.buttonSmall,
    color: Colors.textSecondary,
  },
  modalDeleteButton: {
    flex: 1,
    alignItems: 'center',
    paddingVertical: Spacing.sm + 2,
    borderRadius: BorderRadius.md,
    backgroundColor: Colors.error,
  },
  modalDeleteButtonDisabled: {
    opacity: 0.4,
  },
  modalDeleteText: {
    ...Typography.buttonSmall,
    color: Colors.background,
    fontFamily: 'Inter_600SemiBold',
  },
});
