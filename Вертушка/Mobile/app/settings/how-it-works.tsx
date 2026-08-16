/**
 * «Как это работает» — точка возврата к онбордингу.
 *
 * Раньше её не было вовсе: пропустил тур — потерял навсегда, а resetOnboarding
 * жил только в коде. Теперь весь каталог подсказок виден списком, любую можно
 * вернуть, и отдельно — перезапустить welcome-карусель.
 *
 * Список строится из COACH_MARKS, поэтому тексты здесь и в самих подсказках
 * не могут разъехаться.
 */
import { useCallback, useEffect, useState } from 'react';
import {
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Icon } from '@/components/ui';
import { toast } from '../../lib/toast';
import { useAuthStore, useOnboardingStore } from '../../lib/store';
import {
  COACH_MARKS,
  CoachMarkKey,
  type CoachMarkState,
  isSuppressed,
  loadCoachMarkStates,
  resetCoachMarks,
} from '../../lib/coachMarks';
import { restoreFirstSteps, useFirstStepsDismissed } from '../../lib/onboardingProgress';
import { resetRecordTour, useRecordTourDone } from '../../lib/recordTour';
import { BorderRadius, Colors, Shadows, Spacing, Typography } from '../../constants/theme';

export default function HowItWorksScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const userId = useAuthStore((s) => s.user?.id);
  const resetOnboarding = useOnboardingStore((s) => s.resetOnboarding);

  const stepsDismissed = useFirstStepsDismissed();
  const tourDone = useRecordTourDone();

  const [states, setStates] = useState<Map<CoachMarkKey, CoachMarkState>>(new Map());

  const refresh = useCallback(async () => {
    if (!userId) return;
    const next = await loadCoachMarkStates(userId);
    // Новая Map, иначе React не увидит мутацию кэша.
    setStates(new Map(next));
  }, [userId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const handleReset = async (key: CoachMarkKey) => {
    if (!userId) return;
    await resetCoachMarks(userId, key);
    await refresh();
    toast.info('Подсказка вернётся, когда фича снова будет под рукой');
  };

  const handleResetAll = async () => {
    if (!userId) return;
    await resetCoachMarks(userId);
    await refresh();
    toast.info('Все подсказки сброшены');
  };

  const handleRestoreSteps = async () => {
    if (!stepsDismissed) {
      toast.info('«Первые шаги» и так на месте', 'Загляни в коллекцию');
      return;
    }
    await restoreFirstSteps();
    toast.success('Вернули', 'Чеклист снова в шапке коллекции');
  };

  const handleReplayTour = async () => {
    if (!tourDone) {
      toast.info('Разбор и так включён', 'Открой любую карточку релиза');
      return;
    }
    await resetRecordTour();
    toast.success('Вернули', 'Покажем при следующем открытии карточки');
  };

  const handleReplayWelcome = async () => {
    await resetOnboarding();
    router.replace('/onboarding');
  };

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} hitSlop={12}>
          <Icon name="chevron-back" size={24} color={Colors.text} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Как это работает</Text>
        <View style={styles.headerSpacer} />
      </View>

      <ScrollView
        contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + Spacing.xl }]}
        showsVerticalScrollIndicator={false}
      >
        <Text style={styles.intro}>
          Подсказки появляются сами, когда фича становится доступной. Любую можно
          вернуть — она покажется при следующем подходящем случае.
        </Text>

        {COACH_MARKS.map((mark) => {
          const state = states.get(mark.key) ?? { acknowledged: false, shows: 0 };
          const suppressed = isSuppressed(state);
          return (
            <View key={mark.key} style={[styles.card, Shadows.sm]}>
              <View style={styles.cardRow}>
                <View style={styles.iconWrap}>
                  <Icon name={mark.icon} size={20} color={Colors.royalBlue} />
                </View>
                <View style={styles.cardText}>
                  <Text style={styles.cardTitle}>{mark.title}</Text>
                  <Text style={styles.cardBody}>{mark.body}</Text>
                  {/* Маршрут важнее условия разблокировки: на этот экран
                      заходят, когда фича уже нужна, но не находится. */}
                  <View style={styles.whereRow}>
                    <Icon name="location-outline" size={12} color={Colors.royalBlue} />
                    <Text style={styles.cardWhere}>{mark.where}</Text>
                  </View>
                  <Text style={styles.cardUnlock}>Появляется: {mark.unlock}</Text>
                </View>
              </View>

              {suppressed ? (
                <TouchableOpacity
                  style={styles.cardAction}
                  onPress={() => handleReset(mark.key)}
                  accessibilityRole="button"
                >
                  <Icon name="refresh-outline" size={14} color={Colors.royalBlue} />
                  <Text style={styles.cardActionText}>Показать снова</Text>
                </TouchableOpacity>
              ) : (
                <View style={styles.cardAction}>
                  {/* Три состояния, а не два: показанная, но не закрытая
                      подсказка вернётся сама — и честнее об этом сказать,
                      чем писать «ещё не показывалась». */}
                  <Text style={styles.cardPending}>
                    {state.shows > 0 ? 'Показывалась — вернётся ещё раз' : 'Ещё не показывалась'}
                  </Text>
                </View>
              )}
            </View>
          );
        })}

        <TouchableOpacity style={styles.secondary} onPress={handleRestoreSteps}>
          <Icon name="list-outline" size={20} color={Colors.royalBlue} />
          <Text style={styles.secondaryText}>
            {stepsDismissed ? 'Вернуть «Первые шаги»' : '«Первые шаги» показаны'}
          </Text>
        </TouchableOpacity>

        <TouchableOpacity style={styles.secondary} onPress={handleResetAll}>
          <Icon name="refresh-outline" size={20} color={Colors.royalBlue} />
          <Text style={styles.secondaryText}>Сбросить все подсказки</Text>
        </TouchableOpacity>

        <TouchableOpacity style={styles.secondary} onPress={handleReplayTour}>
          <Icon name="refresh-outline" size={20} color={Colors.royalBlue} />
          <Text style={styles.secondaryText}>
            {tourDone ? 'Повторить разбор карточки релиза' : 'Разбор карточки релиза включён'}
          </Text>
        </TouchableOpacity>

        <TouchableOpacity style={styles.secondary} onPress={handleReplayWelcome}>
          <Icon name="refresh" size={20} color={Colors.royalBlue} />
          <Text style={styles.secondaryText}>Пройти приветствие заново</Text>
        </TouchableOpacity>
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
    alignItems: 'center',
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm,
  },
  headerTitle: {
    ...Typography.h4,
    color: Colors.text,
    flex: 1,
    textAlign: 'center',
  },
  headerSpacer: {
    width: 24,
  },
  content: {
    paddingHorizontal: Spacing.md,
    paddingTop: Spacing.sm,
    gap: Spacing.sm + 4,
  },
  intro: {
    ...Typography.bodySmall,
    color: Colors.textSecondary,
    marginBottom: Spacing.xs,
  },
  card: {
    padding: Spacing.md,
    borderRadius: BorderRadius.lg,
    backgroundColor: Colors.background,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  cardRow: {
    flexDirection: 'row',
    gap: Spacing.sm + 2,
  },
  iconWrap: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: Colors.royalBlue + '14',
  },
  cardText: {
    flex: 1,
  },
  cardTitle: {
    ...Typography.body,
    fontFamily: 'Inter_600SemiBold',
    color: Colors.text,
    marginBottom: 2,
  },
  cardBody: {
    ...Typography.caption,
    color: Colors.textSecondary,
  },
  whereRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 5,
    marginTop: 6,
  },
  cardWhere: {
    ...Typography.caption,
    flex: 1,
    fontSize: 12,
    lineHeight: 16,
    color: Colors.royalBlue,
  },
  cardUnlock: {
    ...Typography.caption,
    color: Colors.textMuted,
    marginTop: 6,
  },
  cardAction: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.xs,
    marginTop: Spacing.sm,
    marginLeft: 36 + Spacing.sm + 2,
  },
  cardActionText: {
    ...Typography.caption,
    fontFamily: 'Inter_600SemiBold',
    color: Colors.royalBlue,
  },
  cardPending: {
    ...Typography.caption,
    color: Colors.textMuted,
  },
  secondary: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm + 2,
    paddingVertical: Spacing.md,
    paddingHorizontal: Spacing.md,
    borderRadius: BorderRadius.lg,
    backgroundColor: Colors.surface,
  },
  secondaryText: {
    ...Typography.body,
    color: Colors.text,
  },
});
