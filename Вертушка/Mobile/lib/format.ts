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
