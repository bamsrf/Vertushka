/**
 * Auth Stack Layout
 */
import { Stack, Redirect } from 'expo-router';
import { useAuthStore } from '../../lib/store';
import { Colors } from '../../constants/theme';

export default function AuthLayout() {
  const { isAuthenticated } = useAuthStore();

  // Если уже авторизован - редирект на главную
  if (isAuthenticated) {
    return <Redirect href="/(tabs)" />;
  }

  return (
    <Stack
      screenOptions={{
        headerShown: false,
        contentStyle: { backgroundColor: Colors.background },
        animation: 'slide_from_right',
      }}
    >
      <Stack.Screen name="login" />
      <Stack.Screen name="register" />
      <Stack.Screen name="forgot-password" />
      <Stack.Screen name="verify-code" />
      <Stack.Screen name="reset-password" />
    </Stack>
  );
}
