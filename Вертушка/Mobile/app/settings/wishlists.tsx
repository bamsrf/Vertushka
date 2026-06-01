/**
 * Вишлисты: «Я дарю» / «Мне дарят» — список бронирований
 * Тап по карточке открывает детальный экран /gift/[id]
 */
import { useEffect, useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  ActivityIndicator,
  RefreshControl,
} from 'react-native';
import { Image } from 'expo-image';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Icon } from '@/components/ui';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useGiftStore } from '../../lib/store';
import { GiftGivenItem, GiftReceivedItem } from '../../lib/types';
import { cleanArtistName } from '../../lib/format';
import { SegmentedControl } from '../../components/ui';
import { Colors, Typography, Spacing, BorderRadius } from '../../constants/theme';

type Tab = 'given' | 'received';

const SEGMENTS: { key: Tab; label: string }[] = [
  { key: 'given', label: 'Я дарю' },
  { key: 'received', label: 'Мне дарят' },
];

type GiftStatus = 'pending' | 'booked' | 'completed' | 'cancelled';

const STATUS_LABEL: Record<GiftStatus, string> = {
  pending: 'Ждёт подтверждения',
  booked: 'Забронировано',
  completed: 'Доставлено',
  cancelled: 'Отменено',
};

const STATUS_COLOR: Record<GiftStatus, string> = {
  pending: Colors.warning,
  booked: Colors.royalBlue,
  completed: Colors.success,
  cancelled: Colors.textMuted,
};

function StatusPill({ status }: { status: GiftStatus }) {
  const color = STATUS_COLOR[status];
  return (
    <View style={[styles.statusPill, { backgroundColor: color + '15' }]}>
      <View style={[styles.statusDot, { backgroundColor: color }]} />
      <Text style={[styles.statusText, { color }]}>{STATUS_LABEL[status]}</Text>
    </View>
  );
}

function GiftRow({
  cover,
  title,
  subtitle,
  status,
  onPress,
}: {
  cover?: string;
  title: string;
  subtitle: string;
  status: GiftStatus;
  onPress: () => void;
}) {
  return (
    <TouchableOpacity style={styles.row} onPress={onPress} activeOpacity={0.7}>
      {cover ? (
        <Image source={cover} style={styles.cover} contentFit="cover" cachePolicy="disk" />
      ) : (
        <View style={[styles.cover, styles.coverPlaceholder]}>
          <Icon name="disc-outline" size={24} color={Colors.textMuted} />
        </View>
      )}
      <View style={styles.rowContent}>
        <Text style={styles.rowTitle} numberOfLines={1}>{title}</Text>
        <Text style={styles.rowSubtitle} numberOfLines={1}>{subtitle}</Text>
        <StatusPill status={status} />
      </View>
    </TouchableOpacity>
  );
}

export default function WishlistsScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const params = useLocalSearchParams<{ tab?: string }>();
  const { given, received, isLoaded, isLoading, loadAll } = useGiftStore();

  const [activeTab, setActiveTab] = useState<Tab>(
    params.tab === 'received' ? 'received' : 'given',
  );
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    if (!isLoaded) loadAll();
  }, [isLoaded, loadAll]);

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    await loadAll();
    setRefreshing(false);
  }, [loadAll]);

  const handlePress = useCallback(
    (id: string, direction: Tab) => {
      router.push(`/gift/${id}?direction=${direction}` as any);
    },
    [router],
  );

  const renderGiven = ({ item }: { item: GiftGivenItem }) => (
    <GiftRow
      cover={item.record.cover_image_url}
      title={item.record.title}
      subtitle={`${cleanArtistName(item.record.artist)} · для @${item.for_user.username}`}
      status={item.status as GiftStatus}
      onPress={() => handlePress(item.id, 'given')}
    />
  );

  const renderReceived = ({ item }: { item: GiftReceivedItem }) => (
    <GiftRow
      cover={item.record.cover_image_url}
      title={item.record.title}
      subtitle={cleanArtistName(item.record.artist)}
      status={item.status}
      onPress={() => handlePress(item.id, 'received')}
    />
  );

  const renderEmpty = () => {
    if (!isLoaded) return null;
    return (
      <View style={styles.emptyContainer}>
        <View style={styles.emptyIconWrap}>
          <Icon
            name={activeTab === 'given' ? 'gift-outline' : 'mail-open-outline'}
            size={36}
            color={Colors.royalBlue}
          />
        </View>
        <Text style={styles.emptyTitle}>
          {activeTab === 'given' ? 'Ты пока никого не дарил' : 'Ничего не забронировано'}
        </Text>
        <Text style={styles.emptySubtitle}>
          {activeTab === 'given'
            ? 'Открой вишлист друга по ссылке и забронируй пластинку — он не узнает, кто даритель'
            : 'Поделись своей публичной ссылкой на вишлист — друзья смогут забронировать пластинку в подарок'}
        </Text>
      </View>
    );
  };

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backButton}>
          <Icon name="arrow-back" size={24} color={Colors.royalBlue} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Вишлисты</Text>
        <View style={styles.placeholder} />
      </View>

      <View style={styles.segmentWrap}>
        <SegmentedControl
          segments={SEGMENTS}
          selectedKey={activeTab}
          onSelect={setActiveTab}
        />
      </View>

      {!isLoaded && isLoading ? (
        <View style={styles.center}>
          <ActivityIndicator size="large" color={Colors.royalBlue} />
        </View>
      ) : activeTab === 'given' ? (
        <FlatList
          data={given}
          keyExtractor={(item) => item.id}
          renderItem={renderGiven}
          ListEmptyComponent={renderEmpty}
          contentContainerStyle={[
            styles.listContent,
            given.length === 0 && styles.listContentEmpty,
            { paddingBottom: insets.bottom + Spacing.xl },
          ]}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={handleRefresh} tintColor={Colors.royalBlue} />
          }
        />
      ) : (
        <FlatList
          data={received}
          keyExtractor={(item) => item.id}
          renderItem={renderReceived}
          ListEmptyComponent={renderEmpty}
          contentContainerStyle={[
            styles.listContent,
            received.length === 0 && styles.listContentEmpty,
            { paddingBottom: insets.bottom + Spacing.xl },
          ]}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={handleRefresh} tintColor={Colors.royalBlue} />
          }
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  center: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: Spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: Colors.divider,
  },
  headerTitle: {
    ...Typography.h4,
    fontSize: 17,
    color: Colors.royalBlue,
  },
  backButton: {
    width: 36,
    height: 36,
    alignItems: 'center',
    justifyContent: 'center',
  },
  placeholder: {
    width: 36,
    height: 36,
  },
  segmentWrap: {
    paddingHorizontal: Spacing.lg,
    paddingTop: Spacing.md,
    paddingBottom: Spacing.sm,
  },
  listContent: {
    paddingHorizontal: Spacing.lg,
    paddingTop: Spacing.sm,
  },
  listContentEmpty: {
    flexGrow: 1,
    justifyContent: 'center',
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: Spacing.md,
    gap: Spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: Colors.divider,
  },
  cover: {
    width: 56,
    height: 56,
    borderRadius: BorderRadius.sm,
    backgroundColor: Colors.surface,
  },
  coverPlaceholder: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  rowContent: {
    flex: 1,
    gap: 4,
  },
  rowTitle: {
    ...Typography.bodyBold,
    color: Colors.text,
  },
  rowSubtitle: {
    ...Typography.caption,
    color: Colors.textSecondary,
  },
  statusPill: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    paddingVertical: 3,
    paddingHorizontal: 8,
    borderRadius: BorderRadius.sm,
    gap: 6,
    marginTop: 2,
  },
  statusDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
  },
  statusText: {
    ...Typography.caption,
    fontWeight: '600',
    fontSize: 11,
  },
  emptyContainer: {
    alignItems: 'center',
    paddingHorizontal: Spacing.xl,
    paddingVertical: Spacing.xxl,
  },
  emptyIconWrap: {
    width: 72,
    height: 72,
    borderRadius: 36,
    backgroundColor: Colors.royalBlue + '12',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: Spacing.md,
  },
  emptyTitle: {
    ...Typography.h4,
    color: Colors.text,
    textAlign: 'center',
    marginBottom: Spacing.sm,
  },
  emptySubtitle: {
    ...Typography.body,
    color: Colors.textSecondary,
    textAlign: 'center',
    lineHeight: 20,
  },
});
