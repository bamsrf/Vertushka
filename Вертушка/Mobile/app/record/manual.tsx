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
 * Бэкенд: docs/plans/collection/USER_SUBMITTED_RECORDS.md
 *   - POST  /records/preflight/      (дабл-чек Discogs + Маркет)
 *   - GET   /records/spotify-search/ (автозаполнение)
 *   - POST  /records/user/           (создание)
 *   - PATCH /records/user/{id}       (правка автором)
 */
import { useState, useCallback, useEffect, useRef, useMemo } from 'react';
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
  Modal,
  FlatList,
  TextInput,
  Keyboard,
  Alert,
  ActionSheetIOS,
} from 'react-native';
import { useRouter, Stack, useLocalSearchParams } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import * as Haptics from 'expo-haptics';
import * as ImagePicker from 'expo-image-picker';
import * as ImageManipulator from 'expo-image-manipulator';
import { LinearGradient } from 'expo-linear-gradient';
import { Icon } from '@/components/ui';
import { Button, Input, Card } from '../../components/ui';
import { toast } from '../../lib/toast';
import { api, apiErrorText, getCoverUrl } from '../../lib/api';
import { useCollectionStore } from '../../lib/store';
import type { SpotifyAlbumCandidate, VinylRecord, PreflightResponse, RecordSearchResult } from '../../lib/types';
import { Colors, Typography, Spacing, BorderRadius, ComponentSizes, Gradients, Shadows } from '../../constants/theme';
import { COUNTRIES } from '../../constants/countries';

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

// Текст ошибки из ответа бэка — общий парсер `detail` живёт в lib/api.
const errorText = apiErrorText;

/**
 * Снимок или файл из галереи → квадратный base64 JPEG (≤1024px).
 *
 * allowsEditing обязателен. Без него из галереи брали исходник целиком: кадр
 * с полкой, столом и половиной соседней пластинки уезжал в обложку как есть, а
 * карточка потом обрезала его по центру — то есть кроп всё равно происходил,
 * просто вслепую и не там, где нужно. Теперь рамку ставит человек.
 *
 * aspect работает на Android; на iOS нативный редактор и так квадратный.
 * Контракт тот же, что у аватара в профиле (app/profile.tsx).
 */
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
  const launch = fromCamera
    ? ImagePicker.launchCameraAsync
    : ImagePicker.launchImageLibraryAsync;
  const res = await launch({
    mediaTypes: ['images'],
    allowsEditing: true,
    aspect: [1, 1],
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

// Спросить источник фото. Камера-по-умолчанию отрезала половину кейсов: обложку
// часто снимают заранее или сохраняют из переписки, и переснять её негде.
// Возвращает выбранное действие; null — юзер закрыл меню.
function askPhotoSource(hasPhoto: boolean): Promise<'library' | 'camera' | 'remove' | null> {
  const options = hasPhoto
    ? ['Выбрать из галереи', 'Сделать фото', 'Убрать фото', 'Отмена']
    : ['Выбрать из галереи', 'Сделать фото', 'Отмена'];
  const cancelIndex = options.length - 1;
  const map: Array<'library' | 'camera' | 'remove'> = hasPhoto
    ? ['library', 'camera', 'remove']
    : ['library', 'camera'];

  return new Promise((resolve) => {
    if (Platform.OS === 'ios') {
      ActionSheetIOS.showActionSheetWithOptions(
        {
          options,
          cancelButtonIndex: cancelIndex,
          destructiveButtonIndex: hasPhoto ? 2 : undefined,
        },
        (index) => resolve(map[index] ?? null),
      );
      return;
    }
    const buttons: any[] = [
      { text: 'Выбрать из галереи', onPress: () => resolve('library') },
      { text: 'Сделать фото', onPress: () => resolve('camera') },
    ];
    if (hasPhoto) {
      buttons.push({ text: 'Убрать фото', style: 'destructive', onPress: () => resolve('remove') });
    }
    buttons.push({ text: 'Отмена', style: 'cancel', onPress: () => resolve(null) });
    Alert.alert('Обложка', undefined, buttons, { cancelable: true, onDismiss: () => resolve(null) });
  });
}


// ─── Черновик ────────────────────────────────────────────────────────────────

interface Draft {
  coverPhoto: string | null;       // display uri
  coverBase64: string | null;      // для отправки
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
const STEP_LABELS = ['Фото', 'Discogs', 'Детали'];

// ─── Экран ───────────────────────────────────────────────────────────────────

export default function ManualRecordScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { editId } = useLocalSearchParams<{ editId?: string }>();
  const isEdit = !!editId;
  const addToCollection = useCollectionStore((s) => s.addToCollection);
  const addToCollectionByRecordId = useCollectionStore((s) => s.addToCollectionByRecordId);
  const addToCollectionWithPhoto = useCollectionStore((s) => s.addToCollectionWithPhoto);

  const [step, setStep] = useState<Step>(0);
  const [draft, setDraft] = useState<Draft>(EMPTY_DRAFT);
  const [submitting, setSubmitting] = useState(false);
  const [loadingEdit, setLoadingEdit] = useState(isEdit);
  // Дедуп-перехват (§10): найденный релиз + статус preflight.
  const [intercept, setIntercept] = useState<PreflightResponse | null>(null);
  const [adding, setAdding] = useState(false);
  // Discogs-поиск в шаге 2: id записи, которую сейчас добавляем.
  const [addingDiscogsId, setAddingDiscogsId] = useState<string | null>(null);
  // Текст поиска Discogs живёт на уровне экрана — не теряется между шагами и
  // префиллит детали при переходе «Далее».
  const [searchQuery, setSearchQuery] = useState('');
  // Пока открыта клавиатура — прячем нижнюю кнопку на всех шагах: жать «Далее»/
  // «Добавить» посреди ввода нелогично, а без футера контент занимает всё место
  // над клавиатурой. Слушаем keyboardWillShow/Hide (fires до анимации → без прыжка).
  const [keyboardVisible, setKeyboardVisible] = useState(false);
  useEffect(() => {
    const showEvt = Platform.OS === 'ios' ? 'keyboardWillShow' : 'keyboardDidShow';
    const hideEvt = Platform.OS === 'ios' ? 'keyboardWillHide' : 'keyboardDidHide';
    const show = Keyboard.addListener(showEvt, () => setKeyboardVisible(true));
    const hide = Keyboard.addListener(hideEvt, () => setKeyboardVisible(false));
    return () => { show.remove(); hide.remove(); };
  }, []);

  const patch = useCallback(
    (p: Partial<Draft>) => setDraft((d) => ({ ...d, ...p })),
    []
  );

  // Замена обложки в edit-режиме (§11). Тап по слоту → камера/галерея.
  const pickCover = useCallback(() => pickCoverInto(draft, patch), [draft, patch]);

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
    // Переход с шага Discogs → префиллим детали текстом поиска, чтобы не терять
    // набранное. «Артист — Название» разбиваем по тире; иначе всё в название.
    if (step === 1) {
      const q = searchQuery.trim();
      if (q && !draft.artist.trim() && !draft.title.trim()) {
        const parts = q.split(/\s+[—–-]\s+/);
        if (parts.length >= 2) {
          patch({ artist: parts[0].trim(), title: parts.slice(1).join(' — ').trim() });
        } else {
          patch({ title: q });
        }
      }
    }
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
      });
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      toast.success('Добавлено', 'Релиз в вашей коллекции', { position: 'bottom' });
      router.back();
    } catch (e: any) {
      toast.error('Не удалось добавить', errorText(e), {
        position: 'bottom',
      });
    } finally {
      setSubmitting(false);
    }
  };

  // §4: выбор Discogs-результата в шаге 2 → добавляем настоящую Discogs-запись
  // (по discogs_id). Она оседает в БД + search-индексе (бэкенд-хук). Не user-record.
  const addDiscogsRecord = async (discogsId: string) => {
    setAddingDiscogsId(discogsId);
    try {
      // Юзер сфоткал свою пластинку → показываем его обложку даже на готовом
      // Discogs-релизе (§: своё фото поверх Discogs).
      if (draft.coverPhoto) {
        await addToCollectionWithPhoto({ discogsId, photoUri: draft.coverPhoto });
      } else {
        await addToCollection(discogsId);
      }
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      toast.success('Добавлено', 'Релиз в вашей коллекции', { position: 'bottom' });
      router.back();
    } catch (e: any) {
      toast.error('Не удалось добавить', errorText(e), {
        position: 'bottom',
      });
    } finally {
      setAddingDiscogsId(null);
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
          toast.error('Не удалось сохранить', errorText(e), {
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
      toast.error('Не удалось добавить', errorText(e), {
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
      const photoUri = draft.coverPhoto;
      if (intercept.match?.id) {
        photoUri
          ? await addToCollectionWithPhoto({ recordId: intercept.match.id, photoUri })
          : await addToCollectionByRecordId(intercept.match.id);
      } else if (intercept.discogs_id) {
        photoUri
          ? await addToCollectionWithPhoto({ discogsId: intercept.discogs_id, photoUri })
          : await addToCollection(intercept.discogs_id);
      }
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      toast.success('Добавлено', 'Релиз в вашей коллекции', { position: 'bottom' });
      router.back();
    } catch (e: any) {
      toast.error('Не удалось добавить', errorText(e), {
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
          {/* Шаг Discogs: поиск закреплён сверху, результаты — в своём скролле,
              чтобы футер и клавиатура не налипали на строку поиска. */}
          {!isEdit && step === 1 ? (
            <DiscogsStep
              query={searchQuery}
              onQueryChange={setSearchQuery}
              onAdd={addDiscogsRecord}
              addingId={addingDiscogsId}
            />
          ) : (
            <ScrollView
              style={styles.flex}
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
                  {step === 2 && <DetailsStep draft={draft} patch={patch} />}
                </>
              )}
            </ScrollView>
          )}

          {/* Нижняя кнопка. Прячем пока открыта клавиатура — на любом шаге. */}
          {!keyboardVisible && (
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
          )}
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
  // Для DUPLICATE/LIKELY_DUPLICATE найденное лежит в match (наш Record), для
  // FOUND_IN_DISCOGS — в discogs_match. Приводим к одному виду, чтобы карточка
  // всегда показывала, ЧТО именно добавится (без этого юзер жал вслепую).
  const dm = pf.discogs_match;
  const m = pf.match
    ? {
        title: pf.match.title,
        artist: pf.match.artist,
        year: pf.match.year,
        cover_image_url: getCoverUrl(pf.match),
      }
    : dm
    ? {
        title: dm.title,
        artist: dm.artist,
        year: dm.year,
        cover_image_url: dm.cover_image_url,
      }
    : null;
  // «Мягкий» перехват = юзеру можно настоять на своём. Это и fuzzy-матч по нашей
  // базе, и находка в Discogs: и то и другое может ошибиться.
  const soft = pf.status === 'LIKELY_DUPLICATE' || pf.status === 'FOUND_IN_DISCOGS';
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
                {m?.title || 'Релиз в Discogs'}
              </Text>
              <Text style={styles.albumMeta} numberOfLines={1}>
                {m
                  ? [m.artist, m.year].filter(Boolean).join(' · ') || 'Добавится из Discogs'
                  : 'Добавится из Discogs'}
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
  return (
    <View style={styles.stepGap}>
      <Text style={styles.stepTitle}>Обложка релиза</Text>
      <Text style={styles.stepHint}>
        Сфотографируй или выбери из галереи — без обложки релиз не добавить.
      </Text>

      <View style={styles.photoSingleRow}>
        <PhotoSlot
          label="Обложка"
          required
          uri={draft.coverPhoto}
          onPress={() => pickCoverInto(draft, patch)}
          wrapStyle={styles.slotWrapSingle}
        />
      </View>
    </View>
  );
}

/** Общий обработчик слота обложки: меню источника → снимок/галерея/сброс. */
async function pickCoverInto(draft: Draft, patch: (p: Partial<Draft>) => void) {
  Haptics.selectionAsync();
  // «Убрать» показываем только для только что выбранного файла: в edit-режиме
  // в слоте лежит серверная обложка, и сброс локального стейта её бы не удалил —
  // кнопка обещала бы то, чего не делает.
  const action = await askPhotoSource(!!draft.coverBase64);
  if (!action) return;
  if (action === 'remove') {
    patch({ coverPhoto: null, coverBase64: null });
    return;
  }
  const picked = await pickPhotoBase64(action === 'camera');
  if (picked) patch({ coverPhoto: picked.uri, coverBase64: picked.base64 });
}

function PhotoSlot({
  label,
  required,
  uri,
  onPress,
  wrapStyle,
}: {
  label: string;
  required?: boolean;
  uri: string | null;
  onPress: () => void;
  wrapStyle?: object;
}) {
  const filled = !!uri;
  return (
    <Pressable onPress={onPress} style={[styles.slotWrap, wrapStyle]}>
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

// ─── Шаг 1: поиск в Discogs ────────────────────────────────────────────────────

function DiscogsStep({
  query,
  onQueryChange,
  onAdd,
  addingId,
}: {
  query: string;
  onQueryChange: (text: string) => void;
  onAdd: (discogsId: string) => void;
  addingId: string | null;
}) {
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<RecordSearchResult[]>([]);
  const [searched, setSearched] = useState(false);
  // Debounce-таймер + счётчик запросов (отбрасываем устаревшие ответы при
  // быстром наборе, чтобы не было гонки порядка результатов).
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reqId = useRef(0);

  const runSearch = useCallback(async (raw: string) => {
    const q = raw.trim();
    if (!q) return;
    const id = ++reqId.current;
    setLoading(true);
    setSearched(true);
    try {
      const r = await api.searchRecords(q);
      if (id !== reqId.current) return;
      setResults(r.results);
    } catch {
      if (id !== reqId.current) return;
      setResults([]);
    } finally {
      if (id === reqId.current) setLoading(false);
    }
  }, []);

  // Живой поиск по образцу основного экрана: debounce 400мс при наборе ≥2
  // символов, без нажатия на лупу. Лупа = немедленный триггер.
  const onChange = useCallback((text: string) => {
    onQueryChange(text);
    if (timer.current) clearTimeout(timer.current);
    if (text.trim().length >= 2) {
      timer.current = setTimeout(() => runSearch(text), 400);
    } else {
      reqId.current++; // гасим возможный висящий ответ
      setResults([]);
      setSearched(false);
      setLoading(false);
    }
  }, [runSearch, onQueryChange]);

  const onSubmit = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    runSearch(query);
  }, [query, runSearch]);

  // Возврат на шаг с уже набранным запросом — восстанавливаем выдачу.
  useEffect(() => {
    if (query.trim().length >= 2 && results.length === 0 && !searched) {
      runSearch(query);
    }
    return () => { if (timer.current) clearTimeout(timer.current); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <View style={styles.flex}>
      {/* Закреплённая шапка: заголовок + строка поиска. */}
      <View style={styles.discogsHead}>
        <Text style={styles.stepTitle}>Найти в Discogs</Text>
        <Text style={styles.stepHint}>
          Если релиз уже есть в Discogs — выбери его, добавим со всеми данными.
          Нет в списке — пропусти и заполни вручную.
        </Text>
        <View style={styles.searchRow}>
          <View style={styles.flex}>
            <Input
              value={query}
              onChangeText={onChange}
              placeholder="Kendrick Lamar — DAMN"
            />
          </View>
          <Pressable onPress={onSubmit} style={styles.searchBtn}>
            <Icon name="magnifying-glass" size={20} color="onBrand" />
          </Pressable>
        </View>
      </View>

      <FlatList
        data={results}
        keyExtractor={(r) => r.discogs_id}
        style={styles.flex}
        contentContainerStyle={styles.discogsList}
        keyboardShouldPersistTaps="handled"
        keyboardDismissMode="on-drag"
        ListHeaderComponent={
          loading ? <ActivityIndicator color={Colors.royalBlue} style={styles.mt16} /> : null
        }
        ListEmptyComponent={
          searched && !loading ? (
            <View style={styles.sparkleNote}>
              <Icon name="sparkles" size={16} color="accent" />
              <Text style={styles.sparkleText}>
                Не нашлось — нажми «Пропустить» и заполни вручную.
              </Text>
            </View>
          ) : null
        }
        renderItem={({ item: r }) => {
          const cover = getCoverUrl(r);
          const busy = addingId === r.discogs_id;
          return (
            <Pressable onPress={() => !addingId && onAdd(r.discogs_id)}>
              <Card style={styles.albumCard}>
                <View style={styles.albumThumb}>
                  {cover ? (
                    <Image source={{ uri: cover }} style={styles.albumThumbImg} resizeMode="cover" />
                  ) : (
                    <Icon name="disc-outline" size={22} color="secondary" />
                  )}
                </View>
                <View style={styles.flex}>
                  <Text style={styles.albumTitle} numberOfLines={1}>
                    {r.title}
                  </Text>
                  <Text style={styles.albumMeta} numberOfLines={1}>
                    {r.artist}
                    {r.year ? ` · ${r.year}` : ''}
                    {r.format_type ? ` · ${r.format_type}` : ''}
                  </Text>
                </View>
                {busy ? (
                  <ActivityIndicator color={Colors.royalBlue} />
                ) : (
                  <Icon name="plus" size={22} color="brand" />
                )}
              </Card>
            </Pressable>
          );
        }}
      />
    </View>
  );
}

// ─── Шаг 2: детали ───────────────────────────────────────────────────────────

function DetailsStep({ draft, patch }: StepProps) {
  const [picker, setPicker] = useState<null | 'year' | 'country'>(null);
  // draft.country хранит value (англ. имя как в Discogs) → показываем рус. label.
  const countryLabel = draft.country
    ? (COUNTRIES.find((c) => c.value === draft.country)?.label ?? draft.country)
    : '';

  return (
    <View style={styles.stepGap}>
      <Text style={styles.stepTitle}>Детали издания</Text>
      <Text style={styles.stepHint}>
        Поля со звёздочкой обязательны. Год и страну выбери из списка — так не
        будет ошибок при добавлении.
      </Text>

      <Input label="Артист *" value={draft.artist} onChangeText={(v) => patch({ artist: v })} placeholder="Антоха МС" />
      <Input label="Название *" value={draft.title} onChangeText={(v) => patch({ title: v })} placeholder="Родня" />
      <PickerField
        label="Год"
        value={draft.year}
        placeholder="Выбрать год"
        onPress={() => {
          Haptics.selectionAsync();
          setPicker('year');
        }}
      />
      <Input label="Лейбл" value={draft.label} onChangeText={(v) => patch({ label: v })} placeholder="Самиздат" />
      <Input label="Каталожный №" value={draft.catalog} onChangeText={(v) => patch({ catalog: v })} placeholder="—" />
      <PickerField
        label="Страна"
        value={countryLabel}
        placeholder="Выбрать страну"
        onPress={() => {
          Haptics.selectionAsync();
          setPicker('country');
        }}
      />

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

      <YearWheelSheet
        visible={picker === 'year'}
        selected={draft.year}
        onSelect={(v) => patch({ year: v })}
        onClose={() => setPicker(null)}
      />
      <CountryPickerModal
        visible={picker === 'country'}
        selected={draft.country}
        onSelect={(v) => patch({ country: v })}
        onClose={() => setPicker(null)}
      />
    </View>
  );
}

// ─── Пикер-филд + bottom-sheet пикер (год / страна) ───────────────────────────

interface PickerOption {
  value: string;
  label: string;
}

// Год: текущий … 1900 (в пределах бэкенд-границы ge=1900, le=2100). Топ —
// текущий год, обновляется автоматически (new Date). Первый пункт — сброс.
const CURRENT_YEAR = new Date().getFullYear();
const YEAR_PICKER_OPTIONS: PickerOption[] = [
  { value: '', label: '—' },
  ...Array.from({ length: CURRENT_YEAR - 1900 + 1 }, (_, i) => {
    const y = CURRENT_YEAR - i;
    return { value: String(y), label: String(y) };
  }),
];

const COUNTRY_PICKER_OPTIONS: PickerOption[] = [
  { value: '', label: '— Не указана' },
  ...COUNTRIES,
];

function PickerField({
  label,
  value,
  placeholder,
  onPress,
}: {
  label: string;
  value: string;
  placeholder: string;
  onPress: () => void;
}) {
  const filled = !!value;
  return (
    <View style={styles.pickerFieldWrap}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <Pressable
        onPress={onPress}
        style={({ pressed }) => [styles.pickerField, pressed && styles.pressedField]}
      >
        <Text style={[styles.pickerValue, !filled && styles.pickerPlaceholder]} numberOfLines={1}>
          {filled ? value : placeholder}
        </Text>
        <Icon name="chevron-down" size={18} color="secondary" />
      </Pressable>
    </View>
  );
}

// ── Крутилка (iOS-style wheel) — компактный вертикальный пикер ────────────────

const WHEEL_ITEM_H = 40;
const WHEEL_VISIBLE = 5; // нечётное — центральный слот подсвечен

function WheelPicker({
  data,
  selectedValue,
  onChange,
}: {
  data: PickerOption[];
  selectedValue: string;
  onChange: (value: string) => void;
}) {
  const scrollRef = useRef<ScrollView>(null);
  const didInit = useRef(false);

  const indexOf = (v: string) => {
    const i = data.findIndex((d) => d.value === v);
    return i < 0 ? 0 : i;
  };

  // Первичная установка на выбранное значение (без анимации).
  const onLayout = () => {
    if (didInit.current) return;
    didInit.current = true;
    scrollRef.current?.scrollTo({ y: indexOf(selectedValue) * WHEEL_ITEM_H, animated: false });
  };

  const commit = (y: number) => {
    const i = Math.min(data.length - 1, Math.max(0, Math.round(y / WHEEL_ITEM_H)));
    if (data[i].value !== selectedValue) {
      Haptics.selectionAsync();
      onChange(data[i].value);
    }
  };

  const fadeH = WHEEL_ITEM_H * ((WHEEL_VISIBLE - 1) / 2);

  return (
    <View style={styles.wheelWrap} onLayout={onLayout}>
      {/* Подсветка центрального слота */}
      <View pointerEvents="none" style={styles.wheelBand} />
      <ScrollView
        ref={scrollRef}
        showsVerticalScrollIndicator={false}
        snapToInterval={WHEEL_ITEM_H}
        decelerationRate="fast"
        onMomentumScrollEnd={(e) => commit(e.nativeEvent.contentOffset.y)}
        contentContainerStyle={{ paddingVertical: fadeH }}
      >
        {data.map((d, i) => {
          const active = d.value === selectedValue;
          return (
            <View key={d.value || `_${i}`} style={styles.wheelItem}>
              <Text style={[styles.wheelText, active && styles.wheelTextActive]} numberOfLines={1}>
                {d.label}
              </Text>
            </View>
          );
        })}
      </ScrollView>
      {/* Fade к фону сверху и снизу — как в iOS-пикере */}
      <LinearGradient
        pointerEvents="none"
        colors={[Colors.background, `${Colors.background}00`]}
        style={[styles.wheelFade, { top: 0, height: fadeH }]}
      />
      <LinearGradient
        pointerEvents="none"
        colors={[`${Colors.background}00`, Colors.background]}
        style={[styles.wheelFade, { bottom: 0, height: fadeH }]}
      />
    </View>
  );
}

// Год: bottom-sheet с крутилкой. Значение применяется на «Готово».
function YearWheelSheet({
  visible,
  selected,
  onSelect,
  onClose,
}: {
  visible: boolean;
  selected: string;
  onSelect: (value: string) => void;
  onClose: () => void;
}) {
  const insets = useSafeAreaInsets();
  const [temp, setTemp] = useState(selected);

  useEffect(() => {
    if (visible) setTemp(selected);
  }, [visible, selected]);

  if (!visible) return null;

  return (
    <Modal visible transparent animationType="slide" onRequestClose={onClose}>
      <View style={styles.sheetOverlay}>
        {/* Мягкий fade к затемнению (плотнее у листа), а не плоская плашка */}
        <LinearGradient pointerEvents="none" colors={Gradients.overlay} style={StyleSheet.absoluteFill} />
        {/* Тап по затемнению закрывает; сам лист — сосед, чтобы скролл крутилки не перехватывался */}
        <Pressable style={StyleSheet.absoluteFill} onPress={onClose} />
        <View style={[styles.sheet, { paddingBottom: insets.bottom + Spacing.md }]}>
          <View style={styles.sheetHandle} />
          <Text style={styles.sheetTitle}>Год издания</Text>
          <WheelPicker data={YEAR_PICKER_OPTIONS} selectedValue={temp} onChange={setTemp} />
          <View style={styles.wheelActions}>
            <Button
              title="Готово"
              onPress={() => {
                onSelect(temp);
                onClose();
              }}
            />
            <Pressable
              onPress={() => {
                onSelect('');
                onClose();
              }}
              style={styles.skip}
            >
              <Text style={styles.skipText}>Сбросить год</Text>
            </Pressable>
          </View>
        </View>
      </View>
    </Modal>
  );
}

// Страна: полноэкранный модал. Поле поиска закреплено сверху — клавиатура не
// перекрывает ввод (баг: не было видно, что печатаешь).
function CountryPickerModal({
  visible,
  selected,
  onSelect,
  onClose,
}: {
  visible: boolean;
  selected: string;
  onSelect: (value: string) => void;
  onClose: () => void;
}) {
  const insets = useSafeAreaInsets();
  const [query, setQuery] = useState('');

  useEffect(() => {
    if (!visible) setQuery('');
  }, [visible]);

  const data = useMemo(() => {
    if (!query.trim()) return COUNTRY_PICKER_OPTIONS;
    const ql = query.trim().toLowerCase();
    return COUNTRY_PICKER_OPTIONS.filter(
      (o) => o.label.toLowerCase().includes(ql) || o.value.toLowerCase().includes(ql)
    );
  }, [query]);

  if (!visible) return null;

  return (
    <Modal visible animationType="slide" onRequestClose={onClose}>
      <View style={styles.countryRoot}>
        <View style={[styles.header, { paddingTop: insets.top + Spacing.sm }]}>
          <Pressable onPress={onClose} hitSlop={12} style={styles.headerBtn}>
            <Icon name="arrow-left" size={24} color="default" />
          </Pressable>
          <Text style={styles.headerTitle}>Страна</Text>
          <View style={styles.headerBtn} />
        </View>

        <View style={styles.countrySearchWrap}>
          <View style={styles.sheetSearch}>
            <Icon name="magnifying-glass" size={18} color="secondary" />
            <TextInput
              value={query}
              onChangeText={setQuery}
              placeholder="Поиск страны"
              placeholderTextColor={Colors.textMuted}
              style={styles.sheetSearchInput}
              autoCorrect={false}
              autoCapitalize="none"
              autoFocus
            />
          </View>
        </View>

        <FlatList
          data={data}
          keyExtractor={(o) => o.value || '__empty'}
          keyboardShouldPersistTaps="handled"
          keyboardDismissMode="on-drag"
          contentContainerStyle={{
            paddingHorizontal: Spacing.md,
            paddingBottom: insets.bottom + Spacing.xl,
          }}
          ListEmptyComponent={
            <View style={styles.sparkleNote}>
              <Text style={styles.sparkleText}>Ничего не нашлось</Text>
            </View>
          }
          renderItem={({ item }) => {
            const active = item.value === selected;
            return (
              <Pressable
                onPress={() => {
                  Haptics.selectionAsync();
                  onSelect(item.value);
                  onClose();
                }}
                style={({ pressed }) => [styles.sheetRow, pressed && styles.pressedRow]}
              >
                <Text style={[styles.sheetRowText, active && styles.sheetRowTextActive]}>
                  {item.label}
                </Text>
                {active && <Icon name="check" size={18} color="brand" />}
              </Pressable>
            );
          }}
        />
      </View>
    </Modal>
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
  photoSingleRow: { alignItems: 'center', marginTop: Spacing.sm },
  slotWrapSingle: { flex: 0, width: '64%', maxWidth: 260 },
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
    overflow: 'hidden',
  },
  albumThumbImg: { width: '100%', height: '100%' },
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
    backgroundColor: Colors.background,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: Colors.divider,
    gap: Spacing.sm,
  },
  skip: { alignItems: 'center', paddingVertical: Spacing.xs },
  skipText: { ...Typography.bodySmall, color: Colors.textMuted },
  loadingWrap: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  editCoverRow: { flexDirection: 'row', gap: Spacing.md },
  // пикер-филд (год / страна) — визуально как Input
  pickerFieldWrap: { marginBottom: Spacing.md },
  pickerField: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    height: ComponentSizes.inputHeight,
    paddingHorizontal: Spacing.md,
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.xl,
    borderWidth: 1.5,
    borderColor: Colors.border,
  },
  pickerValue: { ...Typography.body, color: Colors.text, flex: 1 },
  pickerPlaceholder: { color: Colors.textMuted },
  pressedField: { opacity: 0.7, borderColor: Colors.royalBlue },
  pressedRow: { opacity: 0.6 },
  // шаг Discogs: закреплённая шапка + скролл результатов
  discogsHead: { paddingHorizontal: Spacing.md, paddingTop: Spacing.md, gap: Spacing.md },
  discogsList: { paddingHorizontal: Spacing.md, paddingTop: Spacing.md, paddingBottom: Spacing.xxl, gap: Spacing.sm },
  // крутилка года
  wheelWrap: { height: WHEEL_ITEM_H * WHEEL_VISIBLE, justifyContent: 'center' },
  wheelBand: {
    position: 'absolute',
    left: 0,
    right: 0,
    top: WHEEL_ITEM_H * ((WHEEL_VISIBLE - 1) / 2),
    height: WHEEL_ITEM_H,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderColor: Colors.border,
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.sm,
  },
  wheelItem: { height: WHEEL_ITEM_H, alignItems: 'center', justifyContent: 'center' },
  wheelFade: { position: 'absolute', left: 0, right: 0 },
  wheelText: { ...Typography.body, color: Colors.textMuted, fontVariant: ['tabular-nums'] },
  wheelTextActive: { color: Colors.text, fontWeight: '700', fontSize: 20 },
  wheelActions: { marginTop: Spacing.md, gap: Spacing.xs },
  // модал страны
  countryRoot: { flex: 1, backgroundColor: Colors.background },
  countrySearchWrap: { paddingHorizontal: Spacing.md, paddingBottom: Spacing.sm },
  // bottom-sheet пикер
  sheetOverlay: { flex: 1, justifyContent: 'flex-end' },
  sheet: {
    backgroundColor: Colors.background,
    borderTopLeftRadius: BorderRadius.lg,
    borderTopRightRadius: BorderRadius.lg,
    paddingTop: Spacing.sm,
    paddingHorizontal: Spacing.md,
    maxHeight: '70%',
    ...Shadows.lg,
    shadowOffset: { width: 0, height: -8 },
  },
  sheetHandle: {
    alignSelf: 'center',
    width: 40,
    height: 4,
    borderRadius: 2,
    backgroundColor: Colors.border,
    marginBottom: Spacing.sm,
  },
  sheetTitle: { ...Typography.h3, color: Colors.text, marginBottom: Spacing.sm },
  sheetSearch: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
    height: ComponentSizes.inputHeight,
    paddingHorizontal: Spacing.md,
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.xl,
    borderWidth: 1.5,
    borderColor: Colors.border,
    marginBottom: Spacing.sm,
  },
  sheetSearchInput: { flex: 1, ...Typography.body, color: Colors.text, padding: 0 },
  sheetList: { flexGrow: 0 },
  sheetRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: Spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: Colors.divider,
  },
  sheetRowText: { ...Typography.body, color: Colors.text, fontVariant: ['tabular-nums'] },
  sheetRowTextActive: { color: Colors.royalBlue, fontWeight: '600' },
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
