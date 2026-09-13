/**
 * SwipeBackHintHost — решает, когда показать подсказку про возврат свайпом.
 *
 * Живёт в корневом layout'е рядом со `<Stack>`, а не на экранах: жест общий
 * для всего приложения, и повесить подсказку на какой-то один экран значило
 * бы объяснять её тому, кто до этого экрана дошёл, и молчать для остальных.
 *
 * Условие показа — «мы на вложенном экране, откуда есть куда возвращаться».
 * Тот же предикат, что включает сам жест на Android
 * (`isEdgeSwipeEnabledForSegment`), поэтому подсказка не может появиться там,
 * где свайп ничего не сделает: на табах, авторизации и приветствии.
 *
 * Пауза до показа больше обычной. Экран должен не только доехать, но и
 * загрузиться: карточка релиза досыпает обложку, цену и офферы ещё секунду
 * после появления. Плашка поверх скачущего контента читается как часть этой
 * суеты, а не как подсказка.
 *
 * Про «жест освоен». На Android момент известен точно — `AndroidEdgeSwipeBack`
 * зовёт `markSwipeBackPerformed` на коммите. На iOS жест везёт нативный стек,
 * и отличить свайп от нажатия стрелки в шапке приложение не может: событие
 * перехода одно и то же. Поэтому там подсказка гаснет по обычному лимиту в
 * два показа. Итог для iOS: человек, который жест и так знает, увидит плашку
 * дважды за всё время — это цена, а не поломка.
 */
import { useEffect } from 'react';
import { useSegments } from 'expo-router';

import { SwipeBackHint } from './SwipeBackHint';
import { useGestureHintGate } from '../../lib/useGestureHintGate';
import { isEdgeSwipeEnabledForSegment } from '../../lib/edgeSwipeBack';
import { setSwipeBackPerformedHandler } from '../../lib/swipeBackPerformed';

/**
 * Пауза перед показом. Больше общей (900 мс): ждём, пока вложенный экран не
 * только въедет, но и дозагрузит свои блоки.
 */
const DWELL_MS = 1600;

export function SwipeBackHintHost() {
  const segments = useSegments();
  const onDeepScreen = isEdgeSwipeEnabledForSegment(segments[0]);

  const { armed, performed, finish } = useGestureHintGate('swipe-back', {
    enabled: onDeepScreen,
    dwellMs: DWELL_MS,
  });

  // Android умеет сказать точно, что человек сделал свайп. Держим подписку,
  // пока хост смонтирован; на iOS её никто не дёрнет.
  useEffect(() => setSwipeBackPerformedHandler(performed), [performed]);

  return <SwipeBackHint visible={armed} onDone={finish} />;
}
