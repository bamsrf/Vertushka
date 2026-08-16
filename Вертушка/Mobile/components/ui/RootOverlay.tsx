/**
 * RootOverlay — портал «поверх всего», включая нативные модалки.
 *
 * Зачем: экраны с `presentation: 'modal'` (profile, notifications, messages/new,
 * legal/*) на iOS живут в отдельном UIViewController, презентованном НАД
 * RN-root. Всё, что смонтировано соседом `<Stack>` в `_layout.tsx` (тосты,
 * анимация ачивки), оказывается ПОЗАДИ такой модалки: тост не видно, а
 * RN `<Modal>` вообще не открывается — iOS не даёт презентовать модалку из
 * контроллера, который уже что-то презентует.
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
import { Platform, StyleSheet, View, useWindowDimensions } from 'react-native';
import { FullWindowOverlay } from 'react-native-screens';

interface Props {
  children: React.ReactNode;
}

export function RootOverlay({ children }: Props) {
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
    <FullWindowOverlay>
      <View pointerEvents="box-none" style={{ width, height }}>
        {children}
      </View>
    </FullWindowOverlay>
  );
}

export default RootOverlay;
