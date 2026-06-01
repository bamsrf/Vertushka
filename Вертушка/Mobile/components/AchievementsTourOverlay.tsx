/**
 * AchievementsTourOverlay — одноразовый tooltip при первом заходе на экран
 * /achievements. Хранится факт показа в AsyncStorage по ключу пользователя.
 */
import { useEffect, useState } from 'react';
import {
  Modal,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
  Animated,
  Easing,
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Ionicons } from '@expo/vector-icons';
import { useAuthStore } from '../lib/store';
import { ms } from '../lib/responsive';

const KEY_PREFIX = '@vertushka:achievements_tour_seen:';

export function AchievementsTourOverlay() {
  const userId = useAuthStore((s) => s.user?.id);
  const [visible, setVisible] = useState(false);
  const opacity = new Animated.Value(0);

  useEffect(() => {
    if (!userId) return;
    let cancelled = false;
    (async () => {
      try {
        const seen = await AsyncStorage.getItem(KEY_PREFIX + userId);
        if (!cancelled && !seen) {
          setVisible(true);
        }
      } catch {
        // тихо
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [userId]);

  useEffect(() => {
    if (visible) {
      Animated.timing(opacity, {
        toValue: 1,
        duration: 250,
        easing: Easing.out(Easing.cubic),
        useNativeDriver: true,
      }).start();
    }
  }, [visible, opacity]);

  const handleClose = async () => {
    if (userId) {
      try {
        await AsyncStorage.setItem(KEY_PREFIX + userId, '1');
      } catch {
        // тихо
      }
    }
    Animated.timing(opacity, {
      toValue: 0,
      duration: 180,
      useNativeDriver: true,
    }).start(() => setVisible(false));
  };

  if (!visible) return null;

  return (
    <Modal transparent visible animationType="none" onRequestClose={handleClose} statusBarTranslucent>
      <Animated.View style={[styles.backdrop, { opacity }]}>
        <View style={styles.card}>
          <Text style={styles.emoji}>🏆</Text>
          <Text style={styles.title}>Это твой зал ачивок</Text>
          <Text style={styles.body}>
            Здесь живут трофеи коллекционера. Открываются по делу — добавляешь
            пластинку, заводишь подписку, делаешь приятное другому.
          </Text>
          <View style={styles.points}>
            <Bullet emoji="✨" text="Тиры по цвету: чем темнее, тем реже." />
            <Bullet emoji="🥚" text="Скрытые пасхалки — найдутся сами." />
            <Bullet emoji="📤" text="Каждую можно расшарить картинкой." />
          </View>
          <TouchableOpacity style={styles.btn} onPress={handleClose}>
            <Text style={styles.btnText}>Понятно</Text>
            <Ionicons name="chevron-forward" size={18} color="#FFFFFF" />
          </TouchableOpacity>
        </View>
      </Animated.View>
    </Modal>
  );
}

function Bullet({ emoji, text }: { emoji: string; text: string }) {
  return (
    <View style={styles.bulletRow}>
      <Text style={styles.bulletEmoji}>{emoji}</Text>
      <Text style={styles.bulletText}>{text}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: 'rgba(10, 11, 30, 0.6)',
    justifyContent: 'center',
    paddingHorizontal: 24,
  },
  card: {
    backgroundColor: '#FFFFFF',
    borderRadius: 22,
    padding: 28,
    alignItems: 'center',
  },
  emoji: {
    fontSize: 44,
    marginBottom: 12,
  },
  title: {
    fontSize: ms(22),
    fontWeight: '800',
    color: '#0E121C',
    marginBottom: 8,
    textAlign: 'center',
  },
  body: {
    fontSize: ms(14),
    color: '#4D5263',
    textAlign: 'center',
    lineHeight: ms(20),
    marginBottom: 18,
  },
  points: {
    alignSelf: 'stretch',
    marginBottom: 24,
    gap: 8,
  },
  bulletRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
  },
  bulletEmoji: {
    fontSize: 16,
    width: 22,
  },
  bulletText: {
    flex: 1,
    fontSize: ms(14),
    color: '#0E121C',
    lineHeight: ms(19),
  },
  btn: {
    backgroundColor: '#3B4BF5',
    paddingHorizontal: 22,
    paddingVertical: 12,
    borderRadius: 14,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  btnText: {
    color: '#FFFFFF',
    fontWeight: '700',
    fontSize: ms(15),
  },
});
