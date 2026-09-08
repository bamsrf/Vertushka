/**
 * shareCompat — гарантированное завершение системного share-чузера на Android.
 *
 * `expo-sharing.shareAsync` на Android резолвится только из `onActivityResult`
 * чузера. Если юзер закрывает чузер кнопкой «Назад» / свайпом, результат
 * может не долететь, и промис висит вечно — UI остаётся в «Готовим…»
 * (A11 в docs/BUGS.md). Здесь шаринг гонится с возвратом приложения на
 * передний план: чузер — отдельная Activity, на время его показа наш
 * `AppState` уходит из `active`, а возвращается ровно в момент закрытия.
 *
 * iOS: обёртка прозрачна — просто `await share()`, ветка прежняя.
 */
import { AppState, Platform, type AppStateStatus } from 'react-native';

interface ForegroundWaiter {
  promise: Promise<void>;
  cancel: () => void;
}

/** Резолвится, когда приложение ушло с переднего плана и вернулось обратно. */
export function waitForReturnToForeground(): ForegroundWaiter {
  let cancel: () => void = () => {};
  const promise = new Promise<void>((resolve) => {
    let leftForeground = AppState.currentState !== 'active';
    const sub = AppState.addEventListener('change', (next: AppStateStatus) => {
      if (next !== 'active') {
        leftForeground = true;
        return;
      }
      if (!leftForeground) return;
      sub.remove();
      resolve();
    });
    cancel = () => sub.remove();
  });
  return { promise, cancel };
}

/**
 * Запустить шаринг и дождаться либо его завершения, либо возврата приложения
 * на передний план (Android). На iOS — ровно `share()`.
 */
export async function shareWithForegroundFallback(share: () => Promise<unknown>): Promise<void> {
  if (Platform.OS !== 'android') {
    await share();
    return;
  }
  const waiter = waitForReturnToForeground();
  try {
    await Promise.race([share(), waiter.promise]);
  } finally {
    waiter.cancel();
  }
}
