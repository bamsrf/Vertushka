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
  const username = data?.username as string | undefined;
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
  if ((type === 'gift_booked' || type === 'gift_confirmed') && entityId) {
    return `/gift/${entityId}`;
  }
  if (
    (type === 'wishlist_in_stock' ||
      type === 'wishlist_in_stock_alt' ||
      type === 'wishlist_price_drop') &&
    recordId
  ) {
    return `/record/${recordId}`;
  }
  if (type === 'new_follower' && username) return `/user/${username}`;
  if (recordId) return `/record/${recordId}`;
  if (username) return `/user/${username}`;
  return '/notifications';
}
