/**
 * ToastHost — единственная точка монтирования react-native-toast-message.
 *
 * Тост рисуется через RootOverlay (на iOS — FullWindowOverlay в собственном
 * UIWindow), потому что половина приложения открывается как нативная модалка:
 * profile, notifications, messages/new, legal/* — и всё, что пушится поверх них
 * (settings/*, social/*, collection/value, gift/[id], achievements, records/mine).
 * Такой экран — отдельный UIViewController НАД RN-root, а `<Toast>`,
 * смонтированный соседом `<Stack>`, оставался под ним: действие проходило,
 * плашка «сохранено / не удалось» показывалась и уезжала, но её никто не видел.
 *
 * ВАЖНО: инстанс должен быть ровно ОДИН на всё приложение. `Toast.show()`
 * стреляет в ПОСЛЕДНИЙ смонтированный `<Toast>` из внутреннего реестра
 * ref'ов библиотеки — не в тот, что сейчас на экране. Раньше свои копии
 * держали profile.tsx и четыре пикера (AddRecords/AddWishlistItems/
 * FolderPicker/WishlistFolderPicker) — обход той же проблемы с модалками.
 * Из-за этого тост, вызванный с экрана, запушенного ПОВЕРХ профиля
 * (settings/wishlists и вся ветка настроек), уезжал в профильный инстанс и
 * рисовался на экране, который в этот момент закрыт. Плашки не было видно
 * вообще нигде. Не добавляй сюда локальные `<Toast>`.
 *
 * Оверлей висит в дереве постоянно (по той же причине — реестр ref'ов),
 * поэтому accessibilityIsModal выключен: иначе VoiceOver навсегда потерял бы
 * весь экран под оверлеем. Сквозные тапы не страдают — контейнер
 * FullWindowOverlay отдаёт хит-тест только реальным сабвью.
 *
 * topOffset считается от safe-area, а не константой 56: на устройствах с
 * Dynamic Island карточка заезжала под часы.
 */
import Toast from 'react-native-toast-message';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { RootOverlay } from './ui/RootOverlay';
import { toastConfig } from './CustomToast';

// Отступ снизу для position:'bottom' — над таб-баром.
const BOTTOM_OFFSET = 100;

export function ToastHost() {
  const insets = useSafeAreaInsets();

  return (
    <RootOverlay accessibilityIsModal={false}>
      <Toast config={toastConfig} topOffset={insets.top + 8} bottomOffset={BOTTOM_OFFSET} />
    </RootOverlay>
  );
}

export default ToastHost;
