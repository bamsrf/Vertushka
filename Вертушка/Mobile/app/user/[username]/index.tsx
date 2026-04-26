/**
 * Публичный профиль другого пользователя — light premium редизайн.
 * Палитра: ivory base + cobalt action (см. Design/Vertuska_publicPRofile/).
 */
import { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  Modal,
  TextInput,
  RefreshControl,
  Keyboard,
  TouchableWithoutFeedback,
  KeyboardAvoidingView,
  Platform,
  Animated,
  Easing,
  Pressable,
  Dimensions,
  Share,
} from 'react-native';
import { Image } from 'expo-image';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { api, resolveMediaUrl } from '../../../lib/api';
import { useAuthStore, useFollowStore } from '../../../lib/store';
import {
  PublicProfile,
  PublicProfileRecord,
  WishlistPublicItem,
  WishlistPublicResponse,
} from '../../../lib/types';
import { toast } from '../../../lib/toast';

type ProfileTab = 'collection' | 'wishlist';

const PP = {
  ivory: '#F4EEE6',
  ivorySoft: '#F0EBE2',
  ivoryDeep: '#ECE6DC',
  pearl: '#F7F4EE',
  cobalt: '#3A4BE0',
  cobaltBright: '#4E5BFF',
  periwinkle: '#9AA8FF',
  lavender: '#C9B8FF',
  blush: '#F6C7D0',
  sky: '#BDD4FF',
  ink: '#1B1D26',
  slate: '#6B7080',
  mute: '#9096A6',
  hairline: 'rgba(27,29,38,0.08)',
  whiteSoft: 'rgba(255,255,255,0.6)',
};

const SCREEN_W = Dimensions.get('window').width;
const GRID_GAP = 14;
const GRID_PADDING = 20;
const GRID_COLS = 2;
const CARD_W = (SCREEN_W - GRID_PADDING * 2 - GRID_GAP) / GRID_COLS;

function formatRub(value: number) {
  return Math.round(value).toLocaleString('ru-RU').replace(/,/g, ' ');
}

function Vinyl({ size = 150 }: { size?: number }) {
  const rot = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    Animated.loop(
      Animated.timing(rot, {
        toValue: 1,
        duration: 14000,
        easing: Easing.linear,
        useNativeDriver: true,
      })
    ).start();
  }, [rot]);
  const spin = rot.interpolate({ inputRange: [0, 1], outputRange: ['0deg', '360deg'] });
  return (
    <Animated.View
      style={{
        width: size,
        height: size,
        borderRadius: size / 2,
        backgroundColor: PP.ink,
        transform: [{ rotate: spin }],
        shadowColor: PP.ink,
        shadowOffset: { width: 0, height: 18 },
        shadowOpacity: 0.35,
        shadowRadius: 24,
        elevation: 14,
      }}
    >
      <View
        style={{
          position: 'absolute',
          left: size * 0.3,
          top: size * 0.3,
          width: size * 0.4,
          height: size * 0.4,
          borderRadius: size * 0.2,
          overflow: 'hidden',
        }}
      >
        <LinearGradient
          colors={[PP.periwinkle, PP.cobalt, '#2030B0']}
          style={{ flex: 1 }}
        />
      </View>
      <View
        style={{
          position: 'absolute',
          left: size / 2 - 3,
          top: size / 2 - 3,
          width: 6,
          height: 6,
          borderRadius: 3,
          backgroundColor: PP.ink,
        }}
      />
    </Animated.View>
  );
}

function Segmented({
  value,
  onChange,
  items,
}: {
  value: ProfileTab;
  onChange: (v: ProfileTab) => void;
  items: { id: ProfileTab; label: string; count: number }[];
}) {
  const [widths, setWidths] = useState<number[]>([0, 0]);
  const [offsets, setOffsets] = useState<number[]>([0, 0]);
  const pillX = useRef(new Animated.Value(0)).current;
  const pillW = useRef(new Animated.Value(0)).current;
  const idx = items.findIndex((s) => s.id === value);

  useEffect(() => {
    if (widths[idx]) {
      Animated.parallel([
        Animated.timing(pillX, {
          toValue: offsets[idx],
          duration: 420,
          easing: Easing.bezier(0.22, 0.7, 0.18, 1),
          useNativeDriver: false,
        }),
        Animated.timing(pillW, {
          toValue: widths[idx],
          duration: 420,
          easing: Easing.bezier(0.22, 0.7, 0.18, 1),
          useNativeDriver: false,
        }),
      ]).start();
    }
  }, [idx, widths, offsets, pillX, pillW]);

  return (
    <View style={styles.segmented}>
      <Animated.View
        style={[
          styles.segmentedPill,
          { transform: [{ translateX: pillX }], width: pillW },
        ]}
      />
      {items.map((s, i) => {
        const active = s.id === value;
        return (
          <Pressable
            key={s.id}
            onPress={() => onChange(s.id)}
            onLayout={(e) => {
              const { width, x } = e.nativeEvent.layout;
              setWidths((w) => {
                const next = [...w];
                next[i] = width;
                return next;
              });
              setOffsets((o) => {
                const next = [...o];
                next[i] = x;
                return next;
              });
            }}
            style={styles.segmentedBtn}
          >
            <Text style={[styles.segmentedLabel, active && styles.segmentedLabelActive]}>
              {s.label}
            </Text>
            <View style={[styles.segmentedCount, active && styles.segmentedCountActive]}>
              <Text style={[styles.segmentedCountTxt, active && styles.segmentedCountTxtActive]}>
                {s.count}
              </Text>
            </View>
          </Pressable>
        );
      })}
    </View>
  );
}

function ReservedBadge() {
  const pulse = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, { toValue: 1, duration: 1300, useNativeDriver: false }),
        Animated.timing(pulse, { toValue: 0, duration: 1300, useNativeDriver: false }),
      ])
    ).start();
  }, [pulse]);
  const shadow = pulse.interpolate({ inputRange: [0, 1], outputRange: [0, 6] });
  return (
    <Animated.View
      style={[
        styles.reservedBadge,
        {
          shadowColor: PP.periwinkle,
          shadowOpacity: 0.5,
          shadowRadius: shadow as any,
          shadowOffset: { width: 0, height: 0 },
        },
      ]}
    >
      <View style={styles.reservedDot} />
      <Text style={styles.reservedText}>Забронировано</Text>
    </Animated.View>
  );
}

function Rail({
  title,
  subtitle,
  items,
  showYear,
  onPick,
  titleColor,
}: {
  title: string;
  subtitle: string;
  items: PublicProfileRecord[];
  showYear?: boolean;
  onPick?: (r: PublicProfileRecord) => void;
  titleColor: string;
}) {
  if (!items.length) return null;
  return (
    <View>
      <View style={styles.railHead}>
        <Text style={[styles.railTitle, { color: titleColor }]}>{title.toUpperCase()}</Text>
        <Text style={styles.railSub}>{subtitle}</Text>
      </View>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={{ paddingHorizontal: GRID_PADDING, gap: 12 }}
      >
        {items.map((r) => (
          <TouchableOpacity
            key={r.id}
            activeOpacity={0.85}
            onPress={() => onPick?.(r)}
            style={{ width: 108 }}
          >
            <View style={styles.railCover}>
              {r.cover_image_url ? (
                <Image
                  source={resolveMediaUrl(r.cover_image_url)}
                  style={{ width: 108, height: 108 }}
                  cachePolicy="disk"
                />
              ) : (
                <LinearGradient
                  colors={[PP.lavender, PP.periwinkle]}
                  style={{ width: 108, height: 108 }}
                />
              )}
            </View>
            <Text
              numberOfLines={1}
              style={[
                styles.railArtist,
                { color: titleColor === PP.cobalt ? PP.cobalt : PP.mute },
              ]}
            >
              {r.artist}
            </Text>
            <Text numberOfLines={1} style={styles.railTitleSmall}>
              {r.title}
            </Text>
            {showYear && r.year ? (
              <Text style={styles.railYear}>
                {r.year}
                {r.format_type ? ` · ${r.format_type}` : ''}
              </Text>
            ) : null}
          </TouchableOpacity>
        ))}
      </ScrollView>
    </View>
  );
}

function BookingExplainer() {
  const steps = [
    { icon: '🔒', text: 'Анонимно — владелец видит только метку «Забронировано»' },
    { icon: '🎁', text: 'Бронь действует 60 дней с момента подтверждения' },
    { icon: '⏰', text: 'Напомним за 7 дней до истечения срока' },
    { icon: '📅', text: 'Если не вручили — бронь автоматически освободится' },
  ];
  return (
    <View style={styles.explainer}>
      <Text style={styles.explainerTitle}>Как работает бронирование</Text>
      {steps.map((s, i) => (
        <View key={i} style={styles.explainerRow}>
          <Text style={styles.explainerIcon}>{s.icon}</Text>
          <Text style={styles.explainerText}>{s.text}</Text>
        </View>
      ))}
    </View>
  );
}

function RecordCardLight({
  record,
  reserved,
  onPress,
}: {
  record: PublicProfileRecord;
  reserved?: boolean;
  onPress?: () => void;
}) {
  return (
    <TouchableOpacity activeOpacity={0.85} onPress={onPress} style={{ width: CARD_W }}>
      <View style={styles.cardCover}>
        {record.cover_image_url ? (
          <Image
            source={resolveMediaUrl(record.cover_image_url)}
            style={{ width: '100%', height: '100%' }}
            cachePolicy="disk"
          />
        ) : (
          <LinearGradient
            colors={[PP.lavender, PP.sky]}
            style={{ width: '100%', height: '100%' }}
          />
        )}
      </View>
      <View style={{ paddingTop: 10, paddingHorizontal: 2 }}>
        <Text numberOfLines={1} style={styles.cardArtist}>
          {record.artist}
        </Text>
        <Text numberOfLines={1} style={styles.cardTitle}>
          {record.title}
        </Text>
        <View style={styles.cardBottom}>
          <Text style={styles.cardInfo} numberOfLines={1}>
            {record.year || ''}
            {record.format_type ? ` · ${record.format_type}` : ''}
          </Text>
          {reserved ? <ReservedBadge /> : null}
        </View>
      </View>
    </TouchableOpacity>
  );
}

export default function UserProfileScreen() {
  const { username } = useLocalSearchParams<{ username: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { user: currentUser } = useAuthStore();
  const { followUser, unfollowUser } = useFollowStore();

  const [pubProfile, setPubProfile] = useState<PublicProfile | null>(null);
  const [wishlist, setWishlist] = useState<WishlistPublicResponse | null>(null);
  const [following, setFollowing] = useState(false);
  const [followersCount, setFollowersCount] = useState(0);
  const [profileUserId, setProfileUserId] = useState<string | null>(null);

  const [activeTab, setActiveTab] = useState<ProfileTab>('collection');
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isFollowLoading, setIsFollowLoading] = useState(false);

  // Booking modal state
  const [bookingItem, setBookingItem] = useState<WishlistPublicItem | null>(null);
  const [bookingName, setBookingName] = useState('');
  const [bookingEmail, setBookingEmail] = useState('');
  const [bookingMessage, setBookingMessage] = useState('');
  const [isBooking, setIsBooking] = useState(false);

  // Background tween value (0 — collection, 1 — wishlist)
  const bgAnim = useRef(new Animated.Value(0)).current;
  // Counter
  const counterAnim = useRef(new Animated.Value(0)).current;
  const [displayValue, setDisplayValue] = useState(0);

  const isOwn = currentUser?.username === username;

  const load = useCallback(async () => {
    if (!username) return;
    try {
      const [pub, userMeta] = await Promise.all([
        api.getPublicProfile(username),
        api.getUserByUsername(username).catch(() => null),
      ]);
      setPubProfile(pub);
      if (userMeta) {
        setProfileUserId(userMeta.id);
        setFollowing(userMeta.is_following);
        setFollowersCount(userMeta.followers_count);
      }
    } catch {
      toast.error('Профиль не найден');
      router.back();
    } finally {
      setIsLoading(false);
    }
  }, [username, router]);

  const loadWishlist = useCallback(async () => {
    if (!username) return;
    try {
      const data = await api.getUserWishlistByUsername(username);
      setWishlist(data);
    } catch {
      setWishlist(null);
    }
  }, [username]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (pubProfile && activeTab === 'wishlist' && !wishlist) {
      loadWishlist();
    }
  }, [pubProfile, activeTab, wishlist, loadWishlist]);

  useEffect(() => {
    Animated.timing(bgAnim, {
      toValue: activeTab === 'collection' ? 0 : 1,
      duration: 2500,
      easing: Easing.bezier(0.4, 0, 0.2, 1),
      useNativeDriver: false,
    }).start();
  }, [activeTab, bgAnim]);

  useEffect(() => {
    if (!pubProfile?.collection_value_rub) return;
    counterAnim.setValue(0);
    const id = counterAnim.addListener(({ value }) => {
      setDisplayValue(Math.round(value * (pubProfile.collection_value_rub || 0)));
    });
    Animated.timing(counterAnim, {
      toValue: 1,
      duration: 1600,
      easing: Easing.out(Easing.cubic),
      useNativeDriver: false,
    }).start();
    return () => counterAnim.removeListener(id);
  }, [pubProfile?.collection_value_rub, counterAnim]);

  const handleRefresh = useCallback(async () => {
    setIsRefreshing(true);
    await load();
    if (activeTab === 'wishlist') await loadWishlist();
    setIsRefreshing(false);
  }, [load, loadWishlist, activeTab]);

  const handleFollow = useCallback(async () => {
    if (!profileUserId) return;
    setIsFollowLoading(true);
    try {
      if (following) {
        await unfollowUser(profileUserId);
        setFollowing(false);
        setFollowersCount((c) => Math.max(0, c - 1));
      } else {
        await followUser(profileUserId);
        setFollowing(true);
        setFollowersCount((c) => c + 1);
      }
    } catch (error: any) {
      toast.error('Ошибка', error?.response?.data?.detail || 'Не удалось');
    } finally {
      setIsFollowLoading(false);
    }
  }, [profileUserId, following, followUser, unfollowUser]);

  const handleShare = useCallback(async () => {
    try {
      await Share.share({
        message: `https://vinyl-vertushka.ru/@${username}`,
      });
    } catch {}
  }, [username]);

  const handleBookGift = useCallback(async () => {
    if (!bookingItem || !bookingName.trim() || !bookingEmail.trim()) {
      toast.error('Заполните имя и email');
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
      toast.success('Готово!', 'Бронь на 60 дней. Подтверждение отправлено на email.');
      setBookingItem(null);
      setBookingName('');
      setBookingEmail('');
      setBookingMessage('');
      await loadWishlist();
    } catch (error: any) {
      toast.error('Ошибка', error?.response?.data?.detail || 'Не удалось забронировать');
    } finally {
      setIsBooking(false);
    }
  }, [bookingItem, bookingName, bookingEmail, bookingMessage, loadWishlist]);

  const collectionValueRub = pubProfile?.collection_value_rub;
  const monthlyDelta = pubProfile?.monthly_value_delta_rub;

  const wishlistItems = wishlist?.items || [];
  const recordsForGrid: PublicProfileRecord[] =
    activeTab === 'collection'
      ? pubProfile?.recent_additions || []
      : wishlistItems.map((it) => ({ ...it.record, is_booked: it.is_booked }));

  // Collection grid: используем recent_additions как fallback (полная коллекция отдельно не грузится)
  const gridData = activeTab === 'collection' ? pubProfile?.recent_additions || [] : recordsForGrid;

  const collectionBgOpacity = bgAnim.interpolate({ inputRange: [0, 1], outputRange: [1, 0] });
  const wishlistBgOpacity = bgAnim.interpolate({ inputRange: [0, 1], outputRange: [0, 1] });

  if (isLoading) {
    return (
      <View style={[styles.container, styles.center, { paddingTop: insets.top }]}>
        <ActivityIndicator size="large" color={PP.cobalt} />
      </View>
    );
  }

  if (!pubProfile) return null;

  const initials = pubProfile.username.slice(0, 2).toLowerCase();

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      {/* Background layers */}
      <View style={StyleSheet.absoluteFill}>
        <LinearGradient
          colors={[PP.ivory, PP.ivorySoft, PP.ivoryDeep]}
          style={StyleSheet.absoluteFill}
        />
        <Animated.View style={[StyleSheet.absoluteFill, { opacity: collectionBgOpacity }]}>
          <LinearGradient
            colors={['rgba(154,168,255,0.42)', 'transparent']}
            start={{ x: 0.85, y: 0 }}
            end={{ x: 0.4, y: 0.5 }}
            style={StyleSheet.absoluteFill}
          />
          <LinearGradient
            colors={['rgba(189,212,255,0.26)', 'transparent']}
            start={{ x: 0.05, y: 0 }}
            end={{ x: 0.5, y: 0.5 }}
            style={StyleSheet.absoluteFill}
          />
        </Animated.View>
        <Animated.View style={[StyleSheet.absoluteFill, { opacity: wishlistBgOpacity }]}>
          <LinearGradient
            colors={['rgba(201,184,255,0.42)', 'transparent']}
            start={{ x: 0.85, y: 0 }}
            end={{ x: 0.4, y: 0.5 }}
            style={StyleSheet.absoluteFill}
          />
          <LinearGradient
            colors={['rgba(246,199,208,0.30)', 'transparent']}
            start={{ x: 0.05, y: 0 }}
            end={{ x: 0.5, y: 0.5 }}
            style={StyleSheet.absoluteFill}
          />
        </Animated.View>
      </View>

      {/* Top bar */}
      <View style={styles.topbar}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={22} color={PP.ink} />
        </TouchableOpacity>
        <Text style={styles.brand}>ВЕРТУШКА · ПРОФИЛЬ</Text>
        <TouchableOpacity onPress={handleShare} style={styles.shareBtn}>
          <Ionicons name="share-outline" size={18} color={PP.ink} />
        </TouchableOpacity>
      </View>

      <ScrollView
        showsVerticalScrollIndicator={false}
        contentContainerStyle={{ paddingBottom: 120 }}
        refreshControl={
          <RefreshControl refreshing={isRefreshing} onRefresh={handleRefresh} tintColor={PP.cobalt} />
        }
      >
        {/* HERO */}
        <View style={styles.hero}>
          <View style={{ flex: 1, minWidth: 0 }}>
            <View style={styles.userRow}>
              <LinearGradient
                colors={[PP.blush, PP.lavender, PP.periwinkle, PP.sky]}
                style={styles.avatarRing}
              >
                <View style={styles.avatarInner}>
                  {pubProfile.avatar_url ? (
                    <Image
                      source={resolveMediaUrl(pubProfile.avatar_url)}
                      style={{ width: '100%', height: '100%', borderRadius: 50 }}
                      cachePolicy="disk"
                    />
                  ) : (
                    <Text style={styles.avatarInitials}>{initials}</Text>
                  )}
                </View>
              </LinearGradient>
              <View style={{ flex: 1, minWidth: 0 }}>
                <Text style={styles.username} numberOfLines={1}>
                  @{pubProfile.username}
                </Text>
                {pubProfile.custom_title ? (
                  <Text style={styles.customTitle} numberOfLines={1}>
                    {pubProfile.custom_title}
                  </Text>
                ) : null}
              </View>
            </View>

            {collectionValueRub != null ? (
              <View style={{ marginTop: 6 }}>
                <Text style={styles.statLabel}>Стоимость коллекции</Text>
                <Text style={styles.statValue}>
                  {formatRub(displayValue)} <Text style={styles.currency}>₽</Text>
                </Text>
                {monthlyDelta != null ? (
                  <View style={styles.deltaPill}>
                    <Ionicons
                      name={monthlyDelta >= 0 ? 'arrow-up' : 'arrow-down'}
                      size={11}
                      color={PP.cobalt}
                    />
                    <Text style={styles.deltaText}>
                      {monthlyDelta >= 0 ? '+' : ''}
                      {formatRub(monthlyDelta)} ₽ за месяц
                    </Text>
                  </View>
                ) : null}
              </View>
            ) : (
              <View style={{ marginTop: 4 }}>
                <Text style={styles.statLabel}>Коллекция</Text>
                <Text style={styles.statValue}>
                  {pubProfile.collection_count}{' '}
                  <Text style={styles.currency}>пластинок</Text>
                </Text>
              </View>
            )}
          </View>

          <Vinyl size={140} />
        </View>

        {/* Stats row + follow */}
        <View style={styles.statsRow}>
          <View style={styles.statItem}>
            <Text style={styles.statNum}>{pubProfile.collection_count}</Text>
            <Text style={styles.statLbl}>Пластинок</Text>
          </View>
          {pubProfile.show_wishlist ? (
            <View style={styles.statItem}>
              <Text style={styles.statNum}>{pubProfile.wishlist_count}</Text>
              <Text style={styles.statLbl}>В вишлисте</Text>
            </View>
          ) : null}
          <View style={styles.statItem}>
            <Text style={styles.statNum}>{followersCount || pubProfile.followers_count}</Text>
            <Text style={styles.statLbl}>Подписчиков</Text>
          </View>
        </View>

        {!isOwn && profileUserId ? (
          <TouchableOpacity
            style={[styles.followBtn, following && styles.followBtnActive]}
            onPress={handleFollow}
            disabled={isFollowLoading}
          >
            {isFollowLoading ? (
              <ActivityIndicator size="small" color={following ? PP.cobalt : '#fff'} />
            ) : (
              <>
                <Ionicons
                  name={following ? 'checkmark' : 'person-add-outline'}
                  size={16}
                  color={following ? PP.cobalt : '#fff'}
                />
                <Text style={[styles.followTxt, following && styles.followTxtActive]}>
                  {following ? 'Подписаны' : 'Подписаться'}
                </Text>
              </>
            )}
          </TouchableOpacity>
        ) : null}

        {/* Rails area */}
        <View style={{ marginTop: 22 }}>
          {activeTab === 'collection' ? (
            <Rail
              title="Недавно добавленные"
              subtitle="Свежее в коллекции"
              titleColor={PP.cobalt}
              items={pubProfile.recent_additions}
              onPick={(r) => router.push(`/record/${r.id}`)}
            />
          ) : (
            <View>
              <BookingExplainer />
              <View style={{ marginTop: 16 }}>
                <Rail
                  title="Новинки"
                  subtitle="Свежие релизы"
                  titleColor={PP.slate}
                  items={pubProfile.new_releases}
                  showYear
                  onPick={(r) => router.push(`/record/${r.id}`)}
                />
              </View>
            </View>
          )}
        </View>

        {/* Segmented */}
        <View style={{ paddingHorizontal: GRID_PADDING, marginTop: 22 }}>
          <Segmented
            value={activeTab}
            onChange={setActiveTab}
            items={[
              { id: 'collection', label: 'Коллекция', count: pubProfile.collection_count },
              { id: 'wishlist', label: 'Вишлист', count: pubProfile.wishlist_count },
            ]}
          />
        </View>

        {/* Grid */}
        <View style={styles.grid}>
          {gridData.length === 0 ? (
            <Text style={styles.empty}>
              {activeTab === 'collection' ? 'Коллекция пуста' : 'Вишлист пуст'}
            </Text>
          ) : (
            gridData.map((r, idx) => {
              const isWishlist = activeTab === 'wishlist';
              const item = isWishlist ? wishlistItems[idx] : null;
              const reserved = isWishlist ? !!item?.is_booked : false;
              return (
                <RecordCardLight
                  key={r.id + idx}
                  record={r}
                  reserved={reserved}
                  onPress={() => {
                    if (isWishlist && item && !reserved && !isOwn) {
                      setBookingItem(item);
                    } else {
                      router.push(`/record/${r.id}`);
                    }
                  }}
                />
              );
            })
          )}
        </View>

        <Text style={styles.brandFooter}>VINYL-VERTUSHKA.RU</Text>
      </ScrollView>

      {/* Booking modal */}
      <Modal
        visible={!!bookingItem}
        transparent
        animationType="slide"
        onRequestClose={() => setBookingItem(null)}
      >
        <KeyboardAvoidingView
          style={styles.modalOverlay}
          behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        >
          <TouchableWithoutFeedback onPress={Keyboard.dismiss}>
            <View style={{ flex: 1 }} />
          </TouchableWithoutFeedback>
          <View style={[styles.modalContent, { paddingBottom: insets.bottom + 24 }]}>
            <View style={styles.modalHandle} />
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Забронировать как подарок</Text>
              <TouchableOpacity onPress={() => setBookingItem(null)}>
                <Ionicons name="close" size={22} color={PP.ink} />
              </TouchableOpacity>
            </View>
            {bookingItem ? (
              <Text style={styles.modalRec}>
                {bookingItem.record.artist} — {bookingItem.record.title}
              </Text>
            ) : null}
            <Text style={styles.modalInfo}>
              Бронь анонимная — владелец увидит только метку «Забронировано». Срок 60 дней.
              За 7 дней до истечения мы напомним на email. Если подарок не вручён — бронь
              освободится автоматически.
            </Text>
            <TextInput
              style={styles.input}
              placeholder="Ваше имя"
              placeholderTextColor={PP.mute}
              value={bookingName}
              onChangeText={setBookingName}
              autoCapitalize="words"
            />
            <TextInput
              style={styles.input}
              placeholder="Email для подтверждения"
              placeholderTextColor={PP.mute}
              value={bookingEmail}
              onChangeText={setBookingEmail}
              keyboardType="email-address"
              autoCapitalize="none"
            />
            <TextInput
              style={[styles.input, styles.textarea]}
              placeholder="Сообщение (необязательно)"
              placeholderTextColor={PP.mute}
              value={bookingMessage}
              onChangeText={setBookingMessage}
              multiline
            />
            <TouchableOpacity
              style={[
                styles.confirmBtn,
                (!bookingName.trim() || !bookingEmail.trim() || isBooking) && { opacity: 0.55 },
              ]}
              onPress={handleBookGift}
              disabled={isBooking || !bookingName.trim() || !bookingEmail.trim()}
            >
              {isBooking ? (
                <ActivityIndicator color="#fff" />
              ) : (
                <Text style={styles.confirmBtnTxt}>Подтвердить · бронь на 60 дней</Text>
              )}
            </TouchableOpacity>
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: PP.ivory },
  center: { alignItems: 'center', justifyContent: 'center' },

  topbar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: GRID_PADDING,
    paddingVertical: 8,
  },
  brand: {
    fontFamily: Platform.select({ ios: 'Menlo', android: 'monospace' }),
    fontSize: 11,
    letterSpacing: 1.5,
    color: PP.slate,
  },
  backBtn: {
    width: 36, height: 36, borderRadius: 18,
    alignItems: 'center', justifyContent: 'center',
    backgroundColor: PP.whiteSoft,
    borderWidth: 1, borderColor: PP.hairline,
  },
  shareBtn: {
    width: 36, height: 36, borderRadius: 18,
    alignItems: 'center', justifyContent: 'center',
    backgroundColor: PP.whiteSoft,
    borderWidth: 1, borderColor: PP.hairline,
  },

  hero: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    paddingHorizontal: GRID_PADDING,
    paddingTop: 8,
    paddingBottom: 20,
    gap: 12,
  },
  userRow: { flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 18 },
  avatarRing: {
    width: 50, height: 50, borderRadius: 25, padding: 2,
  },
  avatarInner: {
    flex: 1, borderRadius: 50, backgroundColor: PP.pearl,
    alignItems: 'center', justifyContent: 'center', overflow: 'hidden',
  },
  avatarInitials: { color: PP.cobalt, fontWeight: '600', fontSize: 16 },
  username: { fontSize: 20, fontWeight: '700', color: PP.ink, letterSpacing: -0.3 },
  customTitle: { fontSize: 12, color: PP.slate, marginTop: 2 },

  statLabel: {
    fontSize: 10, color: PP.slate, textTransform: 'uppercase', letterSpacing: 0.8,
    fontWeight: '500', marginTop: 4,
  },
  statValue: {
    fontSize: 32, fontWeight: '700', color: PP.ink, marginTop: 6, letterSpacing: -0.5,
  },
  currency: { fontSize: 18, color: PP.slate, fontWeight: '500' },
  deltaPill: {
    alignSelf: 'flex-start',
    flexDirection: 'row', alignItems: 'center', gap: 6,
    marginTop: 10, paddingHorizontal: 10, paddingVertical: 5,
    borderRadius: 999, backgroundColor: 'rgba(255,255,255,0.55)',
    borderWidth: 1, borderColor: 'rgba(58,75,224,0.12)',
  },
  deltaText: { fontSize: 11, color: PP.cobalt, fontWeight: '500' },

  statsRow: {
    flexDirection: 'row',
    paddingHorizontal: GRID_PADDING,
    gap: 24,
    marginTop: 4,
    marginBottom: 14,
  },
  statItem: {},
  statNum: { fontSize: 17, fontWeight: '700', color: PP.ink },
  statLbl: { fontSize: 11, color: PP.slate, marginTop: 2, textTransform: 'uppercase', letterSpacing: 0.5 },

  followBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
    marginHorizontal: GRID_PADDING, marginTop: 4, marginBottom: 4,
    backgroundColor: PP.cobalt, borderRadius: 14, paddingVertical: 12,
  },
  followBtnActive: {
    backgroundColor: PP.whiteSoft, borderWidth: 1, borderColor: 'rgba(58,75,224,0.25)',
  },
  followTxt: { color: '#fff', fontWeight: '600', fontSize: 14 },
  followTxtActive: { color: PP.cobalt },

  // Rails
  railHead: {
    flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between',
    paddingHorizontal: GRID_PADDING, marginBottom: 12,
  },
  railTitle: {
    fontSize: 10, letterSpacing: 1.2, fontWeight: '600',
    fontFamily: Platform.select({ ios: 'Menlo', android: 'monospace' }),
  },
  railSub: { fontSize: 11, color: PP.mute },
  railCover: {
    width: 108, height: 108, borderRadius: 13, overflow: 'hidden',
    backgroundColor: PP.lavender,
    shadowColor: PP.ink, shadowOffset: { width: 0, height: 8 }, shadowOpacity: 0.18, shadowRadius: 14,
  },
  railArtist: {
    fontFamily: Platform.select({ ios: 'Menlo', android: 'monospace' }),
    fontSize: 9, letterSpacing: 0.6, marginTop: 8,
  },
  railTitleSmall: { fontSize: 11.5, fontWeight: '600', color: PP.ink, marginTop: 2 },
  railYear: { fontSize: 11, color: PP.periwinkle, marginTop: 2 },

  // Segmented
  segmented: {
    alignSelf: 'flex-start',
    flexDirection: 'row',
    backgroundColor: 'rgba(255,255,255,0.55)',
    borderRadius: 999,
    borderWidth: 1, borderColor: PP.hairline,
    padding: 4,
  },
  segmentedPill: {
    position: 'absolute', top: 4, bottom: 4,
    backgroundColor: '#fff',
    borderRadius: 999,
    borderWidth: 1, borderColor: 'rgba(58,75,224,0.18)',
    shadowColor: PP.cobalt, shadowOffset: { width: 0, height: 4 }, shadowOpacity: 0.2, shadowRadius: 8,
  },
  segmentedBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    paddingHorizontal: 16, paddingVertical: 9, borderRadius: 999,
  },
  segmentedLabel: { fontSize: 13, fontWeight: '500', color: PP.slate },
  segmentedLabelActive: { color: PP.ink, fontWeight: '600' },
  segmentedCount: {
    paddingHorizontal: 7, paddingVertical: 1, borderRadius: 999,
    backgroundColor: 'rgba(27,29,38,0.06)',
  },
  segmentedCountActive: { backgroundColor: 'rgba(58,75,224,0.12)' },
  segmentedCountTxt: { fontSize: 11, color: PP.mute, fontWeight: '600' },
  segmentedCountTxtActive: { color: PP.cobalt },

  // Explainer
  explainer: {
    marginHorizontal: GRID_PADDING,
    borderRadius: 18,
    backgroundColor: 'rgba(255,255,255,0.6)',
    borderWidth: 1, borderColor: 'rgba(255,255,255,0.85)',
    padding: 16,
  },
  explainerTitle: { fontSize: 13, fontWeight: '600', color: PP.ink, marginBottom: 10 },
  explainerRow: { flexDirection: 'row', gap: 10, alignItems: 'flex-start', paddingVertical: 4 },
  explainerIcon: { fontSize: 14, lineHeight: 18 },
  explainerText: { flex: 1, fontSize: 12, color: PP.slate, lineHeight: 18 },

  // Grid + cards
  grid: {
    flexDirection: 'row', flexWrap: 'wrap',
    paddingHorizontal: GRID_PADDING,
    paddingTop: 18, paddingBottom: 8,
    gap: GRID_GAP,
    rowGap: 22,
  },
  cardCover: {
    width: '100%', aspectRatio: 1, borderRadius: 14, overflow: 'hidden',
    backgroundColor: PP.lavender,
    shadowColor: PP.ink, shadowOffset: { width: 0, height: 10 }, shadowOpacity: 0.22, shadowRadius: 16,
  },
  cardArtist: {
    fontFamily: Platform.select({ ios: 'Menlo', android: 'monospace' }),
    fontSize: 9.5, letterSpacing: 0.6, color: PP.cobalt, fontWeight: '600',
  },
  cardTitle: {
    fontSize: 13.5, fontWeight: '700', color: PP.ink, marginTop: 4, letterSpacing: -0.2,
  },
  cardBottom: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    marginTop: 6, gap: 6,
  },
  cardInfo: { fontSize: 11, color: PP.mute, flexShrink: 1 },

  // Reserved badge
  reservedBadge: {
    flexDirection: 'row', alignItems: 'center', gap: 5,
    paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999,
    backgroundColor: 'rgba(201,184,255,0.55)',
    borderWidth: 1, borderColor: 'rgba(154,168,255,0.55)',
  },
  reservedDot: { width: 5, height: 5, borderRadius: 3, backgroundColor: PP.cobalt },
  reservedText: { fontSize: 9.5, color: PP.cobalt, fontWeight: '700', letterSpacing: 0.4 },

  empty: {
    width: '100%', textAlign: 'center', color: PP.mute, fontSize: 14, paddingVertical: 60,
  },

  brandFooter: {
    textAlign: 'center', color: PP.mute, fontSize: 10,
    fontFamily: Platform.select({ ios: 'Menlo', android: 'monospace' }),
    letterSpacing: 1.4, marginTop: 24,
  },

  // Modal
  modalOverlay: { flex: 1, justifyContent: 'flex-end', backgroundColor: 'rgba(27,29,38,0.32)' },
  modalContent: {
    backgroundColor: PP.pearl, borderTopLeftRadius: 28, borderTopRightRadius: 28,
    paddingHorizontal: 22, paddingTop: 12,
  },
  modalHandle: {
    alignSelf: 'center', width: 40, height: 4, borderRadius: 2,
    backgroundColor: 'rgba(27,29,38,0.14)', marginBottom: 12,
  },
  modalHeader: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    marginBottom: 6,
  },
  modalTitle: { fontSize: 18, fontWeight: '700', color: PP.ink, letterSpacing: -0.3 },
  modalRec: { fontSize: 13, color: PP.cobalt, fontWeight: '500', marginTop: 4 },
  modalInfo: { fontSize: 12.5, color: PP.slate, lineHeight: 18, marginTop: 10, marginBottom: 16 },
  input: {
    height: 46, paddingHorizontal: 14, borderRadius: 14,
    backgroundColor: 'rgba(255,255,255,0.75)',
    borderWidth: 1, borderColor: PP.hairline,
    fontSize: 14, color: PP.ink,
    marginBottom: 10,
  },
  textarea: { height: 80, paddingTop: 12, textAlignVertical: 'top' },
  confirmBtn: {
    marginTop: 8, height: 50, borderRadius: 14,
    alignItems: 'center', justifyContent: 'center',
    backgroundColor: PP.cobalt,
    shadowColor: PP.cobalt, shadowOffset: { width: 0, height: 8 }, shadowOpacity: 0.45, shadowRadius: 14,
  },
  confirmBtnTxt: { color: '#fff', fontWeight: '700', fontSize: 14 },
});
