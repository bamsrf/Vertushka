/**
 * Сравнение версий для force-update gate.
 *
 * Вынесено отдельным файлом без импортов: от этой функции зависит, увидит
 * пользователь приложение или блокирующий экран, поэтому её нужно уметь
 * прогонять изолированно. См. lib/remoteConfig.ts.
 */

/** Разбор `1.2.3` → [1,2,3]. null, если формат не тот, которому мы доверяем. */
function parseVersion(value: string): number[] | null {
  const parts = value.trim().split('.');
  if (parts.length !== 3) return null;

  const nums = parts.map((p) => Number(p));
  if (nums.some((n) => !Number.isInteger(n) || n < 0)) return null;

  return nums;
}

/**
 * Строго ли `version` ниже `minimum`. Обе строки вида `1.2.3`.
 *
 * Любой вход, в котором мы не уверены (пустая строка, буквы, другое число
 * сегментов), даёт `false` — то есть НЕ блокирует. Ошибка парсинга не должна
 * выгонять на обновление всех пользователей разом.
 */
export function isVersionBelow(version: string, minimum: string): boolean {
  const current = parseVersion(version);
  const min = parseVersion(minimum);
  if (!current || !min) return false;

  for (let i = 0; i < 3; i += 1) {
    if (current[i] < min[i]) return true;
    if (current[i] > min[i]) return false;
  }
  return false;
}
