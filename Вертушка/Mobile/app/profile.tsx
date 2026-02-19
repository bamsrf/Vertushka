/**
 * Экран профиля (модальный) — Blue Gradient Edition
 */
import { useCallback, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Image,
  Alert,
  ScrollView,
  Share,
} from 'react-native';
import * as Clipboard from 'expo-clipboard';
import { LinearGradient } from 'expo-linear-gradient';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useAuthStore, useCollectionStore } from '../lib/store';
import { CollectionTab } from '../lib/types';
import { Button } from '../components/ui';
import { AnimatedGradientText } from '../components/AnimatedGradientText';
import { Colors, Typography, Spacing, BorderRadius, Shadows } from '../constants/theme';

export default function ProfileScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { user, logout } = useAuthStore();
  const { collectionItems, wishlistItems, setActiveTab } = useCollectionStore();

  const handleClose = () => {
    router.back();
  };

  const handleLogout = () => {
    Alert.alert(
      'Выйти из аккаунта?',
      'Вы уверены, что хотите выйти?',
      [
        { text: 'Отмена', style: 'cancel' },
        {
          text: 'Выйти',
          style: 'destructive',
          onPress: async () => {
            await logout();
            router.replace('/(auth)/login');
          },
        },
      ]
    );
  };

  const handleStatPress = (tab: CollectionTab) => {
    setActiveTab(tab);
    router.dismiss();
    router.navigate('/(tabs)/collection');
  };

  const [copied, setCopied] = useState(false);

  const profileUrl = user ? `https://vinyl-vertushka.ru/@${user.username}` : '';

  const handleCopyLink = useCallback(async () => {
    await Clipboard.setStringAsync(profileUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [profileUrl]);

  const handleShareProfile = useCallback(async () => {
    try {
      await Share.share({
        message: `Моя коллекция винила: ${profileUrl}`,
        url: profileUrl,
      });
    } catch {
      // Пользователь отменил
    }
  }, [profileUrl]);

  const stats = [
    {
      label: 'В коллекции',
      value: collectionItems.length,
      icon: 'disc-outline' as const,
      tab: 'collection' as CollectionTab,
    },
    {
      label: 'В списке желаний',
      value: wishlistItems.length,
      icon: 'heart-outline' as const,
      tab: 'wishlist' as CollectionTab,
    },
  ];

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      {/* Editorial header */}
      <View style={styles.header}>
        <AnimatedGradientText style={Typography.display}>Профиль</AnimatedGradientText>
        <TouchableOpacity onPress={handleClose} style={styles.closeButton}>
          <Ionicons name="close" size={28} color={Colors.deepNavy} />
        </TouchableOpacity>
      </View>

      <ScrollView
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
      >
        {/* Аватар и имя */}
        <View style={styles.profileSection}>
          <View style={styles.avatarContainer}>
            {user?.avatar_url ? (
              <Image source={{ uri: user.avatar_url }} style={styles.avatar} />
            ) : (
              <LinearGradient
                colors={[Colors.royalBlue, Colors.periwinkle]}
                style={styles.avatarPlaceholder}
              >
                <Ionicons name="disc" size={48} color={Colors.background} />
              </LinearGradient>
            )}
          </View>

          <Text style={styles.displayName}>
            {user?.display_name || user?.username || 'Пользователь'}
          </Text>
          <Text style={styles.email}>{user?.email}</Text>
        </View>

        {/* Статистика */}
        <View style={styles.statsContainer}>
          {stats.map((stat, index) => (
            <TouchableOpacity
              key={index}
              style={[styles.statCard, Shadows.lg]}
              onPress={() => handleStatPress(stat.tab)}
              activeOpacity={0.7}
            >
              <Ionicons name={stat.icon} size={24} color={Colors.royalBlue} />
              <Text style={styles.statValue}>{stat.value}</Text>
              <Text style={styles.statLabel}>{stat.label}</Text>
            </TouchableOpacity>
          ))}
        </View>

        {/* Ссылка на профиль */}
        <View style={[styles.linkCard, Shadows.sm]}>
          <Text style={styles.linkLabel}>Ваш профиль</Text>
          <Text style={styles.linkUrl}>{profileUrl}</Text>
          <View style={styles.linkActions}>
            <TouchableOpacity style={styles.linkButton} onPress={handleCopyLink}>
              <Ionicons name={copied ? "checkmark-outline" : "copy-outline"} size={18} color={Colors.royalBlue} />
              <Text style={styles.linkButtonText}>{copied ? 'Скопировано' : 'Копировать'}</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.linkButton} onPress={handleShareProfile}>
              <Ionicons name="share-outline" size={18} color={Colors.royalBlue} />
              <Text style={styles.linkButtonText}>Поделиться</Text>
            </TouchableOpacity>
          </View>
        </View>

        {/* Настройки */}
        <View style={styles.settingsSection}>
          <Text style={styles.sectionTitle}>Настройки</Text>

          <TouchableOpacity
            style={styles.settingsItem}
            onPress={() => router.push('/settings/edit-profile')}
          >
            <Ionicons name="person-outline" size={24} color={Colors.royalBlue} />
            <Text style={styles.settingsItemText}>Редактировать профиль</Text>
            <Ionicons name="chevron-forward" size={20} color={Colors.textMuted} />
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.settingsItem}
            onPress={() => router.push('/settings/share-profile')}
          >
            <Ionicons name="globe-outline" size={24} color={Colors.royalBlue} />
            <Text style={styles.settingsItemText}>Настройки профиля</Text>
            <Ionicons name="chevron-forward" size={20} color={Colors.textMuted} />
          </TouchableOpacity>

          <TouchableOpacity style={styles.settingsItem}>
            <Ionicons name="notifications-outline" size={24} color={Colors.royalBlue} />
            <Text style={styles.settingsItemText}>Уведомления</Text>
            <Ionicons name="chevron-forward" size={20} color={Colors.textMuted} />
          </TouchableOpacity>

          <TouchableOpacity style={styles.settingsItem}>
            <Ionicons name="help-circle-outline" size={24} color={Colors.royalBlue} />
            <Text style={styles.settingsItemText}>Помощь</Text>
            <Ionicons name="chevron-forward" size={20} color={Colors.textMuted} />
          </TouchableOpacity>
        </View>

        {/* Кнопка выхода */}
        <View style={styles.logoutSection}>
          <Button
            title="Выйти из аккаунта"
            onPress={handleLogout}
            variant="outline"
            fullWidth
          />
        </View>

        {/* Версия */}
        <Text style={styles.version}>Вертушка v1.0.0</Text>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-end',
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm,
  },
  closeButton: {
    padding: Spacing.xs,
  },
  content: {
    padding: Spacing.lg,
  },
  profileSection: {
    alignItems: 'center',
    marginBottom: Spacing.xl,
  },
  avatarContainer: {
    marginBottom: Spacing.md,
  },
  avatar: {
    width: 100,
    height: 100,
    borderRadius: 50,
  },
  avatarPlaceholder: {
    width: 100,
    height: 100,
    borderRadius: 50,
    alignItems: 'center',
    justifyContent: 'center',
  },
  displayName: {
    ...Typography.h2,
    color: Colors.deepNavy,
    marginBottom: Spacing.xs,
  },
  email: {
    ...Typography.body,
    color: Colors.textSecondary,
  },
  statsContainer: {
    flexDirection: 'row',
    gap: Spacing.md,
    marginBottom: Spacing.xl,
  },
  statCard: {
    flex: 1,
    backgroundColor: Colors.background,
    borderRadius: BorderRadius.lg,
    padding: Spacing.md,
    alignItems: 'center',
  },
  statValue: {
    fontSize: 36,
    fontFamily: 'Inter_800ExtraBold',
    lineHeight: 42,
    color: Colors.deepNavy,
    marginTop: Spacing.sm,
  },
  statLabel: {
    ...Typography.caption,
    color: Colors.textSecondary,
    textAlign: 'center',
  },
  linkCard: {
    backgroundColor: Colors.background,
    borderRadius: BorderRadius.lg,
    padding: Spacing.lg,
    marginBottom: Spacing.xl,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  linkLabel: {
    ...Typography.caption,
    color: Colors.textSecondary,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: Spacing.xs,
  },
  linkUrl: {
    ...Typography.bodyBold,
    color: Colors.royalBlue,
    marginBottom: Spacing.md,
  },
  linkActions: {
    flexDirection: 'row',
    gap: Spacing.md,
  },
  linkButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.xs,
    paddingVertical: Spacing.sm,
    paddingHorizontal: Spacing.md,
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.md,
  },
  linkButtonText: {
    ...Typography.buttonSmall,
    color: Colors.royalBlue,
  },
  settingsSection: {
    marginBottom: Spacing.xl,
    gap: Spacing.sm,
  },
  sectionTitle: {
    ...Typography.h4,
    color: Colors.deepNavy,
    marginBottom: Spacing.sm,
  },
  settingsItem: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: Spacing.md,
    backgroundColor: Colors.background,
    borderRadius: BorderRadius.lg,
    gap: Spacing.md,
    ...Shadows.sm,
  },
  settingsItemText: {
    ...Typography.body,
    color: Colors.text,
    flex: 1,
  },
  logoutSection: {
    marginBottom: Spacing.lg,
  },
  version: {
    ...Typography.caption,
    color: Colors.textMuted,
    textAlign: 'center',
  },
});
