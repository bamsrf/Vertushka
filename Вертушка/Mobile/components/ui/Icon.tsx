/**
 * <Icon> — единый wrapper для всех иконок приложения (Stamper Outline v3).
 *
 * ▶ Концепция (закреплена, не меняем):
 *   2 уровня, без серединных вариаций:
 *     • HERO (3 brand-сущности): heart=fill, disc=duotone, gift=duotone.
 *     • UI (всё остальное): weight=regular (тонкий outline), БЕЗ halo.
 *   Active state выражаем сменой цвета (brand/accent), а не утолщением.
 *   В исключительных случаях (tab bar) можно явно передать weight="fill".
 *
 * ▶ Почему так:
 *   До v3 был внешний halo wrapper (масштабированная копия + iOS shadowBlur)
 *   и встроенный <FeGaussianBlur> у V2-иконок. Результат — серое пятно
 *   вокруг каждого креста/плюса/чека, и filled-силуэты везде по дефолту.
 *   v3 убирает оба halo-слоя и переводит дефолт на `regular`.
 *
 * ▶ ВАЖНО — НЕ ИМПОРТИРУЙ Ionicons или phosphor-react-native НАПРЯМУЮ.
 *   Только через этот компонент.
 *
 * Пример:
 *   <Icon name="bell" size="md" color="brand" />          // outline, без halo
 *   <Icon name="heart" size="md" color="accent" />        // hero filled
 *   <Icon name="disc" size="lg" color="brand" />          // hero duotone
 */

import React from 'react';
import { useColorScheme, View, type StyleProp, type ViewStyle } from 'react-native';

// Phosphor — основной icon set (используем `fill` weight + внешний halo
// wrapper). Для двух имён (`x`, `dots-three-vertical` и их пары) пользователь
// предпочитает кастомные V2-шейпы из b2v2-icons.jsx — оставляем их.
import {
  PlusIcon,
  PlusCircleIcon,
  WarningCircleIcon,
  ArrowLeftIcon,
  ArrowRightIcon,
  ArrowUpRightIcon,
  BellIcon,
  BellSlashIcon,
  BuildingsIcon,
  CalendarIcon,
  CameraIcon,
  CheckIcon,
  CheckCircleIcon,
  CaretLeftIcon,
  CaretRightIcon,
  CaretUpIcon,
  CaretDownIcon,
  ArrowUpIcon,
  ArrowDownIcon,
  EyeIcon,
  EyeSlashIcon,
  CopyIcon,
  UsersIcon,
  UserPlusIcon,
  UserMinusIcon,
  MusicNotesIcon,
  EnvelopeOpenIcon,
  ChatCircleIcon,
  CloudSlashIcon,
  CurrencyCircleDollarIcon,
  CurrencyRubIcon,
  DownloadSimpleIcon,
  FolderIcon,
  GiftIcon,
  GlobeIcon,
  SquaresFourIcon,
  HeartIcon,
  QuestionIcon,
  KeyholeIcon,
  ListIcon,
  MagnifyingGlassIcon,
  MapPinIcon,
  LockOpenIcon,
  GoogleLogoIcon,
  EnvelopeIcon,
  MapTrifoldIcon,
  ScanIcon,
  SlidersIcon,
  PencilIcon,
  UserIcon,
  TagIcon,
  ArrowClockwiseIcon,
  ShareNetworkIcon,
  SparkleIcon,
  StarIcon,
  ArrowsDownUpIcon,
  ClockIcon,
  TrashIcon,
  PaperclipIcon,
  ImageIcon,
  type Icon as PhosphorIcon,
} from 'phosphor-react-native';

// V2 custom-шейпы — точечно для двух иконок, которые юзер
// согласовал отдельно: cross + vertical-dots.
import { XV2, XCircleV2, DotsThreeV2, DotsThreeVerticalV2 } from '../icons/v2';

import { DiscGrooves, TrophyDisc, VinylLabel } from '../icons/hero';

import { T } from '../../constants/theme';

// ───────────────────────────────────────────────────────────────────────────
// Public API types
// ───────────────────────────────────────────────────────────────────────────

export type IconColor =
  | 'default'
  | 'secondary'
  | 'primary'
  | 'brand'
  | 'accent'
  | 'success'
  | 'error'
  | 'warning'
  | 'onBrand'
  | 'disabled';

export type IconSize = 'xs' | 'sm' | 'md' | 'lg' | 'xl';

export type IconVariant = 'default' | 'active' | 'disabled';

// Phosphor weights, которые мы реально используем. `regular` — outline (B2 default),
// `duotone` — два слоя с разной opacity (визуально мягче, дополнительный «характер»),
// `fill` — solid silhouette (для active state).
export type IconWeight = 'regular' | 'duotone' | 'fill';

export interface IconProps {
  /**
   * Имя иконки. Принимает либо новое registry-имя (`'plus'`, `'magnifying-glass'`,
   * `'disc'`, …), либо легаси Ionicon-имя (`'add'`, `'search'`, `'disc-outline'`, …)
   * через alias-таблицу `IONICON_ALIASES` ниже. Это упрощает миграцию: можно
   * просто заменить `<Ionicons>` → `<Icon>` без правки `name`.
   *
   * Также принимает любую `string` — для совместимости с динамическими
   * `name={cond ? 'a' : 'b'}` патернами и legacy `keyof typeof Ionicons.glyphMap`
   * сигнатурами. Если имя не известно — fallback на `'plus'`.
   */
  name: IconName | IoniconAlias | (string & {});
  size?: IconSize | number;
  /**
   * Цвет. Принимает либо семантическую роль (`'brand'`, `'error'`, …), либо
   * raw-строку (hex / rgb). Hex-fallback нужен для постепенной миграции с
   * `Colors.royalBlue` → `color="brand"`. Финальная цель — все вызовы на роли.
   */
  color?: IconColor | string;
  variant?: IconVariant;
  /**
   * Прямой override visual weight. Если не задан — резолвится из variant
   * (default → duotone, active → fill).
   */
  weight?: IconWeight;
  hitSlop?: number;
  testID?: string;
  style?: StyleProp<ViewStyle>;
}

// ───────────────────────────────────────────────────────────────────────────
// Registry — kebab-case → Phosphor / hero component
// ───────────────────────────────────────────────────────────────────────────

// IconComponent — общий interface Phosphor + hero/custom иконок. Custom set
// из `components/icons/custom` принимает совместимые props (size/color/weight),
// поэтому достаточно широкого ComponentType.
type IconComponent = PhosphorIcon | React.ComponentType<any>;

const REGISTRY = {
  // Action
  'plus':                PlusIcon,
  'plus-circle':         PlusCircleIcon,
  'check':               CheckIcon,
  'check-circle':        CheckCircleIcon,
  'x':                   XV2,                // ★ V2 — согласован пользователем
  'x-circle':            XCircleV2,          // ★ V2
  'pencil':              PencilIcon,
  'trash':               TrashIcon,
  'camera':              CameraIcon,
  'paperclip':           PaperclipIcon,
  'image':               ImageIcon,
  'envelope':            EnvelopeIcon,
  'download':            DownloadSimpleIcon,
  'share':               ShareNetworkIcon,
  'arrow-clockwise':     ArrowClockwiseIcon,
  'heart':               HeartIcon,

  // Navigation
  'arrow-left':          ArrowLeftIcon,
  'arrow-right':         ArrowRightIcon,
  'caret-left':          CaretLeftIcon,
  'caret-right':         CaretRightIcon,
  'caret-up':            CaretUpIcon,
  'caret-down':          CaretDownIcon,
  'arrow-up':            ArrowUpIcon,
  'arrow-up-right':      ArrowUpRightIcon, // Hot Stock pill hero-вариант, exit-buttons
  'arrow-down':          ArrowDownIcon,
  'eye':                 EyeIcon,
  'eye-slash':           EyeSlashIcon,
  'copy':                CopyIcon,
  'users':               UsersIcon,
  'user-plus':           UserPlusIcon,
  'user-minus':          UserMinusIcon,
  'music-notes':         MusicNotesIcon,
  'envelope-open':       EnvelopeOpenIcon,
  'chat-circle':         ChatCircleIcon,
  'magnifying-glass':    MagnifyingGlassIcon,
  'user':                UserIcon,

  // State
  'warning-circle':      WarningCircleIcon,

  // System
  'bell':                BellIcon,
  'bell-slash':          BellSlashIcon,
  'cloud-slash':         CloudSlashIcon,
  'lock-open':           LockOpenIcon,
  'question':            QuestionIcon,
  'keyhole':             KeyholeIcon,

  // UI Control
  'dots-three':          DotsThreeV2,         // ★ V2
  'dots-three-vertical': DotsThreeVerticalV2, // ★ V2
  'squares-four':        SquaresFourIcon,
  'list':                ListIcon,
  'sliders':             SlidersIcon,
  'arrows-down-up':      ArrowsDownUpIcon,

  // Domain
  'calendar':            CalendarIcon,
  'clock':               ClockIcon,
  'globe':               GlobeIcon,
  'buildings':           BuildingsIcon,
  'folder':              FolderIcon,
  'tag':                 TagIcon,
  'map-pin':             MapPinIcon,
  'map-trifold':         MapTrifoldIcon,
  'currency-circle-dollar': CurrencyCircleDollarIcon,
  // Стоимость коллекции считается и показывается в рублях, поэтому знак валюты
  // в интерфейсе — рубль. Долларовый глиф оставлен на случай, если появятся
  // места, где валюта действительно не рублёвая.
  'currency-rub':        CurrencyRubIcon,
  'star':                StarIcon,

  // Decorative
  'sparkle':             SparkleIcon,

  // Brand
  'google-logo':         GoogleLogoIcon,

  // HERO set
  'disc':                DiscGrooves,    // ★ HERO — Phosphor VinylRecord (force duotone)
  'gift':                GiftIcon,       // ВАЖНО: НЕ использовать в вишлист-сценариях.
  'trophy':              TrophyDisc,     // ★ HERO
  'scan':                ScanIcon,
  'vinyl-label':         VinylLabel,     // ★ HERO центр VinylSpinner
  // 'rarity-*' (crown / diamond / flame) удалены по решению пользователя — rarity
  // выражается аурой через RarityAura.tsx, иконных маркеров не нужно.
} satisfies Record<string, IconComponent>;

// HERO set — 3 brand-сущности, для которых дефолт = filled/duotone (узнаваемый
// силуэт). Всё остальное в registry едет на regular (тонкий outline).
const HERO_FILL_NAMES = new Set<string>(['heart']);
const HERO_DUOTONE_NAMES = new Set<string>(['disc', 'gift', 'vinyl-label']);

export type IconName = keyof typeof REGISTRY;

// ───────────────────────────────────────────────────────────────────────────
// Ionicon legacy aliases — миграция Phase 3.
// Каждое старое имя из @expo/vector-icons маппится на текущее registry-имя.
// Источник — B2 v1 migration table (52 имени из инвентаря Mobile/).
// Дубликаты пар (`disc` + `disc-outline`, `gift` + `gift-outline` etc.)
// унифицированы в одну hero-иконку.
// ───────────────────────────────────────────────────────────────────────────

const IONICON_ALIASES = {
  // Action
  'add':                    'plus',
  'add-circle-outline':     'plus-circle',
  'checkmark':              'check',
  'checkmark-circle':       'check-circle',
  'checkmark-circle-outline': 'check-circle',
  'close':                  'x',
  'close-circle':           'x-circle',
  'close-circle-outline':   'x-circle',
  'pencil':                 'pencil',
  'trash-outline':          'trash',
  'camera-outline':         'camera',
  'mail-outline':           'envelope',
  'download-outline':       'download',
  'share-outline':          'share',
  'refresh':                'arrow-clockwise',
  'refresh-outline':        'arrow-clockwise',
  'heart-outline':          'heart',
  'checkmark-outline':      'check',
  'copy-outline':           'copy',
  'eye-outline':            'eye',
  'eye-off-outline':        'eye-slash',
  'mail-open-outline':      'envelope-open',
  'musical-notes-outline':  'music-notes',
  'chatbubble-outline':     'chat-circle',
  'chatbubbles-outline':    'chat-circle',

  // Navigation
  'arrow-back':             'arrow-left',
  'arrow-forward-outline':  'arrow-right',
  'arrow-forward-circle':   'arrow-right',
  'chevron-back':           'caret-left',
  'chevron-forward':        'caret-right',
  'chevron-up':             'caret-up',
  'chevron-down':           'caret-down',
  'arrow-up':               'arrow-up',
  'arrow-down':             'arrow-down',
  'search':                 'magnifying-glass',
  'search-outline':         'magnifying-glass',
  'scan-outline':           'scan',
  'person':                 'user',
  'person-outline':         'user',
  'people-outline':         'users',
  'person-add-outline':     'user-plus',
  'person-remove-outline':  'user-minus',

  // State
  'alert-circle-outline':   'warning-circle',

  // System
  'notifications-outline':  'bell',
  'notifications-off-outline': 'bell-slash',
  'cloud-offline-outline':  'cloud-slash',
  'lock-open-outline':      'lock-open',
  'help-circle-outline':    'question',
  'keypad-outline':         'keyhole',

  // UI Control
  'ellipsis-horizontal':    'dots-three',
  'ellipsis-vertical':      'dots-three-vertical',
  'grid-outline':           'squares-four',
  'list-outline':           'list',
  'options-outline':        'sliders',
  'swap-vertical-outline':  'arrows-down-up',

  // Domain
  'calendar-outline':       'calendar',
  'time-outline':           'clock',
  'globe-outline':          'globe',
  'business-outline':       'buildings',
  'folder-outline':         'folder',
  'pricetag-outline':       'tag',
  'location-outline':       'map-pin',
  'map-outline':            'map-trifold',
  'cash-outline':           'currency-circle-dollar',
  'star-outline':           'star',

  // Decorative
  'sparkles':               'sparkle',

  // Brand
  'logo-google':            'google-logo',

  // Hero (унификация дубликатов)
  'disc':                   'disc',
  'disc-outline':           'disc',
  'gift':                   'gift',
  'gift-outline':           'gift',
  'trophy':                 'trophy',
} satisfies Record<string, IconName>;

export type IoniconAlias = keyof typeof IONICON_ALIASES;

// ───────────────────────────────────────────────────────────────────────────
// Maps — size, hit-slop, color resolution
// ───────────────────────────────────────────────────────────────────────────

const SIZE_MAP: Record<IconSize, number> = T.icon.sizes as any;
const HIT_SLOP_MAP: Record<IconSize, number> = T.icon.hitSlop as any;

const COLOR_ROLES: Set<string> = new Set(Object.keys(T.icon.colors));

// Resolve семантической роли → palette token → hex (per mode).
// Если color — не семантическая роль, а raw-строка (hex/rgb) — отдаём как есть.
const resolveColor = (color: IconColor | string, mode: 'light' | 'dark'): string => {
  if (!COLOR_ROLES.has(color)) return color; // raw hex/rgb passthrough
  const tokenKey = T.icon.colors[color as IconColor];
  const swatch = T.palette[tokenKey as keyof typeof T.palette];
  return swatch[mode];
};

// ───────────────────────────────────────────────────────────────────────────
// Component
// ───────────────────────────────────────────────────────────────────────────

export const Icon: React.FC<IconProps> = ({
  name,
  size = 'md',
  color = 'default',
  variant = 'default',
  weight: weightOverride,
  hitSlop: hitSlopOverride,
  testID,
  style,
}) => {
  const scheme = useColorScheme();
  const mode: 'light' | 'dark' = scheme === 'dark' ? 'dark' : 'light';

  const resolvedSize = typeof size === 'number' ? size : SIZE_MAP[size];

  // Resolve name через alias-таблицу если передано legacy Ionicon-имя.
  const resolvedName: IconName =
    name in REGISTRY
      ? (name as IconName)
      : (IONICON_ALIASES[name as IoniconAlias] ?? ('plus' as IconName));

  // disabled-variant перебивает color на 'disabled'-роль.
  const effectiveColor: IconColor | string =
    variant === 'disabled' ? 'disabled' : color;
  const resolvedColor = resolveColor(effectiveColor, mode);

  // Weight resolution — единая логика, без V2-исключений:
  //   1. явный override берём как есть;
  //   2. hero (heart) → fill;
  //   3. hero (disc/gift/vinyl-label) → duotone;
  //   4. всё остальное → regular (тонкий outline).
  let resolvedWeight: IconWeight;
  if (weightOverride) {
    resolvedWeight = weightOverride;
  } else if (HERO_FILL_NAMES.has(resolvedName)) {
    resolvedWeight = 'fill';
  } else if (HERO_DUOTONE_NAMES.has(resolvedName)) {
    resolvedWeight = 'duotone';
  } else {
    resolvedWeight = 'regular';
  }

  // Auto hitSlop: пресет → таблица; число → высчитать так, чтобы общий
  // touch target был ≥ 44pt.
  const computedHitSlop =
    hitSlopOverride ??
    (typeof size === 'string'
      ? HIT_SLOP_MAP[size]
      : Math.max(0, Math.ceil((44 - resolvedSize) / 2)));

  const Component = REGISTRY[resolvedName] as React.ComponentType<any>;

  const containerStyle: ViewStyle = {
    width: resolvedSize,
    height: resolvedSize,
    alignItems: 'center',
    justifyContent: 'center',
  };

  return (
    <View
      style={[containerStyle, style]}
      hitSlop={
        computedHitSlop
          ? {
              top: computedHitSlop,
              bottom: computedHitSlop,
              left: computedHitSlop,
              right: computedHitSlop,
            }
          : undefined
      }
      testID={testID}
    >
      <Component
        size={resolvedSize}
        color={resolvedColor}
        weight={resolvedWeight}
      />
    </View>
  );
};
