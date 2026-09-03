/**
 * PriceHistoryCollapsible — сворачиваемая динамика цены в шторке радара.
 *
 * Шторка и без графика плотная: обложка, цена, порог, статус, карточка аналога,
 * хронология радара, две кнопки. График сидел посередине развёрнутым всегда и
 * на плоских данных занимал 100pt ради двух чисел.
 *
 * Поэтому шапка несёт ответ («−18,6% за 3 мес»), а сам график — по тапу. Открыт
 * по умолчанию только когда движение заметное: развёрнутая ломаная на разбросе
 * в процент ничего не добавляет к цифре, которая уже в шапке.
 */
import React, { useCallback, useState } from 'react';
import { LayoutChangeEvent, Pressable, StyleSheet, Text, View } from 'react-native';
import * as Haptics from 'expo-haptics';
import { Icon } from '@/components/ui';
import { Colors, Typography, Spacing, BorderRadius } from '../../constants/theme';
import { PriceSparkline, MIN_POINTS } from '../PriceSparkline';
import { summarizePriceHistory } from '../../lib/priceHistory';
import { PriceHistoryPoint } from '../../lib/types';

const MONTHS = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];

const fmt = (n: number) => Math.round(n).toLocaleString('ru-RU');

const dm = (iso: string) => {
  const d = new Date(`${iso}T00:00:00Z`);
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`;
};

interface Props {
  points: PriceHistoryPoint[];
  historicalLow: number | null;
  /** Окно истории в днях — ровно то, что просили у /price-history. */
  days?: number;
}

export function PriceHistoryCollapsible({ points, historicalLow, days = 90 }: Props) {
  const summary = summarizePriceHistory(points);
  const [expanded, setExpanded] = useState(() => summary?.isSignificant ?? false);
  // Ширина под график: раньше сюда прилетала константа 300, и на широких
  // экранах ломаная не дотягивалась до правого края карточки.
  const [chartWidth, setChartWidth] = useState(0);

  const onLayout = useCallback((e: LayoutChangeEvent) => {
    setChartWidth(Math.round(e.nativeEvent.layout.width));
  }, []);

  const toggle = useCallback(() => {
    Haptics.selectionAsync();
    setExpanded((v) => !v);
  }, []);

  if (!summary) return null;

  // Хватает ли ряда, чтобы вообще что-то утверждать. Порог общий с графиком:
  // если точек мало для линии, их мало и для слов «минимум» и «почти не
  // менялась» — по одному замеру мы не знаем ни того, ни другого.
  const enough = points.filter((p) => p.min_price_rub != null).length >= MIN_POINTS;

  const dropped = summary.deltaRub < 0;
  const flat = Math.round(summary.deltaPct) === 0;
  const deltaColor = flat ? Colors.textSecondary : dropped ? Colors.success : Colors.warning;
  const deltaBg = flat ? Colors.surfaceHover : dropped ? 'rgba(48,164,108,.14)' : 'rgba(245,166,35,.16)';
  const sign = summary.deltaRub > 0 ? '+' : summary.deltaRub < 0 ? '−' : '';
  const monthsLabel = days >= 60 ? `за ${Math.round(days / 30)} мес` : `за ${days} дн`;

  return (
    <View style={styles.card}>
      <Pressable
        style={styles.header}
        onPress={toggle}
        accessibilityRole="button"
        accessibilityLabel={expanded ? 'Свернуть динамику цены' : 'Развернуть динамику цены'}
      >
        <Text style={styles.title} numberOfLines={1}>Динамика цены</Text>
        {!enough ? (
          // «Почти не менялась» на одной точке — утверждение о движении, которого
          // мы не наблюдали: цена могла меняться до того, как мы начали писать.
          <Text style={styles.flatTxt} numberOfLines={1}>мало данных</Text>
        ) : flat ? (
          <Text style={styles.flatTxt} numberOfLines={1}>почти не менялась</Text>
        ) : (
          <View style={[styles.deltaChip, { backgroundColor: deltaBg, marginLeft: 'auto' }]}>
            {/* «+48,9%» без базы прочитать нельзя: считается оно от ПЕРВОЙ
                точки окна, а не от «цены раньше вообще». Подписываем дату,
                чтобы утверждение стало проверяемым и в свёрнутом виде. */}
            <Text style={[styles.deltaTxt, { color: deltaColor }]}>
              {sign}
              {Math.abs(summary.deltaPct).toFixed(1).replace('.', ',')}% с {dm(summary.firstDate)}
            </Text>
          </View>
        )}
        <Icon name={expanded ? 'chevron-up' : 'chevron-down'} size={16} color="secondary" />
      </Pressable>

      {expanded ? (
        <View style={styles.body} onLayout={onLayout}>
          {chartWidth > 0 ? (
            <PriceSparkline
              points={points}
              historicalLow={historicalLow}
              width={chartWidth}
              variant="bare"
            />
          ) : null}
          <View style={styles.footer}>
            <Text style={styles.footerTxt}>
              {enough && historicalLow != null
                ? `Минимум ${monthsLabel} — ${fmt(historicalLow)} ₽`
                : ''}
            </Text>
            {/* «Сейчас» на протухших точках — это то самое враньё, из-за
                которого график и не читался: последняя цена может быть
                месячной давности, а пресса в наличии уже нет. */}
            <Text style={styles.footerTxt}>
              {summary.isStale
                ? `Последнее изменение ${dm(summary.lastDate)}`
                : `Обновлено ${dm(summary.lastDate)}`}
            </Text>
          </View>
        </View>
      ) : null}
    </View>
  );
}

export default PriceHistoryCollapsible;

const styles = StyleSheet.create({
  card: {
    marginTop: 18,
    backgroundColor: '#fff',
    borderRadius: 14,
    paddingHorizontal: 14,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingVertical: 14,
  },
  // Заголовок не жмём и не переносим: на 390pt «Динамика цены» с flex:1
  // ломалось на две строки, а справа оставалась дырка. Тянется правая часть.
  title: { ...Typography.bodyBold, color: Colors.text, flexShrink: 0 },
  flatTxt: { fontSize: 13, color: Colors.textMuted, flex: 1, textAlign: 'right' },
  deltaChip: { paddingVertical: 5, paddingHorizontal: 10, borderRadius: 9999 },
  deltaTxt: { fontSize: 13, fontFamily: 'Inter_700Bold', fontVariant: ['tabular-nums'] },
  body: { paddingBottom: 14 },
  footer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: Spacing.sm,
    marginTop: 10,
  },
  footerTxt: { fontSize: 12, color: Colors.textMuted },
});
