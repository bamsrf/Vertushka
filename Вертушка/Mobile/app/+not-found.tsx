/**
 * Экран 404 - страница не найдена
 */
import { Link, Stack } from 'expo-router';
import { StyleSheet, View, Text } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Typography, Spacing } from '../constants/theme';

export default function NotFoundScreen() {
  return (
    <>
      <Stack.Screen options={{ title: 'Ошибка' }} />
      <View style={styles.container}>
        <Ionicons name="disc-outline" size={64} color={Colors.textMuted} />
        <Text style={styles.title}>Страница не найдена</Text>
        <Text style={styles.subtitle}>Такой страницы не существует</Text>

        <Link href="/" style={styles.link}>
          <Text style={styles.linkText}>Вернуться на главную</Text>
        </Link>
      </View>
    </>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: Spacing.lg,
    backgroundColor: Colors.background,
  },
  title: {
    ...Typography.h3,
    color: Colors.royalBlue,
    marginTop: Spacing.md,
  },
  subtitle: {
    ...Typography.body,
    color: Colors.textSecondary,
    marginTop: Spacing.xs,
  },
  link: {
    marginTop: Spacing.lg,
    paddingVertical: Spacing.md,
    paddingHorizontal: Spacing.lg,
    backgroundColor: Colors.royalBlue,
    borderRadius: 12,
  },
  linkText: {
    ...Typography.button,
    color: Colors.background,
  },
});
