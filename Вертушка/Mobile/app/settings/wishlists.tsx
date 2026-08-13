/**
 * Вишлисты: «Я дарю» / «Мне дарят» — список бронирований
 * Тап по карточке открывает детальный экран /gift/[id]
 */
import { useEffect, useState, useCallback, useMemo } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  SectionList,
  TouchableOpacity,
  ActivityIndicator,
  RefreshControl,
  Share,
} from 'react-native';
import * as Clipboard from 'expo-clipboard';
import { Image } from 'expo-image';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Icon } from '@/components/ui';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useAuthStore, useGiftStore } from '../../lib/store';
import { toast } from '../../lib/toast';
import { GiftGivenItem, GiftReceivedItem } from '../../lib/types';
import { cleanArtistName, plural } from '../../lib/format';
import { SegmentedControl } from '../../components/ui';
import { Colors, Typography, Spacing, BorderRadius } from '../../constants/theme';
import { ms } from '../../lib/responsive';

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

function ShareLinkBlock({ url }: { url: string }) {
  const handleCopy = useCallback(async () => {
    await Clipboard.setStringAsync(url);
    toast.success('Ссылка скопирована');
  }, [url]);

  const handleShare = useCallback(async () => {
    try {
      await Share.share({ message: `Мой вишлист: ${url}`, url });
    } catch {
      // Пользователь отменил
    }
  }, [url]);

  return (
    <View style={styles.shareCard}>
      <Text style={styles.shareLabel}>Твоя публичная ссылка</Text>
      <TouchableOpacity onPress={handleCopy} activeOpacity={0.7} style={styles.shareUrlRow}>
        <Text style={styles.shareUrl} numberOfLines={1}>{url}</Text>
        <Icon name="copy-outline" size={18} color={Colors.royalBlue} />
      </TouchableOpacity>
      <TouchableOpacity onPress={handleShare} activeOpacity={0.7} style={styles.shareButton}>
        <Icon name="share-outline" size={18} color={Colors.background} />
        <Text style={styles.shareButtonText}>Поделиться</Text>
      </TouchableOpacity>
    </View>
  );
}

export default function WishlistsScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const params = useLocalSearchParams<{ tab?: string }>();
  const { given, received, isLoaded, isLoading, loadAll } = useGiftStore();
  const user = useAuthStore((s) => s.user);
  const profileUrl = user ? `https://vinyl-vertushka.ru/@${user.username}` : '';

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

  // «Я дарю» разбивается надвое: что дарю сейчас и что уже вручил.
  // Архив — это ещё и статистика: сколько подарков дошло и скольким людям.
  const givenSections = useMemo(() => {
    const active = given.filter((g) => g.status !== 'completed');
    const delivered = given.filter((g) => g.status === 'completed');
    const sections: { key: string; title: string; caption?: string; data: GiftGivenItem[] }[] = [];

    if (active.length > 0) {
      sections.push({ key: 'active', title: 'Сейчас дарю', data: active });
    }
    if (delivered.length > 0) {
      const people = new Set(delivered.map((g) => g.for_user.username)).size;
      sections.push({
        key: 'delivered',
        title: 'Уже подарил',
        caption: `${plural(delivered.length, 'подарок', 'подарка', 'подарков')} · ${plural(
          people,
          'человеку',
          'людям',
          'людям',
        )}`,
        data: delivered,
      });
    }
    return sections;
  }, [given]);

  const renderSectionHeader = ({
    section,
  }: {
    section: { title: string; caption?: string };
  }) => (
    <View style={styles.sectionHeader}>
      <Text style={styles.sectionTitle}>{section.title}</Text>
      {section.caption ? <Text style={styles.sectionCaption}>{section.caption}</Text> : null}
    </View>
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
        {activeTab === 'received' && profileUrl ? <ShareLinkBlock url={profileUrl} /> : null}
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
        <SectionList
          sections={givenSections}
          keyExtractor={(item) => item.id}
          renderItem={renderGiven}
          // Заголовок секции не липкий: секций максимум две, а «прилипший»
          // заголовок на коротком списке выглядит шумом.
          stickySectionHeadersEnabled={false}
          renderSectionHeader={givenSections.length > 1 ? renderSectionHeader : undefined}
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
          ListHeaderComponent={
            received.length > 0 && profileUrl ? <ShareLinkBlock url={profileUrl} /> : null
          }
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
    fontSize: ms(17),
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
  sectionHeader: {
    paddingTop: Spacing.lg,
    paddingBottom: Spacing.xs,
  },
  sectionTitle: {
    fontSize: ms(13),
    fontWeight: '700',
    color: Colors.text,
    textTransform: 'uppercase',
    letterSpacing: 0.6,
  },
  sectionCaption: {
    fontSize: ms(12),
    color: Colors.textMuted,
    marginTop: 2,
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
    fontSize: ms(11),
  },
  shareCard: {
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.md,
    padding: Spacing.md,
    gap: Spacing.sm,
    marginTop: Spacing.lg,
    alignSelf: 'stretch',
  },
  shareLabel: {
    ...Typography.caption,
    color: Colors.textSecondary,
  },
  shareUrlRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
    backgroundColor: Colors.background,
    borderRadius: BorderRadius.sm,
    paddingVertical: Spacing.sm,
    paddingHorizontal: Spacing.md,
  },
  shareUrl: {
    ...Typography.body,
    flex: 1,
    color: Colors.text,
  },
  shareButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: Spacing.sm,
    backgroundColor: Colors.royalBlue,
    borderRadius: BorderRadius.sm,
    paddingVertical: Spacing.sm + 2,
  },
  shareButtonText: {
    ...Typography.bodyBold,
    color: Colors.background,
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
