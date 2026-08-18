/**
 * RootOverlay — портал «поверх всего», включая нативные модалки.
 *
 * Зачем: экраны с `presentation: 'modal'` (profile, notifications, messages/new,
 * legal/*) на iOS живут в отдельном UIViewController, презентованном НАД
 * RN-root. Всё, что смонтировано соседом `<Stack>` в `_layout.tsx` (тосты,
 * анимация ачивки), оказывается ПОЗАДИ такой модалки: тост не видно, а
 * RN `<Modal>` вообще не открывается — iOS не даёт презентовать модалку из
 * контроллера, который уже что-то презентует. То же самое касается всего, что
 * запушено ПОВЕРХ модалки (settings/*, social/*, gift/[id], achievements):
 * эти экраны едут в стеке презентованного контроллера, а не RN-root.
 *
 * `FullWindowOverlay` из react-native-screens рисует детей в отдельном
 * UIWindow поверх всей иерархии, поэтому проблема снимается на корню.
 * На Android и вебе такого класса нет — там обычный absolute-fill: экраны
 * модалок лежат в том же окне, и сосед с elevation рисуется сверху.
 *
 * React-контекст (роутер, safe-area, темы) сквозь оверлей проходит: другой
 * тут только нативный view-hierarchy, дерево React — то же самое.
 */
import React from 'react';
import { Modal, Platform, StyleSheet, View, useWindowDimensions } from 'react-native';
import { FullWindowOverlay } from 'react-native-screens';

interface Props {
  children: React.ReactNode;
  /**
   * Прячет от VoiceOver всё, что лежит под оверлеем. Верно для модальных слоёв
   * (ачивка), которые монтируются только на время показа.
   *
   * Хосты, которые висят в дереве постоянно (тосты), обязаны выставлять
   * `false`: иначе экран под ними навсегда исчезает из accessibility-дерева и
   * VoiceOver перестаёт видеть приложение целиком.
   */
  accessibilityIsModal?: boolean;
}

export function RootOverlay({ children, accessibilityIsModal = true }: Props) {
  const { width, height } = useWindowDimensions();

  if (Platform.OS !== 'ios') {
    return (
      <View pointerEvents="box-none" style={StyleSheet.absoluteFill}>
        {children}
      </View>
    );
  }

  // FullWindowOverlay не участвует в обычном layout-проходе: детям нужен
  // явный размер, иначе они схлопываются в нулевую высоту.
  return (
    <FullWindowOverlay unstable_accessibilityContainerViewIsModal={accessibilityIsModal}>
      <View pointerEvents="box-none" style={{ width, height }}>
        {children}
      </View>
    </FullWindowOverlay>
  );
}

/**
 * RootModalOverlay — слой для диалога, который должен перебивать нативные
 * модалки экранов: ачивка, «это подарок?».
 *
 * iOS — RootOverlay: RN `<Modal>` тут не работает вовсе, потому что iOS не даёт
 * презентовать модалку из контроллера, который уже что-то презентует (открыт
 * профиль/уведомления — и диалог просто не появляется).
 *
 * Android — обычная RN-модалка: там это Dialog, он и так поверх всего и ловит
 * системную кнопку «назад». `animationType="none"` намеренно: анимацию
 * появления рисует сам диалог, чтобы на обеих платформах она была одинаковой.
 *
 * Монтировать только на время показа — иначе `accessibilityIsModal` навсегда
 * спрячет приложение от VoiceOver.
 */
export function RootModalOverlay({
  children,
  onRequestClose,
}: {
  children: React.ReactNode;
  onRequestClose: () => void;
}) {
  if (Platform.OS === 'ios') {
    return <RootOverlay>{children}</RootOverlay>;
  }

  return (
    <Modal transparent visible animationType="none" onRequestClose={onRequestClose} statusBarTranslucent>
      {children}
    </Modal>
  );
}

export default RootOverlay;
