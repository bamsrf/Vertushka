/**
 * PriceSparkline — компактный график динамики минимальной цены пластинки.
 *
 * Источник — GET /records/{id}/price-history (дневной минимум in_stock).
 * Точки редкие (только дни со сменой цены) → соединяем прямыми, клиент
 * визуально интерполирует. Показываем историческую нижнюю цену как якорь.
 */
import { View, Text, StyleSheet } from 'react-native';
import Svg, { Polyline, Circle, Line } from 'react-native-svg';
import { Colors, Typography, Spacing, BorderRadius } from '../constants/theme';
import { PriceHistoryPoint } from '../lib/types';

interface PriceSparklineProps {
  points: PriceHistoryPoint[];
  historicalLow: number | null;
  width?: number;
  height?: number;
}

const formatRub = (v: number): string => `${Math.round(v).toLocaleString('ru-RU')} ₽`;

export function PriceSparkline({
  points,
  historicalLow,
  width = 300,
  height = 64,
}: PriceSparklineProps) {
  const priced = points.filter(
    (p): p is PriceHistoryPoint & { min_price_rub: number } => p.min_price_rub != null,
  );

  // Нужно ≥2 точки, иначе линию не построить — показываем только цифру.
  if (priced.length < 2) {
    if (historicalLow == null) return null;
    return (
      <View style={styles.container}>
        <View style={styles.header}>
          <Text style={styles.title}>Динамика цены</Text>
          <Text style={styles.lowValue}>мин. {formatRub(historicalLow)}</Text>
        </View>
        <Text style={styles.tooFew}>Пока мало данных для графика</Text>
      </View>
    );
  }

  const values = priced.map((p) => p.min_price_rub);
  const minV = Math.min(...values);
  const maxV = Math.max(...values);
  const span = maxV - minV || 1;

  const padX = 4;
  const padY = 8;
  const innerW = width - padX * 2;
  const innerH = height - padY * 2;

  const coords = priced.map((p, i) => {
    const x = padX + (priced.length === 1 ? 0 : (i / (priced.length - 1)) * innerW);
    const y = padY + (1 - (p.min_price_rub - minV) / span) * innerH;
    return { x, y, v: p.min_price_rub };
  });

  const polyPoints = coords.map((c) => `${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(' ');
  const last = coords[coords.length - 1];
  const lowY = padY + (1 - (minV - minV) / span) * innerH; // = линия минимума

  const first = values[0];
  const current = values[values.length - 1];
  const trendDown = current < first;

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>Динамика цены</Text>
        <Text style={styles.lowValue}>
          сейчас {formatRub(current)}
          {historicalLow != null ? ` · мин. ${formatRub(historicalLow)}` : ''}
        </Text>
      </View>
      <Svg width={width} height={height}>
        {/* Пунктир минимума-в-окне как ориентир «дна». */}
        <Line
          x1={padX}
          y1={lowY}
          x2={width - padX}
          y2={lowY}
          stroke={Colors.border}
          strokeWidth={1}
          strokeDasharray="3 4"
        />
        <Polyline
          points={polyPoints}
          fill="none"
          stroke={trendDown ? Colors.success : Colors.royalBlue}
          strokeWidth={2}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        <Circle cx={last.x} cy={last.y} r={3.5} fill={trendDown ? Colors.success : Colors.royalBlue} />
      </Svg>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    marginHorizontal: Spacing.md,
    marginBottom: Spacing.md,
    padding: Spacing.md,
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.md,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: Spacing.sm,
  },
  title: {
    ...Typography.caption,
    color: Colors.textSecondary,
  },
  lowValue: {
    ...Typography.caption,
    color: Colors.text,
    fontWeight: '600',
  },
  tooFew: {
    ...Typography.caption,
    color: Colors.textMuted,
  },
});

export default PriceSparkline;
