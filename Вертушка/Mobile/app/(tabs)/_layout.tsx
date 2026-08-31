/**
 * Tab Navigation — Blue Gradient Edition с GlassTabBar
 */
import { Tabs, Redirect } from 'expo-router';
import { useAuthStore, useOnboardingStore } from '../../lib/store';
import { GlassTabBar } from '../../components/GlassTabBar';
import { ErrorBoundary } from '../../components/ErrorBoundary';

export default function TabLayout() {
  const { isAuthenticated, user } = useAuthStore();
  const { hasSeenWelcome, loadedForUserId } = useOnboardingStore();

  if (!isAuthenticated) {
    return <Redirect href="/(auth)/login" />;
  }

  // Флаг лежит в AsyncStorage и читается асинхронно, а `hasSeenWelcome`
  // стартует как false. Без этой проверки первый же рендер после логина
  // редиректил в карусель, не дождавшись чтения, — и человек, прошедший
  // онбординг полгода назад, видел его снова при каждом холодном старте.
  // Возврата назад нет: чтение доезжает уже на экране онбординга.
  //
  // Сравниваем именно `loadedForUserId`, а не `isReady`: на старте флаг
  // успевает прочитаться для userId = null (аккаунт ещё не восстановлен),
  // и одного `isReady` хватило бы, чтобы пропустить чужой ответ.
  if (loadedForUserId !== (user?.id ?? null)) {
    return null;
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
          // См. docs/plans/appstore/APPSTORE_LAUNCH_PLAN.md §4.4.
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
