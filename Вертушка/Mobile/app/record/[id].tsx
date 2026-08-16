/**
 * Экран детальной информации о пластинке — Blue Gradient Edition
 */
import { useEffect, useState, useCallback, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  ActivityIndicator,
  Alert,
  TouchableOpacity,
} from 'react-native';
import { toast } from '../../lib/toast';
import * as Haptics from 'expo-haptics';
import { Image } from 'expo-image';
import { useLocalSearchParams, useRouter, useFocusEffect } from 'expo-router';
import { Icon } from '@/components/ui';
import Animated, {
  Easing,
  useAnimatedStyle,
  useSharedValue,
  withDelay,
  withRepeat,
  withSequence,
  withTiming,
} from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { LinearGradient } from 'expo-linear-gradient';
import { BlurView } from 'expo-blur';
import { Header } from '../../components/Header';
import { GradientText } from '../../components/GradientText';
import { FolderPickerModal } from '../../components/FolderPickerModal';
import { Button, Card, ActionSheet, ActionSheetAction } from '../../components/ui';
import { api, getMasterCoverUrl, getPlaceholderCoverUrl } from '../../lib/api';
import { analytics } from '../../lib/analytics';
import { countSpin } from '../../lib/eggTracker';
import { cleanArtistName } from '../../lib/format';
import { useCollectionStore, useAuthStore } from '../../lib/store';
import { VinylRecord, CollectionItem, PriceHistoryResponse } from '../../lib/types';
import { Colors, Typography, Spacing, BorderRadius, Gradients } from '../../constants/theme';
import { ms } from '../../lib/responsive';
import { VinylColorTag } from '../../components/VinylColorTag';
import { VinylSpinner } from '../../components/VinylSpinner';
import { OffersBlock } from '../../components/OffersBlock';
import { CoachTip } from '../../components/onboarding/CoachTip';
import { CoachPulse } from '../../components/onboarding/CoachPulse';
import { useCoachMark } from '../../lib/useCoachMark';
import { useRecordTour, type RecordTourKey } from '../../lib/recordTour';
import { PriceSparkline } from '../../components/PriceSparkline';
import { RadarIcon } from '../../components/RadarIcon';
import { ThresholdSheet, type ThresholdSheetRef } from '../../components/wishlist/ThresholdSheet';
import { useRadarReopen } from '../../lib/radarReopen';
import { parseVinylColor } from '../../lib/vinylColor';
import { TierFeatureBlock, allRarityTiers } from '../../components/RarityAura';

function getFormatDisplayInfo(format?: string): { label: string; verb: string } {
  if (!format) return { label: 'Винил', verb: 'добавлен' };
  const f = format.toLowerCase();
  if (f.includes('cassette')) return { label: 'Кассета', verb: 'добавлена' };
  if (f.includes('box set')) return { label: 'Бокс-сет', verb: 'добавлен' };
  if (f.includes('cd')) return { label: 'CD', verb: 'добавлен' };
  return { label: 'Винил', verb: 'добавлен' };
}

const AnimatedIcon = Animated.createAnimatedComponent(Icon);

function OtherVersionsButton({ onPress }: { onPress: () => void }) {
  const draw = useSharedValue(0);

  useEffect(() => {
    draw.value = withRepeat(
      withSequence(
        withTiming(-1, { duration: 700, easing: Easing.in(Easing.quad) }),
        withTiming(1.2, { duration: 140, easing: Easing.out(Easing.cubic) }),
        withTiming(0, { duration: 220, easing: Easing.out(Easing.quad) }),
        withDelay(900, withTiming(0, { duration: 0 })),
      ),
      -1,
      false,
    );
  }, [draw]);

  const arrowStyle = useAnimatedStyle(() => ({
    transform: [{ translateX: draw.value * 6 }],
  }));

  return (
    <TouchableOpacity
      style={styles.otherVersionsButton}
      onPress={onPress}
      activeOpacity={0.7}
    >
      <Text style={styles.otherVersionsText}>Смотреть другие версии релиза</Text>
      <AnimatedIcon
        name="chevron-forward"
        size={18}
        color={Colors.text}
        style={arrowStyle}
      />
    </TouchableOpacity>
  );
}

const handleArtistNavigation = async (artistName: string, router: ReturnType<typeof useRouter>) => {
  try {
    const response = await api.searchArtists(artistName, 1, 1);
    if (response.results.length > 0) {
      router.push(`/artist/${response.results[0].artist_id}`);
    }
  } catch {
    // Silently fail — artist search is best-effort
  }
};

export default function RecordDetailScreen() {
  const {
    id,
    folderId,
    folderItemId,
    previewTitle,
    previewArtist,
    previewCover,
    previewThumb,
    previewYear,
    previewBlurhash,
  } = useLocalSearchParams<{
    id: string;
    folderId?: string;
    folderItemId?: string;
    previewTitle?: string;
    previewArtist?: string;
    previewCover?: string;
    previewThumb?: string;
    previewYear?: string;
    previewBlurhash?: string;
  }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [record, setRecord] = useState<VinylRecord | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [priceHistory, setPriceHistory] = useState<PriceHistoryResponse | null>(null);
  const [historyResolved, setHistoryResolved] = useState(false);
  const thresholdSheetRef = useRef<ThresholdSheetRef>(null);
  const radarPulse = useSharedValue(0);
  const radarPulseStyle = useAnimatedStyle(() => ({
    opacity: (1 - radarPulse.value) * 0.55,
    transform: [{ scale: 1 + radarPulse.value * 1.2 }],
  }));
  const hasPreview = Boolean(previewTitle || previewCover || previewThumb || previewArtist);

  // Какие блоки реально отрисуются для этого релиза — по ним и собирается тур.
  // Порядок обязан совпадать с порядком блоков на экране: тур ведёт человека
  // сверху вниз, и прыжок назад заставлял бы искать блок глазами.
  const hasPrice = Boolean(
    record?.estimated_price_median_rub ||
      record?.estimated_price_min_rub ||
      record?.estimated_price_median ||
      record?.estimated_price_min,
  );
  // Блок офферов может быть запрошен, но не отрисован: наличие discogs_id не
  // значит, что магазины что-то предлагают. Для тура важен именно факт
  // отрисовки, поэтому ждём ответ самого блока.
  const [offersCount, setOffersCount] = useState<number | null>(null);
  const offersRequested = Boolean(record?.discogs_id || record?.source === 'store');
  const hasOffers = offersRequested && (offersCount ?? 0) > 0;
  const hasHistory = Boolean(priceHistory && priceHistory.points.length > 0);
  const hasVersions = Boolean(
    record?.discogs_master_id && record.discogs_master_id !== '0',
  );
  const tourKeys: RecordTourKey[] = [
    ...(hasPrice ? (['price'] as const) : []),
    ...(hasOffers ? (['offers'] as const) : []),
    ...(hasHistory ? (['history'] as const) : []),
    ...(hasVersions ? (['versions'] as const) : []),
  ];
  // Тур стартует только когда состав блоков окончательный: офферы и история
  // цен приезжают асинхронно, и запуск по неполному набору отрезал бы шаги,
  // которые дорисуются через секунду.
  const tourReady =
    Boolean(record) && historyResolved && (!offersRequested || offersCount !== null);
  const tour = useRecordTour(tourKeys, tourReady);

  // Подсказка про Маркет разблокируется там, где блок офферов вообще
  // отрисуется, — иначе объясняли бы витрину рядом с пустотой. Пока идёт тур,
  // она молчит: две карточки-объяснения на одном экране спорят друг с другом,
  // и обе читаются хуже.
  const marketTip = useCoachMark('market', hasOffers && !tour.active);

  // Подсказки про свойства самой пластинки. Условие у каждой — факт отрисовки
  // соответствующего блока, поэтому они срабатывают на первом релизе, где это
  // свойство вообще встретилось, а не «через N пластинок в коллекции».
  //
  // Все глушатся на время тура: он объясняет ту же страницу, и две карточки
  // одновременно спорят друг с другом.
  const hasVinylColor = Boolean(record?.display_vinyl_color ?? record?.vinyl_color_raw);
  const rarityTiers = record ? allRarityTiers(record) : [];
  const vinylColorTip = useCoachMark('vinyl-color', hasVinylColor && !tour.active);
  const rarityTip = useCoachMark('rarity-tiers', rarityTiers.length > 0 && !tour.active);
  const offerPriceTip = useCoachMark('offer-price', hasOffers && !tour.active);
  const versionsTip = useCoachMark('other-versions', hasVersions && !tour.active);

  /**
   * Подсказка тура встаёт вплотную НАД блоком, который объясняет, поэтому
   * маршрута «где искать» у неё нет. Крестик здесь — «пропустить весь тур»:
   * человек, которому объяснения не нужны, не должен закрывать их по одному.
   */
  /**
   * Подсказка про свойство этой пластинки. Маршрут не показываем: объясняемый
   * блок стоит в паре строк отсюда и подсвечен — плашка «Карточка релиза →
   * плашка с цветом» повторяла бы то, что и так перед глазами.
   */
  const renderRecordTip = (
    tip: ReturnType<typeof useCoachMark>,
    action?: { label: string; onPress: () => void },
  ) =>
    tip.visible ? (
      <CoachTip
        meta={{ ...tip.meta, where: undefined }}
        analyticsKey={tip.meta.key}
        onDismiss={tip.dismiss}
        action={action}
      />
    ) : null;

  const renderTourTip = (key: RecordTourKey) =>
    tour.isAt(key) && tour.step ? (
      <CoachTip
        meta={tour.step}
        position={tour.position}
        onDismiss={tour.skip}
        action={{ label: tour.isLast ? 'Понятно' : 'Дальше', onPress: tour.next }}
      />
    ) : null;

  // Динамика цены — грузим лениво после появления записи. Тихо игнорим ошибку:
  // блок графика просто не отрисуется, если истории нет.
  useEffect(() => {
    const rid = record?.id;
    if (!rid) return;
    let alive = true;
    setHistoryResolved(false);
    api
      .getPriceHistory(rid, 90)
      .then((res) => {
        if (alive) setPriceHistory(res);
      })
      .catch(() => {})
      // Факт «ответ пришёл» нужен туру: до него нельзя решить, есть график на
      // экране или нет, а стартовать с неполным набором блоков — значит
      // потерять шаг, который дорисуется секундой позже.
      .finally(() => {
        if (alive) setHistoryResolved(true);
      });
    return () => {
      alive = false;
    };
  }, [record?.id]);

  const [showActionSheet, setShowActionSheet] = useState(false);
  const [showFolderPicker, setShowFolderPicker] = useState(false);

  const {
    addToCollection,
    addToCollectionByRecordId,
    addToWishlist,
    addToWishlistByRecordId,
    removeFromCollection,
    removeFromWishlist,
    moveToCollection,
    collectionItems,
    wishlistItems,
    fetchCollectionItems,
    fetchWishlistItems,
    fetchCollections,
    addItemsToFolder,
    isOwned,
  } = useCollectionStore();

  useEffect(() => {
    loadRecord();
  }, [id]);

  // Загружаем и обновляем коллекцию/вишлист при фокусе (включая первый mount)
  useFocusEffect(
    useCallback(() => {
      fetchCollections()
        .then(() => fetchCollectionItems())
        .catch(() => {});
      fetchWishlistItems().catch(() => {});
    }, [fetchCollections, fetchCollectionItems, fetchWishlistItems])
  );

  // Возврат с /radar после «Радар заполнен» → переоткрываем ту же шторку порога,
  // чтобы юзер сразу дозакинул релиз (место мог освободить на радаре).
  useFocusEffect(
    useCallback(() => {
      const pending = useRadarReopen.getState().pending;
      if (!pending || pending.recordId !== id) return;
      useRadarReopen.getState().clear();
      const t = setTimeout(() => thresholdSheetRef.current?.present(pending), 350);
      return () => clearTimeout(t);
    }, [id])
  );

  const getRecordStatus = (): {
    status: import('@/lib/types').RecordStatus;
    copiesCount: number;
    collectionItemId: string | null;
    wishlistItemId: string | null;
    wishlistNotifyMode?: import('@/lib/types').WishlistNotifyMode;
    wishlistPriceThreshold?: number | null;
    wishlistConditions?: import('@/lib/types').WishlistCondition[] | null;
  } => {
    if (!record) {
      return { status: 'not_added', copiesCount: 0, collectionItemId: null, wishlistItemId: null };
    }

    const discogsId = record.discogs_id;
    const recordId = record.id;

    // Гард на null/undefined обязателен: у store-native/user-records discogs_id
    // отсутствует, и `undefined === undefined` ложно слепил бы ВСЕ такие записи
    // с любой другой беz-discogs записью в коллекции → фантомное «Добавлено».
    // Матч только по непустым идентификаторам.
    const collectionCopies = collectionItems.filter(
      (item) =>
        (!!discogsId && item.record.discogs_id === discogsId) ||
        (!!recordId && item.record.id === recordId)
    );

    const wishlistItem = wishlistItems.find(
      (item) =>
        (!!discogsId && item.record.discogs_id === discogsId) ||
        (!!recordId && item.record.id === recordId)
    );

    if (collectionCopies.length > 0) {
      return {
        status: 'in_collection' as const,
        copiesCount: collectionCopies.length,
        collectionItemId: collectionCopies[0].id,
        wishlistItemId: null,
      };
    }

    // Fallback: владение за пределами page-1 collectionItems (большая коллекция,
    // переход с чужой карточки по UUID). collectionItemId неизвестен — действия,
    // которым он нужен (папка/удаление), скрываются в action sheet.
    if (isOwned({ discogsId, recordId })) {
      return {
        status: 'in_collection' as const,
        copiesCount: 1,
        collectionItemId: null,
        wishlistItemId: null,
      };
    }

    if (wishlistItem) {
      return {
        status: 'in_wishlist' as const,
        copiesCount: 0,
        collectionItemId: null,
        wishlistItemId: wishlistItem.id,
        wishlistNotifyMode: wishlistItem.notify_mode ?? 'watched',
        wishlistPriceThreshold: wishlistItem.price_threshold_rub ?? null,
        wishlistConditions: wishlistItem.conditions ?? null,
      };
    }

    return { status: 'not_added' as const, copiesCount: 0, collectionItemId: null, wishlistItemId: null };
  };

  const loadRecord = async () => {
    if (!id) return;

    setIsLoading(true);
    setError(null);

    try {
      // Определяем формат id: UUID или Discogs ID (число)
      const isUUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id);
      const data = isUUID
        ? await api.getRecord(id)
        : await api.getRecordByDiscogsId(id);
      setRecord(data);
      // Середина воронки search → view_record → offer_click. Шлём после
      // успешной загрузки, а не на маунт: открытый экран с ошибкой — это не
      // просмотр карточки.
      analytics.viewRecord(data.discogs_id);
    } catch (err) {
      setError('Не удалось загрузить информацию о пластинке');
    } finally {
      setIsLoading(false);
    }
  };

  const handleAddToCollection = async () => {
    if (!record) return;

    const recordStatus = getRecordStatus();

    // Если пластинка уже в вишлисте - переносим атомарно
    if (recordStatus.status === 'in_wishlist' && recordStatus.wishlistItemId) {
      try {
        await moveToCollection(recordStatus.wishlistItemId);
        // Немедленно обновляем UI - критически важно для правильного отображения кнопок
        await Promise.all([
          fetchCollectionItems(),
          fetchWishlistItems(),
        ]);
        toast.success('Винил перенесён в коллекцию');
      } catch (error: any) {
        const message = error?.response?.data?.detail || error?.message || 'Не удалось перенести в коллекцию';
        toast.error('Ошибка', message);
      }
      return;
    }

    // Иначе просто добавляем в коллекцию. Store-native/user-record без discogs_id
    // добавляем по record_id (UUID) — addToCollection шлёт discogs_id, который
    // у этих записей отсутствует.
    try {
      if (record.discogs_id) {
        await addToCollection(String(record.discogs_id));
      } else {
        await addToCollectionByRecordId(record.id);
      }
      // addToCollection* уже обновляет оба списка
      const fmt = getFormatDisplayInfo(record?.format_type);
      toast.success(`${fmt.label} ${fmt.verb} в коллекцию`);
    } catch (error: any) {
      const message = error?.response?.data?.detail || error?.message || 'Не удалось добавить в коллекцию';
      toast.error('Ошибка', message);
    }
  };

  const handleAddAnotherCopy = () => {
    if (!record) return;
    setShowActionSheet(false);
    Alert.alert(
      'Уже в коллекции',
      `«${record.title}» уже есть в вашей коллекции. Добавить ещё одну копию?`,
      [
        { text: 'Отмена', style: 'cancel' },
        { text: 'Добавить', onPress: handleAddToCollection },
      ]
    );
  };

  const handleAddToWishlist = async () => {
    if (!record) return;

    try {
      if (record.discogs_id) {
        await addToWishlist(String(record.discogs_id));
      } else {
        await addToWishlistByRecordId(record.id);
      }
      const fmt = getFormatDisplayInfo(record?.format_type);
      toast.success(`${fmt.label} ${fmt.verb} в список желаний`);
    } catch (error: any) {
      const message = error?.response?.data?.detail || error?.message || 'Не удалось добавить в список желаний';
      toast.error('Ошибка', message);
    }
  };

  const handleRemoveFromCollection = async () => {
    const status = getRecordStatus();
    if (!status.collectionItemId) return;

    Alert.alert(
      'Удалить из коллекции?',
      `"${record?.title}" будет удалена из вашей коллекции`,
      [
        { text: 'Отмена', style: 'cancel' },
        {
          text: 'Удалить',
          style: 'destructive',
          onPress: async () => {
            try {
              await removeFromCollection(status.collectionItemId!);
              toast.success('Винил удалён из коллекции');
            } catch (error: any) {
              toast.error('Не удалось удалить из коллекции');
            }
          },
        },
      ]
    );
  };

  const handleRemoveFromWishlist = async () => {
    const status = getRecordStatus();
    if (!status.wishlistItemId) return;

    Alert.alert(
      'Удалить из списка?',
      `"${record?.title}" будет удалена из списка желаний`,
      [
        { text: 'Отмена', style: 'cancel' },
        {
          text: 'Удалить',
          style: 'destructive',
          onPress: async () => {
            try {
              await removeFromWishlist(status.wishlistItemId!);
              toast.success('Винил удалён из списка желаний');
            } catch (error: any) {
              toast.error('Не удалось удалить из списка');
            }
          },
        },
      ]
    );
  };

  // Тап по радар-иконке: включаем слежку (если ещё watched), один sonar-пульс,
  // и открываем меню порога. Порог и состояние задаются в самом sheet.
  const handleRadarTap = () => {
    const status = getRecordStatus();
    if (status.status !== 'in_wishlist' || !status.wishlistItemId || !record) return;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
    // единичный пульс
    radarPulse.value = 0;
    radarPulse.value = withTiming(1, { duration: 520, easing: Easing.out(Easing.quad) });

    // Тап всегда открывает меню порога. Подписка — только по «Сохранить»,
    // «Убрать радар» — внизу шторки (когда уже подписан).
    const subscribed = status.wishlistNotifyMode === 'subscribed';
    const priceHint =
      record.estimated_price_median_rub ?? record.estimated_price_min_rub ?? null;
    thresholdSheetRef.current?.present({
      itemId: status.wishlistItemId,
      recordId: record.id,
      currentPrice: priceHint,
      threshold: status.wishlistPriceThreshold ?? null,
      conditions: status.wishlistConditions ?? null,
      subscribed,
    });
  };

  const handleRemoveFromFolder = async () => {
    if (!folderId || !folderItemId) return;

    Alert.alert(
      'Убрать из папки?',
      `"${record?.title}" будет убрана из папки`,
      [
        { text: 'Отмена', style: 'cancel' },
        {
          text: 'Убрать',
          style: 'destructive',
          onPress: async () => {
            try {
              await api.removeFromCollection(folderId, folderItemId);
              await fetchCollections();
              toast.success('Винил убран из папки');
              router.back();
            } catch {
              toast.error('Не удалось убрать из папки');
            }
          },
        },
      ]
    );
  };

  const handleAddRecordToFolder = async (folderId: string) => {
    const status = getRecordStatus();
    if (!status.collectionItemId || !record) return;
    try {
      const folderData = await api.getCollection(folderId);
      const alreadyInFolder = (folderData.items || []).some(
        (i: CollectionItem) => i.record_id === record.id
      );
      if (alreadyInFolder) {
        setShowFolderPicker(false);
        toast.info('Уже есть', 'Эта пластинка уже в этой папке');
        return;
      }
      await addItemsToFolder(folderId, [status.collectionItemId]);
      setShowFolderPicker(false);
      const fmt = getFormatDisplayInfo(record?.format_type);
      toast.success(`${fmt.label} ${fmt.verb} в папку`);
    } catch {
      toast.error('Не удалось добавить в папку');
    }
  };

  // UGC (App Store 1.2): жалоба на чужую user-запись.
  const handleReportRecord = () => {
    setShowActionSheet(false);
    if (!record) return;
    Alert.alert(
      'Пожаловаться на запись?',
      'Запись будет отправлена на проверку модератору. Мы реагируем на жалобы в течение 24 часов.',
      [
        { text: 'Отмена', style: 'cancel' },
        {
          text: 'Пожаловаться',
          style: 'destructive',
          onPress: async () => {
            try {
              await api.reportContent({ target_type: 'record', target_id: record.id });
              toast.success('Спасибо, жалоба отправлена');
            } catch {
              toast.error('Не удалось отправить жалобу');
            }
          },
        },
      ],
    );
  };

  const getActionSheetActions = (): ActionSheetAction[] => {
    const recordStatus = getRecordStatus();
    const actions: ActionSheetAction[] = [];

    // §11: править можно только свою user-record.
    const myId = useAuthStore.getState().user?.id;
    // UGC: чужая user-запись — можно пожаловаться.
    if (record?.source === 'user' && record.created_by_user_id && record.created_by_user_id !== myId) {
      actions.push({
        label: 'Пожаловаться',
        icon: 'flag-outline',
        onPress: handleReportRecord,
        destructive: true,
      });
    }
    if (record?.source === 'user' && record.created_by_user_id && record.created_by_user_id === myId) {
      actions.push({
        label: 'Отредактировать',
        icon: 'create-outline',
        onPress: () => {
          setShowActionSheet(false);
          router.push(`/record/manual?editId=${record.id}` as any);
        },
      });
    }

    if (recordStatus.status === 'in_collection') {
      // Добавить ещё одну копию (с подтверждением)
      actions.push({
        label: 'Добавить ещё копию',
        icon: 'duplicate-outline',
        onPress: handleAddAnotherCopy,
      });
      // Папка/удаление требуют collectionItemId. Если владение определено
      // только через owned-set (collectionItemId === null), эти действия
      // скрываем — доступно лишь «Добавить ещё копию».
      if (recordStatus.collectionItemId) {
        // Добавить в папку
        actions.push({
          label: 'Добавить в папку',
          icon: 'folder-outline',
          onPress: () => setShowFolderPicker(true),
        });

        if (folderId && folderItemId) {
          // Открыли из папки — показываем «Убрать из папки»
          actions.push({
            label: 'Убрать из папки',
            icon: 'folder-open-outline',
            onPress: handleRemoveFromFolder,
            destructive: true,
          });
        } else {
          // Открыли из основной коллекции — показываем «Удалить из коллекции»
          actions.push({
            label: 'Удалить',
            icon: 'trash-outline',
            onPress: handleRemoveFromCollection,
            destructive: true,
          });
        }
      }
    }

    return actions;
  };

  if (isLoading) {
    if (hasPreview) {
      return (
        <View style={styles.container}>
          <Header title="" showBack showProfile={false} />
          <ScrollView
            contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + 100 }]}
            showsVerticalScrollIndicator={false}
          >
            <View style={styles.coverContainer}>
              {previewCover || previewThumb ? (
                <Image
                  // Мастер в source, мелкий превью — в placeholder. Если мастера
                  // ещё нет, показываем один thumb: он мгновенный, но уступит
                  // место мастеру, как только тот приедет. Раньше thumb стоял в
                  // source и залипал растянутым на всю ширину (пикселизация ×8).
                  source={previewCover || undefined}
                  style={styles.cover}
                  contentFit="cover"
                  cachePolicy="memory-disk"
                  placeholder={
                    previewThumb
                      ? previewThumb
                      : previewBlurhash
                        ? { blurhash: previewBlurhash }
                        : undefined
                  }
                  placeholderContentFit="cover"
                />
              ) : (
                <View style={[styles.cover, styles.coverPlaceholder]}>
                  <Icon name="disc-outline" size={80} color={Colors.textMuted} />
                </View>
              )}
            </View>
            <View style={styles.infoSection}>
              {previewTitle ? <Text style={styles.title}>{previewTitle}</Text> : null}
              {previewArtist ? (
                <View style={styles.artistCard}>
                  <View style={styles.artistAvatarBorder}>
                    <View style={styles.artistAvatarPlaceholder}>
                      <Icon name="person" size={24} color={Colors.textMuted} />
                    </View>
                  </View>
                  <Text style={styles.artistName}>{cleanArtistName(previewArtist)}</Text>
                </View>
              ) : null}
              {previewYear ? (
                <View style={styles.metaRow}>
                  <View style={styles.metaItem}>
                    <Icon name="calendar-outline" size={16} color={Colors.textSecondary} />
                    <Text style={styles.metaText}>{previewYear}</Text>
                  </View>
                </View>
              ) : null}
            </View>
            <View style={styles.skeletonLoader}>
              <ActivityIndicator size="small" color={Colors.royalBlue} />
              <Text style={styles.skeletonLoaderText}>Загружаем детали…</Text>
            </View>
          </ScrollView>
        </View>
      );
    }
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color={Colors.royalBlue} />
      </View>
    );
  }

  if (error || !record) {
    return (
      <View style={styles.container}>
        <Header title="Ошибка" showBack showProfile={false} />
        <View style={styles.centered}>
          <Icon name="alert-circle-outline" size={64} color={Colors.textMuted} />
          <Text style={styles.errorText}>{error || 'Винил не найден'}</Text>
          <View style={styles.errorActions}>
            <Button title="Попробовать ещё раз" onPress={loadRecord} />
            <Button title="Назад" onPress={() => router.back()} variant="outline" />
          </View>
        </View>
      </View>
    );
  }

  // Герой карточки — только мастер-грейд. Мелкий превью (в том числе у старых
  // записей, куда 150px-thumb успел попасть в cover_image_url) уходит в
  // плейсхолдер: видно сразу, но не растянуто на всю ширину.
  const imageUrl = getMasterCoverUrl(record);
  const thumbUrl = previewThumb || getPlaceholderCoverUrl(record);

  // UGC: чужая user-запись — жалоба доступна из хедера даже вне коллекции.
  const isForeignUserRecord =
    record.source === 'user' &&
    !!record.created_by_user_id &&
    record.created_by_user_id !== useAuthStore.getState().user?.id;

  return (
    <View style={styles.container}>
      <Header
        title=""
        showBack
        showProfile={false}
        rightAction={
          /* Маркет-чип в правом верхнем углу: с карточки релиза до витрины
             один тап, без возврата в поиск и pull-жеста. Жалоба на чужую
             user-запись (UGC) живёт рядом, не вытесняя вход в Маркет. */
          <View style={styles.headerActions}>
            {isForeignUserRecord ? (
              <TouchableOpacity onPress={handleReportRecord} hitSlop={8}>
                <Icon name="flag-outline" size={22} color={Colors.textSecondary} />
              </TouchableOpacity>
            ) : null}
            <TouchableOpacity
              onPress={() => router.push('/market')}
              hitSlop={8}
              activeOpacity={0.8}
              accessibilityRole="button"
              accessibilityLabel="Перейти в Маркет"
              style={styles.marketChip}
            >
              <Icon name="disc-outline" size={16} color={Colors.royalBlue} />
              <Text style={styles.marketChipText}>В Маркет</Text>
            </TouchableOpacity>
          </View>
        }
      />

      <ScrollView
        contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + 100 }]}
        showsVerticalScrollIndicator={false}
      >
        {/* Обложка */}
        <View style={styles.coverContainer}>
          {imageUrl || thumbUrl ? (
            <Image
              source={imageUrl || undefined}
              style={styles.cover}
              contentFit="cover"
              cachePolicy="memory-disk"
              // Приоритет плейсхолдера: уже показанный thumb (пиксели, но
              // мгновенно и без мигания на blur) → blurhash записи → blurhash
              // из preview-параметров.
              placeholder={
                thumbUrl
                  ? thumbUrl
                  : record.blurhash
                    ? { blurhash: record.blurhash }
                    : previewBlurhash
                      ? { blurhash: previewBlurhash }
                      : undefined
              }
              placeholderContentFit="cover"
            />
          ) : (
            <View style={[styles.cover, styles.coverPlaceholder]}>
              <Icon name="disc-outline" size={80} color={Colors.textMuted} />
            </View>
          )}
        </View>

        {/* Основная информация */}
        <View style={styles.infoSection}>
          <Text style={styles.title}>{record.title}</Text>

          <TouchableOpacity
            style={styles.artistCard}
            onPress={() => record.artist_id
              ? router.push(`/artist/${record.artist_id}`)
              : handleArtistNavigation(record.artist, router)
            }
            activeOpacity={0.7}
          >
            <LinearGradient
              colors={Gradients.blue}
              start={{ x: 0, y: 0 }}
              end={{ x: 1, y: 1 }}
              style={styles.artistAvatarBorder}
            >
              {record.artist_thumb_image_url ? (
                <Image
                  source={record.artist_thumb_image_url}
                  style={styles.artistAvatar}
                  contentFit="cover"
                  cachePolicy="memory-disk"
                />
              ) : (
                <View style={styles.artistAvatarPlaceholder}>
                  <Icon name="person" size={24} color={Colors.textMuted} />
                </View>
              )}
            </LinearGradient>
            <Text style={styles.artistName}>{cleanArtistName(record.artist)}</Text>
          </TouchableOpacity>

          <View style={styles.metaRow}>
            {record.year ? (
              <View style={styles.metaItem}>
                <Icon name="calendar-outline" size={16} color={Colors.textSecondary} />
                <Text style={styles.metaText}>{record.year}</Text>
              </View>
            ) : null}
            {record.format_type ? (
              <View style={styles.metaItem}>
                <Icon name="disc-outline" size={16} color={Colors.textSecondary} />
                <Text style={styles.metaText}>{getFormatDisplayInfo(record.format_type).label}</Text>
              </View>
            ) : null}
            {record.country ? (
              <View style={styles.metaItem}>
                <Icon name="globe-outline" size={16} color={Colors.textSecondary} />
                <Text style={styles.metaText}>{record.country}</Text>
              </View>
            ) : null}
            {/* Ореол, а не кольцо: кольцо расходится до 1.9× от цели, и у
                плашки цвета — она стоит у самого левого края — половина
                подсветки уезжала за экран. */}
            <CoachPulse
              active={vinylColorTip.visible}
              variant="glow"
              radius={BorderRadius.full}
              inset={3}
            >
              <VinylColorTag vinylColorRaw={record.display_vinyl_color ?? record.vinyl_color_raw} />
            </CoachPulse>
          </View>
        </View>

        {/* Подсказка про цвет винила идёт СРАЗУ под шапкой, а не над ней:
            плашка цвета живёт в строке меты вместе с форматом и страной,
            вклиниться туда карточкой нельзя. Место показывает подсветка. */}
        {renderRecordTip(vinylColorTip)}

        {/* Лейбл и каталог */}
        {(record.label || record.catalog_number) && (
          <Card variant="flat" style={styles.card}>
            <Text style={styles.cardTitle}>Издание</Text>
            {record.label && (
              <View style={styles.detailRow}>
                <Text style={styles.detailLabel}>Лейбл</Text>
                <Text style={styles.detailValue}>{record.label}</Text>
              </View>
            )}
            {record.catalog_number && (
              <View style={styles.detailRow}>
                <Text style={styles.detailLabel}>Каталожный №</Text>
                <Text style={styles.detailValue}>{record.catalog_number}</Text>
              </View>
            )}
          </Card>
        )}

        {/* Цвет винила */}
        {(() => {
          const colorConfig = parseVinylColor(record.display_vinyl_color ?? record.vinyl_color_raw);
          if (!colorConfig.isColored) return null;
          return (
            <View style={styles.vinylSpinnerContainer}>
              <VinylSpinner
                colorConfig={colorConfig}
                labelName={record.label ?? undefined}
                size={220}
                onTap={() => countSpin(String(record.id))}
              />
              <Text style={styles.vinylDisclaimer}>
                Это визуальный прототип — реальный цвет может отличаться
              </Text>
            </View>
          );
        })()}

        {/* Жанр */}
        {(record.genre || record.style) && (
          <Card variant="flat" style={styles.card}>
            <Text style={styles.cardTitle}>Жанр</Text>
            {record.genre && <Text style={styles.genreText}>{record.genre}</Text>}
            {record.style && (
              <Text style={styles.styleText}>{record.style}</Text>
            )}
          </Card>
        )}

        {renderRecordTip(rarityTip)}

        {/* Особенности (rarity) */}
        {rarityTiers.length > 0 ? (
          <CoachPulse
            active={rarityTip.visible}
            variant="glow"
            radius={BorderRadius.lg}
            inset={6}
          >
            <View style={styles.featuresSection}>
              <Text style={styles.featuresTitle}>Особенности</Text>
              <View style={styles.featuresList}>
                {rarityTiers.map((tier) => (
                  <TierFeatureBlock key={tier} tier={tier} />
                ))}
              </View>
            </View>
          </CoachPulse>
        ) : null}

        {/* Цена */}
        {(() => {
          const rubPrice = record.estimated_price_median_rub || record.estimated_price_min_rub;
          const usdPrice = record.estimated_price_median || record.estimated_price_min;
          if (!rubPrice && !usdPrice) return null;

          return (
            <>
            {renderTourTip('price')}
            <CoachPulse
              active={tour.isAt('price')}
              variant="glow"
              radius={BorderRadius.lg}
              inset={4}
              style={styles.tourTargetLg}
            >
            {/* Без styles.card: его единственное свойство — marginBottom,
                и держит его теперь обёртка ореола. */}
            <Card variant="flat" style={styles.cardInTour}>
              <Text style={[styles.cardTitle, { textAlign: 'center' }]}>Примерная стоимость</Text>

              {rubPrice ? (
                <View style={styles.priceContainer}>
                  {record.estimated_price_min_rub && record.estimated_price_median_rub ? (
                    <View style={styles.priceItem}>
                      <Text style={styles.priceLabel}>от</Text>
                      <Text style={styles.priceValue}>
                        {Math.round(record.estimated_price_min_rub).toLocaleString('ru-RU')} ₽
                      </Text>
                    </View>
                  ) : null}
                  <View style={styles.priceItem}>
                    <Text style={styles.priceLabel}>{record.estimated_price_median_rub ? '~' : 'от'}</Text>
                    <GradientText style={styles.priceMedian}>
                      {Math.round(rubPrice).toLocaleString('ru-RU')} ₽
                    </GradientText>
                  </View>
                  {record.estimated_price_max_rub ? (
                    <View style={styles.priceItem}>
                      <Text style={styles.priceLabel}>до</Text>
                      <Text style={styles.priceValue}>
                        {Math.round(record.estimated_price_max_rub).toLocaleString('ru-RU')} ₽
                      </Text>
                    </View>
                  ) : null}
                </View>
              ) : null}

              {(() => {
                const src = record.price_source;
                if (src === 'marketplace_active' || src === 'marketplace_historical') {
                  const label = src === 'marketplace_active' ? 'по магазинам' : 'по архивным офферам';
                  const offers = record.price_offers_count;
                  return (
                    <Text style={styles.priceNote}>
                      {label}{offers ? ` · ${offers} ${offers === 1 ? 'оффер' : 'офферов'}` : ''}
                    </Text>
                  );
                }
                if (src === 'discogs_raw' && usdPrice != null) {
                  return (
                    <Text style={styles.priceNote}>
                      Discogs: ${Number(usdPrice).toFixed(2)}
                      {record.usd_rub_rate ? ` · курс ${Number(record.usd_rub_rate).toFixed(1)} ₽` : ''}
                    </Text>
                  );
                }
                if (usdPrice != null) {
                  return (
                    <Text style={styles.priceNote}>
                      Discogs: ${Number(usdPrice).toFixed(2)}
                      {record.usd_rub_rate ? ` · курс ${Number(record.usd_rub_rate).toFixed(1)} ₽` : ''}
                      {record.ru_markup ? ` · × ${Number(record.ru_markup).toFixed(2)}` : ''}
                    </Text>
                  );
                }
                return null;
              })()}
            </Card>
            </CoachPulse>
            </>
          );
        })()}

        {/* Подсказка про Маркет живёт и здесь, а не только на вишлисте: на
            вкладку «Вишлист» заходят не все, а карточка релиза с офферами —
            ровно тот момент, когда витрина магазинов объясняет сама себя. */}
        {marketTip.visible && (
          <CoachTip
            meta={marketTip.meta}
            analyticsKey={marketTip.meta.key}
            onDismiss={marketTip.dismiss}
            action={{ label: 'Открыть Маркет', onPress: () => router.push('/market') }}
          />
        )}

        {renderTourTip('offers')}

        {renderRecordTip(offerPriceTip)}

        {/* Где купить — живые предложения магазинов. Обёртка ореола учитывает
            marginVertical самого блока (Spacing.sm), иначе подсветка обводила
            бы блок вместе с его отступами. */}
        {offersRequested ? (
          <CoachPulse
            active={tour.isAt('offers') || offerPriceTip.visible}
            variant="glow"
            radius={BorderRadius.lg}
            inset={4}
            edges={{ top: -Spacing.sm, bottom: -Spacing.sm }}
          >
            {record.discogs_id ? (
              <OffersBlock discogsId={record.discogs_id} onOffersResolved={setOffersCount} />
            ) : (
              // store-native (нет discogs_id) — берём офферы по record_id через
              // /records/by-id/{uuid}/offers/full. Без alt-version'ов (нет
              // master_id), только exact-match листинги магазинов.
              <OffersBlock recordId={record.id} onOffersResolved={setOffersCount} />
            )}
          </CoachPulse>
        ) : null}

        {renderTourTip('history')}

        {/* Динамика цены (Волна C) — рисуем только когда есть точки истории.
            У самого графика marginHorizontal/marginBottom по Spacing.md —
            втягиваем ореол на эту величину, чтобы он обвёл график, а не его
            отступы. */}
        {hasHistory && priceHistory ? (
          <CoachPulse
            active={tour.isAt('history')}
            variant="glow"
            radius={BorderRadius.lg}
            inset={4}
            edges={{ left: -Spacing.md, right: -Spacing.md, bottom: -Spacing.md }}
          >
            <PriceSparkline
              points={priceHistory.points}
              historicalLow={priceHistory.historical_low_rub}
            />
          </CoachPulse>
        ) : null}

        {renderTourTip('versions')}

        {renderRecordTip(versionsTip, {
          label: 'Посмотреть',
          onPress: () => router.push(`/master/${record.discogs_master_id}/versions` as never),
        })}

        {/* Другие версии релиза. '0' — легаси-артефакт Discogs (master_id=0
            у релизов без мастера), по нему некуда переходить. */}
        {hasVersions ? (
          <CoachPulse
            active={tour.isAt('versions') || versionsTip.visible}
            variant="glow"
            radius={BorderRadius.lg}
            inset={4}
          >
            <OtherVersionsButton
              onPress={() => router.push(`/master/${record.discogs_master_id}/versions`)}
            />
          </CoachPulse>
        ) : null}

        {/* Треклист */}
        {record.tracklist && record.tracklist.length > 0 && (
          <Card variant="flat" style={styles.card}>
            <Text style={styles.cardTitle}>Треклист</Text>
            {record.tracklist.map((track, index) => (
              <View key={index} style={styles.trackRow}>
                <Text style={styles.trackPosition}>{track.position || index + 1}</Text>
                <Text style={styles.trackTitle} numberOfLines={1}>
                  {track.title}
                </Text>
                {track.duration && (
                  <Text style={styles.trackDuration}>{track.duration}</Text>
                )}
              </View>
            ))}
          </Card>
        )}

        {/* Атрибуция источника данных (условие Discogs при использовании их данных/API) */}
        <Text style={styles.dataAttribution}>
          Данные о релизах и обложки — Discogs / Cover Art Archive
        </Text>
      </ScrollView>

      {/* Кнопки действий */}
      {(() => {
        const recordStatus = getRecordStatus();

        // STORE-NATIVE (нет на Discogs) ездит по обычному блоку кнопок: добавление
        // в коллекцию/вишлист идёт по record_id (см. handleAddToCollection), бэк
        // пускает source='store' в whitelist. Купить — через OffersBlock выше.
        // При будущем merge с Discogs запись прозрачно переедет (merged_into_id +
        // ремап items в safe_merge_store_native_into).

        // ========== СТАТУС: В КОЛЛЕКЦИИ ==========
        if (recordStatus.status === 'in_collection') {
          return (
            <BlurView intensity={60} tint="light" style={[styles.actionsContainer, { paddingBottom: insets.bottom + Spacing.md }]}>
              <View style={styles.addedButtonContainer}>
                <View style={styles.addedButton}>
                  <Icon name="checkmark-circle" size={20} color={Colors.textSecondary} />
                  <Text style={styles.addedButtonText}>
                    {recordStatus.copiesCount > 1
                      ? `Добавлено (${recordStatus.copiesCount})`
                      : 'Добавлено'
                    }
                  </Text>
                </View>
                <TouchableOpacity
                  style={styles.moreButton}
                  onPress={() => setShowActionSheet(true)}
                >
                  <Icon name="ellipsis-vertical" size={24} color={Colors.background} />
                </TouchableOpacity>
              </View>
            </BlurView>
          );
        }

        // ========== СТАТУС: В ВИШЛИСТЕ ==========
        if (recordStatus.status === 'in_wishlist') {
          const subscribed = recordStatus.wishlistNotifyMode === 'subscribed';
          return (
            <BlurView intensity={60} tint="light" style={[styles.actionsContainer, { paddingBottom: insets.bottom + Spacing.md }]}>
              <Button
                title="Добавить"
                onPress={handleAddToCollection}
                style={styles.actionButton}
              />
              <TouchableOpacity
                style={[styles.bellButton, subscribed && styles.bellButtonActive]}
                onPress={handleRadarTap}
                accessibilityRole="button"
                accessibilityLabel={subscribed ? 'Настроить радар и порог цены' : 'Поставить на радар'}
                hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
              >
                <Animated.View style={[styles.radarPulseRing, radarPulseStyle]} pointerEvents="none" />
                <RadarIcon
                  size={22}
                  variant={subscribed ? 'on' : 'off'}
                  color={subscribed ? '#FFFFFF' : Colors.textSecondary}
                />
                {subscribed && recordStatus.wishlistPriceThreshold ? (
                  <View style={styles.bellThresholdDot} />
                ) : null}
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.actionButton, styles.removeButton]}
                onPress={handleRemoveFromWishlist}
              >
                <Text style={styles.removeButtonText}>Удалить</Text>
              </TouchableOpacity>
            </BlurView>
          );
        }

        // ========== СТАТУС: НЕ ДОБАВЛЕНА ==========
        return (
          <BlurView intensity={60} tint="light" style={[styles.actionsContainer, { paddingBottom: insets.bottom + Spacing.md }]}>
            <Button
              title="Добавить"
              onPress={handleAddToCollection}
              style={styles.actionButton}
            />
            <Button
              title="В вишлист"
              onPress={handleAddToWishlist}
              variant="outline"
              style={{ ...styles.actionButton, backgroundColor: Colors.surface }}
            />
          </BlurView>
        );
      })()}

      {/* ActionSheet для действий с пластинкой в коллекции */}
      <ActionSheet
        visible={showActionSheet}
        actions={getActionSheetActions()}
        onClose={() => setShowActionSheet(false)}
      />

      <FolderPickerModal
        visible={showFolderPicker}
        onClose={() => setShowFolderPicker(false)}
        onSelectFolder={handleAddRecordToFolder}
        selectedRecordIds={record ? [record.id] : []}
      />

      <ThresholdSheet ref={thresholdSheetRef} onOpenRadar={() => router.push('/radar' as any)} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  headerActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
  },
  marketChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingVertical: 6,
    paddingHorizontal: 10,
    borderRadius: BorderRadius.full,
    backgroundColor: 'rgba(59, 75, 245, 0.08)',
    borderWidth: 1,
    borderColor: 'rgba(59, 75, 245, 0.22)',
  },
  marketChipText: {
    ...Typography.caption,
    fontFamily: 'Inter_700Bold',
    fontWeight: '700',
    color: Colors.royalBlue,
  },
  centered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: Spacing.lg,
  },
  errorText: {
    ...Typography.body,
    color: Colors.textSecondary,
    textAlign: 'center',
    marginVertical: Spacing.lg,
  },
  errorActions: {
    width: '100%',
    gap: Spacing.sm,
  },
  skeletonLoader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: Spacing.sm,
    paddingVertical: Spacing.lg,
  },
  skeletonLoaderText: {
    ...Typography.bodySmall,
    color: Colors.textMuted,
  },
  content: {
    padding: Spacing.md,
  },
  coverContainer: {
    alignItems: 'center',
    marginBottom: Spacing.lg,
  },
  cover: {
    width: '100%',
    aspectRatio: 1,
    borderRadius: 24,
  },
  coverPlaceholder: {
    backgroundColor: Colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
  },
  infoSection: {
    marginBottom: Spacing.lg,
  },
  artistCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.lg,
    padding: Spacing.sm,
    marginBottom: Spacing.md,
    gap: Spacing.sm,
  },
  artistAvatarBorder: {
    width: 52,
    height: 52,
    borderRadius: 26,
    padding: 2,
  },
  artistAvatar: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: Colors.surface,
  },
  artistAvatarPlaceholder: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: Colors.surface,
    justifyContent: 'center',
    alignItems: 'center',
  },
  artistName: {
    ...Typography.body,
    color: Colors.text,
    fontWeight: '500',
    flex: 1,
  },
  title: {
    fontSize: ms(36),
    fontFamily: 'Inter_800ExtraBold',
    lineHeight: ms(42),
    letterSpacing: -1,
    color: Colors.deepNavy,
    marginBottom: Spacing.md,
  },
  metaRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: Spacing.md,
  },
  metaItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.xs,
  },
  metaText: {
    ...Typography.bodySmall,
    color: Colors.textSecondary,
  },
  card: {
    marginBottom: Spacing.md,
  },
  // Отступ карточки, обёрнутой в ореол тура, держит обёртка: ореол рисуется по
  // границам обёртки, и внутренний marginBottom растянул бы его вниз.
  tourTargetLg: {
    marginBottom: Spacing.md,
  },
  cardInTour: {
    marginBottom: 0,
  },
  cardTitle: {
    ...Typography.h4,
    color: Colors.deepNavy,
    marginBottom: Spacing.sm,
  },
  detailRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: Spacing.xs,
  },
  detailLabel: {
    ...Typography.bodySmall,
    color: Colors.textSecondary,
  },
  detailValue: {
    ...Typography.bodySmall,
    color: Colors.text,
    fontWeight: '500',
  },
  genreText: {
    ...Typography.body,
    color: Colors.text,
  },
  styleText: {
    ...Typography.bodySmall,
    color: Colors.textSecondary,
    marginTop: Spacing.xs,
  },
  priceContainer: {
    flexDirection: 'row',
    justifyContent: 'space-around',
  },
  priceItem: {
    alignItems: 'center',
  },
  priceLabel: {
    ...Typography.caption,
    color: Colors.textSecondary,
    marginBottom: Spacing.xs,
  },
  priceValue: {
    ...Typography.h4,
    color: Colors.text,
  },
  priceMedian: {
    ...Typography.h4,
    fontFamily: 'Inter_700Bold',
  },
  priceNote: {
    ...Typography.caption,
    color: Colors.textMuted,
    textAlign: 'center' as const,
    marginTop: Spacing.sm,
  },
  otherVersionsButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.lg,
    paddingVertical: Spacing.md,
    paddingHorizontal: Spacing.md,
    marginBottom: Spacing.md,
  },
  otherVersionsText: {
    ...Typography.body,
    color: Colors.text,
    fontFamily: 'Inter_700Bold',
    fontWeight: '700',
    flex: 1,
  },
  trackRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: Spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: Colors.divider,
  },
  trackPosition: {
    ...Typography.caption,
    color: Colors.textMuted,
    width: 30,
  },
  trackTitle: {
    ...Typography.body,
    color: Colors.text,
    flex: 1,
  },
  trackDuration: {
    ...Typography.caption,
    color: Colors.textSecondary,
    marginLeft: Spacing.sm,
  },
  dataAttribution: {
    ...Typography.caption,
    color: Colors.textMuted,
    textAlign: 'center',
    marginTop: Spacing.md,
  },
  actionsContainer: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    flexDirection: 'row',
    padding: Spacing.md,
    backgroundColor: Colors.glassBg,
    gap: Spacing.sm,
    overflow: 'hidden',
  },
  actionButton: {
    flex: 1,
  },
  addedButtonContainer: {
    flex: 1,
    flexDirection: 'row',
    gap: Spacing.sm,
    alignItems: 'center',
  },
  addedButton: {
    flex: 1,
    height: 56,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: Spacing.sm,
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.md,
  },
  addedButtonText: {
    ...Typography.button,
    color: Colors.textSecondary,
  },
  moreButton: {
    width: 56,
    height: 56,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: Colors.royalBlue,
    borderRadius: BorderRadius.md,
  },
  removeButton: {
    flex: 1,
    height: 56,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.md,
  },
  bellButton: {
    width: 56,
    height: 56,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.md,
    overflow: 'visible',
  },
  bellButtonActive: {
    backgroundColor: Colors.royalBlue,
  },
  radarPulseRing: {
    position: 'absolute',
    width: 56,
    height: 56,
    borderRadius: BorderRadius.md,
    borderWidth: 2,
    borderColor: Colors.royalBlue,
  },
  bellThresholdDot: {
    position: 'absolute',
    top: 10,
    right: 10,
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: '#FFFFFF',
  },
  removeButtonText: {
    ...Typography.button,
    color: Colors.text,
  },
  vinylSpinnerContainer: {
    alignItems: 'center',
    paddingVertical: Spacing.lg,
    marginHorizontal: Spacing.md,
    marginBottom: Spacing.md,
  },
  vinylDisclaimer: {
    ...Typography.caption,
    color: Colors.textMuted,
    textAlign: 'center',
    marginTop: Spacing.md,
    paddingHorizontal: Spacing.lg,
  },
  featuresSection: {
    marginHorizontal: Spacing.md,
    marginBottom: Spacing.md,
  },
  featuresTitle: {
    ...Typography.h4,
    color: Colors.text,
    marginBottom: Spacing.sm,
    paddingHorizontal: 4,
  },
  featuresList: {
    gap: Spacing.sm,
  },
});
