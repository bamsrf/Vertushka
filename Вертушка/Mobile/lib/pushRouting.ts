/**
 * Единая маршрутизация тапа по уведомлению → целевой путь.
 *
 * Общая для трёх точек, чтобы тап всегда доводил до одного раздела:
 *  - OS-пуш warm-tap (_layout responseListener);
 *  - cold-start запускающий пуш (_layout getLastNotificationResponseAsync);
 *  - foreground in-app toast (InAppNotificationToast).
 *
 * Неизвестный тип → лента «Ты» (/notifications), а не «полпути».
 */
export function routeForPush(data: Record<string, unknown> | undefined): string {
  const type = data?.type as string | undefined;
  const recordId = (data?.record_id || data?.recordId) as string | undefined;
  // Бэкенд кладёт имя автора события в actor_username (соцсобытия) и
  // sender_username (чат). Ключа `username` в payload'ах нет ни у одного типа —
  // читать только его значило уводить new_follower в ленту вместо профиля.
  const username = (data?.username ||
    data?.actor_username ||
    data?.sender_username) as string | undefined;
  const entityId = data?.entity_id as string | undefined;
  const code = data?.code as string | undefined;

  if (type === 'follow_request') return '/social/follow-requests';
  if (type === 'message' || type === 'message_request') {
    const convId = (data?.conversation_id as string | undefined) || entityId;
    return convId ? `/messages/${convId}` : '/messages';
  }
  if (type === 'digest_wishlist_in_stock') return '/notifications';
  if (type === 'achievement_unlocked' || type === 'milestone_unlocked') {
    return code ? `/achievements?code=${code}` : '/achievements';
  }
  // Уровень: ведём в hero-блок ачивок, где отыграется анимация повышения.
  if (type === 'level_up') return '/achievements?levelup=1';
  if ((type === 'gift_booked' || type === 'gift_confirmed') && entityId) {
    return `/gift/${entityId}`;
  }
  if (type === 'wishlist_in_stock_alt') {
    // Push сообщает, что в продаже ДРУГОЕ издание. Ведём на него, а не на
    // желаемую пластинку: у той листингов нет, и юзер упирается в тупик.
    const altId = (data?.alt_record_id as string | undefined) || recordId;
    if (altId) return `/record/${altId}`;
  }
  if (
    (type === 'wishlist_in_stock' || type === 'wishlist_price_drop') &&
    recordId
  ) {
    return `/record/${recordId}`;
  }
  if (type === 'new_follower' && username) return `/user/${username}`;
  if (recordId) return `/record/${recordId}`;
  if (username) return `/user/${username}`;
  return '/notifications';
}
