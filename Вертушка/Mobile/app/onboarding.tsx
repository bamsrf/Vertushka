/**
 * Onboarding Welcome Screen
 */
import { View, Text, StyleSheet, Pressable } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import { useOnboardingStore } from '../lib/store';
import { Colors, Typography, BorderRadius, Spacing } from '../constants/theme';

const features = [
  {
    icon: 'camera-outline' as const,
    text: 'Сканируй штрихкод или обложку',
  },
  {
    icon: 'search-outline' as const,
    text: 'Ищи артистов, альбомы и релизы',
  },
  {
    icon: 'library-outline' as const,
    text: 'Управляй коллекцией и вишлистом',
  },
];

export default function OnboardingScreen() {
  const insets = useSafeAreaInsets();
  const { completeWelcome, startTour, completeTour } = useOnboardingStore();

  const handleStart = async () => {
    await completeWelcome();
    startTour();
    router.replace('/(tabs)');
  };

  const handleSkip = async () => {
    await completeWelcome();
    await completeTour();
    router.replace('/(tabs)');
  };

  return (
    <LinearGradient
      colors={['#3B4BF5', '#5B6AF5', '#8B9CF7']}
      style={styles.container}
    >
      <View style={[styles.content, { paddingTop: insets.top + 60, paddingBottom: insets.bottom + 24 }]}>
        <View style={styles.hero}>
          <View style={styles.iconContainer}>
            <Ionicons name="disc-outline" size={72} color="#fff" />
          </View>
          <Text style={styles.title}>Вертушка</Text>
          <Text style={styles.subtitle}>Твоя виниловая коллекция</Text>
        </View>

        <View style={styles.features}>
          {features.map((feature, index) => (
            <View key={index} style={styles.featureRow}>
              <View style={styles.featureIcon}>
                <Ionicons name={feature.icon} size={24} color="#fff" />
              </View>
              <Text style={styles.featureText}>{feature.text}</Text>
            </View>
          ))}
        </View>

        <View style={styles.actions}>
          <Pressable style={styles.startButton} onPress={handleStart}>
            <Text style={styles.startButtonText}>Начать</Text>
          </Pressable>
          <Pressable style={styles.skipButton} onPress={handleSkip}>
            <Text style={styles.skipButtonText}>Пропустить</Text>
          </Pressable>
        </View>
      </View>
    </LinearGradient>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  content: {
    flex: 1,
    paddingHorizontal: Spacing.xl,
    justifyContent: 'space-between',
  },
  hero: {
    alignItems: 'center',
    gap: Spacing.md,
  },
  iconContainer: {
    width: 120,
    height: 120,
    borderRadius: 60,
    backgroundColor: 'rgba(255, 255, 255, 0.15)',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: Spacing.sm,
  },
  title: {
    ...Typography.h1,
    fontSize: 40,
    lineHeight: 46,
    color: '#fff',
  },
  subtitle: {
    ...Typography.body,
    color: 'rgba(255, 255, 255, 0.8)',
  },
  features: {
    gap: Spacing.lg,
  },
  featureRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.md,
  },
  featureIcon: {
    width: 48,
    height: 48,
    borderRadius: BorderRadius.md,
    backgroundColor: 'rgba(255, 255, 255, 0.15)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  featureText: {
    ...Typography.bodyBold,
    color: '#fff',
    flex: 1,
  },
  actions: {
    alignItems: 'center',
    gap: Spacing.md,
  },
  startButton: {
    width: '100%',
    height: 56,
    backgroundColor: '#fff',
    borderRadius: BorderRadius.xl,
    alignItems: 'center',
    justifyContent: 'center',
  },
  startButtonText: {
    ...Typography.button,
    color: Colors.royalBlue,
  },
  skipButton: {
    paddingVertical: Spacing.sm,
  },
  skipButtonText: {
    ...Typography.bodySmall,
    color: 'rgba(255, 255, 255, 0.7)',
  },
});
