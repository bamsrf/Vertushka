/**
 * Курируемый список стран для пикеров (ручное добавление релиза и т.п.).
 * value — английское имя страны как в Discogs-дампе (чтобы совпадало с
 * фильтром стран в Поиске), label — русская подпись для UI.
 *
 * Источник синхронизирован с MAIN_COUNTRIES/ALL_COUNTRIES в app/(tabs)/search.tsx.
 */
export interface CountryOption {
  value: string;
  label: string;
}

export const COUNTRIES: CountryOption[] = [
  { value: 'Russia', label: 'Россия' },
  { value: 'US', label: 'США' },
  { value: 'UK', label: 'Великобритания' },
  { value: 'Germany', label: 'Германия' },
  { value: 'Japan', label: 'Япония' },
  { value: 'France', label: 'Франция' },
  { value: 'Italy', label: 'Италия' },
  { value: 'Netherlands', label: 'Нидерланды' },
  { value: 'Canada', label: 'Канада' },
  { value: 'Australia', label: 'Австралия' },
  { value: 'Sweden', label: 'Швеция' },
  { value: 'Spain', label: 'Испания' },
  { value: 'Brazil', label: 'Бразилия' },
  { value: 'Poland', label: 'Польша' },
  { value: 'Belgium', label: 'Бельгия' },
  { value: 'Austria', label: 'Австрия' },
  { value: 'Denmark', label: 'Дания' },
  { value: 'Finland', label: 'Финляндия' },
  { value: 'Norway', label: 'Норвегия' },
  { value: 'Greece', label: 'Греция' },
  { value: 'Portugal', label: 'Португалия' },
  { value: 'Switzerland', label: 'Швейцария' },
  { value: 'Ireland', label: 'Ирландия' },
  { value: 'Mexico', label: 'Мексика' },
  { value: 'Argentina', label: 'Аргентина' },
  { value: 'China', label: 'Китай' },
  { value: 'South Korea', label: 'Южная Корея' },
  { value: 'India', label: 'Индия' },
  { value: 'Turkey', label: 'Турция' },
  { value: 'Ukraine', label: 'Украина' },
  { value: 'Czechoslovakia', label: 'Чехословакия' },
  { value: 'Yugoslavia', label: 'Югославия' },
  { value: 'USSR', label: 'СССР' },
];
