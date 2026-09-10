const ARTIST_DISCRIMINATOR_RE = /\s*\(\d+\)\s*$/;

export function cleanArtistName(name: string | null | undefined): string {
  if (!name) return '';
  return name.replace(ARTIST_DISCRIMINATOR_RE, '').trim();
}

/**
 * Русские склонения после числа: plural(1, 'подарок', 'подарка', 'подарков').
 * Возвращает число вместе со словом — «1 подарок», «3 подарка», «12 подарков».
 */
export function plural(count: number, one: string, few: string, many: string): string {
  const mod100 = Math.abs(count) % 100;
  const mod10 = mod100 % 10;
  if (mod100 >= 11 && mod100 <= 14) return `${count} ${many}`;
  if (mod10 === 1) return `${count} ${one}`;
  if (mod10 >= 2 && mod10 <= 4) return `${count} ${few}`;
  return `${count} ${many}`;
}

/**
 * Группировка тысяч как у `toLocaleString('ru-RU')` (разделитель U+00A0),
 * но без Intl и без аллокаций локали — пригодна для worklet'а на UI-потоке.
 * Hermes на Android не гарантирует полный Intl, а `toLocaleString` внутри
 * worklet'а — это захват JS-объекта локали на каждом кадре.
 */
export function formatGroupedWorklet(value: number): string {
  'worklet';
  const digits = String(Math.abs(Math.round(value)));
  let out = '';
  for (let i = 0; i < digits.length; i++) {
    if (i > 0 && (digits.length - i) % 3 === 0) out += ' ';
    out += digits[i];
  }
  return (value < 0 ? '-' : '') + out;
}
