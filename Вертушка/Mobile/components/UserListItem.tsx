/**
 * Элемент списка пользователей — аватарка + username + display_name
 */
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { Image } from 'expo-image';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Typography, Spacing, BorderRadius } from '../constants/theme';
import { resolveMediaUrl } from '../lib/api';

interface UserListItemProps {
  username: string;
  displayName?: string;
  avatarUrl?: string;
  onPress: () => void;
}

export function UserListItem({ username, displayName, avatarUrl, onPress }: UserListItemProps) {
  return (
    <TouchableOpacity style={styles.container} onPress={onPress} activeOpacity={0.7}>
      {avatarUrl ? (
        <Image source={resolveMediaUrl(avatarUrl)} style={styles.avatar} cachePolicy="disk" />
      ) : (
        <LinearGradient
          colors={[Colors.royalBlue, Colors.periwinkle]}
          style={styles.avatar}
        >
          <Ionicons name="person" size={18} color={Colors.background} />
        </LinearGradient>
      )}
      <View style={styles.textContainer}>
        <Text style={styles.displayName} numberOfLines={1}>
          {displayName || username}
        </Text>
        <Text style={styles.username} numberOfLines={1}>@{username}</Text>
      </View>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: Spacing.md,
    gap: Spacing.md,
    backgroundColor: Colors.background,
    borderRadius: BorderRadius.lg,
  },
  avatar: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
  },
  textContainer: {
    flex: 1,
  },
  displayName: {
    ...Typography.bodyBold,
    color: Colors.deepNavy,
  },
  username: {
    ...Typography.caption,
    color: Colors.textSecondary,
  },
});
