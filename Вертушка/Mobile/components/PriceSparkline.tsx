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

// Минимум точек для графика. Две точки формально линия, но при нормализации
// они обязаны лечь в противоположные углы — картинка одна и та же при любом
// движении цены. Пять — паритет с MIN_BASELINE_POINTS режима «дешевле обычного».
export const MIN_POINTS = 5;

// Шкала не должна схлопываться под разброс данных: иначе движение на 2%
// рисуется как отвесный обрыв, и график врёт о масштабе. Ниже этой доли от
// цены окно растягиваем вокруг середины.
const MIN_SPAN_RATIO = 0.1;

interface PriceSparklineProps {
  points: PriceHistoryPoint[];
  historicalLow: number | null;
  width?: number;
  height?: number;
  /**
   * 'bare' — без карточной подложки и собственной шапки. Сворачиваемый блок в
   * радаре рисует заголовок с дельтой сам, и вторая строка «Динамика цены ·
   * сейчас X» под ней повторяла бы те же числа слабее.
   */
  variant?: 'card' | 'bare';
}

const formatRub = (v: number): string => `${Math.round(v).toLocaleString('ru-RU')} ₽`;

const MONTHS = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];
const dm = (iso: string): string => {
  const d = new Date(`${iso}T00:00:00Z`);
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`;
};

// Сколько известных замеров показываем вместо графика.
const RETRO_LIMIT = 4;

export function PriceSparkline({
  points,
  historicalLow,
  width = 300,
  height = 64,
  variant = 'card',
}: PriceSparklineProps) {
  const bare = variant === 'bare';
  const priced = points.filter(
    (p): p is PriceHistoryPoint & { min_price_rub: number } => p.min_price_rub != null,
  );

  // Мало точек — отдаём цифры текстом. Рисовать линию по двум замерам значит
  // показывать драму там, где цена шевельнулась на процент.
  if (priced.length < MIN_POINTS) {
    const latest = priced.length ? priced[priced.length - 1].min_price_rub : null;
    if (latest == null && historicalLow == null) return null;
    // Ретроспектива вместо «минимума». По одной-двум точкам минимум — не
    // минимум, а единственное известное значение: на Arctic Monkeys это дало
    // «минимум за 3 мес — 4 490 ₽» у пластинки, которая месяцами стоила 3 990.
    // Замеры показываем как есть, с датами — за них мы ручаемся.
    const known = [...priced].reverse().slice(0, RETRO_LIMIT);
    return (
      <View style={bare ? styles.bareContainer : styles.container}>
        {bare ? null : (
          <View style={styles.header}>
            <Text style={styles.title}>Динамика цены</Text>
            <Text style={styles.lowValue}>
              {latest != null ? `сейчас ${formatRub(latest)}` : ''}
            </Text>
          </View>
        )}
        <Text style={styles.tooFew}>
          {known.length
            ? 'Точек для графика мало. Что известно о цене:'
            : 'Цена ещё ни разу не менялась — истории пока нет'}
        </Text>
        {known.map((p) => (
          <View key={p.date} style={styles.retroRow}>
            <Text style={styles.retroDate}>{dm(p.date)}</Text>
            <Text style={styles.retroPrice}>{formatRub(p.min_price_rub)}</Text>
          </View>
        ))}
      </View>
    );
  }

  const values = priced.map((p) => p.min_price_rub);
  const minV = Math.min(...values);
  const maxV = Math.max(...values);

  // Раньше span = maxV − minV, то есть шкала подгонялась ровно под разброс, и
  // любое движение занимало всю высоту: +100 ₽ на пятитысячной пластинке
  // выглядели как обвал. Держим окно не уже MIN_SPAN_RATIO от цены и центрируем
  // данные внутри — тогда 2% и рисуются как 2%.
  const mid = (maxV + minV) / 2;
  const span = Math.max(maxV - minV, mid * MIN_SPAN_RATIO, 1);
  const floorV = mid - span / 2;

  const padX = 4;
  const padY = 8;
  const innerW = width - padX * 2;
  const innerH = height - padY * 2;

  const yOf = (v: number) => padY + (1 - (v - floorV) / span) * innerH;

  const coords = priced.map((p, i) => ({
    x: padX + (i / (priced.length - 1)) * innerW,
    y: yOf(p.min_price_rub),
    v: p.min_price_rub,
  }));

  const polyPoints = coords.map((c) => `${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(' ');
  const last = coords[coords.length - 1];
  // Пунктир дна теперь считается по общей шкале. Раньше формула (minV−minV)/span
  // давала тождественный ноль, и линия всегда лежала на нижней кромке, куда
  // упиралась и самая нижняя точка.
  const lowY = yOf(minV);

  const first = values[0];
  const current = values[values.length - 1];
  const trendDown = current < first;

  return (
    <View style={bare ? styles.bareContainer : styles.container}>
      {bare ? null : (
        <View style={styles.header}>
          <Text style={styles.title}>Динамика цены</Text>
          <Text style={styles.lowValue}>
            сейчас {formatRub(current)}
            {historicalLow != null ? ` · мин. ${formatRub(historicalLow)}` : ''}
          </Text>
        </View>
      )}
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
  // Подложку и отступы в bare-режиме задаёт родитель — иначе в шторке радара
  // карточка вкладывалась в карточку и график съезжал внутрь двойной рамки.
  bareContainer: {},
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
  retroRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingTop: 6,
  },
  retroDate: {
    ...Typography.caption,
    color: Colors.textSecondary,
  },
  retroPrice: {
    ...Typography.caption,
    color: Colors.text,
    fontWeight: '600',
    fontVariant: ['tabular-nums'],
  },
  tooFew: {
    ...Typography.caption,
    color: Colors.textMuted,
  },
});

export default PriceSparkline;
