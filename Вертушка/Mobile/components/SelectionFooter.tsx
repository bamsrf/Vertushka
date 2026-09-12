/**
 * Панель массовых действий в режиме выбора (коллекция, вишлист, папки).
 *
 * Почему колонкой, а не строкой. Раньше кнопка была `flexDirection: 'row'`:
 * иконка 24pt, отступ, подпись «В коллекцию (1)». На iPhone SE/Mini (320–375pt)
 * трём таким кнопкам достаётся по ~90pt при нужных ~140pt — подпись
 * переносилась на две строки, кнопка распухала, а иконка выезжала за край
 * панели. Тот же слом наступал на любом экране при крупном системном
 * «Размере текста».
 *
 * Теперь иконка над подписью (паттерн нижних панелей iOS): по горизонтали
 * кнопке нужна только ширина слова, а рост шрифта уходит в высоту панели,
 * которая ничем не зажата. Счётчик выбранного вынесен из подписей в отдельную
 * строку сверху — он был в каждой кнопке и съедал те самые ~30pt.
 *
 * Панель абсолютная; `bottom` задаёт экран (над плавающим таб-баром — 96,
 * на экранах папок без таб-бара — 40).
 */
import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { Icon } from './ui/Icon';
import { Colors, Typography, Spacing, BorderRadius } from '../constants/theme';
import { ms } from '../lib/responsive';

export interface SelectionAction {
  /** Стабильный ключ для списка. */
  key: string;
  /** Имя иконки для `<Icon>`. */
  icon: string;
  /** Подпись под иконкой — одно-два слова, без счётчика. */
  label: string;
  onPress: () => void;
  /** Красит иконку и подпись в error-цвет (удаление, изъятие из папки). */
  destructive?: boolean;
}

interface SelectionFooterProps {
  actions: SelectionAction[];
  /** Сколько элементов отмечено. При 0 кнопки выключены. */
  selectedCount: number;
  /** Отступ от низа экрана: 96 над плавающим таб-баром, 40 без него. */
  bottom: number;
}

const ICON_SIZE = 22;

export function SelectionFooter({ actions, selectedCount, bottom }: SelectionFooterProps) {
  const isEmpty = selectedCount === 0;

  return (
    <View style={[styles.footer, { bottom }]}>
      <Text style={styles.counter} numberOfLines={1}>
        {isEmpty ? 'Выберите пластинки' : `Выбрано: ${selectedCount}`}
      </Text>

      <View style={styles.row}>
        {actions.map((action) => {
          const tint = isEmpty
            ? Colors.textMuted
            : action.destructive
              ? Colors.error
              : Colors.royalBlue;

          return (
            <TouchableOpacity
              key={action.key}
              style={styles.button}
              onPress={action.onPress}
              disabled={isEmpty}
              accessibilityRole="button"
              accessibilityState={{ disabled: isEmpty }}
              accessibilityLabel={
                isEmpty ? action.label : `${action.label}, выбрано ${selectedCount}`
              }
            >
              <Icon name={action.icon} size={ICON_SIZE} color={tint} />
              <Text style={[styles.label, { color: tint }]} numberOfLines={2}>
                {action.label}
              </Text>
            </TouchableOpacity>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  footer: {
    position: 'absolute',
    left: Spacing.lg,
    right: Spacing.lg,
    backgroundColor: Colors.glassBg,
    paddingTop: Spacing.sm,
    paddingBottom: Spacing.sm,
    paddingHorizontal: Spacing.sm,
    borderRadius: BorderRadius.lg,
  },
  counter: {
    ...Typography.caption,
    color: Colors.textMuted,
    textAlign: 'center',
    marginBottom: Spacing.xs,
  },
  row: {
    flexDirection: 'row',
    gap: Spacing.xs,
  },
  // `flex: 1` + `minWidth: 0` — иначе длинная подпись распирает колонку и
  // ломает равные доли на узком экране.
  button: {
    flex: 1,
    minWidth: 0,
    alignItems: 'center',
    justifyContent: 'center',
    gap: Spacing.xs,
    paddingVertical: Spacing.sm,
    paddingHorizontal: Spacing.xs,
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.md,
  },
  // lineHeight плотнее дефолтного: на 320pt «В коллекцию» переносится в две
  // строки, и с воздушным интерлиньяжем кнопка выглядела бы вдвое выше соседних.
  label: {
    ...Typography.caption,
    fontSize: ms(12),
    lineHeight: ms(14),
    fontWeight: '600',
    textAlign: 'center',
  },
});

export default SelectionFooter;
