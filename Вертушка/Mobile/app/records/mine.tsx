/**
 * «Мои релизы» (§11): список своих ручных записей (source='user').
 *
 * Точка входа — раздел в настройках профиля (появляется после первого ручного
 * релиза). Тап по записи → карточка релиза, где в «3 точках» есть «Отредактировать».
 */
import { useCallback, useState } from 'react';
import { View, Text, StyleSheet, FlatList, Pressable, ActivityIndicator } from 'react-native';
import { useRouter, useFocusEffect, Stack } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Image } from 'expo-image';
import { Icon } from '@/components/ui';
import { api } from '../../lib/api';
import type { VinylRecord } from '../../lib/types';
import { Colors, Typography, Spacing, BorderRadius } from '../../constants/theme';

const FORMAT_LABEL: Record<string, string> = {
  vinyl: 'Винил',
  cd: 'CD',
  cassette: 'Кассета',
};

function formatLabel(raw: string | null | undefined): string {
  const f = (raw || '').toLowerCase();
  if (f.includes('cd') || f.includes('compact')) return FORMAT_LABEL.cd;
  if (f.includes('cass') || f.includes('tape') || f.includes('кассет')) return FORMAT_LABEL.cassette;
  return FORMAT_LABEL.vinyl;
}

export default function MyRecordsScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [records, setRecords] = useState<VinylRecord[]>([]);
  const [loading, setLoading] = useState(true);

  useFocusEffect(
    useCallback(() => {
      let alive = true;
      setLoading(true);
      api
        .listMyUserRecords()
        .then((recs) => {
          if (alive) setRecords(recs);
        })
        .catch(() => {})
        .finally(() => {
          if (alive) setLoading(false);
        });
      return () => {
        alive = false;
      };
    }, [])
  );

  return (
    <View style={styles.root}>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={[styles.header, { paddingTop: insets.top + Spacing.sm }]}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.headerBtn}>
          <Icon name="arrow-left" size={24} color="default" />
        </Pressable>
        <Text style={styles.headerTitle}>Мои релизы</Text>
        <View style={styles.headerBtn} />
      </View>

      {loading ? (
        <View style={styles.center}>
          <ActivityIndicator color={Colors.royalBlue} />
        </View>
      ) : records.length === 0 ? (
        <View style={styles.center}>
          <Icon name="disc-outline" size={48} color="secondary" />
          <Text style={styles.emptyText}>Пока нет добавленных вручную релизов</Text>
        </View>
      ) : (
        <FlatList
          data={records}
          keyExtractor={(r) => r.id}
          contentContainerStyle={styles.list}
          renderItem={({ item }) => (
            <Pressable style={styles.row} onPress={() => router.push(`/record/${item.id}` as any)}>
              <View style={styles.thumb}>
                {item.cover_image_url ? (
                  <Image source={{ uri: item.cover_image_url }} style={styles.thumbImg} contentFit="cover" />
                ) : (
                  <Icon name="disc-outline" size={24} color="secondary" />
                )}
              </View>
              <View style={styles.flex}>
                <Text style={styles.rowTitle} numberOfLines={1}>
                  {item.title}
                </Text>
                <Text style={styles.rowMeta} numberOfLines={1}>
                  {item.artist}
                  {item.year ? ` · ${item.year}` : ''} · {formatLabel(item.format_type)}
                </Text>
              </View>
              <Icon name="chevron-forward" size={20} color="secondary" />
            </Pressable>
          )}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: Colors.background },
  flex: { flex: 1 },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: Spacing.md,
    paddingBottom: Spacing.sm,
  },
  headerBtn: { width: 32, height: 32, alignItems: 'center', justifyContent: 'center' },
  headerTitle: { ...Typography.h3, color: Colors.text },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: Spacing.md, padding: Spacing.xl },
  emptyText: { ...Typography.bodySmall, color: Colors.textSecondary, textAlign: 'center' },
  list: { padding: Spacing.md, gap: Spacing.sm },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.md,
    padding: Spacing.sm,
    borderRadius: BorderRadius.md,
    backgroundColor: Colors.surface,
  },
  thumb: {
    width: 48,
    height: 48,
    borderRadius: BorderRadius.sm,
    backgroundColor: Colors.background,
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
  },
  thumbImg: { width: '100%', height: '100%' },
  rowTitle: { ...Typography.bodyBold, color: Colors.text },
  rowMeta: { ...Typography.caption, color: Colors.textMuted },
});
