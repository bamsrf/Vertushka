/**
 * Правовая информация — хаб со ссылками на Условия и Конфиденциальность.
 * Один пункт в профиле вместо двух отдельных рядов.
 */
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Icon } from '@/components/ui';
import { Colors, Typography, Spacing } from '../../constants/theme';
import { ms } from '../../lib/responsive';

export default function LegalIndexScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backButton}>
          <Icon name="arrow-back" size={24} color={Colors.royalBlue} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Правовая информация</Text>
        <View style={styles.placeholder} />
      </View>

      <View style={styles.content}>
        <TouchableOpacity
          style={styles.item}
          onPress={() => router.push('/legal/terms' as any)}
        >
          <Icon name="document-text-outline" size={24} color={Colors.royalBlue} />
          <Text style={styles.itemText}>Условия использования</Text>
          <Icon name="chevron-forward" size={20} color={Colors.textMuted} />
        </TouchableOpacity>

        <TouchableOpacity
          style={styles.item}
          onPress={() => router.push('/legal/privacy' as any)}
        >
          <Icon name="shield-checkmark-outline" size={24} color={Colors.royalBlue} />
          <Text style={styles.itemText}>Конфиденциальность</Text>
          <Icon name="chevron-forward" size={20} color={Colors.textMuted} />
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: Spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: Colors.divider,
  },
  headerTitle: { ...Typography.h4, fontSize: ms(17), color: Colors.royalBlue },
  backButton: { width: 36, height: 36, alignItems: 'center', justifyContent: 'center' },
  placeholder: { width: 36, height: 36 },
  content: { paddingTop: Spacing.sm },
  item: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.md,
    paddingVertical: Spacing.md,
    paddingHorizontal: Spacing.lg,
    borderBottomWidth: 1,
    borderBottomColor: Colors.divider,
  },
  itemText: { ...Typography.body, color: Colors.deepNavy, flex: 1 },
});
