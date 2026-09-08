/**
 * +native-intent — фильтр входящих URL для expo-router (B7 в ANDROID_PORT_PLAN).
 *
 * Discogs OAuth заканчивается редиректом `vertushka://discogs-callback?...`.
 * На iOS его целиком забирает ASWebAuthenticationSession, и роутер ничего не
 * видит. На Android Chrome Custom Tab отдаёт URL интентом в `MainActivity`:
 * `Linking` рассылает событие всем подписчикам — `WebBrowser.openAuthSessionAsync`
 * резолвит свой промис (что нам и нужно), а expo-router пытается открыть
 * маршрут `/discogs-callback`, которого нет, и уводит в `+not-found`.
 *
 * `redirectSystemPath` вызывается до навигации: для `discogs-callback`
 * возвращаем `null` — по контракту expo-router (`types.d.ts`, `NativeIntent`)
 * falsy-результат означает «редиректа нет, остаёмся на текущем пути».
 * Обработка результата остаётся в `app/settings/discogs.tsx` и
 * `components/SocialAuthButtons.tsx`.
 *
 * Исключения тут роняют приложение (предупреждение из типов expo-router),
 * поэтому всё обёрнуто в try/catch, а на любой сбой отдаём путь как есть.
 */
const DISCOGS_CALLBACK = 'discogs-callback';

export function redirectSystemPath({ path }: { path: string; initial: boolean }): string | null {
  try {
    if (path.includes(DISCOGS_CALLBACK)) return null;
  } catch {
    // не наш случай — пропускаем как есть
  }
  return path;
}
