/**
 * /dev/thermal — живое термальное состояние устройства и выжимка MetricKit.
 *
 * Назначение:
 *   - Проверить руками, греет ли конкретный экран. Основные подозреваемые —
 *     бесконечные Reanimated-циклы без cancelAnimation: /radar (линейный sweep
 *     4.2с плюс пульс), /collection/value, /record/[id].
 *   - Убедиться, что цепочка «нативный модуль → JS → Sentry» жива, не дожидаясь
 *     суточной доставки MetricKit.
 *
 * Не входит в пользовательскую навигацию — открывается прямой ссылкой
 * `/dev/thermal` (Expo dev-tools или router.push), как и остальные dev-экраны.
 *
 * Как пользоваться: открыть этот экран, посмотреть базовое состояние, уйти на
 * подозрительный экран, подержать несколько минут и вернуться — переходы
 * останутся в ленте, она переживает уход с экрана (история живёт в модуле).
 */
import React, { useEffect, useState } from 'react';
import { ScrollView, View, Text, StyleSheet } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import {
  getCurrentThermalState,
  getThermalHistory,
  getLastMetricSummary,
  subscribeThermal,
  isDeviceMetricsAvailable,
  type ThermalState,
  type ThermalEntry,
} from '../../lib/deviceMetrics';
import { Colors, Typography, Spacing, BorderRadius } from '../../constants/theme';
import { withDevOnly } from '../../components/DevOnly';

/** serious/critical означают, что система уже троттлит — это красная зона. */
const STATE_COLOR: Record<ThermalState, string> = {
  nominal: Colors.success,
  fair: Colors.warning,
  serious: Colors.error,
  critical: Colors.error,
  unknown: Colors.textMuted,
};

const STATE_HINT: Record<ThermalState, string> = {
  nominal: 'Норма, троттлинга нет',
  fair: 'Слегка тёплый, вентиляторы условно закрутились',
  serious: 'Система троттлит CPU и GPU',
  critical: 'Крит, работает только необходимое',
  unknown: 'Нативный модуль недоступен',
};

function formatTime(timestamp: number): string {
  const d = new Date(timestamp);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

function ThermalScreen() {
  const insets = useSafeAreaInsets();
  const available = isDeviceMetricsAvailable();
  const [state, setState] = useState<ThermalState>(() => getCurrentThermalState());
  const [history, setHistory] = useState<ThermalEntry[]>(() => getThermalHistory());

  useEffect(() => {
    // Состояние могло смениться, пока экран был закрыт.
    setState(getCurrentThermalState());
    setHistory(getThermalHistory());

    return subscribeThermal((entry) => {
      setState(entry.state);
      setHistory(getThermalHistory());
    });
  }, []);

  const summary = getLastMetricSummary();

  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + Spacing.xl }]}
    >
      {!available && (
        <View style={styles.warning}>
          <Text style={styles.warningText}>
            Нативный модуль device-metrics не собран. В Expo Go его нет — нужна нативная
            сборка (`npx expo run:ios --device`).
          </Text>
        </View>
      )}

      <View style={[styles.hero, { borderColor: STATE_COLOR[state] }]}>
        <Text style={styles.heroLabel}>Текущее состояние</Text>
        <Text style={[styles.heroState, { color: STATE_COLOR[state] }]}>{state}</Text>
        <Text style={styles.heroHint}>{STATE_HINT[state]}</Text>
      </View>

      <Text style={styles.sectionTitle}>Переходы ({history.length})</Text>
      {history.length === 0 ? (
        <Text style={styles.empty}>Пока ничего. Состояние меняется редко — это нормально.</Text>
      ) : (
        <View style={styles.card}>
          {[...history].reverse().map((entry, i) => (
            <View key={`${entry.timestamp}-${i}`} style={styles.row}>
              <Text style={styles.rowTime}>{formatTime(entry.timestamp)}</Text>
              <View style={[styles.dot, { backgroundColor: STATE_COLOR[entry.state] }]} />
              <Text style={styles.rowState}>{entry.state}</Text>
            </View>
          ))}
        </View>
      )}

      <Text style={styles.sectionTitle}>Последний пейлоад MetricKit</Text>
      {!summary ? (
        <Text style={styles.empty}>
          Ещё не приходил. iOS отдаёт агрегат раз в сутки; чтобы не ждать, запусти сборку из
          Xcode и дёрни Debug → Simulate MetricKit Payloads.
        </Text>
      ) : (
        <View style={styles.card}>
          {Object.entries(summary).map(([key, value]) => (
            <View key={key} style={styles.row}>
              <Text style={styles.metricKey}>{key}</Text>
              <Text style={styles.metricValue} numberOfLines={2}>
                {String(value)}
              </Text>
            </View>
          ))}
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: Colors.background },
  content: { padding: Spacing.md, gap: Spacing.md },
  warning: {
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.md,
    padding: Spacing.md,
    borderLeftWidth: 3,
    borderLeftColor: Colors.warning,
  },
  warningText: { ...Typography.caption, color: Colors.textSecondary },
  hero: {
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.lg,
    padding: Spacing.lg,
    alignItems: 'center',
    borderWidth: 2,
  },
  heroLabel: { ...Typography.caption, color: Colors.textMuted },
  heroState: { ...Typography.h1, marginVertical: Spacing.xs },
  heroHint: { ...Typography.caption, color: Colors.textSecondary, textAlign: 'center' },
  sectionTitle: { ...Typography.h3, color: Colors.text, marginTop: Spacing.sm },
  empty: { ...Typography.caption, color: Colors.textMuted },
  card: {
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.md,
    paddingHorizontal: Spacing.md,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
    paddingVertical: Spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: Colors.divider,
  },
  rowTime: { ...Typography.caption, color: Colors.textMuted, width: 70 },
  dot: { width: 8, height: 8, borderRadius: 4 },
  rowState: { ...Typography.body, color: Colors.text },
  metricKey: { ...Typography.caption, color: Colors.textSecondary, flex: 1 },
  metricValue: { ...Typography.caption, color: Colors.text, flex: 1, textAlign: 'right' },
});

// В релизной сборке экран подменяется заглушкой: см. components/DevOnly.
export default withDevOnly(ThermalScreen);
