/**
 * Tab Navigation — Blue Gradient Edition с GlassTabBar
 */
import { Tabs, Redirect } from 'expo-router';
import { useAuthStore, useOnboardingStore } from '../../lib/store';
import { GlassTabBar } from '../../components/GlassTabBar';
import { ErrorBoundary } from '../../components/ErrorBoundary';

export default function TabLayout() {
  const { isAuthenticated } = useAuthStore();
  const { hasSeenWelcome } = useOnboardingStore();

  if (!isAuthenticated) {
    return <Redirect href="/(auth)/login" />;
  }

  if (!hasSeenWelcome) {
    return <Redirect href="/onboarding" />;
  }

  return (
    <ErrorBoundary>
      <Tabs
        tabBar={(props) => <GlassTabBar {...props} />}
        screenOptions={{
          headerShown: false,
          // Останавливаем ре-рендеры невидимых табов на уровне навигатора
          // (react-native-screens). Системный аналог lib/useAnimationGate.ts,
          // который гейтит вручную и только четыре компонента: freezeOnBlur
          // страхует всё разом, включая анимации, добавленные позже.
          // См. docs/plans/APPSTORE_LAUNCH_PLAN.md §4.4.
          freezeOnBlur: true,
        }}
      >
        <Tabs.Screen
          name="search"
          options={{ title: 'Поиск' }}
        />
        <Tabs.Screen
          name="index"
          options={{ title: 'Скан' }}
        />
        <Tabs.Screen
          name="collection"
          options={{ title: 'Коллекция' }}
        />
      </Tabs>
    </ErrorBoundary>
  );
}
