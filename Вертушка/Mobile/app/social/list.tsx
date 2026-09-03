/**
 * Экран списка подписок / подписчиков
 *
 * Свой список (без `username`) живёт в `useFollowStore` — он же кормит счётчики
 * на профиле. Чужой (`?username=ник`) грузится отдельно и постранично: чужие
 * подписчики в глобальный стор не кладутся, иначе они бы затёрли свои.
 */
import { useEffect, useState, useCallback, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  ActivityIndicator,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useFollowStore } from '../../lib/store';
import { api } from '../../lib/api';
import { UserPublic } from '../../lib/types';
import { UserListItem } from '../../components/UserListItem';
import { SegmentedControl } from '../../components/ui';
import { Header } from '../../components/Header';
import { Colors, Spacing } from '../../constants/theme';
import { ms } from '../../lib/responsive';

type Tab = 'followers' | 'following';

const SEGMENTS: { key: Tab; label: string }[] = [
  { key: 'following', label: 'Подписки' },
  { key: 'followers', label: 'Подписчики' },
];

const PER_PAGE = 30;

export default function SocialListScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const params = useLocalSearchParams<{ tab?: string; username?: string }>();
  const username = params.username || null;
  const [activeTab, setActiveTab] = useState<Tab>(
    params.tab === 'followers' ? 'followers' : 'following'
  );

  const {
    followers,
    following,
    isLoadingFollowers,
    isLoadingFollowing,
    fetchFollowers,
    fetchFollowing,
  } = useFollowStore();

  // Чужой профиль: свои списки под каждый таб + пагинация и запрет доступа.
  const [publicList, setPublicList] = useState<Record<Tab, UserPublic[]>>({
    followers: [],
    following: [],
  });
  const [publicLoading, setPublicLoading] = useState(false);
  const [forbidden, setForbidden] = useState(false);
  const exhausted = useRef<Record<Tab, boolean>>({ followers: false, following: false });

  const loadPublicPage = useCallback(
    async (tab: Tab, page: number) => {
      if (!username) return;
      setPublicLoading(true);
      try {
        const items =
          tab === 'followers'
            ? await api.getFollowersByUsername(username, page, PER_PAGE)
            : await api.getFollowingByUsername(username, page, PER_PAGE);
        if (items.length < PER_PAGE) exhausted.current[tab] = true;
        setPublicList((prev) => ({
          ...prev,
          [tab]: page === 1 ? items : [...prev[tab], ...items],
        }));
      } catch (e: any) {
        if (e?.response?.status === 403) setForbidden(true);
        exhausted.current[tab] = true;
      } finally {
        setPublicLoading(false);
      }
    },
    [username]
  );

  useEffect(() => {
    if (username) {
      if (publicList[activeTab].length === 0 && !exhausted.current[activeTab]) {
        loadPublicPage(activeTab, 1);
      }
      return;
    }
    fetchFollowers();
    fetchFollowing();
    // publicList намеренно вне зависимостей: иначе дозагрузка страницы
    // перезапускала бы эффект и первая страница грузилась бы дважды.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [username, activeTab, loadPublicPage, fetchFollowers, fetchFollowing]);

  const data: UserPublic[] = username
    ? publicList[activeTab]
    : activeTab === 'followers'
      ? followers
      : following;
  const isLoading = username
    ? publicLoading && data.length === 0
    : activeTab === 'followers'
      ? isLoadingFollowers
      : isLoadingFollowing;

  const onEndReached = useCallback(() => {
    if (!username || publicLoading || exhausted.current[activeTab]) return;
    if (data.length === 0) return;
    loadPublicPage(activeTab, Math.floor(data.length / PER_PAGE) + 1);
  }, [username, publicLoading, activeTab, data.length, loadPublicPage]);

  const renderItem = useCallback(({ item }: { item: UserPublic }) => (
    <UserListItem
      username={item.username}
      displayName={item.display_name}
      avatarUrl={item.avatar_url}
      onPress={() => router.push(`/user/${item.username}` as any)}
    />
  ), [router]);

  const renderEmpty = () => {
    if (isLoading) return null;
    if (forbidden) {
      return (
        <View style={styles.emptyContainer}>
          <Text style={styles.emptyText}>
            Профиль приватный — списки видны только подписчикам.
          </Text>
        </View>
      );
    }
    return (
      <View style={styles.emptyContainer}>
        <Text style={styles.emptyText}>
          {activeTab === 'followers'
            ? 'Пока нет подписчиков'
            : username
              ? 'Пока ни на кого не подписан'
              : 'Вы ни на кого не подписаны'}
        </Text>
      </View>
    );
  };

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <Header title={username ? `@${username}` : 'Подписки'} showBack showProfile={false} />

      <SegmentedControl
        segments={SEGMENTS}
        selectedKey={activeTab}
        onSelect={setActiveTab}
        style={styles.segmentedControl}
      />

      {isLoading ? (
        <ActivityIndicator size="large" color={Colors.royalBlue} style={styles.loader} />
      ) : (
        <FlatList
          data={data}
          keyExtractor={(item) => item.id}
          renderItem={renderItem}
          ListEmptyComponent={renderEmpty}
          ListFooterComponent={
            username && publicLoading && data.length > 0 ? (
              <ActivityIndicator color={Colors.royalBlue} style={styles.footerLoader} />
            ) : null
          }
          onEndReached={onEndReached}
          onEndReachedThreshold={0.5}
          contentContainerStyle={styles.listContent}
          showsVerticalScrollIndicator={false}
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
  segmentedControl: {
    marginHorizontal: Spacing.lg,
    marginBottom: Spacing.md,
  },
  loader: {
    marginTop: Spacing.xxl,
  },
  footerLoader: {
    marginVertical: Spacing.lg,
  },
  listContent: {
    paddingHorizontal: Spacing.lg,
    gap: Spacing.sm,
    paddingBottom: Spacing.xxl,
  },
  emptyContainer: {
    alignItems: 'center',
    paddingTop: Spacing.xxl,
  },
  emptyText: {
    fontSize: ms(15),
    color: Colors.textSecondary,
    textAlign: 'center',
  },
});
