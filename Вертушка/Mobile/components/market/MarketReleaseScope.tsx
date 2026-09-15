/**
 * Витрина Маркета, суженная до одного релиза, — и объяснение, когда сужать
 * оказалось не до чего.
 *
 * Зачем: кнопка «В Маркет» на карточке релиза читается как обещание («раз
 * ведут в Маркет — значит, пластинка там есть»). До этой фичи она открывала
 * общую витрину, где про эту пластинку не было ни слова: кто не долистывал до
 * блока офферов, уходил с ощущением, что приложение соврало. Здесь два ответа
 * на «а где она?»:
 *
 *   • ScopeBar — плашка «показываем только это» с крестиком. Стоит над сеткой,
 *     потому что объяснять выдачу надо до того, как в неё начали смотреть.
 *   • MissModal — когда в наличии нет ничего. Сказать это словами дешевле, чем
 *     дать человеку самому догадаться по пустому экрану; после «Понятно»
 *     сужение снимается, и под модалкой остаётся обычный Маркет.
 */
import React from 'react';
import { Modal, Pressable, StyleSheet, Text, View } from 'react-native';

import { Icon } from '../ui/Icon';
import { MarketPalette } from '../../constants/theme';
import { ms } from '../../lib/responsive';
import type { MarketReleaseScope } from '../../lib/types';

// ─── Плашка над сеткой ──────────────────────────────────────────────────

interface ScopeBarProps {
  scope: MarketReleaseScope;
  /**
   * Нашлись офферы именно этого прессинга. false означает, что в выдаче стоят
   * только другие издания альбома — и это обязательно сказать: молча показать
   * не ту версию хуже, чем показать пустоту.
   */
  exactInStock: boolean;
  onReset: () => void;
}

export function MarketReleaseScopeBar({ scope, exactInStock, onReset }: ScopeBarProps) {
  return (
    <View style={styles.bar}>
      <View style={styles.barText}>
        <Text style={styles.barLabel} numberOfLines={1}>
          {scope.artist.toUpperCase()} — {scope.title}
        </Text>
        <Text style={styles.barNote} numberOfLines={2}>
          {exactInStock
            ? 'Эта пластинка и другие её издания'
            : 'Именно этой версии сейчас нет — вот другие издания альбома'}
        </Text>
      </View>
      <Pressable
        onPress={onReset}
        hitSlop={10}
        accessibilityRole="button"
        accessibilityLabel="Показать весь Маркет"
        style={styles.barReset}
      >
        <Text style={styles.barResetText}>Сбросить</Text>
        <Icon name="close" size={14} color="rgba(255,255,255,0.75)" />
      </Pressable>
    </View>
  );
}

// ─── «Этой пластинки нет» ───────────────────────────────────────────────

interface MissModalProps {
  visible: boolean;
  scope: MarketReleaseScope | null;
  onDismiss: () => void;
}

export function MarketReleaseMissModal({ visible, scope, onDismiss }: MissModalProps) {
  if (!scope) return null;

  return (
    <Modal
      visible={visible}
      transparent
      animationType="fade"
      // Аппаратная «назад» на Android обязана закрывать так же, как кнопка, —
      // иначе Маркет останется под модалкой суженным до пустоты.
      onRequestClose={onDismiss}
      statusBarTranslucent
    >
      <View style={styles.backdrop}>
        <View style={styles.card}>
          <View style={styles.cardIcon}>
            <Icon name="disc-outline" size={22} color={MarketPalette.chrome.textPrimary} />
          </View>
          <Text style={styles.cardTitle}>Этой пластинки пока нет</Text>
          <Text style={styles.cardRelease} numberOfLines={2}>
            {scope.artist} — {scope.title}
          </Text>
          <Text style={styles.cardBody}>
            Ни в одном подключённом магазине её сейчас не продают. Посмотрите,
            что есть в Маркете.
          </Text>
          <Pressable
            onPress={onDismiss}
            accessibilityRole="button"
            style={({ pressed }) => [styles.cardButton, pressed && styles.cardButtonPressed]}
          >
            <Text style={styles.cardButtonText}>Смотреть Маркет</Text>
          </Pressable>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  bar: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    marginHorizontal: 16,
    marginBottom: 14,
    paddingVertical: 10,
    paddingHorizontal: 14,
    borderRadius: 14,
    backgroundColor: MarketPalette.chrome.fillStrong,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: MarketPalette.chrome.border,
  },
  barText: {
    flex: 1,
    gap: 2,
  },
  barLabel: {
    fontFamily: 'Inter_700Bold',
    fontSize: ms(13),
    letterSpacing: 0.2,
    color: MarketPalette.chrome.textPrimary,
  },
  barNote: {
    fontFamily: 'Inter_400Regular',
    fontSize: ms(11),
    lineHeight: ms(15),
    color: MarketPalette.chrome.textMuted,
  },
  barReset: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingVertical: 6,
    paddingHorizontal: 10,
    borderRadius: 999,
    backgroundColor: 'rgba(255,255,255,0.10)',
  },
  barResetText: {
    fontFamily: 'Inter_500Medium',
    fontSize: ms(11),
    color: 'rgba(255,255,255,0.75)',
  },

  backdrop: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 28,
    backgroundColor: 'rgba(8, 3, 20, 0.72)',
  },
  card: {
    width: '100%',
    alignItems: 'center',
    paddingVertical: 26,
    paddingHorizontal: 22,
    borderRadius: 22,
    backgroundColor: MarketPalette.indigo,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: MarketPalette.chrome.border,
  },
  cardIcon: {
    width: 44,
    height: 44,
    borderRadius: 22,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 14,
    backgroundColor: MarketPalette.chrome.fillStrong,
  },
  cardTitle: {
    fontFamily: 'Inter_700Bold',
    fontSize: ms(17),
    textAlign: 'center',
    color: MarketPalette.chrome.textPrimary,
  },
  cardRelease: {
    marginTop: 6,
    fontFamily: 'Inter_500Medium',
    fontSize: ms(13),
    textAlign: 'center',
    color: MarketPalette.chrome.textSecondary,
  },
  cardBody: {
    marginTop: 12,
    fontFamily: 'Inter_400Regular',
    fontSize: ms(13),
    lineHeight: ms(19),
    textAlign: 'center',
    color: MarketPalette.chrome.textMuted,
  },
  cardButton: {
    marginTop: 20,
    alignSelf: 'stretch',
    paddingVertical: 13,
    borderRadius: 999,
    alignItems: 'center',
    backgroundColor: MarketPalette.cobalt,
  },
  cardButtonPressed: {
    opacity: 0.85,
  },
  cardButtonText: {
    fontFamily: 'Inter_700Bold',
    fontSize: ms(14),
    color: '#FFFFFF',
  },
});
