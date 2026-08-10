/**
 * Трекер жестов для «Скрытой дорожки» (пасхалки серии E).
 *
 * Эти пасхалки ловят то, чего в БД не видно: тапы по крутящемуся винилу,
 * упрямый pull-to-refresh, промах распознавания обложки. Бэкенд про такое
 * узнать не может, поэтому считаем на клиенте и шлём готовый факт — событие
 * означает «условие выполнено», а не «вот ещё один тап».
 *
 * Счётчики живут в памяти модуля: сессия закончилась — счёт обнулился, и это
 * ровно та семантика, которая нужна («78 обновлений ЗА СЕССИЮ»). Слать событие
 * повторно не страшно (бэкенд идемпотентен), но мы и так шлём один раз на
 * сессию — незачем шуметь в сеть.
 */
import { api } from './api';

/** Тапов по спиннеру на ОДНОЙ карточке. Отсылка к 33⅓ об/мин. */
const SPIN_TARGET = 33;
/** Pull-to-refresh за сессию. Отсылка к 78 об/мин. */
const PULL_TARGET = 78;
/**
 * Сколько ждём ручного добавления после промаха скана. Полчаса — это ещё
 * «я долистал и добавил сам», а не случайное совпадение через день.
 */
const SCAN_MISS_TTL_MS = 30 * 60 * 1000;

let spinRecordId: string | null = null;
let spinCount = 0;
let spinSent = false;

let pullCount = 0;
let pullSent = false;

let scanMissAt = 0;

/** Тап по вращающемуся винилу на карточке релиза. */
export function countSpin(recordId: string): void {
  if (spinRecordId !== recordId) {
    // Ушли на другую карточку — счёт начинается заново: условие про «33 раза
    // на одной карточке», а не про упорство вообще.
    spinRecordId = recordId;
    spinCount = 0;
  }
  spinCount += 1;
  if (spinCount >= SPIN_TARGET && !spinSent) {
    spinSent = true;
    void api.trackAchievementEvent('vinyl_spun_33');
  }
}

/** Pull-to-refresh на любом списке. */
export function countPull(): void {
  pullCount += 1;
  if (pullCount >= PULL_TARGET && !pullSent) {
    pullSent = true;
    void api.trackAchievementEvent('pulled_78');
  }
}

/** Пластинка добавлена из результатов скана камерой. */
export function reportScanAdd(recordId?: string): void {
  void api.trackAchievementEvent('scan_added', recordId ? { record_id: recordId } : undefined);
}

/** Скан вернул промах — камера не узнала обложку. */
export function reportScanMiss(): void {
  scanMissAt = Date.now();
}

/**
 * Пластинка добавлена руками. Если незадолго до этого скан промахнулся —
 * это и есть «Глаз-алмаз»: машина не справилась, а человек справился.
 */
export function reportManualAdd(): void {
  if (!scanMissAt || Date.now() - scanMissAt > SCAN_MISS_TTL_MS) return;
  scanMissAt = 0;
  void api.trackAchievementEvent('scan_miss_manual_add');
}

/** Открыт экран «Ачивки» — бэкенд сверит дату с годовщиной регистрации. */
export function reportAchievementsOpened(): void {
  void api.trackAchievementEvent('achievements_opened');
}
