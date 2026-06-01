/**
 * Экран входящих заявок на подписку (для приватных профилей).
 *
 * Загружает /users/me/follow-requests/incoming, показывает список с аватаром,
 * именем и кнопками «Одобрить / Отклонить». Pull-to-refresh.
 */
import { useCallback, useEffect, useState } from 'react';
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
import { useRouter } from 'expo-router';
import { Icon } from '@/components/ui';
import { api, resolveMediaUrl } from '../../lib/api';
import { FollowRequestItem } from '../../lib/types';
import { toast } from '../../lib/toast';
import { Colors, Spacing, BorderRadius, Typography } from '../../constants/theme';
import { ms } from '../../lib/responsive';

export default function FollowRequestsScreen() {
  const router = useRouter();
  const [items, setItems] = useState<FollowRequestItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [pendingIds, setPendingIds] = useState<Set<string>>(new Set());

  const load = useCallback(async () => {
    try {
      const data = await api.getIncomingFollowRequests();
      setItems(data);
    } catch {
      toast.error('Не удалось загрузить заявки');
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleRefresh = useCallback(() => {
    setIsRefreshing(true);
    load();
  }, [load]);

  const setBusy = (id: string, busy: boolean) => {
    setPendingIds((prev) => {
      const next = new Set(prev);
      if (busy) next.add(id);
      else next.delete(id);
      return next;
    });
  };

  const handleApprove = useCallback(async (req: FollowRequestItem) => {
    setBusy(req.id, true);
    try {
      await api.approveFollowRequest(req.id);
      setItems((prev) => prev.filter((r) => r.id !== req.id));
      toast.success('Подписка одобрена');
    } catch (error: any) {
      toast.error('Ошибка', error?.response?.data?.detail || 'Не удалось одобрить');
    } finally {
      setBusy(req.id, false);
    }
  }, []);

  const handleReject = useCallback(async (req: FollowRequestItem) => {
    setBusy(req.id, true);
    try {
      await api.rejectFollowRequest(req.id);
      setItems((prev) => prev.filter((r) => r.id !== req.id));
      toast.info('Заявка отклонена');
    } catch (error: any) {
      toast.error('Ошибка', error?.response?.data?.detail || 'Не удалось отклонить');
    } finally {
      setBusy(req.id, false);
    }
  }, []);

  const renderItem = ({ item }: { item: FollowRequestItem }) => {
    const busy = pendingIds.has(item.id);
    const u = item.requester;
    const displayName = u.display_name || u.username;
    return (
      <View style={styles.row}>
        <TouchableOpacity
          activeOpacity={0.8}
          onPress={() => router.push(`/user/${u.username}`)}
          style={styles.userBlock}
        >
          <View style={styles.avatar}>
            {u.avatar_url ? (
              <Image
                source={resolveMediaUrl(u.avatar_url)}
                style={{ width: 44, height: 44 }}
                cachePolicy="disk"
              />
            ) : (
              <Text style={styles.avatarInitials}>{u.username.slice(0, 2).toLowerCase()}</Text>
            )}
          </View>
          <View style={{ flex: 1, minWidth: 0 }}>
            <Text style={styles.name} numberOfLines={1}>{displayName}</Text>
            <Text style={styles.handle} numberOfLines={1}>@{u.username}</Text>
          </View>
        </TouchableOpacity>
        <View style={styles.actions}>
          <TouchableOpacity
            disabled={busy}
            onPress={() => handleReject(item)}
            style={[styles.btn, styles.btnGhost]}
          >
            {busy ? <ActivityIndicator size="small" color={Colors.textMuted} /> : (
              <Icon name="close" size={18} color={Colors.textMuted} />
            )}
          </TouchableOpacity>
          <TouchableOpacity
            disabled={busy}
            onPress={() => handleApprove(item)}
            style={[styles.btn, styles.btnPrimary]}
          >
            {busy ? <ActivityIndicator size="small" color="#fff" /> : (
              <Icon name="checkmark" size={18} color="#fff" />
            )}
          </TouchableOpacity>
        </View>
      </View>
    );
  };

  if (isLoading) {
    return (
      <View style={[styles.container, styles.center]}>
        <ActivityIndicator size="large" color={Colors.royalBlue} />
      </View>
    );
  }

  return (
    <FlatList
      style={styles.container}
      contentContainerStyle={items.length === 0 ? styles.emptyWrap : { paddingVertical: Spacing.md }}
      data={items}
      keyExtractor={(item) => item.id}
      renderItem={renderItem}
      refreshControl={
        <RefreshControl refreshing={isRefreshing} onRefresh={handleRefresh} tintColor={Colors.royalBlue} />
      }
      ListEmptyComponent={
        <View style={styles.center}>
          <Icon name="mail-outline" size={48} color={Colors.textMuted} />
          <Text style={styles.emptyTitle}>Нет новых заявок</Text>
          <Text style={styles.emptySub}>
            Сюда придут запросы на подписку, когда профиль в приватном режиме.
          </Text>
        </View>
      }
    />
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  center: { alignItems: 'center', justifyContent: 'center', padding: Spacing.lg },

  row: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: Spacing.lg,
    paddingVertical: Spacing.md,
    gap: Spacing.md,
  },
  userBlock: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.md,
    minWidth: 0,
  },
  avatar: {
    width: 44, height: 44, borderRadius: 22,
    backgroundColor: Colors.surface,
    alignItems: 'center', justifyContent: 'center',
    overflow: 'hidden',
  },
  avatarInitials: { fontSize: 14, fontWeight: '700', color: Colors.royalBlue },
  name: { fontSize: ms(15), fontWeight: '600', color: Colors.text },
  handle: { fontSize: ms(12), color: Colors.textMuted, marginTop: 2 },

  actions: { flexDirection: 'row', gap: 8 },
  btn: {
    width: 38, height: 38, borderRadius: 19,
    alignItems: 'center', justifyContent: 'center',
  },
  btnGhost: {
    backgroundColor: Colors.surface,
    borderWidth: 1, borderColor: Colors.surfaceHover,
  },
  btnPrimary: {
    backgroundColor: Colors.royalBlue,
  },

  emptyWrap: { flexGrow: 1, justifyContent: 'center' },
  emptyTitle: {
    fontSize: ms(17), fontWeight: '700', color: Colors.text,
    marginTop: Spacing.md, textAlign: 'center',
  },
  emptySub: {
    fontSize: ms(13), color: Colors.textMuted, marginTop: 6,
    textAlign: 'center', maxWidth: 280, lineHeight: ms(18),
  },
});
