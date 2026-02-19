/**
 * Страница со списком всех версий мастер-релиза
 */
import { useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  ActivityIndicator,
  Alert,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Header } from '../../../components/Header';
import { VersionCard } from '../../../components/VersionCard';
import { api } from '../../../lib/api';
import { MasterVersion } from '../../../lib/types';
import { Colors, Typography, Spacing } from '../../../constants/theme';

export default function VersionsScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [versions, setVersions] = useState<MasterVersion[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);
  const [total, setTotal] = useState(0);

  useEffect(() => {
    loadVersions();
  }, [id]);

  const loadVersions = async (pageNum = 1) => {
    if (!id) return;
    if (pageNum > 1 && isLoading) return;

    setIsLoading(true);

    try {
      const response = await api.getMasterVersions(id, pageNum, 50);
      const existingLength = pageNum === 1 ? 0 : versions.length;

      if (pageNum === 1) {
        setVersions(response.results);
        setTotal(response.total);
      } else {
        setVersions([...versions, ...response.results]);
      }
      setPage(pageNum);
      setHasMore(existingLength + response.results.length < response.total);
    } catch (err) {
      console.error('Error loading versions:', err);
      Alert.alert('Ошибка', 'Не удалось загрузить версии');
    } finally {
      setIsLoading(false);
    }
  };

  const loadMoreVersions = () => {
    if (hasMore && !isLoading) {
      loadVersions(page + 1);
    }
  };

  const handleVersionPress = (version: MasterVersion) => {
    router.push(`/record/${version.release_id}`);
  };

  return (
    <View style={styles.container}>
      <Header
        title={`Все версии (${total})`}
        showBack
      />

      <FlatList
        data={versions}
        keyExtractor={(item) => item.release_id}
        renderItem={({ item }) => (
          <VersionCard
            version={item}
            onPress={() => handleVersionPress(item)}
          />
        )}
        onEndReached={loadMoreVersions}
        onEndReachedThreshold={0.5}
        ListEmptyComponent={
          !isLoading ? (
            <View style={styles.emptyContainer}>
              <Ionicons name="disc-outline" size={64} color={Colors.textMuted} />
              <Text style={styles.emptyText}>Версии не найдены</Text>
            </View>
          ) : null
        }
        ListFooterComponent={
          isLoading ? (
            <View style={styles.loadingMore}>
              <ActivityIndicator size="small" color={Colors.royalBlue} />
            </View>
          ) : null
        }
        contentContainerStyle={[
          styles.listContent,
          { paddingBottom: insets.bottom + Spacing.lg },
        ]}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.surface,
  },
  listContent: {
    padding: Spacing.md,
  },
  emptyContainer: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: Spacing.xl * 2,
  },
  emptyText: {
    ...Typography.body,
    color: Colors.textMuted,
    marginTop: Spacing.md,
  },
  loadingMore: {
    paddingVertical: Spacing.md,
    alignItems: 'center',
  },
});
