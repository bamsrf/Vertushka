/**
 * FolderIcon — иконка папки коллекции и вишлиста.
 *
 * Заменяет растровый `folder-placeholder.png` (1024×1024, 754 КБ, один и тот
 * же кадр на все папки). Иконка векторная: одна геометрия обслуживает и сетку
 * 80 px, и пикеры, и списки.
 *
 * Язык формы: ни одного контура и ничего внутри. Объём держат две заливки —
 * корпус с мягким градиентом и матовое стекло-клапан поверх нижней трети.
 * Единственная линия во всей иконке — светлая кромка стекла: она и читается
 * как стекло, поэтому диагональных бликов и содержимого папке не нужно.
 *
 * Цвет — цвет ступени пользователя, а не самой папки. Корпус берёт градиент
 * `LEVEL_FOLDER_BODY`, подтон стекла и кромка — акцент иконки уровня. Поэтому
 * вся полка папок перекрашивается разом, когда юзер берёт новый уровень:
 * ступень видно не только на экране ачивок.
 *
 * Ступень приходит из `useCurrentLevelKey` — общего стора, который
 * `achievementsBus` обновляет с уже запрашиваемых ответов `/achievements/me`.
 * Свой запрос иконка не делает: их в скролле десяток.
 */
import Svg, {
  Defs,
  Ellipse,
  LinearGradient,
  Path,
  RadialGradient,
  Stop,
} from 'react-native-svg';

import { levelFolderBody, levelIconAccent } from './achievement-mockup/levelTheme';
import { useCurrentLevelKey } from '../lib/levelStore';

/** Корпус папки: язычок слева, скос, тело. */
const BACK_PATH =
  'M10 14.5 a4 4 0 0 1 4-4 h11.4 a1.8 1.8 0 0 1 1.55 0.88 l2.15 3.62 h24.9 ' +
  'a4 4 0 0 1 4 4 v29.5 a4 4 0 0 1 -4 4 h-44 a4 4 0 0 1 -4 -4 Z';

/** Клапан-стекло: шире корпуса, верхняя кромка идёт вниз-вправо. */
const FLAP_PATH =
  'M7 30 a1.7 1.7 0 0 1 2-1.68 L55.3 33.9 a1.9 1.9 0 0 1 1.7 1.9 ' +
  'V50 a4.5 4.5 0 0 1 -4.5 4.5 H11.5 a4.5 4.5 0 0 1 -4.5 -4.5 Z';

/** Светлая кромка стекла. Идёт по той же линии, что верх FLAP_PATH. */
const EDGE_PATH = 'M7.8 29.4 L55.9 34.5';

/** Плюс на карточке «Новая папка». */
const PLUS_PATH = 'M32 36.5 v11 M26.5 42 h11';

export interface FolderPalette {
  /** Верх градиента корпуса. */
  backTop: string;
  /** Низ градиента корпуса. */
  backBottom: string;
  /** Подтон стекла и кромка. */
  accent: string;
}

/** Палитра папки для ступени — см. LEVEL_FOLDER_BODY в levelTheme. */
export function folderPalette(levelKey: string): FolderPalette {
  const [backTop, backBottom] = levelFolderBody(levelKey);
  return { backTop, backBottom, accent: levelIconAccent(levelKey) };
}

/** Пустая папка и карточка «Новая» вне цвета ступени: хвастаться нечем. */
const NEUTRAL_PALETTE: FolderPalette = {
  backTop: '#3A404E',
  backBottom: '#22262F',
  accent: '#8B91A3',
};

/** Градиенты живут в общем неймспейсе документа: одинаковые id перетирают
 *  друг друга, и вторая папка в скролле берёт чужой градиент. */
let defsSeq = 0;

export type FolderIconVariant = 'filled' | 'empty' | 'new';

interface FolderIconProps {
  size?: number;
  variant?: FolderIconVariant;
  /** Явная ступень вместо текущей — для превью и дизайн-экранов. */
  level?: string;
}

export function FolderIcon({ size = 80, variant = 'filled', level }: FolderIconProps) {
  const currentLevel = useCurrentLevelKey();
  const p = variant === 'filled' ? folderPalette(level ?? currentLevel) : NEUTRAL_PALETTE;

  const k = (defsSeq += 1);
  const id = {
    shadow: `fi-sd-${k}`,
    back: `fi-bk-${k}`,
    glass: `fi-gl-${k}`,
    edge: `fi-ed-${k}`,
  };

  return (
    <Svg width={size} height={size} viewBox="0 0 64 64" fill="none">
      <Defs>
        <RadialGradient id={id.shadow} cx="50%" cy="50%" r="50%">
          <Stop offset="0" stopColor="#0B1024" stopOpacity={0.2} />
          <Stop offset="1" stopColor="#0B1024" stopOpacity={0} />
        </RadialGradient>
        <LinearGradient id={id.back} x1="0.1" y1="0" x2="0.3" y2="1">
          <Stop offset="0" stopColor={p.backTop} />
          <Stop offset="1" stopColor={p.backBottom} />
        </LinearGradient>
        {/* Стекло: сверху почти прозрачное, книзу плотное — но не глухое.
            Корпуса ступеней насыщенные, и полностью чёрный низ съедал бы их
            цвет: «Первозвук» переставал быть золотым. Подтон ступени держит
            клапан в семье корпуса, иначе он читается серой накладкой. */}
        <LinearGradient id={id.glass} x1="0.15" y1="0" x2="0.45" y2="1">
          <Stop offset="0" stopColor="#FFFFFF" stopOpacity={0.7} />
          <Stop offset="0.1" stopColor="#FFFFFF" stopOpacity={0.32} />
          <Stop offset="0.34" stopColor={p.accent} stopOpacity={0.18} />
          <Stop offset="0.64" stopColor="#10131C" stopOpacity={0.44} />
          <Stop offset="1" stopColor="#06080E" stopOpacity={0.78} />
        </LinearGradient>
        <LinearGradient id={id.edge} x1="0" y1="0" x2="1" y2="0">
          <Stop offset="0" stopColor="#FFFFFF" stopOpacity={0.85} />
          <Stop offset="1" stopColor="#FFFFFF" stopOpacity={0.22} />
        </LinearGradient>
      </Defs>

      <Ellipse cx={32} cy={53.5} rx={24} ry={6} fill={`url(#${id.shadow})`} />
      <Path d={BACK_PATH} fill={`url(#${id.back})`} />
      <Path d={FLAP_PATH} fill={`url(#${id.glass})`} />
      <Path d={EDGE_PATH} stroke={`url(#${id.edge})`} strokeWidth={0.9} strokeLinecap="round" />

      {variant === 'new' ? (
        <Path
          d={PLUS_PATH}
          stroke="#FFFFFF"
          strokeOpacity={0.82}
          strokeWidth={2}
          strokeLinecap="round"
        />
      ) : null}
    </Svg>
  );
}

export default FolderIcon;
