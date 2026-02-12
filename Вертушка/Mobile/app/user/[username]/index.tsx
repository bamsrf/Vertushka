/**
 * Экран профиля другого пользователя
 */
import { useEffect, useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  Image,
  TouchableOpacity,
  ActivityIndicator,
  Alert,
  FlatList,
  Modal,
  TextInput,
  RefreshControl,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { api } from '../../../lib/api';
import { useAuthStore, useFollowStore } from '../../../lib/store';
import {
  UserWithStats,
  WishlistPublicResponse,
  WishlistPublicItem,
  Collection,
  CollectionItem,
} from '../../../lib/types';
import { RecordCard } from '../../../components/RecordCard';
import { SegmentedControl } from '../../../components/ui';
import { Colors, Typography, Spacing, BorderRadius, Shadows } from '../../../constants/theme';

type ProfileTab = 'collection' | 'wishlist';

const SEGMENTS: { key: ProfileTab; label: string }[] = [
  { key: 'collection', label: 'Коллекция' },
  { key: 'wishlist', label: 'Вишлист' },
];

export default function UserProfileScreen() {
  const { username } = useLocalSearchParams<{ username: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { user: currentUser } = useAuthStore();
  const { followUser, unfollowUser } = useFollowStore();

  const [profile, setProfile] = useState<UserWithStats | null>(null);
  const [activeTab, setActiveTab] = useState<ProfileTab>('collection');
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isFollowLoading, setIsFollowLoading] = useState(false);

  // Collection data
  const [collectionItems, setCollectionItems] = useState<CollectionItem[]>([]);
  const [isLoadingCollection, setIsLoadingCollection] = useState(false);

  // Wishlist data
  const [wishlist, setWishlist] = useState<WishlistPublicResponse | null>(null);
  const [isLoadingWishlist, setIsLoadingWishlist] = useState(false);
  const [wishlistError, setWishlistError] = useState<string | null>(null);

  // Booking modal
  const [bookingItem, setBookingItem] = useState<WishlistPublicItem | null>(null);
  const [bookingName, setBookingName] = useState('');
  const [bookingEmail, setBookingEmail] = useState('');
  const [bookingMessage, setBookingMessage] = useState('');
  const [isBooking, setIsBooking] = useState(false);

  const isOwn = currentUser?.username === username;

  const loadProfile = useCallback(async () => {
    if (!username) return;
    try {
      const data = await api.getUserByUsername(username);
      setProfile(data);
    } catch {
      Alert.alert('Ошибка', 'Пользователь не найден');
      router.back();
    } finally {
      setIsLoading(false);
    }
  }, [username]);

  const loadCollection = useCallback(async () => {
    if (!profile) return;
    setIsLoadingCollection(true);
    try {
      const collections = await api.getUserCollection(profile.id);
      const items = collections.flatMap((c: Collection) => c.items || []);
      setCollectionItems(items);
    } catch {
      setCollectionItems([]);
    } finally {
      setIsLoadingCollection(false);
    }
  }, [profile?.id]);

  const loadWishlist = useCallback(async () => {
    if (!username) return;
    setIsLoadingWishlist(true);
    setWishlistError(null);
    try {
      const data = await api.getUserWishlistByUsername(username);
      setWishlist(data);
    } catch (error: any) {
      const status = error?.response?.status;
      if (status === 403) {
        setWishlistError('Подпишитесь, чтобы увидеть вишлист');
      } else {
        setWishlistError('Не удалось загрузить вишлист');
      }
    } finally {
      setIsLoadingWishlist(false);
    }
  }, [username]);

  useEffect(() => {
    loadProfile();
  }, [loadProfile]);

  useEffect(() => {
    if (!profile) return;
    if (activeTab === 'collection') {
      loadCollection();
    } else {
      loadWishlist();
    }
  }, [profile, activeTab]);

  const handleRefresh = useCallback(async () => {
    setIsRefreshing(true);
    await loadProfile();
    if (activeTab === 'collection') {
      await loadCollection();
    } else {
      await loadWishlist();
    }
    setIsRefreshing(false);
  }, [activeTab, loadProfile, loadCollection, loadWishlist]);

  const handleFollow = useCallback(async () => {
    if (!profile) return;
    setIsFollowLoading(true);
    try {
      if (profile.is_following) {
        await unfollowUser(profile.id);
        setProfile(prev => prev ? { ...prev, is_following: false, followers_count: prev.followers_count - 1 } : null);
      } else {
        await followUser(profile.id);
        setProfile(prev => prev ? { ...prev, is_following: true, followers_count: prev.followers_count + 1 } : null);
      }
    } catch (error: any) {
      const msg = error?.response?.data?.detail || 'Не удалось выполнить действие';
      Alert.alert('Ошибка', msg);
    } finally {
      setIsFollowLoading(false);
    }
  }, [profile, followUser, unfollowUser]);

  const handleRecordPress = useCallback((item: CollectionItem | WishlistPublicItem) => {
    if ('record' in item && 'id' in item.record) {
      const record = item.record;
      // Используем discogs_id если есть
      const recordId = ('discogs_id' in record && record.discogs_id) ? record.discogs_id : record.id;
      router.push(`/record/${recordId}`);
    }
  }, [router]);

  const handleBookGift = useCallback(async () => {
    if (!bookingItem || !bookingName.trim() || !bookingEmail.trim()) {
      Alert.alert('Ошибка', 'Заполните имя и email');
      return;
    }

    setIsBooking(true);
    try {
      await api.bookGift({
        wishlist_item_id: bookingItem.id,
        gifter_name: bookingName.trim(),
        gifter_email: bookingEmail.trim(),
        gifter_message: bookingMessage.trim() || undefined,
      });
      Alert.alert('Забронировано!', 'Подарок забронирован анонимно. Владелец не узнает кто дарит.');
      setBookingItem(null);
      setBookingName('');
      setBookingEmail('');
      setBookingMessage('');
      loadWishlist();
    } catch (error: any) {
      const msg = error?.response?.data?.detail || 'Не удалось забронировать';
      Alert.alert('Ошибка', msg);
    } finally {
      setIsBooking(false);
    }
  }, [bookingItem, bookingName, bookingEmail, bookingMessage, loadWishlist]);

  if (isLoading) {
    return (
      <View style={[styles.container, styles.center, { paddingTop: insets.top }]}>
        <ActivityIndicator size="large" color={Colors.primary} />
      </View>
    );
  }

  if (!profile) return null;

  const renderProfileHeader = () => (
    <View>
      {/* Profile info */}
      <View style={styles.profileSection}>
        <View style={styles.avatarContainer}>
          {profile.avatar_url ? (
            <Image source={{ uri: profile.avatar_url }} style={styles.avatar} />
          ) : (
            <View style={styles.avatarPlaceholder}>
              <Ionicons name="person" size={40} color={Colors.background} />
            </View>
          )}
        </View>

        <Text style={styles.displayName}>
          {profile.display_name || profile.username}
        </Text>
        <Text style={styles.username}>@{profile.username}</Text>
        {profile.bio && <Text style={styles.bio}>{profile.bio}</Text>}
      </View>

      {/* Stats */}
      <View style={styles.statsContainer}>
        <View style={styles.statItem}>
          <Text style={styles.statValue}>{profile.collection_count}</Text>
          <Text style={styles.statLabel}>Пластинок</Text>
        </View>
        <View style={styles.statDivider} />
        <View style={styles.statItem}>
          <Text style={styles.statValue}>{profile.followers_count}</Text>
          <Text style={styles.statLabel}>Подписчиков</Text>
        </View>
        <View style={styles.statDivider} />
        <View style={styles.statItem}>
          <Text style={styles.statValue}>{profile.following_count}</Text>
          <Text style={styles.statLabel}>Подписок</Text>
        </View>
      </View>

      {/* Follow button */}
      {!isOwn && (
        <TouchableOpacity
          style={[
            styles.followButton,
            profile.is_following && styles.followButtonActive,
          ]}
          onPress={handleFollow}
          disabled={isFollowLoading}
        >
          {isFollowLoading ? (
            <ActivityIndicator size="small" color={profile.is_following ? Colors.primary : Colors.background} />
          ) : (
            <>
              <Ionicons
                name={profile.is_following ? 'checkmark' : 'person-add-outline'}
                size={18}
                color={profile.is_following ? Colors.primary : Colors.background}
              />
              <Text style={[
                styles.followButtonText,
                profile.is_following && styles.followButtonTextActive,
              ]}>
                {profile.is_following ? 'Подписаны' : 'Подписаться'}
              </Text>
            </>
          )}
        </TouchableOpacity>
      )}

      {/* Tabs */}
      <View style={styles.tabContainer}>
        <SegmentedControl
          segments={SEGMENTS}
          selectedKey={activeTab}
          onSelect={setActiveTab}
        />
      </View>
    </View>
  );

  const renderCollectionItem = ({ item }: { item: CollectionItem }) => (
    <RecordCard
      record={item.record}
      onPress={() => handleRecordPress(item)}
    />
  );

  const renderWishlistItem = ({ item }: { item: WishlistPublicItem }) => (
    <View style={styles.wishlistCard}>
      <RecordCard
        record={item.record}
        onPress={() => handleRecordPress(item)}
        isBooked={item.is_booked}
      />
      {!item.is_booked && !isOwn && profile.is_following && (
        <TouchableOpacity
          style={styles.giftButton}
          onPress={() => setBookingItem(item)}
        >
          <Ionicons name="gift-outline" size={16} color={Colors.background} />
          <Text style={styles.giftButtonText}>Подарить</Text>
        </TouchableOpacity>
      )}
    </View>
  );

  const renderEmpty = () => {
    if (activeTab === 'wishlist' && wishlistError) {
      return (
        <View style={styles.emptyContainer}>
          <Ionicons name="lock-closed-outline" size={48} color={Colors.textMuted} />
          <Text style={styles.emptyText}>{wishlistError}</Text>
          {!profile.is_following && !isOwn && (
            <TouchableOpacity style={styles.followPromptButton} onPress={handleFollow}>
              <Text style={styles.followPromptText}>Подписаться</Text>
            </TouchableOpacity>
          )}
        </View>
      );
    }

    const loading = activeTab === 'collection' ? isLoadingCollection : isLoadingWishlist;
    if (loading) {
      return (
        <View style={styles.emptyContainer}>
          <ActivityIndicator color={Colors.primary} />
        </View>
      );
    }

    return (
      <View style={styles.emptyContainer}>
        <Text style={styles.emptyText}>
          {activeTab === 'collection' ? 'Коллекция пуста' : 'Вишлист пуст'}
        </Text>
      </View>
    );
  };

  const data = activeTab === 'collection' ? collectionItems : (wishlist?.items || []);
  const isDataLoading = activeTab === 'collection' ? isLoadingCollection : isLoadingWishlist;
  const showEmpty = (!isDataLoading && data.length === 0) || (activeTab === 'wishlist' && wishlistError);

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      {/* Back button */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backButton}>
          <Ionicons name="arrow-back" size={24} color={Colors.primary} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>@{username}</Text>
        <View style={styles.headerPlaceholder} />
      </View>

      <FlatList
        data={showEmpty ? [] : data}
        renderItem={activeTab === 'collection' ? renderCollectionItem : renderWishlistItem}
        keyExtractor={(item) => item.id}
        numColumns={2}
        columnWrapperStyle={data.length > 0 ? styles.row : undefined}
        contentContainerStyle={styles.listContent}
        ListHeaderComponent={renderProfileHeader}
        ListEmptyComponent={renderEmpty}
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl
            refreshing={isRefreshing}
            onRefresh={handleRefresh}
            tintColor={Colors.primary}
          />
        }
      />

      {/* Booking Modal */}
      <Modal
        visible={!!bookingItem}
        transparent
        animationType="slide"
        onRequestClose={() => setBookingItem(null)}
      >
        <View style={styles.modalOverlay}>
          <View style={[styles.modalContent, { paddingBottom: insets.bottom + Spacing.lg }]}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Забронировать подарок</Text>
              <TouchableOpacity onPress={() => setBookingItem(null)}>
                <Ionicons name="close" size={24} color={Colors.text} />
              </TouchableOpacity>
            </View>

            {bookingItem && (
              <Text style={styles.modalRecordTitle}>
                {bookingItem.record.artist} — {bookingItem.record.title}
              </Text>
            )}

            <Text style={styles.modalHint}>
              Бронирование анонимное — владелец не узнает, кто дарит
            </Text>

            <TextInput
              style={styles.input}
              placeholder="Ваше имя"
              placeholderTextColor={Colors.textMuted}
              value={bookingName}
              onChangeText={setBookingName}
              autoCapitalize="words"
            />

            <TextInput
              style={styles.input}
              placeholder="Email (для уведомлений)"
              placeholderTextColor={Colors.textMuted}
              value={bookingEmail}
              onChangeText={setBookingEmail}
              keyboardType="email-address"
              autoCapitalize="none"
            />

            <TextInput
              style={[styles.input, styles.messageInput]}
              placeholder="Сообщение (необязательно)"
              placeholderTextColor={Colors.textMuted}
              value={bookingMessage}
              onChangeText={setBookingMessage}
              multiline
              numberOfLines={3}
            />

            <TouchableOpacity
              style={[styles.bookButton, (!bookingName.trim() || !bookingEmail.trim()) && styles.bookButtonDisabled]}
              onPress={handleBookGift}
              disabled={isBooking || !bookingName.trim() || !bookingEmail.trim()}
            >
              {isBooking ? (
                <ActivityIndicator color={Colors.background} />
              ) : (
                <Text style={styles.bookButtonText}>Забронировать</Text>
              )}
            </TouchableOpacity>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  center: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: Colors.divider,
  },
  headerTitle: {
    ...Typography.h4,
    color: Colors.primary,
  },
  backButton: {
    width: 36,
    height: 36,
    alignItems: 'center',
    justifyContent: 'center',
  },
  headerPlaceholder: {
    width: 36,
  },
  listContent: {
    padding: Spacing.md,
  },
  row: {
    justifyContent: 'space-between',
  },
  profileSection: {
    alignItems: 'center',
    marginBottom: Spacing.lg,
  },
  avatarContainer: {
    marginBottom: Spacing.md,
  },
  avatar: {
    width: 96,
    height: 96,
    borderRadius: 48,
  },
  avatarPlaceholder: {
    width: 96,
    height: 96,
    borderRadius: 48,
    backgroundColor: Colors.accent,
    alignItems: 'center',
    justifyContent: 'center',
  },
  displayName: {
    ...Typography.h3,
    color: Colors.primary,
    marginBottom: 2,
  },
  username: {
    ...Typography.body,
    color: Colors.textSecondary,
    marginBottom: Spacing.xs,
  },
  bio: {
    ...Typography.bodySmall,
    color: Colors.textSecondary,
    textAlign: 'center',
    paddingHorizontal: Spacing.xl,
    marginTop: Spacing.xs,
  },
  statsContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.lg,
    paddingVertical: Spacing.md,
    paddingHorizontal: Spacing.lg,
    marginBottom: Spacing.lg,
  },
  statItem: {
    flex: 1,
    alignItems: 'center',
  },
  statValue: {
    ...Typography.h4,
    color: Colors.primary,
  },
  statLabel: {
    ...Typography.caption,
    color: Colors.textSecondary,
    marginTop: 2,
  },
  statDivider: {
    width: 1,
    height: 32,
    backgroundColor: Colors.border,
  },
  followButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: Spacing.sm,
    backgroundColor: Colors.primary,
    borderRadius: BorderRadius.md,
    paddingVertical: Spacing.sm,
    marginBottom: Spacing.lg,
  },
  followButtonActive: {
    backgroundColor: Colors.surface,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  followButtonText: {
    ...Typography.button,
    color: Colors.background,
  },
  followButtonTextActive: {
    color: Colors.primary,
  },
  tabContainer: {
    marginBottom: Spacing.md,
  },
  wishlistCard: {
    flex: 1,
    maxWidth: '50%',
  },
  giftButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
    backgroundColor: Colors.accent,
    borderRadius: BorderRadius.sm,
    paddingVertical: Spacing.xs,
    marginHorizontal: 2,
    marginBottom: Spacing.sm,
  },
  giftButtonText: {
    ...Typography.caption,
    color: Colors.background,
    fontWeight: '600',
  },
  emptyContainer: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: Spacing.xxl,
    gap: Spacing.md,
  },
  emptyText: {
    ...Typography.body,
    color: Colors.textMuted,
    textAlign: 'center',
  },
  followPromptButton: {
    backgroundColor: Colors.primary,
    borderRadius: BorderRadius.md,
    paddingVertical: Spacing.sm,
    paddingHorizontal: Spacing.xl,
    marginTop: Spacing.sm,
  },
  followPromptText: {
    ...Typography.button,
    color: Colors.background,
  },
  // Modal
  modalOverlay: {
    flex: 1,
    justifyContent: 'flex-end',
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
  },
  modalContent: {
    backgroundColor: Colors.background,
    borderTopLeftRadius: BorderRadius.xl,
    borderTopRightRadius: BorderRadius.xl,
    padding: Spacing.lg,
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: Spacing.md,
  },
  modalTitle: {
    ...Typography.h3,
    color: Colors.text,
  },
  modalRecordTitle: {
    ...Typography.bodyBold,
    color: Colors.text,
    marginBottom: Spacing.sm,
  },
  modalHint: {
    ...Typography.bodySmall,
    color: Colors.textSecondary,
    marginBottom: Spacing.lg,
  },
  input: {
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.md,
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.md,
    fontSize: 16,
    color: Colors.text,
    marginBottom: Spacing.md,
  },
  messageInput: {
    minHeight: 80,
    textAlignVertical: 'top',
  },
  bookButton: {
    backgroundColor: Colors.accent,
    borderRadius: BorderRadius.lg,
    paddingVertical: Spacing.md,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: Spacing.sm,
  },
  bookButtonDisabled: {
    opacity: 0.5,
  },
  bookButtonText: {
    ...Typography.button,
    color: Colors.background,
  },
});
