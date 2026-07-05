/**
 * AuthHeader — общий хедер экранов входа/регистрации.
 *
 * Логотип + название + таглайн + сегмент-таб [ Вход | Регистрация ].
 * Сегмент выведён над форму (above-fold) — регистрация видна без скролла.
 *
 * Переключение идёт через router.replace с анимацией 'fade' (см. (auth)/_layout).
 * Хедер на обоих экранах идентичен, поэтому при кроссфейде он визуально «стоит»
 * на месте, а морфится только форма — ощущение табов, а не навигации.
 */
import { View, Text, StyleSheet } from 'react-native';
import { useRouter } from 'expo-router';
import { LinearGradient } from 'expo-linear-gradient';
import * as Haptics from 'expo-haptics';
import { Icon } from '@/components/ui';
import { SegmentedControl } from './ui/SegmentedControl';
import { Colors, Typography, Spacing } from '../constants/theme';

type AuthMode = 'login' | 'register';

interface AuthHeaderProps {
  mode: AuthMode;
}

export function AuthHeader({ mode }: AuthHeaderProps) {
  const router = useRouter();

  const handleSelect = (key: AuthMode) => {
    if (key === mode) return;
    Haptics.selectionAsync().catch(() => {});
    router.replace(key === 'login' ? '/(auth)/login' : '/(auth)/register');
  };

  return (
    <View style={styles.container}>
      <LinearGradient
        colors={[Colors.royalBlue, Colors.periwinkle]}
        style={styles.logo}
      >
        <Icon name="disc" size={56} color={Colors.background} />
      </LinearGradient>

      <Text style={styles.appName}>Вертушка</Text>
      <Text style={styles.tagline}>Твоя коллекция винила</Text>

      <SegmentedControl<AuthMode>
        segments={[
          { key: 'login', label: 'Вход' },
          { key: 'register', label: 'Регистрация' },
        ]}
        selectedKey={mode}
        onSelect={handleSelect}
        style={styles.segment}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    alignItems: 'center',
    marginBottom: Spacing.xl,
  },
  logo: {
    width: 88,
    height: 88,
    borderRadius: 44,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: Spacing.md,
  },
  appName: {
    ...Typography.h1,
    color: Colors.deepNavy,
  },
  tagline: {
    ...Typography.body,
    color: Colors.textSecondary,
    marginTop: Spacing.xs,
  },
  segment: {
    alignSelf: 'stretch',
    marginTop: Spacing.xl,
  },
});

export default AuthHeader;
