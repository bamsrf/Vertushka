/**
 * Ручное добавление / редактирование релиза (source='user').
 *
 * Визард из 3 шагов для кейса: релиза нет ни в Discogs (баркод/фото),
 * ни в Маркете. Юзер фоткает, автозаполняет из Spotify, дополняет руками.
 * Запись проходит preflight-дедуп и сразу попадает в коллекцию (§6: модерации нет).
 *
 * Форматы: винил / CD / кассета (§9). Edit-режим через ?editId= (§11).
 * Дедуп-перехват: если релиз уже есть — предлагаем добавить найденный (§10).
 *
 * Бэкенд: docs/plans/USER_SUBMITTED_RECORDS.md
 *   - POST  /records/preflight/      (дабл-чек Discogs + Маркет)
 *   - GET   /records/spotify-search/ (автозаполнение)
 *   - POST  /records/user/           (создание)
 *   - PATCH /records/user/{id}       (правка автором)
 */
import { useState, useCallback, useEffect } from 'react';
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
import { useRouter, Stack, useLocalSearchParams } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import * as Haptics from 'expo-haptics';
import * as ImagePicker from 'expo-image-picker';
import * as ImageManipulator from 'expo-image-manipulator';
import { Icon } from '@/components/ui';
import { Button, Input, Card } from '../../components/ui';
import { toast } from '../../lib/toast';
import { api, getCoverUrl } from '../../lib/api';
import { useCollectionStore } from '../../lib/store';
import type { SpotifyAlbumCandidate, VinylRecord, PreflightResponse } from '../../lib/types';
import { Colors, Typography, Spacing, BorderRadius } from '../../constants/theme';

// Форматы носителя (§9). value → format_type на бэке.
const FORMAT_OPTIONS = [
  { label: 'Винил', value: 'vinyl' },
  { label: 'CD', value: 'cd' },
  { label: 'Кассета', value: 'cassette' },
] as const;

// Нормализуем произвольный format_type записи (LP / Vinyl / Cassette / …) в один
// из трёх сегментов. Дефолт — винил.
function normalizeFormat(raw: string | null | undefined): string {
  const f = (raw || '').toLowerCase();
  if (f.includes('cd') || f.includes('compact')) return 'cd';
  if (f.includes('cass') || f.includes('tape') || f.includes('кассет')) return 'cassette';
  return 'vinyl';
}

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
  format: 'vinyl',
};

type Step = 0 | 1 | 2;
const STEP_LABELS = ['Фото', 'Из Spotify', 'Детали'];

// ─── Экран ───────────────────────────────────────────────────────────────────

export default function ManualRecordScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { editId } = useLocalSearchParams<{ editId?: string }>();
  const isEdit = !!editId;
  const addToCollection = useCollectionStore((s) => s.addToCollection);
  const addToCollectionByRecordId = useCollectionStore((s) => s.addToCollectionByRecordId);

  const [step, setStep] = useState<Step>(0);
  const [draft, setDraft] = useState<Draft>(EMPTY_DRAFT);
  const [submitting, setSubmitting] = useState(false);
  const [loadingEdit, setLoadingEdit] = useState(isEdit);
  // Дедуп-перехват (§10): найденный релиз + статус preflight.
  const [intercept, setIntercept] = useState<PreflightResponse | null>(null);
  const [adding, setAdding] = useState(false);

  const patch = useCallback(
    (p: Partial<Draft>) => setDraft((d) => ({ ...d, ...p })),
    []
  );

  // Замена обложки в edit-режиме (§11). Тап по слоту → камера/галерея.
  const pickCover = useCallback(async () => {
    Haptics.selectionAsync();
    const picked = await pickPhotoBase64(true);
    if (picked) patch({ coverPhoto: picked.uri, coverBase64: picked.base64 });
  }, [patch]);

  // Edit-режим (§11): подтягиваем запись и префиллим черновик.
  useEffect(() => {
    if (!editId) return;
    let alive = true;
    (async () => {
      try {
        const rec = await api.getRecord(editId);
        if (!alive) return;
        setDraft({
          coverPhoto: getCoverUrl(rec) ?? null,
          coverBase64: null,
          spinePhoto: null,
          spineBase64: null,
          spotify: null,
          artist: rec.artist ?? '',
          title: rec.title ?? '',
          year: rec.year != null ? String(rec.year) : '',
          label: rec.label ?? '',
          catalog: rec.catalog_number ?? '',
          country: rec.country ?? '',
          format: normalizeFormat(rec.format_type),
        });
        setStep(2); // в edit сразу к деталям
      } catch {
        toast.error('Не удалось загрузить', 'Попробуйте ещё раз', { position: 'bottom' });
        router.back();
      } finally {
        if (alive) setLoadingEdit(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [editId, router]);

  const goNext = () => {
    Haptics.selectionAsync();
    setStep((s) => Math.min(2, s + 1) as Step);
  };
  const goBack = () => {
    if (step === 0) return router.back();
    setStep((s) => Math.max(0, s - 1) as Step);
  };

  const yearNum = () => {
    const n = draft.year.trim() ? parseInt(draft.year, 10) : null;
    return Number.isFinite(n as number) ? n : null;
  };

  // Создать source='user' (после чистого preflight или «всё равно создать своё»).
  const doCreate = async () => {
    setSubmitting(true);
    try {
      await api.createUserRecord({
        artist: draft.artist.trim(),
        title: draft.title.trim(),
        year: yearNum(),
        label: draft.label.trim() || null,
        catalog_number: draft.catalog.trim() || null,
        country: draft.country.trim() || null,
        format_type: draft.format || null,
        spotify_album_id: draft.spotify?.id ?? null,
        tracklist: draft.spotify?.tracks ?? null,
        cover_photo_base64: draft.coverBase64,
        spine_photo_base64: draft.spineBase64,
      });
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      toast.success('Добавлено', 'Релиз в вашей коллекции', { position: 'bottom' });
      router.back();
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      toast.error('Не удалось добавить', typeof detail === 'string' ? detail : 'Попробуйте ещё раз', {
        position: 'bottom',
      });
    } finally {
      setSubmitting(false);
    }
  };

  const handleSubmit = async () => {
    // Edit-режим (§11): без preflight, просто PATCH.
    if (isEdit && editId) {
      setSubmitting(true);
      try {
        await api.updateUserRecord(editId, {
          artist: draft.artist.trim(),
          title: draft.title.trim(),
          year: yearNum(),
          label: draft.label.trim() || null,
          catalog_number: draft.catalog.trim() || null,
          country: draft.country.trim() || null,
          format_type: draft.format || null,
          cover_photo_base64: draft.coverBase64,
        });
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
        toast.success('Сохранено', 'Релиз обновлён', { position: 'bottom' });
        router.back();
      } catch (e: any) {
        const detail = e?.response?.data?.detail;
        toast.error('Не удалось сохранить', typeof detail === 'string' ? detail : 'Попробуйте ещё раз', {
          position: 'bottom',
        });
      } finally {
        setSubmitting(false);
      }
      return;
    }

    // Create-режим: preflight → перехват дубля (§10) или создание.
    setSubmitting(true);
    try {
      const pf = await api.preflightRecord({
        artist: draft.artist.trim(),
        title: draft.title.trim(),
        year: yearNum(),
        catalog: draft.catalog.trim() || null,
        format_type: draft.format || null,
      });
      if (pf.status === 'ALLOW_CREATE') {
        await doCreate();
        return;
      }
      // Дубль найден → показываем перехват-экран (§10).
      setIntercept(pf);
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      toast.error('Не удалось добавить', typeof detail === 'string' ? detail : 'Попробуйте ещё раз', {
        position: 'bottom',
      });
    } finally {
      setSubmitting(false);
    }
  };

  // §10: добавить НАЙДЕННЫЙ релиз в коллекцию (не создаём дубль).
  const addFound = async () => {
    if (!intercept) return;
    setAdding(true);
    try {
      if (intercept.match?.id) {
        await addToCollectionByRecordId(intercept.match.id);
      } else if (intercept.discogs_id) {
        await addToCollection(intercept.discogs_id);
      }
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      toast.success('Добавлено', 'Релиз в вашей коллекции', { position: 'bottom' });
      router.back();
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      toast.error('Не удалось добавить', typeof detail === 'string' ? detail : 'Попробуйте ещё раз', {
        position: 'bottom',
      });
    } finally {
      setAdding(false);
    }
  };

  const canLeaveStep0 = !!draft.coverPhoto;
  // В edit фото опционально (обложка уже есть). В create — обязательна.
  const canSubmit = draft.artist.trim() && draft.title.trim() && (isEdit || draft.coverPhoto);

  const headerTitle = isEdit ? 'Редактировать релиз' : 'Свой релиз';

  // Экран-перехват дубля (§10) поверх визарда.
  if (intercept) {
    return (
      <InterceptScreen
        pf={intercept}
        adding={adding}
        onAddFound={addFound}
        onCreateAnyway={() => {
          setIntercept(null);
          doCreate();
        }}
        onClose={() => setIntercept(null)}
        insetsTop={insets.top}
        insetsBottom={insets.bottom}
      />
    );
  }

  return (
    <View style={styles.root}>
      <Stack.Screen options={{ headerShown: false }} />

      {/* Кастомный хедер */}
      <View style={[styles.header, { paddingTop: insets.top + Spacing.sm }]}>
        <Pressable onPress={goBack} hitSlop={12} style={styles.headerBtn}>
          <Icon name="arrow-left" size={24} color="default" />
        </Pressable>
        <Text style={styles.headerTitle}>{headerTitle}</Text>
        <View style={styles.headerBtn} />
      </View>

      {!isEdit && <StepIndicator step={step} />}

      {loadingEdit ? (
        <View style={styles.loadingWrap}>
          <ActivityIndicator color={Colors.royalBlue} />
        </View>
      ) : (
        <KeyboardAvoidingView
          style={styles.flex}
          behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        >
          <ScrollView
            contentContainerStyle={styles.scroll}
            keyboardShouldPersistTaps="handled"
          >
            {isEdit ? (
              <View style={styles.stepGap}>
                <Text style={styles.stepTitle}>Обложка</Text>
                <View style={styles.editCoverRow}>
                  <PhotoSlot label="Обложка" uri={draft.coverPhoto} onPress={pickCover} />
                  <View style={styles.flex} />
                </View>
                <DetailsStep draft={draft} patch={patch} />
              </View>
            ) : (
              <>
                {step === 0 && <PhotoStep draft={draft} patch={patch} />}
                {step === 1 && <SpotifyStep draft={draft} patch={patch} />}
                {step === 2 && <DetailsStep draft={draft} patch={patch} />}
              </>
            )}
          </ScrollView>

          {/* Нижняя кнопка */}
          <View style={[styles.footer, { paddingBottom: insets.bottom + Spacing.md }]}>
            {!isEdit && step < 2 ? (
              <Button
                title="Далее"
                onPress={goNext}
                disabled={step === 0 && !canLeaveStep0}
              />
            ) : (
              <Button
                title={isEdit ? 'Сохранить' : 'Добавить релиз'}
                onPress={handleSubmit}
                loading={submitting}
                disabled={!canSubmit}
              />
            )}
            {!isEdit && step === 1 && (
              <Pressable onPress={goNext} style={styles.skip}>
                <Text style={styles.skipText}>Пропустить — заполню руками</Text>
              </Pressable>
            )}
          </View>
        </KeyboardAvoidingView>
      )}
    </View>
  );
}

// ─── Экран-перехват дубля (§10) ────────────────────────────────────────────────

function InterceptScreen({
  pf,
  adding,
  onAddFound,
  onCreateAnyway,
  onClose,
  insetsTop,
  insetsBottom,
}: {
  pf: PreflightResponse;
  adding: boolean;
  onAddFound: () => void;
  onCreateAnyway: () => void;
  onClose: () => void;
  insetsTop: number;
  insetsBottom: number;
}) {
  const m = pf.match;
  const soft = pf.status === 'LIKELY_DUPLICATE';
  const title = soft ? 'Возможно, это оно' : 'Чел, такой релиз уже есть';
  const subtitle = soft
    ? 'Похоже на то, что вы добавляете. Добавить найденное — или всё равно создать своё?'
    : 'Вот он. Добавить в коллекцию?';

  return (
    <View style={styles.root}>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={[styles.header, { paddingTop: insetsTop + Spacing.sm }]}>
        <Pressable onPress={onClose} hitSlop={12} style={styles.headerBtn}>
          <Icon name="arrow-left" size={24} color="default" />
        </Pressable>
        <Text style={styles.headerTitle}>Уже есть</Text>
        <View style={styles.headerBtn} />
      </View>

      <ScrollView contentContainerStyle={styles.scroll}>
        <View style={styles.stepGap}>
          <Text style={styles.stepTitle}>{title}</Text>
          <Text style={styles.stepHint}>{subtitle}</Text>

          <Card style={styles.foundCard}>
            <View style={styles.foundThumb}>
              {m?.cover_image_url ? (
                <Image source={{ uri: m.cover_image_url }} style={styles.foundThumbImg} resizeMode="cover" />
              ) : (
                <Icon name="disc-outline" size={28} color="secondary" />
              )}
            </View>
            <View style={styles.flex}>
              <Text style={styles.albumTitle} numberOfLines={2}>
                {m ? m.title : 'Релиз в Discogs'}
              </Text>
              <Text style={styles.albumMeta} numberOfLines={1}>
                {m ? `${m.artist}${m.year ? ` · ${m.year}` : ''}` : 'Добавится из Discogs'}
              </Text>
            </View>
          </Card>
        </View>
      </ScrollView>

      <View style={[styles.footer, { paddingBottom: insetsBottom + Spacing.md }]}>
        <Button title="Добавить в коллекцию" onPress={onAddFound} loading={adding} />
        {soft && (
          <Pressable onPress={onCreateAnyway} style={styles.skip}>
            <Text style={styles.skipText}>Всё равно создать своё</Text>
          </Pressable>
        )}
      </View>
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
      <Text style={styles.stepTitle}>Сфотографируй релиз</Text>
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

      <View>
        <Text style={styles.fieldLabel}>Формат</Text>
        <View style={styles.segment}>
          {FORMAT_OPTIONS.map((opt) => {
            const active = draft.format === opt.value;
            return (
              <Pressable
                key={opt.value}
                onPress={() => {
                  Haptics.selectionAsync();
                  patch({ format: opt.value });
                }}
                style={[styles.segmentItem, active && styles.segmentItemActive]}
              >
                <Text style={[styles.segmentText, active && styles.segmentTextActive]}>
                  {opt.label}
                </Text>
              </Pressable>
            );
          })}
        </View>
      </View>
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
  loadingWrap: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  editCoverRow: { flexDirection: 'row', gap: Spacing.md },
  // format-сегмент (§9)
  fieldLabel: { ...Typography.bodySmall, color: Colors.textSecondary, marginBottom: Spacing.xs },
  segment: {
    flexDirection: 'row',
    gap: Spacing.xs,
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.md,
    padding: 4,
  },
  segmentItem: {
    flex: 1,
    paddingVertical: Spacing.sm,
    borderRadius: BorderRadius.sm,
    alignItems: 'center',
  },
  segmentItemActive: { backgroundColor: Colors.royalBlue },
  segmentText: { ...Typography.buttonSmall, color: Colors.textSecondary },
  segmentTextActive: { color: '#fff' },
  // перехват дубля (§10)
  foundCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.md,
    padding: Spacing.md,
    marginTop: Spacing.sm,
  },
  foundThumb: {
    width: 56,
    height: 56,
    borderRadius: BorderRadius.sm,
    backgroundColor: Colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
  },
  foundThumbImg: { width: '100%', height: '100%' },
});
