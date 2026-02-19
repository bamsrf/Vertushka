/**
 * Хедер приложения — Editorial Gradient Edition
 * Huge left-aligned GradientText, аватар справа
 */
import React from 'react';
import {
  View,
  TouchableOpacity,
  StyleSheet,
  Image,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { GradientText } from './GradientText';
import { Colors, Typography, Spacing } from '../constants/theme';
import { useAuthStore } from '../lib/store';

interface HeaderProps {
  title?: string;
  showProfile?: boolean;
  showBack?: boolean;
  rightAction?: React.ReactNode;
}

export function Header({
  title = 'Вертушка',
  showProfile = true,
  showBack = false,
  rightAction,
}: HeaderProps) {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user } = useAuthStore();

  const handleProfilePress = () => {
    router.push('/profile');
  };

  const handleBackPress = () => {
    router.back();
  };

  return (
    <View style={[styles.container, { paddingTop: insets.top + 8 }]}>
      {/* Верхняя строка: back / пустота + аватар / rightAction */}
      <View style={styles.topRow}>
        <View style={styles.leftSection}>
          {showBack && (
            <TouchableOpacity style={styles.backButton} onPress={handleBackPress}>
              <Ionicons name="arrow-back" size={24} color={Colors.deepNavy} />
            </TouchableOpacity>
          )}
        </View>

        <View style={styles.rightSection}>
          {rightAction || (
            showProfile && (
              <TouchableOpacity style={styles.profileButton} onPress={handleProfilePress}>
                {user?.avatar_url ? (
                  <Image source={{ uri: user.avatar_url }} style={styles.avatar} />
                ) : (
                  <LinearGradient
                    colors={[Colors.royalBlue, Colors.periwinkle]}
                    style={styles.avatarPlaceholder}
                  >
                    <Ionicons name="disc" size={20} color={Colors.background} />
                  </LinearGradient>
                )}
              </TouchableOpacity>
            )
          )}
        </View>
      </View>

      {/* Заголовок: huge, left-aligned, GradientText */}
      {title ? (
        <View style={styles.titleRow}>
          <GradientText style={Typography.display}>{title}</GradientText>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: Colors.background,
    paddingHorizontal: Spacing.md,
    paddingBottom: Spacing.sm,
  },
  topRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    minHeight: 40,
  },
  leftSection: {
    alignItems: 'flex-start',
  },
  rightSection: {
    alignItems: 'flex-end',
  },
  titleRow: {
    marginTop: 4,
  },
  profileButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    overflow: 'hidden',
    borderWidth: 2,
    borderColor: Colors.lavender,
  },
  avatar: {
    width: '100%',
    height: '100%',
  },
  avatarPlaceholder: {
    width: '100%',
    height: '100%',
    alignItems: 'center',
    justifyContent: 'center',
  },
  backButton: {
    width: 40,
    height: 40,
    alignItems: 'center',
    justifyContent: 'center',
  },
});

export default Header;
