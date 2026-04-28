import React, { useEffect } from 'react';
import { View, StyleSheet } from 'react-native';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withRepeat,
  withTiming,
  Easing,
} from 'react-native-reanimated';
import Svg, {
  Circle,
  Ellipse,
  Defs,
  RadialGradient,
  Stop,
  G,
  Text as SvgText,
  Path,
  Polygon,
  ClipPath,
  Filter,
  FeGaussianBlur,
} from 'react-native-svg';
import { VinylColorConfig } from '../lib/vinylColor';

interface VinylSpinnerProps {
  colorConfig: VinylColorConfig;
  size?: number;
  labelName?: string;
}

// ── Цветовые утилиты (точно как в дизайне) ──────────────────────

function hexToRgb(hex: string): { r: number; g: number; b: number } {
  const n = parseInt(hex.replace('#', ''), 16);
  return { r: (n >> 16) & 0xff, g: (n >> 8) & 0xff, b: n & 0xff };
}

function rgbToHex(r: number, g: number, b: number): string {
  return (
    '#' +
    [r, g, b]
      .map((v) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0'))
      .join('')
  );
}

function darken(hex: string, amount: number): string {
  const { r, g, b } = hexToRgb(hex);
  return rgbToHex(r * (1 - amount), g * (1 - amount), b * (1 - amount));
}

function saturate(hex: string, sa = 0.1, br = 0.08): string {
  let { r, g, b } = hexToRgb(hex);
  let rn = r / 255, gn = g / 255, bn = b / 255;
  const max = Math.max(rn, gn, bn), min = Math.min(rn, gn, bn);
  let h = 0, s = 0;
  const l = (max + min) / 2;

  if (max !== min) {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    if (max === rn) h = (gn - bn) / d + (gn < bn ? 6 : 0);
    else if (max === gn) h = (bn - rn) / d + 2;
    else h = (rn - gn) / d + 4;
    h /= 6;
  }

  const sNew = Math.min(1, s + sa);
  const lNew = Math.min(1, l + br);

  function h2r(p: number, q: number, t: number): number {
    if (t < 0) t += 1;
    if (t > 1) t -= 1;
    if (t < 1 / 6) return p + (q - p) * 6 * t;
    if (t < 1 / 2) return q;
    if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
    return p;
  }

  let nr: number, ng: number, nb: number;
  if (sNew === 0) {
    nr = ng = nb = lNew;
  } else {
    const q = lNew < 0.5 ? lNew * (1 + sNew) : lNew + sNew - lNew * sNew;
    const p = 2 * lNew - q;
    nr = h2r(p, q, h + 1 / 3);
    ng = h2r(p, q, h);
    nb = h2r(p, q, h - 1 / 3);
  }
  return rgbToHex(nr * 255, ng * 255, nb * 255);
}

// ── Marble и Splatter оверлеи ────────────────────────────────────

function MarbleOverlay({ color, scale }: { color: string; scale: number }) {
  return (
    <G>
      <Path
        d={`M${-110 * scale},${-30 * scale} C${-60 * scale},${-80 * scale} ${20 * scale},${-10 * scale} ${60 * scale},${40 * scale} C${90 * scale},${75 * scale} ${110 * scale},${30 * scale} ${110 * scale},${-10 * scale}`}
        stroke={color} strokeWidth={14 * scale} strokeOpacity={0.45} fill="none" strokeLinecap="round"
      />
      <Path
        d={`M${-80 * scale},${60 * scale} C${-30 * scale},${20 * scale} ${40 * scale},${80 * scale} ${90 * scale},${30 * scale}`}
        stroke={color} strokeWidth={7 * scale} strokeOpacity={0.35} fill="none" strokeLinecap="round"
      />
      <Path
        d={`M${-50 * scale},${-70 * scale} C${10 * scale},${-40 * scale} ${50 * scale},${10 * scale} ${20 * scale},${70 * scale}`}
        stroke={color} strokeWidth={5 * scale} strokeOpacity={0.3} fill="none" strokeLinecap="round"
      />
    </G>
  );
}

function SplatterOverlay({ color, scale }: { color: string; scale: number }) {
  const s = scale;
  const blobs = [
    `${-55*s},${-62*s} ${-45*s},${-78*s} ${-30*s},${-65*s} ${-35*s},${-50*s}`,
    `${40*s},${-70*s} ${55*s},${-60*s} ${48*s},${-42*s} ${35*s},${-50*s}`,
    `${65*s},${20*s} ${80*s},${10*s} ${85*s},${30*s} ${70*s},${38*s}`,
    `${-75*s},${35*s} ${-60*s},${25*s} ${-55*s},${45*s} ${-70*s},${52*s}`,
    `${20*s},${65*s} ${35*s},${55*s} ${40*s},${72*s} ${25*s},${80*s}`,
    `${-30*s},${75*s} ${-15*s},${68*s} ${-10*s},${82*s} ${-28*s},${88*s}`,
    `${55*s},${-25*s} ${68*s},${-35*s} ${72*s},${-15*s} ${60*s},${-8*s}`,
    `${-65*s},${-10*s} ${-50*s},${-20*s} ${-45*s},${-5*s} ${-58*s},${5*s}`,
    `${10*s},${-85*s} ${22*s},${-95*s} ${30*s},${-80*s} ${18*s},${-70*s}`,
    `${-20*s},${-50*s} ${-8*s},${-58*s} ${-5*s},${-44*s} ${-17*s},${-38*s}`,
  ];
  const drops: Array<[number, number, number]> = [
    [48,-50,3.5],[-40,-40,2],[70,-45,2],[-60,55,2],[30,-55,2],
    [-25,70,2],[80,40,3.5],[-80,-30,2],[55,60,2],[-45,-75,2],
    [15,82,2],[-70,10,3.5],[42,78,2],[-55,30,2],[68,-10,2],
    [25,-75,2],[-35,58,2],[60,35,3.5],[-75,-55,2],[38,48,2],
    [-20,-85,2],[75,-30,2],[-48,80,2],[18,-60,2],
  ].map(([dx, dy, r]) => [dx * s, dy * s, r * s]);

  return (
    <G>
      {blobs.map((pts, i) => (
        <Polygon key={`b${i}`} points={pts} fill={color} fillOpacity={i % 3 === 0 ? 1 : 0.7} />
      ))}
      {drops.map(([cx, cy, r], i) => (
        <Circle key={`d${i}`} cx={cx} cy={cy} r={r} fill={color} fillOpacity={0.8} />
      ))}
    </G>
  );
}

// ── VinylSpinner ─────────────────────────────────────────────────

export function VinylSpinner({ colorConfig, size = 220, labelName }: VinylSpinnerProps) {
  const rotation = useSharedValue(0);
  const { primaryColor, secondaryColor, type, opacity } = colorConfig;

  const isTranslucent = type === 'translucent';
  const scale = size / 220;
  const cx = size / 2;
  const cy = size / 2;

  // Цвета по дизайну
  const colorBright = saturate(primaryColor, 0.12, 0.1);
  const colorMid = primaryColor;
  const colorDark = darken(primaryColor, 0.28);
  const colorEdge = darken(primaryColor, 0.48);

  // CIC inner colors
  const innerBright = secondaryColor ? saturate(secondaryColor, 0.12, 0.1) : undefined;
  const innerDark = secondaryColor ? darken(secondaryColor, 0.32) : undefined;

  const edgeR = 110 * scale;
  const innerColorR = 78 * scale;
  const labelR = 38 * scale;
  const labelInnerR = 5 * scale;

  // 26 бороздок (как в дизайне)
  const grooveCount = 26;
  const grooves = Array.from(
    { length: grooveCount },
    (_, i) => 44 * scale + (i / (grooveCount - 1)) * 60 * scale,
  );

  const grooveSW = isTranslucent ? 0.6 : 0.45;
  const grooveOp = isTranslucent ? 0.34 : 0.22;
  const specStr = isTranslucent ? 0.45 : 0.32;

  const discFillOpacity = isTranslucent ? opacity : 1;

  const uid = primaryColor.replace('#', '');

  useEffect(() => {
    rotation.value = withRepeat(
      withTiming(360, { duration: 1800, easing: Easing.linear }),
      -1,
    );
  }, []);

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [{ rotate: `${rotation.value}deg` }],
  }));

  const podSize = size + 40;

  return (
    <View
      style={[
        styles.pod,
        {
          width: podSize,
          height: podSize,
          borderRadius: podSize / 2,
          shadowColor: primaryColor,
        },
      ]}
    >
      <Animated.View style={[{ width: size, height: size }, animatedStyle]}>
        {/* Основной SVG — диск + бороздки + лейбл */}
        <Svg
          width={size}
          height={size}
          viewBox={`0 0 ${size} ${size}`}
          style={{ position: 'absolute' }}
        >
          <Defs>
            {/* Основной радиальный градиент: 4 стопа */}
            <RadialGradient id={`bg-${uid}`} cx="50%" cy="50%" r="50%">
              <Stop offset="0%" stopColor={colorBright} />
              <Stop offset="40%" stopColor={colorMid} />
              <Stop offset="78%" stopColor={colorDark} />
              <Stop offset="100%" stopColor={colorEdge} />
            </RadialGradient>

            {/* CIC: градиент внутреннего круга */}
            {type === 'cic' && innerBright && secondaryColor && innerDark && (
              <RadialGradient id={`ig-${uid}`} cx="50%" cy="50%" r="50%">
                <Stop offset="0%" stopColor={innerBright} />
                <Stop offset="60%" stopColor={secondaryColor} />
                <Stop offset="100%" stopColor={innerDark} />
              </RadialGradient>
            )}

            {/* Blur для тени лейбла и CIC-кольца */}
            <Filter id={`bl-${uid}`} x="-20%" y="-20%" width="140%" height="140%">
              <FeGaussianBlur stdDeviation={2 * scale} />
            </Filter>

            {/* Клип по диску */}
            <ClipPath id={`cl-${uid}`}>
              <Circle cx={cx} cy={cy} r={edgeR} />
            </ClipPath>
          </Defs>

          {/* Основной диск */}
          <Circle
            cx={cx} cy={cy} r={edgeR}
            fill={`url(#bg-${uid})`}
            fillOpacity={discFillOpacity}
          />

          {/* CIC — внутренний круг другого цвета */}
          {type === 'cic' && secondaryColor && (
            <G clipPath={`url(#cl-${uid})`}>
              <Circle
                cx={cx} cy={cy} r={innerColorR + 2 * scale}
                fill={secondaryColor} opacity={0.4}
                filter={`url(#bl-${uid})`}
              />
              <Circle
                cx={cx} cy={cy} r={innerColorR}
                fill={`url(#ig-${uid})`}
              />
            </G>
          )}

          {/* Marble overlay */}
          {type === 'marble' && secondaryColor && (
            <G clipPath={`url(#cl-${uid})`}>
              <MarbleOverlay color={secondaryColor} scale={scale} />
            </G>
          )}

          {/* Splatter overlay */}
          {type === 'splatter' && secondaryColor && (
            <G clipPath={`url(#cl-${uid})`}>
              <SplatterOverlay color={secondaryColor} scale={scale} />
            </G>
          )}

          {/* Бороздки — 26 колец */}
          <G opacity={grooveOp} clipPath={`url(#cl-${uid})`}>
            {grooves.map((gr, i) => (
              <Circle
                key={i} cx={cx} cy={cy} r={gr}
                fill="none"
                stroke={darken(primaryColor, 0.6)}
                strokeWidth={grooveSW}
              />
            ))}
          </G>

          {/* Двойная тень у края */}
          <Circle cx={cx} cy={cy} r={edgeR - 1} fill="none"
            stroke="rgba(0,0,0,0.30)" strokeWidth={3 * scale} />
          <Circle cx={cx} cy={cy} r={edgeR - 3.5 * scale} fill="none"
            stroke="rgba(0,0,0,0.12)" strokeWidth={2 * scale} />

          {/* Тень лейбла (блюр) */}
          <Circle cx={cx} cy={cy} r={labelR + 0.5 * scale}
            fill="rgba(0,0,0,0.45)" filter={`url(#bl-${uid})`} />

          {/* Центральный лейбл */}
          <Circle cx={cx} cy={cy} r={labelR} fill="#1C1D3A" />

          {/* «Вертушка» — Rubik Mono One */}
          <SvgText
            x={cx} y={cy - 8 * scale}
            textAnchor="middle"
            dominantBaseline="middle"
            fontSize={8 * scale}
            fill="#B8BCDB"
            fontFamily="RubikMonoOne-Regular"
            fontWeight="400"
            letterSpacing={1 * scale}
          >
            Вертушка
          </SvgText>

          {/* 33⅓ RPM — Inter */}
          <SvgText
            x={cx} y={cy + 14 * scale}
            textAnchor="middle"
            dominantBaseline="middle"
            fontSize={5 * scale}
            fill="#5C6080"
            fontFamily="Inter_500Medium"
            fontWeight="500"
            letterSpacing={1.5 * scale}
          >
            {'33⅓ RPM'}
          </SvgText>

          {/* Отверстие */}
          <Circle cx={cx} cy={cy} r={labelInnerR} fill="#000" />
        </Svg>

        {/* Оверлей бликов — отдельный SVG поверх (не вращается вместе с дыркой) */}
        <Svg
          width={size}
          height={size}
          viewBox={`0 0 ${size} ${size}`}
          style={{ position: 'absolute' }}
          pointerEvents="none"
        >
          <Defs>
            <RadialGradient id={`sp1-${uid}`} cx="50%" cy="50%" r="50%">
              <Stop offset="0%" stopColor="#fff" stopOpacity={specStr} />
              <Stop offset="55%" stopColor="#fff" stopOpacity={specStr * 0.45} />
              <Stop offset="100%" stopColor="#fff" stopOpacity={0} />
            </RadialGradient>
            <RadialGradient id={`sp2-${uid}`} cx="50%" cy="50%" r="50%">
              <Stop offset="0%" stopColor="#fff" stopOpacity={specStr * 0.55} />
              <Stop offset="100%" stopColor="#fff" stopOpacity={0} />
            </RadialGradient>
            <ClipPath id={`spc-${uid}`}>
              <Circle cx={cx} cy={cy} r={edgeR} />
            </ClipPath>
          </Defs>
          <G clipPath={`url(#spc-${uid})`}>
            {/* Главный блик — верх-лево */}
            <Ellipse
              cx={cx - (size / 2) * 0.18}
              cy={cy - (size / 2) * 0.32}
              rx={75 * scale}
              ry={45 * scale}
              fill={`url(#sp1-${uid})`}
              rotation={-35}
              origin={`${cx - (size / 2) * 0.18},${cy - (size / 2) * 0.32}`}
            />
            {/* Второй блик — низ-право */}
            <Ellipse
              cx={cx + (size / 2) * 0.22}
              cy={cy + (size / 2) * 0.28}
              rx={55 * scale}
              ry={32 * scale}
              fill={`url(#sp2-${uid})`}
              rotation={-35}
              origin={`${cx + (size / 2) * 0.22},${cy + (size / 2) * 0.28}`}
            />
          </G>
        </Svg>
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  pod: {
    backgroundColor: '#12133A',
    alignItems: 'center',
    justifyContent: 'center',
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.35,
    shadowRadius: 24,
    elevation: 16,
  },
});
