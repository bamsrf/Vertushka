/**
 * Экран списка подписок / подписчиков
 */
import { useEffect, useState, useCallback } from 'react';
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
import { UserPublic } from '../../lib/types';
import { UserListItem } from '../../components/UserListItem';
import { SegmentedControl } from '../../components/ui';
import { Header } from '../../components/Header';
import { Colors, Spacing } from '../../constants/theme';

type Tab = 'followers' | 'following';

const SEGMENTS: { key: Tab; label: string }[] = [
  { key: 'following', label: 'Подписки' },
  { key: 'followers', label: 'Подписчики' },
];

export default function SocialListScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const params = useLocalSearchParams<{ tab?: string }>();
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

  useEffect(() => {
    fetchFollowers();
    fetchFollowing();
  }, [fetchFollowers, fetchFollowing]);

  const data: UserPublic[] = activeTab === 'followers' ? followers : following;
  const isLoading = activeTab === 'followers' ? isLoadingFollowers : isLoadingFollowing;

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
    return (
      <View style={styles.emptyContainer}>
        <Text style={styles.emptyText}>
          {activeTab === 'followers'
            ? 'Пока нет подписчиков'
            : 'Вы ни на кого не подписаны'}
        </Text>
      </View>
    );
  };

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <Header title="Подписки" showBack showProfile={false} />

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
    fontSize: 15,
    color: Colors.textSecondary,
  },
});
