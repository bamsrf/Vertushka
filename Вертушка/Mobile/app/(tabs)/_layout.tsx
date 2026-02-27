/**
 * Tab Navigation — Blue Gradient Edition с GlassTabBar
 */
import { View } from 'react-native';
import { Tabs, Redirect } from 'expo-router';
import { useAuthStore, useOnboardingStore } from '../../lib/store';
import { GlassTabBar } from '../../components/GlassTabBar';
import { OnboardingOverlay } from '../../components/OnboardingOverlay';

export default function TabLayout() {
  const { isAuthenticated } = useAuthStore();
  const { hasSeenWelcome, tourStep } = useOnboardingStore();

  if (!isAuthenticated) {
    return <Redirect href="/(auth)/login" />;
  }

  if (!hasSeenWelcome) {
    return <Redirect href="/onboarding" />;
  }

  return (
    <View style={{ flex: 1 }}>
      <Tabs
        tabBar={(props) => <GlassTabBar {...props} />}
        screenOptions={{
          headerShown: false,
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
      {tourStep !== null && <OnboardingOverlay />}
    </View>
  );
}
