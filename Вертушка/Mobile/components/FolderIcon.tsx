/**
 * FolderIcon — иконка папки коллекции и вишлиста.
 *
 * Заменяет растровый `folder-placeholder.png` (1024×1024, 754 КБ, один и тот
 * же кадр на все папки). Иконка векторная: одна геометрия обслуживает и сетку
 * 80 px, и пикеры, и списки, а папки перестают быть на одно лицо.
 *
 * Язык формы: ни одного контура. Объём держат заливки и градиенты — тёмный
 * корпус папки, поверх него светлый конверт и пластинка, а нижнюю треть
 * закрывает матовое стекло-клапан. Содержимое НЕ обрезается по кромке
 * стекла: конверт и диск нарисованы целиком и просвечивают сквозь него
 * приглушёнными — это и есть эффект напыления, а не имитация.
 *
 * Порядок слоёв снизу вверх: тень → корпус → пластинка → конверт → стекло →
 * блик по стеклу → светлая кромка. Менять его нельзя: если поднять стекло
 * выше содержимого, папка схлопнется в тёмное пятно.
 *
 * Цвет папки детерминирован: хеш от `seed` (id папки) → один из шести тонов.
 * Тон красит корпус (тёмный оттенок), лейбл пластинки и обложку конверта —
 * поэтому папки различаются и на 24 px, где детали уже не читаются.
 */
import Svg, {
  Circle,
  Defs,
  Ellipse,
  G,
  LinearGradient,
  Path,
  RadialGradient,
  Rect,
  Stop,
} from 'react-native-svg';

/** Корпус папки: язычок слева, скос, тело. */
const BACK_PATH =
  'M10 14.5 a4 4 0 0 1 4-4 h11.4 a1.8 1.8 0 0 1 1.55 0.88 l2.15 3.62 h24.9 ' +
  'a4 4 0 0 1 4 4 v29.5 a4 4 0 0 1 -4 4 h-44 a4 4 0 0 1 -4 -4 Z';

/** Клапан-стекло: шире корпуса, верхняя кромка идёт вниз-вправо. */
const FLAP_PATH =
  'M7 30 a1.7 1.7 0 0 1 2-1.68 L55.3 33.9 a1.9 1.9 0 0 1 1.7 1.9 ' +
  'V50 a4.5 4.5 0 0 1 -4.5 4.5 H11.5 a4.5 4.5 0 0 1 -4.5 -4.5 Z';

/** Диагональный отблеск по стеклу — левый верхний угол клапана. */
const SHEEN_PATH = 'M9.6 29.6 L31 31.9 L23.5 45 L9.2 45 Z';

/** Светлая кромка стекла. Идёт по той же линии, что верх FLAP_PATH. */
const EDGE_PATH = 'M7.8 29.4 L55.9 34.5';

const SLEEVE_FILL = '#F7F9FC';
const DISC_INK = '#090B11';

/** Геометрия пластинки — вынесена, чтобы не считать доли радиуса по месту. */
const DISC = { cx: 41.5, cy: 27.5, r: 12 };
/** Геометрия конверта: квадрат, слегка повёрнут против часовой. */
const SLEEVE = { x: 14, y: 15.5, size: 22, rotation: -4 };

export interface FolderTone {
  /** Верх градиента корпуса. */
  backTop: string;
  /** Низ градиента корпуса. */
  backBottom: string;
  /** Лейбл пластинки, обложка и корешок конверта, подтон стекла. */
  accent: string;
}

export const FOLDER_TONES: readonly FolderTone[] = [
  { backTop: '#39435C', backBottom: '#161C2C', accent: '#3E63E8' }, // cobalt — бренд-ось
  { backTop: '#4E3830', backBottom: '#241612', accent: '#E85A2A' }, // ember
  { backTop: '#4B3341', backBottom: '#22141B', accent: '#D45AA0' }, // rose
  { backTop: '#3E3459', backBottom: '#1B152E', accent: '#7B5FD0' }, // purple
  { backTop: '#4B402A', backBottom: '#211B10', accent: '#C89234' }, // gold
  { backTop: '#334349', backBottom: '#141D22', accent: '#3F7E9C' }, // steel
] as const;

/**
 * Тон по стабильному ключу.
 *
 * djb2: важна не криптостойкость, а то, что тон не скачет между рендерами и
 * между устройствами. Поэтому сеять надо id папки, а не именем — переименование
 * не должно перекрашивать карточку.
 */
export function folderTone(seed: string | undefined): FolderTone {
  if (!seed) return FOLDER_TONES[0];
  let h = 5381;
  for (let i = 0; i < seed.length; i++) {
    h = ((h << 5) + h + seed.charCodeAt(i)) | 0;
  }
  return FOLDER_TONES[Math.abs(h) % FOLDER_TONES.length];
}

/** Серый корпус карточки «Новая папка» — тона тут нет, папки ещё не существует. */
const NEUTRAL_TONE: FolderTone = {
  backTop: '#4A5060',
  backBottom: '#232833',
  accent: '#8B91A3',
};

/** Градиенты живут в общем неймспейсе документа: одинаковые id перетирают
 *  друг друга, и вторая папка в скролле берёт чужой градиент. */
let defsSeq = 0;

export type FolderIconVariant = 'filled' | 'empty' | 'new';

interface FolderIconProps {
  size?: number;
  /** Стабильный ключ окраски — id папки. */
  seed?: string;
  variant?: FolderIconVariant;
  /** Явный тон вместо хеша — для превью и дизайн-экранов. */
  tone?: FolderTone;
}

export function FolderIcon({ size = 80, seed, variant = 'filled', tone }: FolderIconProps) {
  const t = variant === 'new' ? NEUTRAL_TONE : (tone ?? folderTone(seed));
  const k = (defsSeq += 1);
  const id = {
    shadow: `fi-sh-${k}`,
    back: `fi-bk-${k}`,
    glass: `fi-gl-${k}`,
    sheen: `fi-sn-${k}`,
    edge: `fi-ed-${k}`,
    disc: `fi-dc-${k}`,
  };

  return (
    <Svg width={size} height={size} viewBox="0 0 64 64" fill="none">
      <Defs>
        <RadialGradient id={id.shadow} cx="50%" cy="50%" r="50%">
          <Stop offset="0" stopColor="#0B1024" stopOpacity={0.2} />
          <Stop offset="1" stopColor="#0B1024" stopOpacity={0} />
        </RadialGradient>
        <LinearGradient id={id.back} x1="0.1" y1="0" x2="0.3" y2="1">
          <Stop offset="0" stopColor={t.backTop} />
          <Stop offset="1" stopColor={t.backBottom} />
        </LinearGradient>
        <LinearGradient id={id.disc} x1="0.15" y1="0" x2="0.7" y2="1">
          <Stop offset="0" stopColor="#454A57" />
          <Stop offset="1" stopColor={DISC_INK} />
        </LinearGradient>
        {/* Стекло: сверху почти прозрачное — там сквозь него виден конверт;
            книзу глухое, потому что под ним уже только корпус. */}
        <LinearGradient id={id.glass} x1="0.15" y1="0" x2="0.45" y2="1">
          <Stop offset="0" stopColor="#FFFFFF" stopOpacity={0.74} />
          <Stop offset="0.1" stopColor="#FFFFFF" stopOpacity={0.36} />
          <Stop offset="0.34" stopColor={t.accent} stopOpacity={0.2} />
          <Stop offset="0.64" stopColor="#10131C" stopOpacity={0.56} />
          <Stop offset="1" stopColor="#06080E" stopOpacity={0.92} />
        </LinearGradient>
        <LinearGradient id={id.sheen} x1="0" y1="0" x2="0.6" y2="1">
          <Stop offset="0" stopColor="#FFFFFF" stopOpacity={0.22} />
          <Stop offset="1" stopColor="#FFFFFF" stopOpacity={0} />
        </LinearGradient>
        <LinearGradient id={id.edge} x1="0" y1="0" x2="1" y2="0">
          <Stop offset="0" stopColor="#FFFFFF" stopOpacity={0.85} />
          <Stop offset="1" stopColor="#FFFFFF" stopOpacity={0.22} />
        </LinearGradient>
      </Defs>

      <Ellipse cx={32} cy={53.5} rx={24} ry={6} fill={`url(#${id.shadow})`} />
      <Path d={BACK_PATH} fill={`url(#${id.back})`} />

      {variant === 'filled' ? (
        <>
          <Disc gradientId={id.disc} accent={t.accent} />
          <Sleeve accent={t.accent} />
        </>
      ) : null}

      <Path d={FLAP_PATH} fill={`url(#${id.glass})`} />
      <Path d={SHEEN_PATH} fill={`url(#${id.sheen})`} />
      <Path d={EDGE_PATH} stroke={`url(#${id.edge})`} strokeWidth={0.9} strokeLinecap="round" />

      {variant === 'new' ? (
        <Path
          d="M32 36.5 v11 M26.5 42 h11"
          stroke="#FFFFFF"
          strokeOpacity={0.82}
          strokeWidth={2}
          strokeLinecap="round"
        />
      ) : null}
    </Svg>
  );
}

/** Пластинка: канавки, блик, цветной лейбл, шпиндель. */
function Disc({ gradientId, accent }: { gradientId: string; accent: string }) {
  const { cx, cy, r } = DISC;
  return (
    <>
      <Circle cx={cx} cy={cy} r={r} fill={`url(#${gradientId})`} />
      <Circle cx={cx} cy={cy} r={r * 0.78} stroke="#FFFFFF" strokeOpacity={0.14} strokeWidth={0.6} />
      <Circle cx={cx} cy={cy} r={r * 0.62} stroke="#FFFFFF" strokeOpacity={0.11} strokeWidth={0.6} />
      <Circle cx={cx} cy={cy} r={r * 0.47} stroke="#FFFFFF" strokeOpacity={0.08} strokeWidth={0.6} />
      <Path
        d={`M${cx - r * 0.7} ${cy - r * 0.46} a${r * 0.84} ${r * 0.84} 0 0 1 ${r * 0.7} -${r * 0.32}`}
        stroke="#FFFFFF"
        strokeOpacity={0.32}
        strokeWidth={0.9}
        strokeLinecap="round"
      />
      <Circle cx={cx} cy={cy} r={r * 0.3} fill={accent} />
      <Circle cx={cx} cy={cy} r={r * 0.085} fill={DISC_INK} />
    </>
  );
}

/** Конверт: светлый квадрат, цветной корешок и обложка-лейбл. */
function Sleeve({ accent }: { accent: string }) {
  const { x, y, size, rotation } = SLEEVE;
  const cx = x + size / 2;
  const cy = y + size / 2;
  return (
    <G rotation={rotation} originX={cx} originY={cy}>
      <Rect x={x} y={y} width={size} height={size} rx={1.8} fill={SLEEVE_FILL} />
      <Rect x={x} y={y} width={1.5} height={size} rx={0.7} fill={accent} fillOpacity={0.3} />
      <Circle cx={cx + 0.6} cy={cy} r={4.6} fill={accent} fillOpacity={0.85} />
      <Circle cx={cx + 0.6} cy={cy} r={1.01} fill={SLEEVE_FILL} />
    </G>
  );
}

export default FolderIcon;
