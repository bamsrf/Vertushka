/**
 * Сторис «стоимость коллекции» — три вида для шеринга (1080×1920).
 *
 * Рисуем в базе 360×640 (1/3 сторис) и масштабируем: превью в шторке через
 * transform scale, экспорт — view-shot с width/height 1080×1920.
 *
 * Безопасная зона Instagram + TikTok в базовых единицах: 83 сверху, 113 снизу,
 * 53 справа под колонку кнопок. Заголовки и цифры — всегда в одну строку.
 *
 * Дизайн: docs — холст «Вертушка — сторис стоимости коллекции» (Claude Design).
 */
import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { Image } from 'expo-image';
import { LinearGradient } from 'expo-linear-gradient';
import Svg, { Defs, RadialGradient, Stop, Circle } from 'react-native-svg';
import { Icon } from '@/components/ui';

export const STORY_BASE_WIDTH = 360;
export const STORY_BASE_HEIGHT = 640;

export type CollectionStoryVariant = 'hifi' | 'ivory' | 'label';

export interface CollectionStoryRecord {
  title: string;
  artist: string;
  meta: string;
  priceRub: number;
  coverUrl?: string;
  isCollectible: boolean;
}

export interface CollectionStoryData {
  username: string;
  totalRub: number;
  totalUsd: number | null;
  deltaRub: number | null;
  recordsCount: number;
  oldestYear: number | null;
  favoriteDecade: string | null;
  top: CollectionStoryRecord[];
}

export const STORY_VARIANTS: { id: CollectionStoryVariant; label: string }[] = [
  { id: 'hifi', label: 'Hi-Fi' },
  { id: 'ivory', label: 'Ценник' },
  { id: 'label', label: 'Лейбл' },
];

const MASCOT = require('../../assets/images/mascot-kick.webp');
const LINK = 'vinyl-vertushka.ru/links';

const C = {
  navy: '#0B1438',
  deep: '#06080F',
  cobalt: '#2A4BD7',
  cobaltSoft: '#7B95F5',
  ember: '#FF7A4A',
  emberLight: '#E85A2A',
  ivory: '#F4EEE6',
  ivoryCard: '#FBF5EA',
  text: '#F4F5F7',
  textSecondary: '#B6BCCC',
  textMuted: '#8B91A3',
  elevated: 'rgba(34,37,47,0.72)',
  border: '#363A4A',
  gold: '#F4D27A',
  green: '#52C285',
  greenDark: '#2A7A4E',
  navyText: '#0B1438',
  ivoryMuted: '#6B7080',
  ivorySecondary: '#4D5263',
};

export function formatRubStory(value: number): string {
  return Math.round(value).toLocaleString('ru-RU');
}

interface StoryProps {
  variant: CollectionStoryVariant;
  data: CollectionStoryData;
}

/** Полноразмерная (360×640) сторис выбранного вида. */
export function CollectionValueStory({ variant, data }: StoryProps) {
  if (variant === 'ivory') return <IvoryStory data={data} />;
  if (variant === 'label') return <LabelStory data={data} />;
  return <HiFiStory data={data} />;
}

/** Превью: та же сторис, уменьшенная до заданной ширины. */
export function CollectionValueStoryPreview({ variant, data, width }: StoryProps & { width: number }) {
  const scale = width / STORY_BASE_WIDTH;
  return (
    <View style={{ width, height: STORY_BASE_HEIGHT * scale, overflow: 'hidden' }}>
      <View
        style={{
          width: STORY_BASE_WIDTH,
          height: STORY_BASE_HEIGHT,
          transform: [{ translateX: -(STORY_BASE_WIDTH * (1 - scale)) / 2 }, { translateY: -(STORY_BASE_HEIGHT * (1 - scale)) / 2 }, { scale }],
        }}
      >
        <CollectionValueStory variant={variant} data={data} />
      </View>
    </View>
  );
}

// ───────────────────────────── общие кусочки ─────────────────────────────

function LogoMark({ size, dark }: { size: number; dark: boolean }) {
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: size * 0.25 }}>
      <LinearGradient
        colors={['#3B4BF5', '#8B9CF7']}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={{ width: size, height: size, borderRadius: size / 2, alignItems: 'center', justifyContent: 'center' }}
      >
        <Icon name="disc" size={size * 0.62} color="#FAFBFF" />
      </LinearGradient>
      <Text
        numberOfLines={1}
        style={{ fontFamily: 'Inter_800ExtraBold', fontSize: size * 0.53, letterSpacing: -0.3, color: dark ? C.text : C.navyText }}
      >
        Вертушка
      </Text>
    </View>
  );
}

/**
 * Число в Rubik Mono One. Шрифт моноширинный: обычный пробел-разделитель
 * тысяч занимает ширину целой цифры, и «331 902» читается как два числа.
 * Рисуем группы отдельными Text с узким зазором.
 */
function MonoNumber({ value, size, color, prefix, suffix }: {
  value: number;
  size: number;
  color: string;
  prefix?: string;
  suffix?: React.ReactNode;
}) {
  const groups = formatRubStory(value).split(/\s/);
  return (
    <View style={{ flexDirection: 'row', alignItems: 'baseline' }}>
      {prefix ? <Text style={{ fontFamily: 'RubikMonoOne-Regular', fontSize: size, color, marginRight: size * 0.3 }}>{prefix}</Text> : null}
      {groups.map((g, i) => (
        <Text
          key={i}
          style={{ fontFamily: 'RubikMonoOne-Regular', fontSize: size, color, letterSpacing: -size * 0.02, includeFontPadding: false, marginRight: i < groups.length - 1 ? size * 0.22 : 0 }}
        >
          {g}
        </Text>
      ))}
      {suffix ? <View style={{ marginLeft: size * 0.22 }}>{suffix}</View> : null}
    </View>
  );
}

/** Мягкое свечение — view-shot не рендерит shadow/blur, поэтому SVG-радиал. */
function Glow({ size, color, opacity, style }: { size: number; color: string; opacity: number; style?: object }) {
  return (
    <Svg width={size} height={size} style={[{ position: 'absolute' }, style]} pointerEvents="none">
      <Defs>
        <RadialGradient id="glow" cx="50%" cy="50%" r="50%">
          <Stop offset="0" stopColor={color} stopOpacity={opacity} />
          <Stop offset="0.55" stopColor={color} stopOpacity={opacity * 0.35} />
          <Stop offset="1" stopColor={color} stopOpacity={0} />
        </RadialGradient>
      </Defs>
      <Circle cx={size / 2} cy={size / 2} r={size / 2} fill="url(#glow)" />
    </Svg>
  );
}

function Rub({ size, color }: { size: number; color: string }) {
  return <Text style={{ fontFamily: 'Inter_800ExtraBold', fontSize: size, color }}>₽</Text>;
}

function Cover({ uri, size, radius }: { uri?: string; size: number; radius: number }) {
  return (
    <View style={{ width: size, height: size, borderRadius: radius, overflow: 'hidden', backgroundColor: '#1A1D27' }}>
      {uri ? (
        <Image source={{ uri }} style={{ width: size, height: size }} contentFit="cover" cachePolicy="disk" />
      ) : (
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
          <Icon name="disc" size={size * 0.5} color={C.textMuted} />
        </View>
      )}
    </View>
  );
}

function GrooveDisc({ size, style, ringStep = 4 }: { size: number; style?: object; ringStep?: number }) {
  const rings: number[] = [];
  for (let d = size; d > size * 0.34; d -= ringStep) rings.push(d);
  return (
    <View style={[{ width: size, height: size, borderRadius: size / 2, backgroundColor: C.deep, alignItems: 'center', justifyContent: 'center' }, style]}>
      {rings.map((d) => (
        <View
          key={d}
          style={{ position: 'absolute', width: d, height: d, borderRadius: d / 2, borderWidth: 0.6, borderColor: 'rgba(255,255,255,0.16)' }}
        />
      ))}
    </View>
  );
}

// ───────────────────────────── 1. Hi-Fi (основной) ─────────────────────────────

function HiFiStory({ data }: { data: CollectionStoryData }) {
  const [first, ...rest] = data.top;
  return (
    <View style={[s.base, { backgroundColor: C.deep }]}>
      <LinearGradient colors={[C.navy, C.deep, C.deep]} locations={[0, 0.58, 1]} style={StyleSheet.absoluteFill} />
      <GrooveDisc size={393} style={{ position: 'absolute', right: -157, top: -173, opacity: 0.9 }} />
      <Glow size={240} color="#2A4BD7" opacity={0.55} style={{ left: -87, top: 367 }} />
      <Glow size={70} color={C.ember} opacity={0.5} style={{ right: 6, top: -11 }} />
      <View style={s.emberDot} />

      <View style={s.safeColumn}>
        {/* Шапка */}
        <View style={s.rowBetween}>
          <LogoMark size={21} dark />
          <View style={s.handlePill}>
            <Text numberOfLines={1} style={s.handleText}>@{data.username}</Text>
          </View>
        </View>

        {/* Сумма */}
        <View style={{ gap: 4 }}>
          <Text numberOfLines={1} style={s.overline}>МОЯ КОЛЛЕКЦИЯ СТОИТ</Text>
          <MonoNumber value={data.totalRub} size={35} color={C.ivory} suffix={<Rub size={23} color={C.ember} />} />
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
            {data.deltaRub != null && data.deltaRub !== 0 && (
              <View style={s.deltaPill}>
                <Icon name="arrow-up-right" size={7} color={C.green} />
                <Text numberOfLines={1} style={s.deltaText}>
                  {data.deltaRub > 0 ? '+' : '−'}{formatRubStory(Math.abs(data.deltaRub))} ₽ за месяц
                </Text>
              </View>
            )}
            {data.totalUsd != null && (
              <Text numberOfLines={1} style={s.usdText}>≈ ${formatRubStory(data.totalUsd)} на Discogs</Text>
            )}
          </View>
        </View>

        {/* Топ-3 */}
        <View style={{ gap: 5 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
            <Text numberOfLines={1} style={s.sectionLabel}>САМЫЕ ДОРОГИЕ</Text>
            <View style={{ flex: 1, height: 1, backgroundColor: 'rgba(255,255,255,0.08)' }} />
          </View>
          {first && (
            <View style={[s.card, s.cardFirst]}>
              <Text style={[s.rank, { color: C.ember, fontSize: 13 }]}>1</Text>
              <Cover uri={first.coverUrl} size={35} radius={4} />
              <View style={{ flex: 1, gap: 2 }}>
                <Text numberOfLines={1} style={s.cardTitle}>{first.title}</Text>
                <Text numberOfLines={1} style={s.cardArtist}>{first.meta}</Text>
                {first.isCollectible && (
                  <View style={s.goldPill}>
                    <Icon name="star" size={5} color={C.gold} />
                    <Text style={s.goldText}>КОЛЛЕКЦИОНКА</Text>
                  </View>
                )}
              </View>
              <MonoNumber value={first.priceRub} size={9} color={C.ivory} prefix="≈" suffix={<Rub size={9} color={C.ivory} />} />
            </View>
          )}
          {rest.map((r, i) => (
            <View key={`${r.title}-${i}`} style={s.card}>
              <Text style={[s.rank, { color: C.cobaltSoft }]}>{i + 2}</Text>
              <Cover uri={r.coverUrl} size={31} radius={3} />
              <View style={{ flex: 1, gap: 2 }}>
                <Text numberOfLines={1} style={s.cardTitle}>{r.title}</Text>
                <Text numberOfLines={1} style={s.cardArtist}>{r.meta}</Text>
              </View>
              <MonoNumber value={r.priceRub} size={9} color={C.ivory} prefix="≈" suffix={<Rub size={9} color={C.ivory} />} />
            </View>
          ))}
        </View>

        {/* Сводка */}
        <View style={{ flexDirection: 'row', gap: 5 }}>
          <Tile dark value={String(data.recordsCount)} label={pluralRecords(data.recordsCount)} />
          <Tile dark value={data.oldestYear ? String(data.oldestYear) : '—'} label="самая старая" />
          <Tile dark value={data.favoriteDecade ?? '—'} label="любимая декада" />
        </View>

        {/* Подвал */}
        <View style={[s.rowBetween, { alignItems: 'flex-end', minHeight: 83 }]}>
          <View style={{ gap: 7, paddingBottom: 5, flexShrink: 1 }}>
            <Text numberOfLines={1} adjustsFontSizeToFit style={s.cta}>А сколько стоит твоя полка?</Text>
            <LinearGradient colors={[C.cobalt, '#5C7AE8']} start={{ x: 0, y: 0 }} end={{ x: 1, y: 0 }} style={s.linkPill}>
              <Text numberOfLines={1} style={s.linkText}>{LINK}</Text>
              <Icon name="arrow-right" size={9} color="#FFFFFF" />
            </LinearGradient>
          </View>
          <Image source={MASCOT} style={{ width: 83, height: 83, marginRight: -7 }} contentFit="contain" />
        </View>
      </View>
    </View>
  );
}

function Tile({ value, label, dark }: { value: string; label: string; dark: boolean }) {
  return (
    <View style={[s.tile, dark ? s.tileDark : null]}>
      <Text numberOfLines={1} adjustsFontSizeToFit style={[s.tileValue, { color: dark ? C.text : C.navyText }]}>{value}</Text>
      <Text numberOfLines={1} adjustsFontSizeToFit style={[s.tileLabel, { color: dark ? C.textMuted : C.ivoryMuted }]}>{label}</Text>
    </View>
  );
}

function pluralRecords(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return 'пластинка';
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return 'пластинки';
  return 'пластинок';
}

// ───────────────────────────── 2. Ценник (ivory) ─────────────────────────────

function IvoryStory({ data }: { data: CollectionStoryData }) {
  return (
    <View style={[s.base, { backgroundColor: C.ivory }]}>
      <View style={s.tagShadow} />
      <View style={s.tag}>
        <View style={s.rowBetween}>
          <LogoMark size={19} dark={false} />
          <Text numberOfLines={1} style={s.ivoryHandle}>@{data.username}</Text>
        </View>

        <View style={{ gap: 3 }}>
          <Text numberOfLines={1} style={[s.overline, { color: C.emberLight }]}>ЦЕННИК КОЛЛЕКЦИИ</Text>
          <MonoNumber value={data.totalRub} size={32} color={C.navyText} suffix={<Rub size={21} color={C.emberLight} />} />
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5 }}>
            {data.deltaRub != null && data.deltaRub !== 0 && (
              <Text numberOfLines={1} style={[s.ivorySub, { fontFamily: 'Inter_700Bold', color: C.greenDark }]}>
                {data.deltaRub > 0 ? '+' : '−'}{formatRubStory(Math.abs(data.deltaRub))} ₽ за месяц
              </Text>
            )}
            {data.totalUsd != null && (
              <Text numberOfLines={1} style={s.ivorySub}>≈ ${formatRubStory(data.totalUsd)} на Discogs</Text>
            )}
          </View>
        </View>

        <View style={s.perf} />

        <View style={{ gap: 6 }}>
          <Text numberOfLines={1} style={[s.sectionLabel, { color: C.ivoryMuted }]}>САМЫЕ ДОРОГИЕ</Text>
          {data.top.map((r, i) => (
            <View key={`${r.title}-${i}`} style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 5 }}>
              <Text numberOfLines={1} style={[s.rank, { color: i === 0 ? C.emberLight : C.cobalt, width: 24, textAlign: 'left', fontSize: 9 }]}>0{i + 1}</Text>
              <View style={{ borderWidth: 0.7, borderColor: C.navyText, borderRadius: 3 }}>
                <Cover uri={r.coverUrl} size={24} radius={2} />
              </View>
              <View style={{ flexShrink: 1, gap: 1 }}>
                <Text numberOfLines={1} style={[s.cardTitle, { color: C.navyText, fontSize: 11 }]}>{r.title}</Text>
                <Text numberOfLines={1} style={[s.cardArtist, { color: C.ivoryMuted, fontSize: 7 }]}>{r.meta}</Text>
              </View>
              <View style={{ flex: 1, height: 1, marginBottom: 3, marginHorizontal: 2, backgroundColor: '#C4CAD6' }} />
              <MonoNumber value={r.priceRub} size={10} color={C.navyText} suffix={<Rub size={10} color={C.navyText} />} />
            </View>
          ))}
        </View>

        <View style={s.perf} />

        <View style={{ flexDirection: 'row', gap: 5 }}>
          <Tile dark={false} value={String(data.recordsCount)} label={pluralRecords(data.recordsCount)} />
          <Tile dark={false} value={data.oldestYear ? String(data.oldestYear) : '—'} label="самая старая" />
          <Tile dark={false} value={data.favoriteDecade ?? '—'} label="любимая декада" />
        </View>

        <View style={[s.rowBetween, { alignItems: 'flex-end' }]}>
          <View style={{ gap: 4 }}>
            <View style={s.stamp}>
              <Text style={s.stampText}>ОЦЕНЕНО</Text>
            </View>
            <Text numberOfLines={1} style={{ fontFamily: 'Inter_600SemiBold', fontSize: 8, color: C.navyText }}>{LINK}</Text>
          </View>
          <Image source={MASCOT} style={{ width: 80, height: 80, marginRight: -8, marginBottom: -5 }} contentFit="contain" />
        </View>
      </View>
    </View>
  );
}

// ───────────────────────────── 3. Лейбл пластинки ─────────────────────────────

function LabelStory({ data }: { data: CollectionStoryData }) {
  // Дырка — в геометрическом центре лейбла. Сумма стоит над ней, прирост и
  // сводка — под ней, так дырка читается как часть пластинки, а не как точка
  // после текста. Ссылка живёт внутри лейбла под сводкой, как строка на
  // этикетке (решение владельца). Сумма — 19pt: шесть моно-цифр плюс ₽ занимают ~135 из 190,
  // по ~25 воздуха с каждой стороны до края лейбла даже в самой узкой точке.
  const DISC = 280;
  const DISC_TOP = 92;
  const LABEL = 190;
  const HOLE = 10;
  const LIST_TOP = 384;
  return (
    <View style={[s.base, { backgroundColor: C.navy }]}>
      <LinearGradient colors={['#11225C', C.navy, C.deep]} locations={[0, 0.45, 1]} style={StyleSheet.absoluteFill} />
      <GrooveDisc size={DISC} ringStep={4} style={{ position: 'absolute', left: (STORY_BASE_WIDTH - DISC) / 2, top: DISC_TOP }} />

      <View style={[s.labelCircle, { width: LABEL, height: LABEL, borderRadius: LABEL / 2, left: (STORY_BASE_WIDTH - LABEL) / 2, top: DISC_TOP + (DISC - LABEL) / 2 }]}>
        <View style={{ position: 'absolute', left: 0, right: 0, top: 0, height: LABEL / 2, alignItems: 'center', justifyContent: 'flex-end', paddingBottom: HOLE / 2 + 6, gap: 3 }}>
          <LogoMark size={14} dark={false} />
          <Text numberOfLines={1} style={[s.overline, { fontSize: 7.5, letterSpacing: 1.1, color: C.emberLight }]}>@{data.username.toUpperCase()}</Text>
          <View style={{ marginTop: 2 }}>
            <MonoNumber value={data.totalRub} size={19} color={C.navyText} suffix={<Rub size={13} color={C.cobalt} />} />
          </View>
        </View>
        <View style={{ position: 'absolute', left: LABEL / 2 - HOLE / 2, top: LABEL / 2 - HOLE / 2, width: HOLE, height: HOLE, borderRadius: HOLE / 2, backgroundColor: C.navyText }} />
        <View style={{ position: 'absolute', left: 0, right: 0, top: LABEL / 2, height: LABEL / 2, alignItems: 'center', paddingTop: HOLE / 2 + 6, gap: 2 }}>
          {data.deltaRub != null && data.deltaRub !== 0 && (
            <Text numberOfLines={1} style={{ fontFamily: 'Inter_700Bold', fontSize: 8, color: C.greenDark }}>
              {data.deltaRub > 0 ? '+' : '−'}{formatRubStory(Math.abs(data.deltaRub))} ₽ за месяц
            </Text>
          )}
          <Text numberOfLines={1} style={{ fontFamily: 'Inter_500Medium', fontSize: 7, color: C.ivorySecondary }}>
            {data.recordsCount} {pluralRecords(data.recordsCount)}{data.oldestYear ? ` · с ${data.oldestYear}` : ''} · 33 ⅓ RPM
          </Text>
          <Text numberOfLines={1} style={{ marginTop: 3, fontFamily: 'Inter_600SemiBold', fontSize: 6.5, letterSpacing: 0.4, color: C.cobalt }}>{LINK}</Text>
        </View>
      </View>

      <Text numberOfLines={1} style={[s.overline, { position: 'absolute', left: 24, right: 24, top: 68, fontSize: 10, letterSpacing: 1.6 }]}>МОЯ КОЛЛЕКЦИЯ СТОИТ</Text>

      {/* Топ-3 на всю ширину: дизайн важнее правой TikTok-зоны (решение владельца). */}
      <View style={{ position: 'absolute', left: 24, right: 24, top: LIST_TOP, gap: 7 }}>
        <Text numberOfLines={1} style={[s.sectionLabel, { fontSize: 9.5, letterSpacing: 1.3, color: C.cobaltSoft, marginBottom: 2 }]}>САМЫЕ ДОРОГИЕ</Text>
        {data.top.map((r, i) => (
          <View key={`${r.title}-${i}`} style={[s.card, { paddingVertical: 6, paddingLeft: 7, paddingRight: 10, gap: 8 }]}>
            <Text numberOfLines={1} style={[s.rank, { color: i === 0 ? C.ember : C.cobaltSoft, fontSize: 14, width: 16 }]}>{i + 1}</Text>
            <Cover uri={r.coverUrl} size={32} radius={5} />
            <View style={{ flex: 1, gap: 2 }}>
              <Text numberOfLines={1} style={[s.cardTitle, { fontSize: 13 }]}>{r.title}</Text>
              <Text numberOfLines={1} style={[s.cardArtist, { fontSize: 9.5 }]}>{r.meta}</Text>
            </View>
            <MonoNumber value={r.priceRub} size={11} color={i === 0 ? C.ember : C.ivory} prefix="≈" suffix={<Rub size={11} color={i === 0 ? C.ember : C.ivory} />} />
          </View>
        ))}
      </View>
    </View>
  );
}

// ───────────────────────────── стили (база 360×640) ─────────────────────────────

const s = StyleSheet.create({
  base: { width: STORY_BASE_WIDTH, height: STORY_BASE_HEIGHT, overflow: 'hidden' },
  safeColumn: { position: 'absolute', left: 24, right: 53, top: 83, bottom: 113, justifyContent: 'space-between' },
  rowBetween: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  emberDot: {
    position: 'absolute', right: 33, top: 16, width: 15, height: 15, borderRadius: 8, backgroundColor: C.ember,
  },
  handlePill: {
    paddingHorizontal: 7, paddingVertical: 3, borderRadius: 999, borderWidth: 0.7,
    borderColor: 'rgba(255,255,255,0.14)', backgroundColor: 'rgba(19,21,28,0.55)',
  },
  handleText: { fontFamily: 'Inter_600SemiBold', fontSize: 8, color: C.textSecondary },
  overline: { fontFamily: 'Inter_700Bold', fontSize: 8, letterSpacing: 1.3, color: C.cobaltSoft },
  deltaPill: {
    flexDirection: 'row', alignItems: 'center', gap: 3, paddingHorizontal: 5, paddingVertical: 2, borderRadius: 999,
    backgroundColor: 'rgba(20,46,32,0.9)', borderWidth: 0.5, borderColor: 'rgba(82,194,133,0.5)',
  },
  deltaText: { fontFamily: 'Inter_700Bold', fontSize: 8, color: C.green },
  usdText: { fontFamily: 'Inter_500Medium', fontSize: 8.5, color: C.textSecondary },
  sectionLabel: { fontFamily: 'Inter_700Bold', fontSize: 7.5, letterSpacing: 1, color: C.textMuted },
  card: {
    flexDirection: 'row', alignItems: 'center', gap: 5, paddingVertical: 5, paddingLeft: 5, paddingRight: 7,
    borderRadius: 9, backgroundColor: C.elevated, borderWidth: 0.7, borderColor: C.border,
  },
  cardFirst: { backgroundColor: 'rgba(58,31,18,0.85)', borderColor: 'rgba(255,122,74,0.35)' },
  rank: { fontFamily: 'RubikMonoOne-Regular', fontSize: 11, width: 13, textAlign: 'center' },
  cardTitle: { fontFamily: 'Inter_700Bold', fontSize: 10, color: C.text },
  cardArtist: { fontFamily: 'Inter_500Medium', fontSize: 8, color: C.textSecondary },
  goldPill: {
    flexDirection: 'row', alignItems: 'center', gap: 2, alignSelf: 'flex-start', paddingHorizontal: 4, paddingVertical: 1.5,
    borderRadius: 999, backgroundColor: 'rgba(184,134,11,0.22)', borderWidth: 0.5, borderColor: 'rgba(244,210,122,0.55)',
  },
  goldText: { fontFamily: 'Inter_700Bold', fontSize: 6, letterSpacing: 0.4, color: C.gold },
  tile: { flex: 1, gap: 2, paddingVertical: 7, paddingHorizontal: 6, borderRadius: 7 },
  tileDark: { backgroundColor: C.elevated, borderWidth: 0.7, borderColor: C.border },
  tileValue: { fontFamily: 'RubikMonoOne-Regular', fontSize: 13, includeFontPadding: false },
  tileLabel: { fontFamily: 'Inter_500Medium', fontSize: 7 },
  cta: { fontFamily: 'Inter_800ExtraBold', fontSize: 11, letterSpacing: -0.3, color: C.text },
  linkPill: { flexDirection: 'row', alignItems: 'center', alignSelf: 'flex-start', gap: 4, paddingHorizontal: 9, paddingVertical: 5, borderRadius: 999 },
  linkText: { fontFamily: 'Inter_600SemiBold', fontSize: 8.5, color: '#FFFFFF' },

  // ivory
  tagShadow: { position: 'absolute', left: 29, right: 19, top: 88, bottom: 108, borderRadius: 12, backgroundColor: C.navyText },
  tag: {
    position: 'absolute', left: 24, right: 24, top: 83, bottom: 113, borderRadius: 12, padding: 16, paddingBottom: 13,
    backgroundColor: C.ivoryCard, borderWidth: 1, borderColor: C.navyText, justifyContent: 'space-between',
  },
  ivoryHandle: { fontFamily: 'Inter_600SemiBold', fontSize: 7.5, color: C.ivorySecondary },
  ivorySub: { fontFamily: 'Inter_500Medium', fontSize: 8.5, color: C.ivorySecondary },
  perf: { height: 0, borderTopWidth: 1, borderStyle: 'dashed', borderColor: '#C4CAD6' },
  stamp: {
    alignSelf: 'flex-start', paddingHorizontal: 7, paddingVertical: 3, borderWidth: 1, borderColor: C.emberLight, borderRadius: 4,
    transform: [{ rotate: '-4deg' }],
  },
  stampText: { fontFamily: 'Inter_800ExtraBold', fontSize: 8, letterSpacing: 1, color: C.emberLight },

  // label
  labelCircle: {
    position: 'absolute', backgroundColor: C.ivory,
  },
});
