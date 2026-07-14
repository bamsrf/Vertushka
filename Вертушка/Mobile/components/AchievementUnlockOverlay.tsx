/**
 * AchievementUnlockOverlay — модальная анимация открытия ачивки.
 *
 * Использование:
 * 1) В корне приложения (`app/_layout.tsx`) монтируется `<AchievementUnlockHost />`
 *    который слушает события из bus.
 * 2) Из любого места вызываем `notifyAchievementUnlocked(codes)` — хост
 *    подгружает данные через API и показывает overlay.
 *
 * Анимация: затемнение → пин падает и вращается → конфетти + haptic →
 * лента с названием → кнопки «Поделиться» / «Дальше».
 *
 * Batch: если открылось 2+ ачивки за один emit_event, показываем стек —
 * сверху главная (самая редкая), снизу подписные пины с «+N ещё».
 */
import { useEffect, useRef, useState } from 'react';
import {
  Animated,
  Dimensions,
  Easing,
  Modal,
  Share,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
  Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import * as Sharing from 'expo-sharing';
import { LinearGradient } from 'expo-linear-gradient';

import { api } from '../lib/api';
import { AchievementPin } from './AchievementPin';
import { Confetti } from './Confetti';
import { TIER_AURA } from './achievement-scenes';
import type { AchievementItem, AchievementTierKey } from '../lib/types';

// ─── Event bus ──────────────────────────────────────────────────────────────

type Listener = (codes: string[]) => void;
const _listeners: Set<Listener> = new Set();

export function notifyAchievementUnlocked(codes: string[]) {
  if (!codes || codes.length === 0) return;
  _listeners.forEach((cb) => {
    try {
      cb(codes);
    } catch {
      // ignore
    }
  });
}

function subscribe(cb: Listener): () => void {
  _listeners.add(cb);
  return () => _listeners.delete(cb);
}

// ─── Tier ranking для выбора «главной» в batch ─────────────────────────────

const TIER_RANK: Record<AchievementTierKey, number> = {
  simple: 1,
  notable: 2,
  rare: 3,
  epic: 4,
  legend: 5,
};

function pickBatchOrder(items: AchievementItem[]): AchievementItem[] {
  return [...items].sort((a, b) => {
    const ra = TIER_RANK[a.tier.key] || 0;
    const rb = TIER_RANK[b.tier.key] || 0;
    if (ra !== rb) return rb - ra;
    // Мета впереди обычных
    if (a.is_meta !== b.is_meta) return a.is_meta ? -1 : 1;
    return 0;
  });
}

// ─── Host ──────────────────────────────────────────────────────────────────

interface BatchPayload {
  /** Главная ачивка (самая редкая в batch'е) */
  main: AchievementItem;
  /** Остальные ачивки batch'а — подписные пины */
  others: AchievementItem[];
}

export function AchievementUnlockHost() {
  const [queue, setQueue] = useState<BatchPayload[]>([]);
  const [current, setCurrent] = useState<BatchPayload | null>(null);

  useEffect(() => {
    return subscribe(async (codes) => {
      try {
        const my = await api.getMyAchievements();
        const lookup = new Map<string, AchievementItem>();
        for (const s of my.series) for (const it of s.items) lookup.set(it.code, it);
        try {
          const random = await api.getMyRandomUnlocked();
          for (const it of random.items) lookup.set(it.code, it);
        } catch {
          // тихо
        }
        const items = codes
          .map((c) => lookup.get(c))
          .filter((x): x is AchievementItem => Boolean(x) && x!.is_unlocked);
        if (items.length === 0) return;
        const ordered = pickBatchOrder(items);
        const [main, ...others] = ordered;
        setQueue((prev) => [...prev, { main, others }]);
      } catch {
        // тихо
      }
    });
  }, []);

  useEffect(() => {
    if (!current && queue.length > 0) {
      setCurrent(queue[0]);
      setQueue((prev) => prev.slice(1));
    }
  }, [current, queue]);

  if (!current) return null;

  return (
    <UnlockModal
      payload={current}
      onDismiss={() => setCurrent(null)}
    />
  );
}

// ─── Modal ─────────────────────────────────────────────────────────────────

function UnlockModal({
  payload,
  onDismiss,
}: {
  payload: BatchPayload;
  onDismiss: () => void;
}) {
  const { main, others } = payload;
  const aura = TIER_AURA[main.tier.key] || TIER_AURA.simple;

  const backdrop = useRef(new Animated.Value(0)).current;
  const pinScale = useRef(new Animated.Value(0)).current;
  const pinRotate = useRef(new Animated.Value(0)).current;
  const pinTranslateY = useRef(new Animated.Value(-120)).current;
  const ribbonOpacity = useRef(new Animated.Value(0)).current;
  const ribbonTranslateY = useRef(new Animated.Value(20)).current;
  const [sharing, setSharing] = useState(false);
  const shareCardRef = useRef<View>(null);

  useEffect(() => {
    // Haptic — сразу
    if (Platform.OS !== 'web') {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
    }
    Animated.parallel([
      Animated.timing(backdrop, {
        toValue: 1,
        duration: 200,
        useNativeDriver: true,
      }),
      Animated.sequence([
        Animated.parallel([
          Animated.timing(pinTranslateY, {
            toValue: 0,
            duration: 700,
            easing: Easing.bezier(0.25, 1.4, 0.5, 1.0),
            useNativeDriver: true,
          }),
          Animated.timing(pinScale, {
            toValue: 1,
            duration: 700,
            easing: Easing.bezier(0.2, 1.2, 0.5, 1),
            useNativeDriver: true,
          }),
          Animated.timing(pinRotate, {
            toValue: 1,
            duration: 900,
            easing: Easing.out(Easing.cubic),
            useNativeDriver: true,
          }),
        ]),
        Animated.parallel([
          Animated.timing(ribbonOpacity, {
            toValue: 1,
            duration: 350,
            useNativeDriver: true,
          }),
          Animated.timing(ribbonTranslateY, {
            toValue: 0,
            duration: 350,
            easing: Easing.out(Easing.cubic),
            useNativeDriver: true,
          }),
        ]),
      ]),
    ]).start();
  }, [main.code]);

  const handleDismiss = () => {
    Animated.timing(backdrop, {
      toValue: 0,
      duration: 200,
      useNativeDriver: true,
    }).start(() => onDismiss());
  };

  const handleShare = async () => {
    setSharing(true);
    if (Platform.OS !== 'web') {
      Haptics.selectionAsync().catch(() => {});
    }
    try {
      // Снимаем реальную карточку (пин + текст) в PNG на клиенте.
      // Ленивый require: view-shot — нативный модуль, его нет в Expo Go.
      // Статический импорт ронял старт; здесь падение ловит catch ниже.
      const { captureRef } = require('react-native-view-shot');
      const uri = await captureRef(shareCardRef, {
        format: 'png',
        quality: 1,
        result: 'tmpfile',
      });
      const available = await Sharing.isAvailableAsync();
      if (available) {
        await Sharing.shareAsync(uri, {
          mimeType: 'image/png',
          dialogTitle: main.title_ru || 'Ачивка',
        });
      } else {
        // Fallback на стандартный Share с текстом
        await Share.share({
          message: `Открыл ачивку «${main.title_ru}» в Вертушке 🎵`,
        });
      }
    } catch {
      try {
        await Share.share({
          message: `Открыл ачивку «${main.title_ru}» в Вертушке 🎵`,
        });
      } catch {
        // отмена пользователем
      }
    } finally {
      setSharing(false);
    }
  };

  const rotateInterp = pinRotate.interpolate({
    inputRange: [0, 1],
    outputRange: ['0deg', '360deg'],
  });

  return (
    <Modal transparent visible animationType="none" onRequestClose={handleDismiss} statusBarTranslucent>
      <Animated.View
        style={[
          styles.backdrop,
          { opacity: backdrop, backgroundColor: backdropColor(main.tier.key) },
        ]}
      >
        {/* Конфетти на заднем плане */}
        <Confetti
          colors={[aura.aura, aura.auraSoft, '#FFFFFF', '#FFD66B']}
          count={36}
          duration={2400}
          triggerKey={main.code}
        />

        <View style={styles.center} pointerEvents="box-none">
          <Text style={styles.eyebrow}>
            {others.length > 0
              ? `Открыто ${others.length + 1} ачивки`
              : 'Открыта новая ачивка'}
          </Text>

          <Animated.View
            style={{
              transform: [
                { translateY: pinTranslateY },
                { scale: pinScale },
                { rotate: rotateInterp },
              ],
            }}
          >
            <AchievementPin item={main} size={140} glowOverride />
          </Animated.View>

          <Animated.View
            style={[
              styles.ribbon,
              {
                opacity: ribbonOpacity,
                transform: [{ translateY: ribbonTranslateY }],
              },
            ]}
          >
            <Text style={styles.title}>{main.title_ru || '🥚 Пасхалка'}</Text>
            <View style={[styles.tierChip, { borderColor: aura.aura }]}>
              <Text style={styles.tierChipText}>{main.tier.label_ru}</Text>
            </View>
            {main.flavor_ru ? (
              <Text style={styles.flavor}>«{main.flavor_ru}»</Text>
            ) : main.description_done_ru || main.description_ru ? (
              <Text style={styles.flavor}>
                {main.description_done_ru || main.description_ru}
              </Text>
            ) : null}

            {/* Batch — подписные пины */}
            {others.length > 0 && (
              <View style={styles.batchRow}>
                <Text style={styles.batchEyebrow}>и ещё:</Text>
                <View style={styles.batchPinsRow}>
                  {others.slice(0, 4).map((o) => (
                    <View key={o.code} style={styles.batchPinCell}>
                      <AchievementPin item={o} size={56} />
                      <Text numberOfLines={1} style={styles.batchPinLabel}>
                        {o.title_ru || '?'}
                      </Text>
                    </View>
                  ))}
                  {others.length > 4 && (
                    <View style={styles.batchPinCell}>
                      <View style={styles.batchPlus}>
                        <Text style={styles.batchPlusText}>+{others.length - 4}</Text>
                      </View>
                    </View>
                  )}
                </View>
              </View>
            )}
          </Animated.View>

          <Animated.View style={[styles.actions, { opacity: ribbonOpacity }]}>
            <TouchableOpacity
              style={[styles.btnPrimary, sharing && { opacity: 0.6 }]}
              onPress={handleShare}
              disabled={sharing}
            >
              <Ionicons name="share-outline" size={20} color="#FFFFFF" />
              <Text style={styles.btnPrimaryText}>
                {sharing ? 'Готовим…' : 'Поделиться'}
              </Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.btnSecondary} onPress={handleDismiss}>
              <Text style={styles.btnSecondaryText}>Дальше</Text>
            </TouchableOpacity>
          </Animated.View>
        </View>
      </Animated.View>

      {/* Off-screen карточка для шаринга (снимается через view-shot) */}
      <View style={styles.shareCardOffscreen} pointerEvents="none">
        <View ref={shareCardRef} collapsable={false} style={styles.shareCard}>
          <LinearGradient
            colors={[main.tier.color_hex + '33', '#0E0E16']}
            start={{ x: 0, y: 0 }}
            end={{ x: 0, y: 1 }}
            style={styles.shareCardBg}
          >
            <Text style={styles.shareCardBrand}>Вертушка</Text>
            <AchievementPin item={main} size={140} glowOverride />
            <Text style={styles.shareCardTitle}>{main.title_ru || '🥚 Пасхалка'}</Text>
            <View
              style={[
                styles.shareCardTierChip,
                { backgroundColor: main.tier.color_hex, shadowColor: main.tier.color_hex },
              ]}
            >
              <Text style={styles.shareCardTierText}>
                {main.tier.label_ru.toUpperCase()}
              </Text>
            </View>
            {main.flavor_ru ? (
              <Text style={styles.shareCardFlavor}>«{main.flavor_ru}»</Text>
            ) : main.description_done_ru || main.description_ru ? (
              <Text style={styles.shareCardFlavor}>
                {main.description_done_ru || main.description_ru}
              </Text>
            ) : null}
          </LinearGradient>
        </View>
      </View>
    </Modal>
  );
}

function backdropColor(tier: AchievementTierKey): string {
  if (tier === 'legend' || tier === 'epic') return 'rgba(10, 11, 30, 0.92)';
  if (tier === 'rare') return 'rgba(60, 22, 60, 0.88)';
  return 'rgba(20, 30, 80, 0.85)';
}

const { width: SCREEN_W } = Dimensions.get('window');

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    justifyContent: 'center',
  },
  shareCardOffscreen: {
    position: 'absolute',
    left: -9999,
    top: 0,
  },
  shareCard: {
    width: 1080 / 3,
    height: 1920 / 3,
  },
  shareCardBg: {
    flex: 1,
    paddingHorizontal: 36,
    alignItems: 'center',
    justifyContent: 'center',
  },
  shareCardTitle: {
    fontSize: 28,
    fontWeight: '800',
    color: '#FFFFFF',
    textAlign: 'center',
    marginTop: 16,
  },
  shareCardTierChip: {
    marginTop: 16,
    paddingHorizontal: 18,
    paddingVertical: 8,
    borderRadius: 16,
    shadowOpacity: 0.5,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 2 },
    elevation: 6,
  },
  shareCardTierText: {
    fontSize: 14,
    fontWeight: '800',
    color: '#FFFFFF',
    letterSpacing: 1.5,
  },
  shareCardFlavor: {
    fontSize: 15,
    fontStyle: 'italic',
    color: 'rgba(255,255,255,0.82)',
    textAlign: 'center',
    marginTop: 14,
    lineHeight: 21,
  },
  shareCardBrand: {
    position: 'absolute',
    top: 72,
    fontFamily: 'RubikMonoOne-Regular',
    fontSize: 26,
    color: 'rgba(255,255,255,0.92)',
    textAlign: 'center',
    letterSpacing: 1,
  },
  center: {
    alignItems: 'center',
    paddingHorizontal: 32,
  },
  eyebrow: {
    color: 'rgba(255,255,255,0.65)',
    fontSize: 13,
    letterSpacing: 1.6,
    textTransform: 'uppercase',
    marginBottom: 28,
    fontWeight: '600',
  },
  ribbon: {
    marginTop: 28,
    alignItems: 'center',
    maxWidth: SCREEN_W - 64,
  },
  title: {
    fontSize: 30,
    fontWeight: '800',
    color: '#FFFFFF',
    textAlign: 'center',
    marginBottom: 10,
  },
  tierChip: {
    paddingHorizontal: 14,
    paddingVertical: 5,
    borderRadius: 14,
    borderWidth: 1.5,
    marginBottom: 14,
  },
  tierChipText: {
    fontSize: 13,
    fontWeight: '700',
    letterSpacing: 0.4,
    color: '#FFFFFF',
  },
  flavor: {
    color: 'rgba(255,255,255,0.75)',
    fontSize: 14,
    fontStyle: 'italic',
    textAlign: 'center',
    paddingHorizontal: 8,
  },
  batchRow: {
    marginTop: 22,
    alignItems: 'center',
  },
  batchEyebrow: {
    color: 'rgba(255,255,255,0.55)',
    fontSize: 11,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 1.2,
    marginBottom: 10,
  },
  batchPinsRow: {
    flexDirection: 'row',
    gap: 10,
    flexWrap: 'wrap',
    justifyContent: 'center',
  },
  batchPinCell: {
    alignItems: 'center',
    width: 64,
  },
  batchPinLabel: {
    color: 'rgba(255,255,255,0.7)',
    fontSize: 10,
    marginTop: 4,
    textAlign: 'center',
  },
  batchPlus: {
    width: 56,
    height: 56,
    borderRadius: 28,
    borderWidth: 1.5,
    borderColor: 'rgba(255,255,255,0.35)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  batchPlusText: {
    color: '#FFFFFF',
    fontWeight: '800',
    fontSize: 16,
  },
  actions: {
    marginTop: 36,
    flexDirection: 'row',
    gap: 12,
  },
  btnPrimary: {
    backgroundColor: '#3B4BF5',
    paddingHorizontal: 20,
    paddingVertical: 12,
    borderRadius: 14,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  btnPrimaryText: {
    color: '#FFFFFF',
    fontWeight: '700',
    fontSize: 15,
  },
  btnSecondary: {
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.3)',
  },
  btnSecondaryText: {
    color: '#FFFFFF',
    fontWeight: '600',
    fontSize: 15,
  },
});
