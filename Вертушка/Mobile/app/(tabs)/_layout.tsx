/**
 * Tab Navigation — Blue Gradient Edition с GlassTabBar
 */
import { Tabs, Redirect } from 'expo-router';
import { useAuthStore } from '../../lib/store';
import { GlassTabBar } from '../../components/GlassTabBar';

export default function TabLayout() {
  const { isAuthenticated } = useAuthStore();

  if (!isAuthenticated) {
    return <Redirect href="/(auth)/login" />;
  }

  return (
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
  );
}
