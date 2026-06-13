/**
 * Ручное добавление пластинки (source='user').
 *
 * Визард из 3 шагов для кейса: пластинки нет ни в Discogs (баркод/фото),
 * ни в Маркете. Юзер фоткает, автозаполняет из Spotify, дополняет руками.
 * Запись проходит preflight-дедуп и уходит на модерацию (pending).
 *
 * Бэкенд: docs/plans/USER_SUBMITTED_RECORDS.md
 *   - POST /records/preflight/      (дабл-чек Discogs + Маркет)
 *   - GET  /records/spotify-search/ (автозаполнение)
 *   - POST /records/user/           (создание)
 */
import { useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  Pressable,
  ActivityIndicator,
  Image,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { useRouter, Stack } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import * as Haptics from 'expo-haptics';
import * as ImagePicker from 'expo-image-picker';
import * as ImageManipulator from 'expo-image-manipulator';
import { Icon } from '@/components/ui';
import { Button, Input, Card } from '../../components/ui';
import { toast } from '../../lib/toast';
import { api } from '../../lib/api';
import type { SpotifyAlbumCandidate } from '../../lib/types';
import { Colors, Typography, Spacing, BorderRadius } from '../../constants/theme';

// Сжать фото с camera/library → base64 JPEG (≤1024px), как в режиме скана.
async function pickPhotoBase64(fromCamera: boolean): Promise<{ uri: string; base64: string } | null> {
  const perm = fromCamera
    ? await ImagePicker.requestCameraPermissionsAsync()
    : await ImagePicker.requestMediaLibraryPermissionsAsync();
  if (!perm.granted) {
    toast.error('Нет доступа', fromCamera ? 'Разрешите камеру в настройках' : 'Разрешите доступ к фото', {
      position: 'bottom',
    });
    return null;
  }
  const res = fromCamera
    ? await ImagePicker.launchCameraAsync({ quality: 0.7 })
    : await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ImagePicker.MediaTypeOptions.Images,
        quality: 0.7,
      });
  if (res.canceled || !res.assets?.[0]?.uri) return null;
  const manipulated = await ImageManipulator.manipulateAsync(
    res.assets[0].uri,
    [{ resize: { width: 1024 } }],
    { compress: 0.5, format: ImageManipulator.SaveFormat.JPEG, base64: true }
  );
  if (!manipulated.base64) return null;
  return { uri: manipulated.uri, base64: manipulated.base64 };
}

// ─── Черновик ────────────────────────────────────────────────────────────────

interface Draft {
  coverPhoto: string | null;       // display uri
  coverBase64: string | null;      // для отправки
  spinePhoto: string | null;
  spineBase64: string | null;
  spotify: SpotifyAlbumCandidate | null;
  artist: string;
  title: string;
  year: string;
  label: string;
  catalog: string;
  country: string;
  format: string;
}

const EMPTY_DRAFT: Draft = {
  coverPhoto: null,
  coverBase64: null,
  spinePhoto: null,
  spineBase64: null,
  spotify: null,
  artist: '',
  title: '',
  year: '',
  label: '',
  catalog: '',
  country: '',
  format: 'LP',
};

type Step = 0 | 1 | 2;
const STEP_LABELS = ['Фото', 'Из Spotify', 'Детали'];

// ─── Экран ───────────────────────────────────────────────────────────────────

export default function ManualRecordScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [step, setStep] = useState<Step>(0);
  const [draft, setDraft] = useState<Draft>(EMPTY_DRAFT);
  const [submitting, setSubmitting] = useState(false);

  const patch = useCallback(
    (p: Partial<Draft>) => setDraft((d) => ({ ...d, ...p })),
    []
  );

  const goNext = () => {
    Haptics.selectionAsync();
    setStep((s) => Math.min(2, s + 1) as Step);
  };
  const goBack = () => {
    if (step === 0) return router.back();
    setStep((s) => Math.max(0, s - 1) as Step);
  };

  const handleSubmit = async () => {
    setSubmitting(true);
    try {
      const yearNum = draft.year.trim() ? parseInt(draft.year, 10) : null;
      // 1) Дабл-чек
      const pf = await api.preflightRecord({
        artist: draft.artist.trim(),
        title: draft.title.trim(),
        year: Number.isFinite(yearNum as number) ? yearNum : null,
        catalog: draft.catalog.trim() || null,
      });
      if (pf.status === 'FOUND_IN_DISCOGS') {
        toast.info('Нашлось в Discogs', 'Эта пластинка уже есть — добавьте её из обычного поиска', {
          position: 'bottom',
        });
        return;
      }
      if (pf.status === 'DUPLICATE' || pf.status === 'LIKELY_DUPLICATE') {
        const m = pf.match;
        toast.info(
          'Похоже, она уже есть',
          m ? `${m.artist} — ${m.title}. Откройте её карточку.` : 'Такая пластинка уже в базе',
          { position: 'bottom' }
        );
        return;
      }
      // 2) ALLOW_CREATE → создаём source='user'
      await api.createUserRecord({
        artist: draft.artist.trim(),
        title: draft.title.trim(),
        year: Number.isFinite(yearNum as number) ? yearNum : null,
        label: draft.label.trim() || null,
        catalog_number: draft.catalog.trim() || null,
        country: draft.country.trim() || null,
        format_type: draft.format.trim() || null,
        spotify_album_id: draft.spotify?.id ?? null,
        tracklist: draft.spotify?.tracks ?? null,
        cover_photo_base64: draft.coverBase64,
        spine_photo_base64: draft.spineBase64,
      });
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      toast.success('Добавлено', 'Пластинка в вашей коллекции, отправлена на модерацию', {
        position: 'bottom',
      });
      router.back();
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      if (e?.response?.status === 409) {
        toast.info('Похоже, она уже есть', 'Эта пластинка уже в базе — добавьте из поиска', {
          position: 'bottom',
        });
      } else {
        toast.error('Не удалось добавить', typeof detail === 'string' ? detail : 'Попробуйте ещё раз', {
          position: 'bottom',
        });
      }
    } finally {
      setSubmitting(false);
    }
  };

  const canLeaveStep0 = !!draft.coverPhoto;
  const canSubmit = draft.artist.trim() && draft.title.trim() && draft.coverPhoto;

  return (
    <View style={styles.root}>
      <Stack.Screen options={{ headerShown: false }} />

      {/* Кастомный хедер */}
      <View style={[styles.header, { paddingTop: insets.top + Spacing.sm }]}>
        <Pressable onPress={goBack} hitSlop={12} style={styles.headerBtn}>
          <Icon name="arrow-left" size={24} color="default" />
        </Pressable>
        <Text style={styles.headerTitle}>Своя пластинка</Text>
        <View style={styles.headerBtn} />
      </View>

      <StepIndicator step={step} />

      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <ScrollView
          contentContainerStyle={styles.scroll}
          keyboardShouldPersistTaps="handled"
        >
          {step === 0 && <PhotoStep draft={draft} patch={patch} />}
          {step === 1 && <SpotifyStep draft={draft} patch={patch} />}
          {step === 2 && <DetailsStep draft={draft} patch={patch} />}
        </ScrollView>

        {/* Нижняя кнопка */}
        <View style={[styles.footer, { paddingBottom: insets.bottom + Spacing.md }]}>
          {step < 2 ? (
            <Button
              title="Далее"
              onPress={goNext}
              disabled={step === 0 && !canLeaveStep0}
            />
          ) : (
            <Button
              title="Добавить пластинку"
              onPress={handleSubmit}
              loading={submitting}
              disabled={!canSubmit}
            />
          )}
          {step === 1 && (
            <Pressable onPress={goNext} style={styles.skip}>
              <Text style={styles.skipText}>Пропустить — заполню руками</Text>
            </Pressable>
          )}
        </View>
      </KeyboardAvoidingView>
    </View>
  );
}

// ─── Шаг 0: фото ─────────────────────────────────────────────────────────────

function PhotoStep({ draft, patch }: StepProps) {
  const pick = async (slot: 'cover' | 'spine') => {
    Haptics.selectionAsync();
    const uriKey = slot === 'cover' ? 'coverPhoto' : 'spinePhoto';
    const b64Key = slot === 'cover' ? 'coverBase64' : 'spineBase64';
    // Уже есть фото → тап очищает слот.
    if (draft[uriKey]) {
      patch({ [uriKey]: null, [b64Key]: null } as Partial<Draft>);
      return;
    }
    const picked = await pickPhotoBase64(true);
    if (picked) {
      patch({ [uriKey]: picked.uri, [b64Key]: picked.base64 } as Partial<Draft>);
    }
  };

  return (
    <View style={styles.stepGap}>
      <Text style={styles.stepTitle}>Сфотографируй пластинку</Text>
      <Text style={styles.stepHint}>
        Обложка обязательна. Корешок — по желанию, помогает распознать издание.
      </Text>

      <View style={styles.photoRow}>
        <PhotoSlot
          label="Обложка"
          required
          uri={draft.coverPhoto}
          onPress={() => pick('cover')}
        />
        <PhotoSlot
          label="Корешок"
          uri={draft.spinePhoto}
          onPress={() => pick('spine')}
        />
      </View>
    </View>
  );
}

function PhotoSlot({
  label,
  required,
  uri,
  onPress,
}: {
  label: string;
  required?: boolean;
  uri: string | null;
  onPress: () => void;
}) {
  const filled = !!uri;
  return (
    <Pressable onPress={onPress} style={styles.slotWrap}>
      <View style={[styles.slot, filled && styles.slotFilled]}>
        {filled ? (
          <Image source={{ uri: uri! }} style={styles.slotImage} resizeMode="cover" />
        ) : (
          <Icon name="camera" size={28} color="secondary" />
        )}
      </View>
      <Text style={styles.slotLabel}>
        {label}
        {required ? ' *' : ''}
      </Text>
    </Pressable>
  );
}

// ─── Шаг 1: Spotify ──────────────────────────────────────────────────────────

function SpotifyStep({ draft, patch }: StepProps) {
  const [q, setQ] = useState('');
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<SpotifyAlbumCandidate[]>([]);

  const search = async () => {
    if (!q.trim()) return;
    setLoading(true);
    try {
      const r = await api.spotifySearchAlbums(q.trim());
      setResults(r);
      if (r.length === 0) {
        toast.info('Ничего не нашлось', 'Заполните данные вручную на следующем шаге', {
          position: 'bottom',
        });
      }
    } catch {
      toast.error('Spotify недоступен', 'Заполните данные вручную', { position: 'bottom' });
    } finally {
      setLoading(false);
    }
  };

  const pick = (a: SpotifyAlbumCandidate) => {
    Haptics.selectionAsync();
    patch({
      spotify: a,
      artist: a.artist,
      title: a.name,
      year: a.year != null ? String(a.year) : '',
    });
  };

  return (
    <View style={styles.stepGap}>
      <Text style={styles.stepTitle}>Подтянуть данные из Spotify</Text>
      <Text style={styles.stepHint}>
        Артист, треклист и год заполнятся автоматически. Прессинг и каталог
        добавишь на следующем шаге.
      </Text>

      <View style={styles.searchRow}>
        <View style={styles.flex}>
          <Input
            value={q}
            onChangeText={setQ}
            placeholder="Антоха МС — Родня"
          />
        </View>
        <Pressable onPress={search} style={styles.searchBtn}>
          <Icon name="magnifying-glass" size={20} color="onBrand" />
        </Pressable>
      </View>

      {loading && <ActivityIndicator color={Colors.royalBlue} style={styles.mt16} />}

      {results.map((a) => {
        const active = draft.spotify?.id === a.id;
        return (
          <Pressable key={a.id} onPress={() => pick(a)}>
            <Card style={StyleSheet.flatten([styles.albumCard, active && styles.albumCardActive])}>
              <View style={styles.albumThumb}>
                <Icon name="music-notes" size={22} color="secondary" />
              </View>
              <View style={styles.flex}>
                <Text style={styles.albumTitle} numberOfLines={1}>
                  {a.name}
                </Text>
                <Text style={styles.albumMeta} numberOfLines={1}>
                  {a.artist}{a.year ? ` · ${a.year}` : ''} · {a.tracks.length} треков
                </Text>
              </View>
              {active && <Icon name="check-circle" size={22} color="accent" />}
            </Card>
          </Pressable>
        );
      })}

      {draft.spotify && (
        <View style={styles.sparkleNote}>
          <Icon name="sparkles" size={16} color="accent" />
          <Text style={styles.sparkleText}>
            Заполнено: {draft.spotify.tracks.length} треков, {draft.year} год
          </Text>
        </View>
      )}
    </View>
  );
}

// ─── Шаг 2: детали ───────────────────────────────────────────────────────────

function DetailsStep({ draft, patch }: StepProps) {
  return (
    <View style={styles.stepGap}>
      <Text style={styles.stepTitle}>Детали издания</Text>
      <Text style={styles.stepHint}>
        Поля со звёздочкой обязательны. Каталог DGS-* в прототипе вернёт
        «нашлось в Discogs».
      </Text>

      <Input label="Артист *" value={draft.artist} onChangeText={(v) => patch({ artist: v })} placeholder="Антоха МС" />
      <Input label="Название *" value={draft.title} onChangeText={(v) => patch({ title: v })} placeholder="Родня" />
      <Input label="Год" value={draft.year} onChangeText={(v) => patch({ year: v })} placeholder="2022" keyboardType="numeric" />
      <Input label="Лейбл" value={draft.label} onChangeText={(v) => patch({ label: v })} placeholder="Самиздат" />
      <Input label="Каталожный №" value={draft.catalog} onChangeText={(v) => patch({ catalog: v })} placeholder="—" />
      <Input label="Страна" value={draft.country} onChangeText={(v) => patch({ country: v })} placeholder="Россия" />
      <Input label="Формат" value={draft.format} onChangeText={(v) => patch({ format: v })} placeholder="LP" />
    </View>
  );
}

// ─── Индикатор шагов ─────────────────────────────────────────────────────────

function StepIndicator({ step }: { step: Step }) {
  return (
    <View style={styles.indicator}>
      {STEP_LABELS.map((label, i) => (
        <View key={label} style={styles.indicatorItem}>
          <View style={[styles.dot, i <= step && styles.dotActive]}>
            <Text style={[styles.dotNum, i <= step && styles.dotNumActive]}>
              {i + 1}
            </Text>
          </View>
          <Text style={[styles.indicatorLabel, i === step && styles.indicatorLabelActive]}>
            {label}
          </Text>
        </View>
      ))}
    </View>
  );
}

// ─── Типы пропсов ────────────────────────────────────────────────────────────

interface StepProps {
  draft: Draft;
  patch: (p: Partial<Draft>) => void;
}

// ─── Стили ───────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: Colors.background },
  flex: { flex: 1 },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: Spacing.md,
    paddingBottom: Spacing.sm,
  },
  headerBtn: { width: 32, height: 32, alignItems: 'center', justifyContent: 'center' },
  headerTitle: { ...Typography.h3, color: Colors.text },
  indicator: {
    flexDirection: 'row',
    justifyContent: 'center',
    gap: Spacing.lg,
    paddingVertical: Spacing.md,
  },
  indicatorItem: { alignItems: 'center', gap: 4 },
  dot: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: Colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
  },
  dotActive: { backgroundColor: Colors.royalBlue },
  dotNum: { ...Typography.buttonSmall, color: Colors.textMuted },
  dotNumActive: { color: '#fff' },
  indicatorLabel: { ...Typography.caption, color: Colors.textMuted },
  indicatorLabelActive: { color: Colors.text },
  scroll: { padding: Spacing.md, paddingBottom: Spacing.xxl },
  stepGap: { gap: Spacing.md },
  stepTitle: { ...Typography.h2, color: Colors.text },
  stepHint: { ...Typography.bodySmall, color: Colors.textSecondary },
  // фото
  photoRow: { flexDirection: 'row', gap: Spacing.md, marginTop: Spacing.sm },
  slotWrap: { flex: 1, alignItems: 'center', gap: Spacing.xs },
  slot: {
    width: '100%',
    aspectRatio: 1,
    borderRadius: BorderRadius.lg,
    borderWidth: 1.5,
    borderColor: Colors.border,
    borderStyle: 'dashed',
    backgroundColor: Colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
  },
  slotFilled: { borderStyle: 'solid', borderColor: Colors.royalBlue, backgroundColor: Colors.surfaceHover, overflow: 'hidden' },
  slotImage: { width: '100%', height: '100%', borderRadius: BorderRadius.lg },
  slotLabel: { ...Typography.caption, color: Colors.textSecondary },
  // spotify
  searchRow: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm },
  searchBtn: {
    width: 48,
    height: 48,
    borderRadius: BorderRadius.md,
    backgroundColor: Colors.royalBlue,
    alignItems: 'center',
    justifyContent: 'center',
  },
  mt16: { marginTop: Spacing.md },
  albumCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.md,
    padding: Spacing.md,
  },
  albumCardActive: { borderWidth: 1.5, borderColor: Colors.royalBlue },
  albumThumb: {
    width: 44,
    height: 44,
    borderRadius: BorderRadius.sm,
    backgroundColor: Colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
  },
  albumTitle: { ...Typography.bodyBold, color: Colors.text },
  albumMeta: { ...Typography.caption, color: Colors.textMuted },
  sparkleNote: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.xs,
    padding: Spacing.sm,
    borderRadius: BorderRadius.sm,
    backgroundColor: Colors.surface,
  },
  sparkleText: { ...Typography.caption, color: Colors.textSecondary },
  // footer
  footer: {
    paddingHorizontal: Spacing.md,
    paddingTop: Spacing.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: Colors.divider,
    gap: Spacing.sm,
  },
  skip: { alignItems: 'center', paddingVertical: Spacing.xs },
  skipText: { ...Typography.bodySmall, color: Colors.textMuted },
});
