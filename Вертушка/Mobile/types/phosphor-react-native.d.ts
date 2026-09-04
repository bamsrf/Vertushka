/**
 * Ambient-типы для phosphor-react-native 3.0.6.
 *
 * Пакет объявляет `types: lib/typescript/index.d.ts`, но в опубликованном
 * tarball этого файла нет (в lib/typescript/ лежат только per-icon d.ts,
 * которые сами импортируют типы из главного модуля — по кругу). Из-за этого
 * tsc падал в TS7016 implicit-any на каждом импорте.
 *
 * Здесь минимальный контракт: IconProps/Icon + те иконки, которые проект
 * реально импортирует. Новая иконка в коде = новая строка здесь (tsc сам
 * подскажет). Удалить файл, когда апстрим начнёт публиковать index.d.ts.
 */
declare module 'phosphor-react-native' {
  import type { ComponentType } from 'react';
  import type { StyleProp, ViewStyle } from 'react-native';

  export type IconWeight = 'thin' | 'light' | 'regular' | 'bold' | 'fill' | 'duotone';

  export interface IconProps {
    size?: number | string;
    color?: string;
    weight?: IconWeight;
    mirrored?: boolean;
    style?: StyleProp<ViewStyle>;
    duotoneColor?: string;
    duotoneOpacity?: number;
  }

  export type Icon = ComponentType<IconProps>;

  export const ArrowClockwiseIcon: Icon;
  export const ArrowDownIcon: Icon;
  export const ArrowLeftIcon: Icon;
  export const ArrowRightIcon: Icon;
  export const ArrowUpIcon: Icon;
  export const ArrowUpRightIcon: Icon;
  export const ArrowsDownUpIcon: Icon;
  export const ArrowsLeftRightIcon: Icon;
  export const BellIcon: Icon;
  export const BellSlashIcon: Icon;
  export const BuildingsIcon: Icon;
  export const CalendarIcon: Icon;
  export const CameraIcon: Icon;
  export const CaretDownIcon: Icon;
  export const CaretLeftIcon: Icon;
  export const CaretRightIcon: Icon;
  export const CaretUpIcon: Icon;
  export const ChatCircleIcon: Icon;
  export const CheckCircleIcon: Icon;
  export const CheckIcon: Icon;
  export const ClockIcon: Icon;
  export const CloudSlashIcon: Icon;
  export const CopyIcon: Icon;
  export const CurrencyCircleDollarIcon: Icon;
  export const CurrencyRubIcon: Icon;
  export const DownloadSimpleIcon: Icon;
  export const EnvelopeIcon: Icon;
  export const EnvelopeOpenIcon: Icon;
  export const EyeIcon: Icon;
  export const EyeSlashIcon: Icon;
  export const FileTextIcon: Icon;
  export const FlagIcon: Icon;
  export const FolderIcon: Icon;
  export const FolderOpenIcon: Icon;
  export const GiftIcon: Icon;
  export const GlobeIcon: Icon;
  export const GoogleLogoIcon: Icon;
  export const HeartIcon: Icon;
  export const ImageIcon: Icon;
  export const KeyholeIcon: Icon;
  export const ListIcon: Icon;
  export const LockOpenIcon: Icon;
  export const MagnifyingGlassIcon: Icon;
  export const MapPinIcon: Icon;
  export const MapTrifoldIcon: Icon;
  export const MusicNotesIcon: Icon;
  export const PaperPlaneTiltIcon: Icon;
  export const PaperclipIcon: Icon;
  export const PencilIcon: Icon;
  export const PlusCircleIcon: Icon;
  export const PlusIcon: Icon;
  export const QuestionIcon: Icon;
  export const ScanIcon: Icon;
  export const ShareNetworkIcon: Icon;
  export const ShieldCheckIcon: Icon;
  export const SlidersIcon: Icon;
  export const SparkleIcon: Icon;
  export const SquaresFourIcon: Icon;
  export const StarIcon: Icon;
  export const StorefrontIcon: Icon;
  export const TagIcon: Icon;
  export const TrashIcon: Icon;
  export const TrophyIcon: Icon;
  export const UserIcon: Icon;
  export const UserMinusIcon: Icon;
  export const UserPlusIcon: Icon;
  export const UsersIcon: Icon;
  export const VinylRecordIcon: Icon;
  export const WarningCircleIcon: Icon;
}
