/**
 * Хедер приложения — Editorial Gradient Edition
 * Huge left-aligned GradientText, аватар справа
 */
import React from 'react';
import {
  View,
  TouchableOpacity,
  StyleSheet,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Icon } from '@/components/ui';
import { useRouter } from 'expo-router';
import { GradientText } from './GradientText';
import { ProfileAvatarButton } from './ProfileAvatarButton';
import { Colors, Typography, Spacing } from '../constants/theme';

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
              <Icon name="arrow-back" size={24} color={Colors.royalBlue} />
            </TouchableOpacity>
          )}
          {showBack && title ? (
            <GradientText style={styles.inlineTitle}>{title}</GradientText>
          ) : null}
        </View>

        <View style={styles.rightSection}>
          {rightAction || (showProfile && <ProfileAvatarButton />)}
        </View>
      </View>

      {/* Заголовок: huge, left-aligned, GradientText — только когда нет back */}
      {!showBack && title ? (
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
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
    gap: 8,
  },
  rightSection: {
    alignItems: 'flex-end',
  },
  titleRow: {
    marginTop: 4,
  },
  backButton: {
    width: 40,
    height: 40,
    alignItems: 'center',
    justifyContent: 'center',
  },
  inlineTitle: {
    ...Typography.h2,
    flexShrink: 1,
  },
});

export default Header;
