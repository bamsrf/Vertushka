/**
 * /dev/icons — галерея всех 53 имён из Icon registry (B2 Iconography).
 *
 * Назначение:
 *   - Глазная проверка hero-SVG до миграции продуктовых экранов на <Icon>.
 *   - Сравнение размеров (xs/sm/md/lg/xl) и weight (regular/fill).
 *   - Перебор семантических color-ролей (default/brand/accent/state.*).
 *
 * Не входит в навигацию пользователя — открывается прямой ссылкой `/dev/icons`
 * (Expo dev-tools или router.push).
 */

import React, { useState, useMemo } from 'react';
import { ScrollView, View, Text, StyleSheet, TouchableOpacity, Pressable } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Icon, type IconName, type IconColor, type IconSize, type IconVariant, type IconWeight } from '../../components/ui';
import { Colors, Typography, Spacing, BorderRadius } from '../../constants/theme';
import { withDevOnly } from '../../components/DevOnly';

// ───────────────────────────────────────────────────────────────────────────
// Группировка имён — одинакова с migration table B2.
// ───────────────────────────────────────────────────────────────────────────

const GROUPS: Array<{ title: string; names: IconName[] }> = [
  {
    title: 'Action',
    names: ['plus', 'plus-circle', 'check', 'check-circle', 'x', 'x-circle', 'pencil', 'trash', 'camera', 'envelope', 'download', 'share', 'arrow-clockwise', 'heart'],
  },
  {
    title: 'Navigation',
    names: ['arrow-left', 'arrow-right', 'caret-left', 'caret-right', 'magnifying-glass', 'user'],
  },
  {
    title: 'State',
    names: ['warning-circle'],
  },
  {
    title: 'System',
    names: ['bell', 'bell-slash', 'cloud-slash', 'lock-open', 'question', 'keyhole'],
  },
  {
    title: 'UI Control',
    names: ['dots-three', 'dots-three-vertical', 'squares-four', 'list', 'sliders', 'arrows-down-up'],
  },
  {
    title: 'Domain',
    names: ['calendar', 'clock', 'globe', 'buildings', 'folder', 'tag', 'map-pin', 'map-trifold', 'currency-circle-dollar', 'star'],
  },
  {
    title: 'Decorative / Brand',
    names: ['sparkle', 'google-logo'],
  },
  {
    title: '★ Custom hero (B2)',
    names: ['disc', 'gift', 'trophy', 'scan', 'vinyl-label'],
  },
];

const SIZES: IconSize[] = ['xs', 'sm', 'md', 'lg', 'xl'];
const COLORS: IconColor[] = ['default', 'secondary', 'primary', 'brand', 'accent', 'success', 'error', 'warning', 'disabled'];
const VARIANTS: IconVariant[] = ['default', 'active', 'disabled'];
type WeightChoice = 'auto' | IconWeight;
const WEIGHTS: WeightChoice[] = ['auto', 'regular', 'duotone', 'fill'];

// ───────────────────────────────────────────────────────────────────────────

function IconsGalleryScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [size, setSize] = useState<IconSize>('md');
  const [color, setColor] = useState<IconColor>('default');
  const [variant, setVariant] = useState<IconVariant>('default');
  const [weight, setWeight] = useState<WeightChoice>('auto');
  const [showOnBrand, setShowOnBrand] = useState(false);

  // weight='auto' означает «не передавать prop, пусть резолвит variant»
  const weightProp = weight === 'auto' ? undefined : weight;

  const totalCount = useMemo(() => GROUPS.reduce((acc, g) => acc + g.names.length, 0), []);

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Icon name="arrow-left" size="md" color="brand" />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={styles.title}>Icons gallery</Text>
          <Text style={styles.subtitle}>{totalCount} names · B2 Iconography</Text>
        </View>
      </View>

      <ScrollView
        contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + Spacing.xl }]}
        showsVerticalScrollIndicator={false}
      >
        {/* Toolbar */}
        <View style={styles.toolbar}>
          <Toolrow label="Size">
            {SIZES.map((s) => (
              <Chip key={s} active={size === s} onPress={() => setSize(s)} text={s} />
            ))}
          </Toolrow>
          <Toolrow label="Color">
            {COLORS.map((c) => (
              <Chip key={c} active={color === c} onPress={() => setColor(c)} text={c} />
            ))}
          </Toolrow>
          <Toolrow label="Variant">
            {VARIANTS.map((v) => (
              <Chip key={v} active={variant === v} onPress={() => setVariant(v)} text={v} />
            ))}
          </Toolrow>
          <Toolrow label="Weight">
            {WEIGHTS.map((w) => (
              <Chip key={w} active={weight === w} onPress={() => setWeight(w)} text={w} />
            ))}
          </Toolrow>
          <Toolrow label="Background">
            <Chip active={!showOnBrand} onPress={() => setShowOnBrand(false)} text="surface" />
            <Chip active={showOnBrand} onPress={() => setShowOnBrand(true)} text="brand" />
          </Toolrow>
        </View>

        {/* Groups */}
        {GROUPS.map((g) => (
          <View key={g.title} style={styles.group}>
            <Text style={styles.groupTitle}>{g.title}</Text>
            <Text style={styles.groupCount}>{g.names.length}</Text>
            <View style={styles.grid}>
              {g.names.map((name) => (
                <View
                  key={name}
                  style={[
                    styles.cell,
                    { backgroundColor: showOnBrand ? Colors.royalBlue : Colors.surface },
                  ]}
                >
                  <Icon
                    name={name}
                    size={size}
                    color={showOnBrand ? 'onBrand' : color}
                    variant={variant}
                    weight={weightProp}
                  />
                  <Text
                    style={[
                      styles.cellLabel,
                      { color: showOnBrand ? '#FFFFFF' : Colors.textSecondary },
                    ]}
                    numberOfLines={1}
                  >
                    {name}
                  </Text>
                </View>
              ))}
            </View>
          </View>
        ))}

        {/* Weight comparison — Phosphor regular vs duotone vs fill side-by-side
            на пачке частотных иконок. Главный смысл этой галереи. */}
        <View style={styles.group}>
          <Text style={styles.groupTitle}>Weight comparison</Text>
          <Text style={styles.groupCount}>regular · duotone · fill</Text>
          <View style={styles.weightTable}>
            <View style={styles.weightRow}>
              <Text style={styles.weightHeaderCell}>icon</Text>
              <Text style={styles.weightHeaderCell}>regular</Text>
              <Text style={styles.weightHeaderCell}>duotone</Text>
              <Text style={styles.weightHeaderCell}>fill</Text>
            </View>
            {(['heart', 'magnifying-glass', 'gift', 'bell', 'folder', 'star', 'envelope', 'user', 'disc', 'trophy'] as IconName[]).map((n) => (
              <View key={n} style={styles.weightRow}>
                <Text style={[styles.cellLabel, styles.weightNameCell]} numberOfLines={1}>{n}</Text>
                <View style={styles.weightCell}><Icon name={n} size="lg" color="brand" weight="regular" /></View>
                <View style={styles.weightCell}><Icon name={n} size="lg" color="brand" weight="duotone" /></View>
                <View style={styles.weightCell}><Icon name={n} size="lg" color="brand" weight="fill" /></View>
              </View>
            ))}
          </View>
        </View>

        {/* Size matrix — disc во всех 5 размерах × duotone */}
        <View style={styles.group}>
          <Text style={styles.groupTitle}>Size matrix · disc</Text>
          <Text style={styles.groupCount}>5 sizes × 3 weights</Text>
          <View style={styles.matrix}>
            {SIZES.map((s) => (
              <View key={s} style={styles.matrixCell}>
                <View style={styles.matrixIcons}>
                  <Icon name="disc" size={s} color="brand" weight="regular" />
                  <Icon name="disc" size={s} color="brand" weight="duotone" />
                  <Icon name="disc" size={s} color="brand" weight="fill" />
                </View>
                <Text style={styles.cellLabel}>{s}</Text>
              </View>
            ))}
          </View>
        </View>

        {/* Rarity-маркеры удалены — выражаются через RarityAura, не иконками. */}

        {/* Footer note */}
        <View style={styles.footer}>
          <Text style={styles.footerText}>
            ▸ <Text style={styles.mono}>{`<Icon name="${'<name>'}" size="${size}" color="${color}" variant="${variant}"${weight === 'auto' ? '' : ` weight="${weight}"`} />`}</Text>
          </Text>
          <Text style={styles.footerText}>
            ▸ Phosphor поддерживает 6 weights; здесь — regular / duotone / fill.
          </Text>
          <Text style={styles.footerText}>
            ▸ Hero (★ disc, gift, trophy, scan, rarity-*, vinyl-label) — кастомные SVG, понимают только regular + fill. Duotone у них рендерится как regular.
          </Text>
        </View>
      </ScrollView>
    </View>
  );
}

// ───────────────────────────────────────────────────────────────────────────
// Helpers
// ───────────────────────────────────────────────────────────────────────────

function Toolrow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <View style={styles.toolrow}>
      <Text style={styles.toolrowLabel}>{label}</Text>
      <View style={styles.toolrowChips}>{children}</View>
    </View>
  );
}

function Chip({ active, onPress, text }: { active: boolean; onPress: () => void; text: string }) {
  return (
    <Pressable
      onPress={onPress}
      style={[styles.chip, active && styles.chipActive]}
      hitSlop={6}
    >
      <Text style={[styles.chipText, active && styles.chipTextActive]} numberOfLines={1}>
        {text}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm,
    gap: Spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: Colors.divider,
  },
  backBtn: {
    width: 40,
    height: 40,
    alignItems: 'center',
    justifyContent: 'center',
  },
  title: {
    ...Typography.h2,
    color: Colors.text,
  },
  subtitle: {
    ...Typography.caption,
    color: Colors.textMuted,
    marginTop: 2,
  },
  content: {
    paddingHorizontal: Spacing.md,
    paddingTop: Spacing.md,
  },
  toolbar: {
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.lg,
    padding: Spacing.md,
    gap: Spacing.sm,
    marginBottom: Spacing.lg,
  },
  toolrow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: Spacing.sm,
  },
  toolrowLabel: {
    ...Typography.caption,
    color: Colors.textMuted,
    width: 88,
    paddingTop: 6,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  toolrowChips: {
    flex: 1,
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
  chip: {
    paddingHorizontal: Spacing.sm,
    paddingVertical: 5,
    borderRadius: 14,
    backgroundColor: Colors.background,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  chipActive: {
    backgroundColor: Colors.royalBlue,
    borderColor: Colors.royalBlue,
  },
  chipText: {
    fontSize: 12,
    fontFamily: 'Inter_500Medium',
    color: Colors.textSecondary,
  },
  chipTextActive: {
    color: '#FFFFFF',
  },
  group: {
    marginBottom: Spacing.lg,
  },
  groupTitle: {
    ...Typography.h4,
    color: Colors.text,
    marginBottom: 2,
  },
  groupCount: {
    ...Typography.caption,
    color: Colors.textMuted,
    marginBottom: Spacing.sm,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.sm,
  },
  cell: {
    width: '23.5%' as any,
    aspectRatio: 1,
    borderRadius: BorderRadius.md,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: Spacing.sm,
    gap: 6,
  },
  cellLabel: {
    fontSize: 9,
    fontFamily: 'Inter_500Medium',
    textAlign: 'center',
    paddingHorizontal: 4,
  },
  matrix: {
    flexDirection: 'row',
    gap: Spacing.sm,
  },
  matrixCell: {
    flex: 1,
    aspectRatio: 0.55,
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.md,
    alignItems: 'center',
    justifyContent: 'center',
    gap: Spacing.sm,
    paddingVertical: Spacing.sm,
  },
  matrixIcons: {
    alignItems: 'center',
    gap: 10,
  },
  weightTable: {
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.md,
    paddingVertical: Spacing.xs,
  },
  weightRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 6,
    paddingHorizontal: Spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: Colors.divider,
  },
  weightHeaderCell: {
    flex: 1,
    fontSize: 10,
    fontFamily: 'Inter_700Bold',
    color: Colors.textMuted,
    textAlign: 'center',
    textTransform: 'uppercase',
    letterSpacing: 0.6,
  },
  weightNameCell: {
    flex: 1,
    color: Colors.text,
    textAlign: 'left',
  },
  weightCell: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  footer: {
    marginTop: Spacing.md,
    padding: Spacing.md,
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.md,
    gap: Spacing.xs,
  },
  footerText: {
    ...Typography.caption,
    color: Colors.textSecondary,
  },
  mono: {
    fontFamily: 'Inter_600SemiBold',
    color: Colors.deepNavy,
  },
});

// В релизной сборке экран подменяется заглушкой: см. components/DevOnly.
export default withDevOnly(IconsGalleryScreen);
