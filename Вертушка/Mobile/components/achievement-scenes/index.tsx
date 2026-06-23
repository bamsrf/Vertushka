/**
 * Achievement scenes — SVG-иллюстрации для пинов.
 *
 * Каждая ачивка имеет свой сюжет: винил/кассета/окно/корабль/...
 * Сцены рендерятся через react-native-svg, тир получают через prop и
 * подмешивают в акцентные цвета. Форма не круг — края могут заходить
 * за квадрат-рамку (см. виду каждого пина).
 *
 * Пока scene нет — fallback на дефолтный пин (буква+канавки).
 *
 * НЕ заменяет финальные пины от дизайнера — это «живой» плейсхолдер,
 * чтобы понять как фича выглядит и ведёт себя в приложении.
 */
import { ReactElement } from 'react';
import { Image, ImageSourcePropType } from 'react-native';
import Svg, {
  Circle,
  Defs,
  Ellipse,
  G,
  Line,
  LinearGradient,
  Path,
  Polygon,
  Rect,
  Stop,
  Text as SvgText,
  TSpan,
} from 'react-native-svg';

import type { AchievementTierKey } from '../../lib/types';

export interface SceneProps {
  /** Размер «канвы» сцены — 100×100 viewport, контент может выходить
   *  за рамки, но клиппер у пина сам решит, обрезать или нет. */
  size: number;
  /** Главный акцентный цвет — обычно цвет тира. Сюжет варьируется,
   *  но рамка/акценты — этого цвета. */
  accent: string;
  /** Второй цвет (для градиентов и теней). */
  accentDark: string;
  /** Цвет «бумаги»/контура — обычно тёмный. */
  ink: string;
  /** Для locked-состояния — приглушённое отображение. */
  locked: boolean;
}

// ─── helpers ────────────────────────────────────────────────────────────────

function shiftAlpha(hex: string, alpha: number): string {
  const a = Math.round(Math.min(1, Math.max(0, alpha)) * 255)
    .toString(16)
    .padStart(2, '0');
  return `${hex}${a}`;
}

function lockedColor(c: string, locked: boolean): string {
  return locked ? '#B2B7C2' : c;
}

// Vinyl-кольцо: пять концентрических окружностей вокруг центра. Утилита для
// частого мотива, не для всех сцен.
function VinylCircle({
  cx,
  cy,
  r,
  color,
  labelColor,
}: {
  cx: number;
  cy: number;
  r: number;
  color: string;
  labelColor?: string;
}) {
  const rings = [r, r * 0.85, r * 0.7, r * 0.55, r * 0.4];
  return (
    <G>
      {rings.map((rr, i) => (
        <Circle
          key={i}
          cx={cx}
          cy={cy}
          r={rr}
          stroke={color}
          strokeOpacity={0.7 - i * 0.1}
          strokeWidth={0.6}
          fill="none"
        />
      ))}
      <Circle cx={cx} cy={cy} r={r * 0.18} fill={labelColor || color} />
      <Circle cx={cx} cy={cy} r={r * 0.04} fill="#FFFFFF" />
    </G>
  );
}

// ─── A1 «Поехали» — игла опускается на пластинку ──────────────────────────

export function ScenePoehali({ accent, accentDark, ink, locked }: SceneProps): ReactElement {
  const a = lockedColor(accent, locked);
  const ad = lockedColor(accentDark, locked);
  const c = lockedColor(ink, locked);
  return (
    <Svg width="100%" height="100%" viewBox="0 0 100 100">
      {/* Пластинка */}
      <Circle cx={42} cy={62} r={32} fill={c} />
      <VinylCircle cx={42} cy={62} r={28} color={shiftAlpha('#FFFFFF', 0.35)} labelColor={a} />
      {/* Тонарм/игла спускается сверху-справа */}
      <Line x1={88} y1={6} x2={62} y2={42} stroke={ad} strokeWidth={3.5} strokeLinecap="round" />
      <Circle cx={88} cy={6} r={5} fill={ad} />
      {/* Картридж в конце */}
      <Polygon points="62,42 68,38 72,46 66,50" fill={a} />
      {/* Импульс «поехали» */}
      <Path d="M 62 42 q 4 -2 8 -1" stroke={a} strokeOpacity={0.5} strokeWidth={1.5} fill="none" />
    </Svg>
  );
}

// ─── A2 «Хотелка» — сердце с виниловой канавкой ──────────────────────────

export function SceneHotelka({ accent, accentDark, ink, locked }: SceneProps): ReactElement {
  const heart = lockedColor(accent, locked);
  const heartD = lockedColor(accentDark, locked);
  const c = lockedColor(ink, locked);
  return (
    <Svg width="100%" height="100%" viewBox="0 0 100 100">
      <Defs>
        <LinearGradient id="heartGrad" x1="0" y1="0" x2="1" y2="1">
          <Stop offset="0" stopColor={heart} />
          <Stop offset="1" stopColor={heartD} />
        </LinearGradient>
      </Defs>
      {/* Сердце */}
      <Path
        d="M 50 85 C 18 65 12 38 28 26 C 40 18 50 28 50 36 C 50 28 60 18 72 26 C 88 38 82 65 50 85 Z"
        fill="url(#heartGrad)"
      />
      {/* Виниловые канавки внутри */}
      <VinylCircle cx={50} cy={52} r={22} color={shiftAlpha('#FFFFFF', 0.4)} labelColor={c} />
    </Svg>
  );
}

// ─── A3 «Аватар» — портретная рамка с силуэтом ────────────────────────────

export function SceneAvatar({ accent, accentDark, ink, locked }: SceneProps): ReactElement {
  const f = lockedColor(accent, locked);
  const fd = lockedColor(accentDark, locked);
  const c = lockedColor(ink, locked);
  return (
    <Svg width="100%" height="100%" viewBox="0 0 100 100">
      {/* Рамка-фотокарточка */}
      <Rect x={16} y={14} width={68} height={78} rx={6} fill={f} />
      <Rect x={20} y={18} width={60} height={62} rx={4} fill="#FFFFFF" />
      {/* Силуэт */}
      <Circle cx={50} cy={42} r={12} fill={c} />
      <Path d="M 28 84 C 28 64 72 64 72 84 Z" fill={c} />
      {/* Декоративная скоба внизу */}
      <Rect x={28} y={84} width={44} height={4} rx={2} fill={fd} />
    </Svg>
  );
}

// ─── A4 «Распахнул» — окно с летящими пластинками ─────────────────────────

export function SceneOpenWindow({ accent, accentDark, ink, locked }: SceneProps): ReactElement {
  const f = lockedColor(accent, locked);
  const fd = lockedColor(accentDark, locked);
  const c = lockedColor(ink, locked);
  return (
    <Svg width="100%" height="100%" viewBox="0 0 100 100">
      <Defs>
        <LinearGradient id="windowSky" x1="0" y1="0" x2="0" y2="1">
          <Stop offset="0" stopColor={shiftAlpha(f, 0.95)} />
          <Stop offset="1" stopColor={shiftAlpha(fd, 0.5)} />
        </LinearGradient>
      </Defs>
      {/* Рама */}
      <Rect x={14} y={14} width={56} height={70} rx={3} fill={c} />
      <Rect x={18} y={18} width={48} height={62} fill="url(#windowSky)" />
      {/* Створка распахнута (правая половина) */}
      <Path d="M 42 18 L 86 8 L 86 90 L 42 80 Z" fill={shiftAlpha(c, 0.85)} />
      <Rect x={50} y={20} width={30} height={64} rx={2} fill={shiftAlpha(f, 0.55)} />
      {/* Перекрестье створки */}
      <Line x1={42} y1={49} x2={86} y2={49} stroke={c} strokeWidth={1.2} />
      <Line x1={65} y1={14} x2={65} y2={85} stroke={c} strokeWidth={1.2} />
      {/* Пластинка вылетающая */}
      <Circle cx={32} cy={48} r={9} fill={c} />
      <Circle cx={32} cy={48} r={2} fill={f} />
      <Circle cx={32} cy={48} r={0.7} fill="#FFFFFF" />
      {/* Маленькая летящая */}
      <Circle cx={20} cy={32} r={5} fill={c} />
      <Circle cx={20} cy={32} r={1.2} fill={f} />
    </Svg>
  );
}

// ─── A5 «Полка-двойник» — две стопки пластинок ────────────────────────────

export function SceneTwoShelves({ accent, accentDark, ink, locked }: SceneProps): ReactElement {
  const f = lockedColor(accent, locked);
  const fd = lockedColor(accentDark, locked);
  const c = lockedColor(ink, locked);
  return (
    <Svg width="100%" height="100%" viewBox="0 0 100 100">
      {/* Полка нижняя */}
      <Rect x={8} y={84} width={84} height={6} rx={2} fill={c} />
      <Rect x={8} y={54} width={84} height={4} rx={1} fill={c} />
      {/* Стопка слева (узкие конверты) */}
      <Rect x={14} y={58} width={5} height={26} fill={f} />
      <Rect x={20} y={58} width={5} height={26} fill={fd} />
      <Rect x={26} y={58} width={5} height={26} fill={f} />
      <Rect x={32} y={58} width={5} height={26} fill={fd} />
      {/* Стопка справа */}
      <Rect x={56} y={58} width={5} height={26} fill={f} />
      <Rect x={62} y={58} width={5} height={26} fill={fd} />
      <Rect x={68} y={58} width={5} height={26} fill={f} />
      <Rect x={74} y={58} width={5} height={26} fill={fd} />
      <Rect x={80} y={58} width={5} height={26} fill={f} />
      {/* Опорные стенки */}
      <Rect x={42} y={24} width={4} height={64} fill={c} />
      {/* Верхняя одна (намёк) */}
      <Rect x={28} y={28} width={4} height={24} fill={f} />
      <Rect x={34} y={28} width={4} height={24} fill={fd} />
      <Rect x={60} y={28} width={4} height={24} fill={f} />
    </Svg>
  );
}

// ─── META_foundation «На борту» — кораблик из винила ─────────────────────

export function SceneOnBoard({ accent, accentDark, ink, locked }: SceneProps): ReactElement {
  const f = lockedColor(accent, locked);
  const fd = lockedColor(accentDark, locked);
  const c = lockedColor(ink, locked);
  return (
    <Svg width="100%" height="100%" viewBox="0 0 100 100">
      {/* Море-волна */}
      <Path
        d="M 0 78 Q 25 70 50 78 T 100 78 L 100 100 L 0 100 Z"
        fill={shiftAlpha(f, 0.5)}
      />
      <Path d="M 0 84 Q 30 76 60 84 T 100 84" stroke={fd} strokeWidth={1.2} fill="none" />
      {/* Корпус — половина пластинки */}
      <Path d="M 20 70 L 80 70 L 70 84 L 30 84 Z" fill={c} />
      <VinylCircle cx={50} cy={70} r={18} color={shiftAlpha('#FFFFFF', 0.45)} labelColor={f} />
      {/* Мачта */}
      <Rect x={49} y={22} width={2.5} height={48} fill={c} />
      {/* Парус */}
      <Path d="M 51 24 L 78 50 L 51 60 Z" fill={f} />
      <Path d="M 51 24 L 35 50 L 51 60 Z" fill={fd} />
      {/* Флажок */}
      <Polygon points="49,18 60,22 49,26" fill={fd} />
    </Svg>
  );
}

// ─── B-серия (B1..B6) — растущая стопка пластинок ─────────────────────────

export function SceneStack({ accent, accentDark, ink, locked, count }: SceneProps & { count: number }): ReactElement {
  const f = lockedColor(accent, locked);
  const fd = lockedColor(accentDark, locked);
  const c = lockedColor(ink, locked);
  const layers = Math.min(Math.max(count, 1), 6);
  // Слой = виниловая пластинка
  const items: ReactElement[] = [];
  for (let i = 0; i < layers; i++) {
    const y = 84 - i * 9;
    items.push(
      <G key={i}>
        <Ellipse cx={50} cy={y} rx={28 - i * 1.2} ry={5} fill={i % 2 ? f : fd} />
        <Ellipse cx={50} cy={y - 1} rx={28 - i * 1.2} ry={4.5} fill={c} />
        <Circle cx={50} cy={y - 1} r={3} fill={i % 2 ? fd : f} />
        <Circle cx={50} cy={y - 1} r={0.7} fill="#FFFFFF" />
      </G>,
    );
  }
  return <Svg width="100%" height="100%" viewBox="0 0 100 100">{items}</Svg>;
}

// ─── J1 «Подарил» — коробка с лентой ─────────────────────────────────────

export function SceneGiftBox({ accent, accentDark, ink, locked }: SceneProps): ReactElement {
  const f = lockedColor(accent, locked);
  const fd = lockedColor(accentDark, locked);
  const c = lockedColor(ink, locked);
  return (
    <Svg width="100%" height="100%" viewBox="0 0 100 100">
      {/* Тело коробки */}
      <Rect x={18} y={38} width={64} height={50} rx={3} fill={c} />
      {/* Крышка */}
      <Rect x={14} y={34} width={72} height={12} rx={2} fill={fd} />
      {/* Лента вертикальная */}
      <Rect x={46} y={34} width={8} height={54} fill={f} />
      {/* Лента горизонтальная */}
      <Rect x={14} y={56} width={72} height={6} fill={f} />
      {/* Бантик */}
      <Path d="M 50 30 C 38 18 32 32 50 38 C 68 32 62 18 50 30 Z" fill={f} />
      <Circle cx={50} cy={32} r={3} fill={fd} />
    </Svg>
  );
}

// ─── R_self_titled «Тёзка» — две одинаковые пластинки ────────────────────

export function SceneTwin({ accent, accentDark, ink, locked }: SceneProps): ReactElement {
  const f = lockedColor(accent, locked);
  const fd = lockedColor(accentDark, locked);
  const c = lockedColor(ink, locked);
  return (
    <Svg width="100%" height="100%" viewBox="0 0 100 100">
      {/* Левая пластинка */}
      <Circle cx={36} cy={50} r={28} fill={c} />
      <VinylCircle cx={36} cy={50} r={24} color={shiftAlpha('#FFFFFF', 0.4)} labelColor={f} />
      {/* Правая (зеркально) */}
      <Circle cx={64} cy={50} r={28} fill={c} opacity={0.92} />
      <VinylCircle cx={64} cy={50} r={24} color={shiftAlpha('#FFFFFF', 0.4)} labelColor={fd} />
      {/* Знак «=» */}
      <Rect x={47} y={45} width={6} height={2.5} fill="#FFFFFF" />
      <Rect x={47} y={52} width={6} height={2.5} fill="#FFFFFF" />
    </Svg>
  );
}

// ─── R_thirty_three «Тридцать три» — 33⅓ ─────────────────────────────────

export function SceneThirtyThree({ accent, accentDark, ink, locked }: SceneProps): ReactElement {
  const f = lockedColor(accent, locked);
  const fd = lockedColor(accentDark, locked);
  const c = lockedColor(ink, locked);
  return (
    <Svg width="100%" height="100%" viewBox="0 0 100 100">
      <Circle cx={50} cy={50} r={42} fill={c} />
      <VinylCircle cx={50} cy={50} r={36} color={shiftAlpha('#FFFFFF', 0.18)} labelColor={f} />
      <SvgText
        x="50"
        y="58"
        fontSize="22"
        fontWeight="900"
        fill="#FFFFFF"
        textAnchor="middle"
      >
        33⅓
      </SvgText>
    </Svg>
  );
}

// ─── R_pi «Число Пи» ─────────────────────────────────────────────────────

export function ScenePi({ accent, accentDark, ink, locked }: SceneProps): ReactElement {
  const f = lockedColor(accent, locked);
  const fd = lockedColor(accentDark, locked);
  const c = lockedColor(ink, locked);
  return (
    <Svg width="100%" height="100%" viewBox="0 0 100 100">
      <Circle cx={50} cy={50} r={42} fill={c} />
      <VinylCircle cx={50} cy={50} r={36} color={shiftAlpha('#FFFFFF', 0.18)} labelColor={fd} />
      <SvgText x="50" y="62" fontSize="40" fontWeight="900" fill={f} textAnchor="middle">π</SvgText>
    </Svg>
  );
}

// ─── R_seventy_eight «Семьдесят восемь» — граммофон-горн ──────────────────

export function SceneGramophone({ accent, accentDark, ink, locked }: SceneProps): ReactElement {
  const f = lockedColor(accent, locked);
  const fd = lockedColor(accentDark, locked);
  const c = lockedColor(ink, locked);
  return (
    <Svg width="100%" height="100%" viewBox="0 0 100 100">
      {/* Воронка-горн */}
      <Path d="M 20 16 L 80 16 L 64 50 L 36 50 Z" fill={f} />
      <Path d="M 36 50 L 64 50 L 60 54 L 40 54 Z" fill={fd} />
      {/* Трубка */}
      <Rect x={46} y={54} width={8} height={20} fill={c} />
      {/* Основание */}
      <Rect x={26} y={74} width={48} height={10} rx={2} fill={c} />
      <SvgText x="50" y="92" fontSize="11" fontWeight="900" fill={f} textAnchor="middle">78 RPM</SvgText>
    </Svg>
  );
}

// ─── K-серия (микрофон/ухо/мегафон) ───────────────────────────────────────

export function SceneMic({ accent, accentDark, ink, locked }: SceneProps): ReactElement {
  const f = lockedColor(accent, locked);
  const fd = lockedColor(accentDark, locked);
  const c = lockedColor(ink, locked);
  return (
    <Svg width="100%" height="100%" viewBox="0 0 100 100">
      {/* Микрофон капсула */}
      <Rect x={36} y={14} width={28} height={42} rx={14} fill={c} />
      {/* Решётка */}
      <Line x1={40} y1={22} x2={60} y2={22} stroke={f} strokeWidth={1.2} />
      <Line x1={40} y1={28} x2={60} y2={28} stroke={f} strokeWidth={1.2} />
      <Line x1={40} y1={34} x2={60} y2={34} stroke={f} strokeWidth={1.2} />
      <Line x1={40} y1={40} x2={60} y2={40} stroke={f} strokeWidth={1.2} />
      <Line x1={40} y1={46} x2={60} y2={46} stroke={f} strokeWidth={1.2} />
      {/* Подставка */}
      <Path d="M 26 56 Q 50 80 74 56" stroke={c} strokeWidth={3} fill="none" />
      <Line x1={50} y1={74} x2={50} y2={88} stroke={c} strokeWidth={3} strokeLinecap="round" />
      <Rect x={36} y={86} width={28} height={4} rx={2} fill={fd} />
    </Svg>
  );
}

export function SceneEar({ accent, accentDark, ink, locked }: SceneProps): ReactElement {
  const f = lockedColor(accent, locked);
  const fd = lockedColor(accentDark, locked);
  const c = lockedColor(ink, locked);
  return (
    <Svg width="100%" height="100%" viewBox="0 0 100 100">
      {/* Контур уха */}
      <Path
        d="M 36 18 Q 22 26 24 50 Q 26 76 46 84 Q 56 88 60 78 Q 64 68 56 62 Q 48 58 52 50 Q 56 42 50 38 Q 44 36 44 30 Q 44 22 36 18 Z"
        fill={c}
      />
      <Path d="M 40 38 Q 50 38 50 48 Q 50 56 44 58" stroke={f} strokeWidth={2} fill="none" />
      {/* Звуковые волны */}
      <Path d="M 70 36 Q 80 50 70 64" stroke={fd} strokeWidth={2} fill="none" />
      <Path d="M 78 28 Q 92 50 78 72" stroke={fd} strokeWidth={2} fill="none" />
    </Svg>
  );
}

// ─── Дефолтная сцена — пластинка с инициалом (fallback) ──────────────────

export function SceneDefault({ accent, accentDark, ink, locked, label }: SceneProps & { label: string }): ReactElement {
  const f = lockedColor(accent, locked);
  const fd = lockedColor(accentDark, locked);
  const c = lockedColor(ink, locked);
  return (
    <Svg width="100%" height="100%" viewBox="0 0 100 100">
      <Circle cx={50} cy={50} r={42} fill={c} />
      <VinylCircle cx={50} cy={50} r={36} color={shiftAlpha('#FFFFFF', 0.22)} labelColor={f} />
      <SvgText
        x="50"
        y="59"
        fontSize="22"
        fontWeight="900"
        fill="#FFFFFF"
        textAnchor="middle"
      >
        {label}
      </SvgText>
    </Svg>
  );
}

// ─── PNG-based scenes (финальные пины от дизайнера) ───────────────────────
//
// Когда дизайнер отдаёт готовый PNG-пин с прозрачным фоном — оборачиваем
// его через `makeImageScene(src)` и регистрируем в REGISTRY как обычную
// SVG-сцену. Helper держит API совместимым с `SceneRenderer`.
//
// Для locked-стейта PNG приглушается через opacity (точная desaturation —
// отдельная задача, см. PLAN_ACHIEVEMENTS_PINS_PROMPT.md §Verification).

function makeImageScene(src: ImageSourcePropType): SceneRendererImpl {
  return function SceneImage({ size, locked }: SceneProps): ReactElement {
    return (
      <Image
        source={src}
        style={{
          width: size,
          height: size,
          opacity: locked ? 0.32 : 1,
        }}
        resizeMode="contain"
      />
    );
  };
}

// `SceneRenderer` объявлен ниже, но TS требует тип для makeImageScene выше —
// дублируем сигнатуру локально, чтобы избежать forward-reference в типах.
type SceneRendererImpl = (p: SceneProps) => ReactElement;

// D3 «Кругосветка» — финальный пин (PNG, 256×256, прозрачный фон).
// Источник 256 выбран как баланс памяти и резкости: на гриде 64 px
// downscale выглядит чисто, в unlock-overlay 256 px — нативно.
// Для share-card 700 px переключим источник через size-aware helper позже.
export const SceneCircumnavigation: SceneRendererImpl = makeImageScene(
  require('../../assets/achievements/256/circumnavigation.png'),
);

// ─── Mapping code → scene renderer ────────────────────────────────────────

export type SceneRenderer = (p: SceneProps) => ReactElement;

const REGISTRY: Record<string, SceneRenderer> = {
  // Foundation
  A1_first_record: ScenePoehali,
  A2_first_wishlist: SceneHotelka,
  A3_avatar_set: SceneAvatar,
  A4_public_profile: SceneOpenWindow,
  META_foundation: SceneOnBoard,
  // Scale (стопка растёт с тиром)
  B1_starter: (p) => <SceneStack {...p} count={2} />,
  B2_collector: (p) => <SceneStack {...p} count={3} />,
  B3_archivist: (p) => <SceneStack {...p} count={4} />,
  B4_curator: (p) => <SceneStack {...p} count={5} />,
  B5_keeper: (p) => <SceneStack {...p} count={6} />,
  B6_warden: (p) => <SceneStack {...p} count={6} />,
  META_scale: (p) => <SceneStack {...p} count={6} />,
  // Gifts
  J1_first_gift: SceneGiftBox,
  // Community
  K2_first_follower: SceneEar,
  K3_followers_x5: SceneMic,
  K4_followers_x50: SceneMic,
  K5_views_x100: SceneEar,
  K6_views_x1000: SceneEar,
  // Random
  R_self_titled: SceneTwin,
  R_thirty_three: SceneThirtyThree,
  R_seventy_eight: SceneGramophone,
  R_pi: ScenePi,
  // ── Phase 2–4 scaffold mappings (заглушки, чтобы каркасные пины не были
  // одинаково-серыми; финальные дизайны заменят это поштучно)
  // J2–J5 + J7/J8/J9 + META_gifts (J6 удалён)
  J2_gift_done: SceneGiftBox,
  J3_three_recipients: SceneGiftBox,
  J4_ten_recipients: SceneGiftBox,
  J5_first_received: SceneGiftBox,
  J7_boomerang: SceneGiftBox,
  J8_loved: SceneGiftBox,
  J9_santa: SceneGiftBox,
  META_gifts: SceneGiftBox,
  // Rarity (C) — пока используем стопку и витрину
  C1_limited_x5: (p) => <SceneStack {...p} count={3} />,
  C2_limited_x25: (p) => <SceneStack {...p} count={5} />,
  C3_collectible_x1: SceneOpenWindow,
  C4_collectible_x5: (p) => <SceneStack {...p} count={4} />,
  C5_collectible_x15: (p) => <SceneStack {...p} count={6} />,
  C6_hot_in_wishlist: SceneHotelka,
  C7_hot_in_collection: SceneTwoShelves,
  META_rarity: SceneOpenWindow,
  // Geography (D)
  D1_country_x5: SceneOpenWindow,
  D2_country_x15: SceneOpenWindow,
  D3_country_x30: SceneCircumnavigation, // финальный PNG-пин
  D4_japanese_x10: SceneOpenWindow,
  D5_melodiya_x10: SceneOpenWindow,
  D6_uk_collectible_x3: SceneOpenWindow,
  D7_german_x10: SceneOpenWindow,
  META_geography: SceneOpenWindow,
  // Eras (E)
  E1_60s: SceneGramophone,
  E2_70s: SceneGramophone,
  E3_80s: SceneGramophone,
  E4_modern: SceneGramophone,
  E5_pre_1960: SceneGramophone,
  E6_decade_full: SceneGramophone,
  META_eras: SceneGramophone,
  // Genres (F) — пока через стопку разной высоты
  F1_diversity_5: (p) => <SceneStack {...p} count={3} />,
  F2_diversity_10: (p) => <SceneStack {...p} count={4} />,
  F3_jazz_x25: (p) => <SceneStack {...p} count={5} />,
  F4_electronic_x25: (p) => <SceneStack {...p} count={5} />,
  F5_classical_x15: (p) => <SceneStack {...p} count={4} />,
  F6_rock_x25: (p) => <SceneStack {...p} count={5} />,
  META_genres: (p) => <SceneStack {...p} count={6} />,
  // Invitations (INV) — пока через ухо/микрофон (распространение)
  INV_first: SceneMic,
  INV_three: SceneMic,
  INV_ten: SceneMic,
  INV_active_circle: SceneEar,
  INV_chain: SceneMic,
  INV_from_showcase: SceneOpenWindow,
  META_evangelist: SceneMic,
  // Discography (H) — пока через стопку и патефон
  H1_artist_x5: (p) => <SceneStack {...p} count={3} />,
  H2_artist_studio_full: SceneGramophone,
  H3_master_pressings_3: (p) => <SceneStack {...p} count={3} />,
  H4_master_pressings_5: SceneGramophone,
  H5_label_x20: (p) => <SceneStack {...p} count={5} />,
  META_depth: SceneGramophone,
};

export function getSceneRenderer(code: string): SceneRenderer | null {
  return REGISTRY[code] || null;
}

// ─── Tier color palette (для AchievementPin) ──────────────────────────────

export const TIER_AURA: Record<AchievementTierKey, { aura: string; auraSoft: string; ink: string }> = {
  simple: { aura: '#A5C8E1', auraSoft: '#D8E7F2', ink: '#0E121C' },
  notable: { aura: '#5B7DD8', auraSoft: '#A0B5EC', ink: '#0E121C' },
  rare: { aura: '#E89AC0', auraSoft: '#F2BFD7', ink: '#0E121C' },
  epic: { aura: '#1B237D', auraSoft: '#4651A0', ink: '#FFFFFF' },
  legend: { aura: '#0A0A1A', auraSoft: '#2E2E40', ink: '#FFFFFF' },
};
