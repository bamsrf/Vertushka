/**
 * Экран «Ачивки» — детальный грид по сериям + блок рандомных «Пасхалки».
 *
 * Открывается:
 * - С виджета AchievementsBlock в `app/profile.tsx` → свои.
 * - С виджета в `user/[username]/index.tsx` → через `/user/[username]/achievements`
 *   (см. соседний роут с параметром username).
 */
import { useEffect, useState, useCallback, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  RefreshControl,
  Share,
  Platform,
  Dimensions,
} from 'react-native';
import { Stack, useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import * as Haptics from 'expo-haptics';
import * as Sharing from 'expo-sharing';
import { LinearGradient } from 'expo-linear-gradient';
import { api } from '../lib/api';
import { Colors, Spacing, BorderRadius } from '../constants/theme';
import { ms } from '../lib/responsive';
import { AchievementPin } from '../components/AchievementPin';
import { prewarmAchievementPins, prefetchAchievementAsset } from '../lib/achievementAssets';
import { AchievementsHero } from '../components/AchievementsHero';
import { setCurrentLevelFrom } from '../lib/levelStore';
import { countPull, reportAchievementsOpened } from '../lib/eggTracker';
import { AchievementsTourOverlay } from '../components/AchievementsTourOverlay';
import { MetaTrophyShelf } from '../components/MetaTrophyShelf';
import { Capsule } from '../components/achievement-mockup/Capsule';
import { GroovesBg } from '../components/achievement-mockup/GroovesBg';
import {
  M_EMBER,
  M_EMBER_GLOW,
  M_GOLD,
  M_GOLD_HI,
  M_GOLD_RIM_SOFT,
  M_IVORY,
  M_IVORY_DIM,
  M_IVORY_MUTED,
  M_NAVY,
} from '../components/achievement-mockup/palette';
import type {
  AchievementItem,
  AchievementSeriesItem,
  AchievementStats,
  MyAchievementsResponse,
} from '../lib/types';

// ─── Метрики грида ──────────────────────────────────────────────────────────
// Ячейки считаем от ширины экрана, а не фиксируем в 88pt: на узких телефонах
// (iPhone mini/SE, 375pt) при фиксе три колонки не влезали в карточку на 1pt
// и грид схлопывался в две. Ширина карточки = экран − 2×marginHorizontal(md)
// − 2×paddingHorizontal(lg).
const GRID_COLS = 3;
const GRID_GAP = 16;
const GRID_MAX_CELL = 88;
const GRID_INNER_WIDTH =
  Dimensions.get('window').width - 2 * Spacing.md - 2 * Spacing.lg;
const GRID_CELL = Math.min(
  GRID_MAX_CELL,
  Math.floor((GRID_INNER_WIDTH - GRID_GAP * (GRID_COLS - 1)) / GRID_COLS),
);

export default function AchievementsScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const params = useLocalSearchParams<{
    username?: string;
    code?: string;
    levelup?: string;
  }>();
  const username = params.username || null;
  const deepLinkCode = params.code || null;

  const [data, setData] = useState<MyAchievementsResponse | null>(null);
  const [randomItems, setRandomItems] = useState<AchievementItem[]>([]);
  // Чужой профиль: пасхалки на пересечении с моими + сколько скрыто сверх них.
  const [peerRandom, setPeerRandom] = useState<AchievementItem[]>([]);
  const [peerHidden, setPeerHidden] = useState(0);
  const [peerRandomFailed, setPeerRandomFailed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [selected, setSelected] = useState<AchievementItem | null>(null);

  const load = useCallback(async () => {
    try {
      const resp = username
        ? await api.getAchievementsByUsername(username)
        : await api.getMyAchievements();
      setData(resp);
      if (!username) {
        // Приход по пушу «новый уровень» — единственный путь, где ступень
        // поднялась без действия в приложении, а значит `achievementsBus` её
        // ещё не пересчитал. Ответ уже на руках, так что иконки папок
        // перекрашиваются здесь же, не дожидаясь следующего добавления
        // пластинки. Чужой профиль ступень трогать не должен.
        setCurrentLevelFrom(resp);
        const random = await api.getMyRandomUnlocked();
        setRandomItems(random.items);
      } else {
        // Пересечение: раскрывать чужие пасхалки целиком нельзя — названия
        // описывают действие, которым они открываются, и витрина стала бы
        // гайдом. Общие безопасны: про них смотрящий уже всё знает.
        // Свой try: упавший запрос пасхалок не должен ронять весь экран, но и
        // молчать нельзя — пустой блок читается как «общих нет», хотя на деле
        // ответа не было (ровно так выглядел незадеплоенный эндпоинт).
        try {
          const peer = await api.getRandomUnlockedByUsername(username);
          setPeerRandom(peer.items);
          setPeerHidden(peer.hidden_count);
          setPeerRandomFailed(false);
        } catch (e) {
          setPeerRandomFailed(true);
        }
      }
    } catch (e) {
      // оставляем data null — UI покажет пустое состояние
    }
  }, [username]);

  useEffect(() => {
    setLoading(true);
    load().finally(() => setLoading(false));
  }, [load]);

  // Прогрев декода PNG-пинов в фоне — иконки в шите/шере готовы мгновенно.
  useEffect(() => {
    prewarmAchievementPins();
  }, []);

  // Пасхалка «Год спустя»: дату регистрации знает только бэкенд, наше дело —
  // сообщить, что юзер зашёл. На чужом профиле молчим: годовщина не наша.
  useEffect(() => {
    if (!username) reportAchievementsOpened();
  }, [username]);

  const onRefresh = useCallback(async () => {
    countPull();  // пасхалка «Заело»
    setRefreshing(true);
    await load();
    setRefreshing(false);
  }, [load]);

  // Deep-link из push/уведомления: ?code=XXX → авто-открыть DetailsSheet нужной ачивки.
  const deepLinkOpened = useRef(false);
  useEffect(() => {
    if (!deepLinkCode || deepLinkOpened.current || !data) return;
    const match = data.series
      .flatMap((s) => s.items)
      .find((it) => it.code === deepLinkCode);
    if (match) {
      deepLinkOpened.current = true;
      setSelected(match);
    }
  }, [deepLinkCode, data]);

  if (loading) {
    return (
      <>
        <Stack.Screen options={{ title: 'Ачивки' }} />
        <View style={[styles.center, { paddingTop: insets.top + 60 }]}>
          <ActivityIndicator size="large" />
        </View>
      </>
    );
  }

  if (!data) {
    return (
      <>
        <Stack.Screen options={{ title: 'Ачивки' }} />
        <View style={[styles.center, { paddingTop: insets.top + 60 }]}>
          <Text style={styles.errorText}>Не удалось загрузить ачивки.</Text>
        </View>
      </>
    );
  }

  const titleText = username ? `Ачивки @${username}` : 'Ачивки';

  return (
    <>
      <Stack.Screen options={{ title: titleText }} />
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={{ paddingBottom: insets.bottom + 40 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
      >
        {/* Hero — counter + архетип-уровень + флейвор + прогресс к следующему уровню */}
        <AchievementsHero
          data={data}
          extraRandom={randomItems}
          username={username}
          forceLevelUp={params.levelup === '1' && !username}
        />

        {/* Витрина мета-трофеев — финал каждой серии в навигационной сетке */}
        <MetaTrophyShelf data={data} onPin={(item) => setSelected(item)} />

        {/* Серии — navy-карточки с пинами */}
        {data.series.map((series) => (
          <SeriesGroup
            key={series.key}
            series={series}
            onPin={(item) => setSelected(item)}
          />
        ))}

        {/* Блок рандомных: у себя — все свои, на чужом — только общие */}
        {(!username || data.random_unlocked > 0) && (
          <SurpriseBlock
            randomCount={data.random_unlocked}
            randomItems={username ? peerRandom : randomItems}
            hiddenCount={username ? peerHidden : 0}
            peerUsername={username}
            loadFailed={username ? peerRandomFailed : false}
            onPin={(item) => setSelected(item)}
          />
        )}

        <View style={{ height: 24 }} />
      </ScrollView>

      {/* Bottom-sheet с деталями */}
      {selected && <DetailsSheet item={selected} username={username} onClose={() => setSelected(null)} />}

      {/* Onboarding tour — только на своём профиле */}
      {!username && <AchievementsTourOverlay />}
    </>
  );
}

// ─── Серия ──────────────────────────────────────────────────────────────────

function SeriesGroup({
  series,
  onPin,
}: {
  series: AchievementSeriesItem;
  onPin: (item: AchievementItem) => void;
}) {
  const regulars = series.items.filter((i) => !i.is_meta);
  const meta = series.items.find((i) => i.is_meta) || null;
  const progress = series.total > 0 ? series.unlocked / series.total : 0;

  return (
    <View style={styles.seriesCard}>
      <GroovesBg opacity={0.05} originX={0} originY={-20} />

      {/* Header: emoji + title + counter capsule */}
      <View style={styles.seriesHeader}>
        <View style={styles.seriesHeaderLeft}>
          <Text style={styles.seriesEmoji}>{series.icon_emoji}</Text>
          <View style={styles.seriesHeaderText}>
            <Text style={styles.seriesTitle}>{series.title_ru}</Text>
            <Text style={styles.seriesDescription} numberOfLines={1}>
              {series.description_ru}
            </Text>
          </View>
        </View>
        <Capsule tone="gold" size="md">{`${series.unlocked} / ${series.total}`}</Capsule>
      </View>

      {/* Gold progress thread + dot */}
      <View style={styles.seriesProgressTrack}>
        <View
          style={[
            styles.seriesProgressFill,
            { width: `${Math.round(progress * 100)}%` },
          ]}
        />
        {progress > 0 && progress < 1 && (
          <View
            style={[
              styles.seriesProgressDot,
              { left: `${Math.round(progress * 100)}%` },
            ]}
          />
        )}
      </View>

      <View style={styles.gridWrap}>
        {regulars.map((it) => (
          <TouchableOpacity
            key={it.code}
            style={styles.gridCell}
            onPress={() => onPin(it)}
            activeOpacity={0.7}
          >
            <AchievementPin item={it} size={72} />
            <Text
              numberOfLines={1}
              style={[
                styles.gridLabel,
                !it.is_unlocked && { color: M_IVORY_DIM },
              ]}
            >
              {it.title_ru || '?'}
            </Text>
            {it.progress_target > 0 && !it.is_unlocked && (
              <Text style={styles.gridProgress}>
                {it.progress}/{it.progress_target}
              </Text>
            )}
          </TouchableOpacity>
        ))}

        {meta && (
          <TouchableOpacity
            style={[styles.gridCell, styles.gridCellMeta]}
            onPress={() => onPin(meta)}
            activeOpacity={0.7}
          >
            {/* Пин фиксированных размеров (PinSize); на узких экранах он
                чуть шире ячейки и заходит в гэп — это ок, он центрирован. */}
            <AchievementPin item={meta} size={96} />
            <Text
              numberOfLines={1}
              style={[
                styles.gridLabel,
                styles.gridLabelMeta,
                !meta.is_unlocked && { color: M_IVORY_DIM },
              ]}
            >
              {meta.title_ru || '?'}
            </Text>
            <Text style={styles.gridMetaTag}>МЕТА</Text>
          </TouchableOpacity>
        )}
      </View>
    </View>
  );
}

// ─── Пасхалки ───────────────────────────────────────────────────────────────

function SurpriseBlock({
  randomCount,
  randomItems,
  hiddenCount = 0,
  peerUsername = null,
  loadFailed = false,
  onPin,
}: {
  randomCount: number;
  randomItems: AchievementItem[];
  /** Сколько чужих пасхалок осталось нераскрытыми (0 на своём профиле). */
  hiddenCount?: number;
  /** Ник владельца, если смотрим чужой профиль. */
  peerUsername?: string | null;
  /** Запрос чужих пасхалок не дошёл — это не «общих нет». */
  loadFailed?: boolean;
  onPin: (item: AchievementItem) => void;
}) {
  const isPeer = !!peerUsername;
  return (
    <View style={[styles.seriesCard, styles.surpriseCard]}>
      <GroovesBg opacity={0.05} originX={350} originY={400} />

      <View style={styles.seriesHeader}>
        <View style={styles.seriesHeaderLeft}>
          <Text style={styles.seriesEmoji}>🥚</Text>
          <View style={styles.seriesHeaderText}>
            <Text style={styles.seriesTitle}>Пасхалки</Text>
            <Text style={[styles.seriesDescription, { fontStyle: 'italic' }]} numberOfLines={1}>
              {isPeer ? 'Показаны только общие с тобой.' : 'Они находятся сами.'}
            </Text>
          </View>
        </View>
        <Capsule tone="ember" size="md">{`${randomCount} открыто`}</Capsule>
      </View>

      <View style={styles.surpriseDivider} />

      {randomItems.length === 0 ? (
        <View style={styles.surpriseEmpty}>
          <Text style={styles.surpriseEmptyText}>
            {loadFailed
              ? 'Не удалось загрузить — потяни экран вниз.'
              : isPeer
                ? 'Общих с тобой пока нет.'
                : 'Пока ничего не нашлось.'}
          </Text>
        </View>
      ) : (
        <View style={styles.gridWrap}>
          {randomItems.map((it) => (
            <TouchableOpacity
              key={it.code}
              style={styles.gridCell}
              onPress={() => onPin(it)}
              activeOpacity={0.7}
            >
              <AchievementPin item={it} size={72} />
              <Text numberOfLines={1} style={styles.gridLabel}>
                {it.title_ru || '?'}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      )}

      {/* Остальные не показываем намеренно — это и есть механика серии */}
      {isPeer && hiddenCount > 0 && randomItems.length > 0 && (
        <Text style={styles.surpriseHiddenNote}>
          {`Ещё ${hiddenCount} — секрет: их находят сами.`}
        </Text>
      )}
    </View>
  );
}

// ─── Деталь ────────────────────────────────────────────────────────────────

const HOW_TO_UNLOCK: Record<string, string> = {
  // Foundation
  A1_first_record: 'Добавь первую пластинку в коллекцию.',
  A2_first_wishlist: 'Добавь первую запись в вишлист.',
  A3_avatar_set: 'Поставь аватар.',
  A4_public_profile: 'Отправь друзьям ссылку на свой профиль.',
  META_foundation: 'Открой все ачивки серии «Первые шаги».',
  // Formats
  META_formats:
    'Нужно минимум по 10 штук каждого носителя: винилов, кассет, CD и бокс-сетов. ' +
    'Виниловый бокс-сет считается сразу за оба формата.',
  // Scale (B1-B6 + META_scale) — текст подставляется из progress_target
  // Gifts
  J1_first_gift: 'Забронируй первый подарок кому-нибудь.',
  // Community
  K1_following_x5: 'Подпишись на 5 коллекций.',
  K2_first_follower: 'Подожди, пока кто-то подпишется на тебя.',
  K3_followers_x5: 'Получи 5 подписчиков с реальными коллекциями.',
  K4_followers_x50: 'Получи 50 подписчиков с реальными коллекциями.',
  K5_views_x100: 'Поделись профилем — нужно 100 просмотров.',
  K6_views_x1000: '1 000 просмотров публичного профиля.',
  K7_mutual_x10: '10 взаимных подписок с активными юзерами.',
  META_community: 'Открой «Хедлайнер», «Бэкстейдж» и «Уолл-стрит» — вершины трёх веток сообщества.',
};

function howToUnlockText(item: AchievementItem): string | null {
  if (item.is_unlocked) return null;
  if (item.is_hidden) {
    return 'Скрытая ачивка. Откроется внезапно.';
  }
  const explicit = HOW_TO_UNLOCK[item.code];
  if (explicit) return explicit;
  // Прогресс-серии — динамическая подсказка
  if (item.code.startsWith('B') && item.progress_target > 0) {
    return `Собери ${item.progress_target} уникальных пластинок.`;
  }
  if (item.code.startsWith('META_')) {
    return 'Закрой все ачивки этой серии.';
  }
  return item.description_ru || 'Открой действием в приложении.';
}

function DetailsSheet({
  item,
  username,
  onClose,
}: {
  item: AchievementItem;
  username: string | null;
  onClose: () => void;
}) {
  const insets = useSafeAreaInsets();
  const [stats, setStats] = useState<AchievementStats | null>(null);
  const [sharing, setSharing] = useState(false);
  const shareCardRef = useRef<View>(null);

  // Подтягиваем статистику для не-скрытых ачивок (для скрытых до анлока — нет смысла)
  useEffect(() => {
    const visible = !item.is_hidden || item.is_unlocked;
    if (!visible) {
      setStats(null);
      return;
    }
    let cancelled = false;
    api
      .getAchievementStats(item.code)
      .then((s) => {
        if (!cancelled) setStats(s);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [item.code, item.is_hidden, item.is_unlocked]);

  const handleShare = async () => {
    if (!item.is_unlocked) return;
    if (Platform.OS !== 'web') {
      Haptics.selectionAsync().catch(() => {});
    }
    setSharing(true);
    try {
      // Снимаем реальную карточку (пин + текст) в PNG на клиенте.
      // Ленивый require: нативный модуль view-shot отсутствует в Expo Go —
      // статический импорт ронял старт приложения. Тут падение ловит catch
      // ниже и шаринг деградирует до текстового.
      const { captureRef } = require('react-native-view-shot');
      const opts = { format: 'png' as const, quality: 1, result: 'tmpfile' as const };
      // Дизайн-пин рендерится через async <Image>. Без готового битмапа view-shot
      // снимает пустой пин. Детерминированно ждём декода именно этого пина
      // (мгновенно, если уже прогрет prewarm'ом), затем даём кадру осесть в layout.
      await prefetchAchievementAsset(item);
      await new Promise((r) => requestAnimationFrame(() => r(null)));
      await captureRef(shareCardRef, opts);
      const uri = await captureRef(shareCardRef, opts);
      const available = await Sharing.isAvailableAsync();
      if (available) {
        await Sharing.shareAsync(uri, {
          mimeType: 'image/png',
          dialogTitle: item.title_ru || 'Ачивка',
        });
      } else {
        await Share.share({
          message: `Открыл ачивку «${item.title_ru}» в Вертушке 🎵`,
        });
      }
    } catch {
      try {
        await Share.share({
          message: `Открыл ачивку «${item.title_ru}» в Вертушке 🎵`,
        });
      } catch {
        // отмена
      }
    } finally {
      setSharing(false);
    }
  };

  const howTo = howToUnlockText(item);
  const isMystery = item.is_hidden && !item.is_unlocked;

  return (
    <View style={styles.sheetBackdrop} pointerEvents="box-none">
      <TouchableOpacity style={StyleSheet.absoluteFill} onPress={onClose} activeOpacity={1} />
      <View style={[styles.sheet, { paddingBottom: insets.bottom + 24 }]}>
        <View style={styles.sheetHandle} />
        <View style={styles.sheetTopRow}>
          <AchievementPin item={item} size={140} />
        </View>
        <Text style={styles.sheetTitle}>
          {item.title_ru || '🥚 Пасхалка'}
        </Text>
        <View style={styles.sheetTierRow}>
          <View
            style={[
              styles.tierChip,
              { backgroundColor: item.tier.color_hex + '22', borderColor: item.tier.color_hex },
            ]}
          >
            <Text style={[styles.tierChipText, { color: item.tier.color_hex }]}>
              {item.tier.label_ru}
            </Text>
          </View>
          {item.is_meta && (
            <View style={styles.metaChip}>
              <Text style={styles.metaChipText}>★ Мета</Text>
            </View>
          )}
        </View>
        {(item.is_unlocked && item.description_done_ru
          ? item.description_done_ru
          : item.description_ru) && (
          <Text style={styles.sheetDescription}>
            {item.is_unlocked && item.description_done_ru
              ? item.description_done_ru
              : item.description_ru}
          </Text>
        )}
        {item.flavor_ru && !item.is_hidden && item.is_unlocked && (
          <Text style={styles.sheetFlavor}>«{item.flavor_ru}»</Text>
        )}
        {item.is_unlocked && item.evidence_text && (
          <Text style={styles.sheetEvidence}>♪ {item.evidence_text}</Text>
        )}

        {/* Прогресс — для счётчиковых ачивок */}
        {item.progress_target > 0 && !item.is_unlocked && (
          <View style={styles.sheetProgressRow}>
            <Text style={styles.sheetProgressText}>
              Прогресс: {item.progress} / {item.progress_target}
            </Text>
            <View style={styles.progressBar}>
              <View
                style={[
                  styles.progressBarFill,
                  {
                    width: `${Math.min(100, (item.progress / Math.max(item.progress_target, 1)) * 100)}%`,
                    backgroundColor: item.tier.color_hex,
                  },
                ]}
              />
            </View>
          </View>
        )}

        {/* Как открыть — для locked */}
        {howTo && (
          <View style={styles.howToRow}>
            <Text style={styles.howToEyebrow}>Как открыть</Text>
            <Text style={styles.howToText}>{howTo}</Text>
          </View>
        )}

        {/* % юзеров — для не-скрытых или уже открытых */}
        {stats && !isMystery && stats.total_users >= 5 && (
          <View style={styles.statsRow}>
            <Ionicons name="people-outline" size={14} color={Colors.textMuted} />
            <Text style={styles.statsText}>
              {formatStatsLine(stats)}
            </Text>
          </View>
        )}

        {/* Дата */}
        {item.is_unlocked && item.unlocked_at && (
          <Text style={styles.sheetDate}>Открыто {formatDate(item.unlocked_at)}</Text>
        )}

        {/* Share — для открытых на своём профиле */}
        {item.is_unlocked && !username && (
          <TouchableOpacity
            style={[styles.shareBtn, sharing && { opacity: 0.6 }]}
            onPress={handleShare}
            disabled={sharing}
          >
            <Ionicons name="share-outline" size={18} color="#FFFFFF" />
            <Text style={styles.shareBtnText}>
              {sharing ? 'Готовим…' : 'Поделиться'}
            </Text>
          </TouchableOpacity>
        )}

        <TouchableOpacity style={styles.sheetCloseBtn} onPress={onClose}>
          <Ionicons name="close" size={22} color={Colors.text} />
        </TouchableOpacity>
      </View>

      {/* Off-screen карточка для шаринга (снимается через view-shot) */}
      <View style={styles.shareCardOffscreen} pointerEvents="none">
        <View ref={shareCardRef} collapsable={false} style={styles.shareCard}>
          <LinearGradient
            colors={[item.tier.color_hex + '33', '#0E0E16']}
            start={{ x: 0, y: 0 }}
            end={{ x: 0, y: 1 }}
            style={styles.shareCardBg}
          >
            <Text style={styles.shareCardBrand}>Вертушка</Text>
            <View style={styles.shareCardPinWrap}>
              <AchievementPin item={item} size={140} glowOverride />
            </View>
            <Text style={styles.shareCardTitle}>{item.title_ru || '🥚 Пасхалка'}</Text>
            <View
              style={[
                styles.shareCardTierChip,
                {
                  backgroundColor: item.tier.color_hex,
                  shadowColor: item.tier.color_hex,
                },
              ]}
            >
              <Text style={styles.shareCardTierText}>
                {item.tier.label_ru.toUpperCase()}
              </Text>
            </View>
            {(item.description_done_ru || item.description_ru) && (
              <Text style={styles.shareCardReason}>
                {item.description_done_ru || item.description_ru}
              </Text>
            )}
            {item.flavor_ru && !item.is_hidden && (
              <Text style={styles.shareCardFlavor}>«{item.flavor_ru}»</Text>
            )}
            {/* Улика «за какую музыку получено» — тот же текст, что в шите.
                Для «Спрятанного трека» это и есть релиз, где нашёлся бонус;
                бэкендовая PNG-карточка рисует эту строку с самого начала,
                клиентская до сих пор молчала. Только музыка: улики с людьми
                и ценами бэкенд в metadata не кладёт (evidence.py). */}
            {item.evidence_text && (
              <Text style={styles.shareCardEvidence} numberOfLines={2}>
                ♪ {item.evidence_text}
              </Text>
            )}
            {item.unlocked_at && (
              <Text style={styles.shareCardDate}>Открыто {formatDate(item.unlocked_at)}</Text>
            )}
          </LinearGradient>
        </View>
      </View>
    </View>
  );
}

function formatStatsLine(stats: AchievementStats): string {
  const pct = stats.unlocked_pct * 100;
  if (pct < 1) {
    return `Менее 1% юзеров уже открыли`;
  }
  if (pct < 100) {
    return `${pct.toFixed(pct < 10 ? 1 : 0)}% юзеров уже открыли`;
  }
  return `Все юзеры открыли`;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

// ─── Styles ─────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  scroll: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  center: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: Colors.background,
  },
  errorText: {
    color: Colors.textMuted,
    fontSize: ms(14),
  },
  summary: {
    paddingHorizontal: Spacing.lg,
    paddingTop: Spacing.lg,
    paddingBottom: Spacing.md,
  },
  summaryHeader: {
    fontSize: ms(28),
    fontWeight: '800',
    color: Colors.text,
    marginBottom: 6,
  },
  summaryCount: {
    fontSize: ms(15),
    color: Colors.textSecondary,
  },
  summaryRandom: {
    marginTop: 4,
    fontSize: ms(14),
    color: Colors.textMuted,
  },
  seriesCard: {
    backgroundColor: M_NAVY,
    borderRadius: BorderRadius.xl,
    paddingHorizontal: Spacing.lg,
    paddingVertical: Spacing.md,
    marginHorizontal: Spacing.md,
    marginBottom: Spacing.md,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: M_GOLD_RIM_SOFT,
  },
  surpriseCard: {
    borderColor: M_EMBER,
    borderWidth: 1.5,
    shadowColor: M_EMBER_GLOW,
    shadowOpacity: 0.5,
    shadowRadius: 14,
    shadowOffset: { width: 0, height: 0 },
    elevation: 4,
  },
  seriesHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  seriesHeaderLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    flex: 1,
    minWidth: 0,
  },
  seriesHeaderText: {
    flexShrink: 1,
  },
  seriesEmoji: {
    fontSize: 22,
    lineHeight: 24,
  },
  seriesTitle: {
    fontSize: ms(17),
    fontWeight: '800',
    color: M_IVORY,
    letterSpacing: -0.3,
  },
  seriesDescription: {
    fontSize: ms(12),
    color: M_IVORY_MUTED,
    marginTop: 1,
  },
  seriesProgressTrack: {
    height: 2,
    backgroundColor: 'rgba(217,168,78,0.18)',
    marginTop: 14,
    marginBottom: 16,
    borderRadius: 1,
    position: 'relative',
  },
  seriesProgressFill: {
    height: '100%',
    backgroundColor: M_GOLD_HI,
    borderRadius: 1,
    shadowColor: M_GOLD,
    shadowOpacity: 0.8,
    shadowRadius: 6,
    shadowOffset: { width: 0, height: 0 },
  },
  seriesProgressDot: {
    position: 'absolute',
    top: -3,
    marginLeft: -4,
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: M_GOLD_HI,
    borderWidth: 2,
    borderColor: M_NAVY,
    shadowColor: M_GOLD,
    shadowOpacity: 0.9,
    shadowRadius: 4,
    shadowOffset: { width: 0, height: 0 },
  },
  surpriseDivider: {
    height: 1,
    backgroundColor: 'rgba(232,90,42,0.27)',
    marginTop: 14,
    marginBottom: 16,
  },
  gridWrap: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: GRID_GAP,
    rowGap: 18,
  },
  gridCell: {
    width: GRID_CELL,
    alignItems: 'center',
  },
  gridCellMeta: {
    width: GRID_CELL,
  },
  gridLabel: {
    marginTop: 8,
    fontSize: ms(12),
    color: M_IVORY,
    textAlign: 'center',
    fontWeight: '600',
  },
  gridLabelMeta: {
    fontWeight: '800',
    fontSize: ms(13),
  },
  gridMetaTag: {
    marginTop: 2,
    fontSize: 9,
    color: M_GOLD,
    fontWeight: '700',
    letterSpacing: 1,
  },
  gridProgress: {
    marginTop: 2,
    fontSize: ms(11),
    color: M_IVORY_MUTED,
    fontWeight: '600',
  },
  surpriseEmpty: {
    paddingVertical: Spacing.lg,
    alignItems: 'center',
  },
  surpriseEmptyText: {
    color: M_IVORY_DIM,
    fontSize: ms(13),
  },
  surpriseHiddenNote: {
    color: M_IVORY_DIM,
    fontSize: ms(12),
    fontStyle: 'italic',
    marginTop: Spacing.md,
    textAlign: 'center',
  },
  sheetBackdrop: {
    position: 'absolute',
    top: 0,
    bottom: 0,
    left: 0,
    right: 0,
    backgroundColor: 'rgba(10, 11, 59, 0.4)',
    justifyContent: 'flex-end',
  },
  sheet: {
    backgroundColor: Colors.background,
    paddingHorizontal: Spacing.lg,
    paddingTop: Spacing.sm,
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    minHeight: 360,
  },
  shareCardOffscreen: {
    position: 'absolute',
    left: -9999,
    top: 0,
  },
  shareCard: {
    width: 1080 / 3,
    height: 1920 / 3,
  },
  shareCardBg: {
    flex: 1,
    paddingHorizontal: 36,
    alignItems: 'center',
    justifyContent: 'center',
  },
  shareCardPinWrap: {
    marginBottom: 8,
  },
  shareCardTitle: {
    fontSize: 28,
    fontWeight: '800',
    color: '#FFFFFF',
    textAlign: 'center',
    marginTop: 12,
  },
  shareCardTierChip: {
    marginTop: 16,
    paddingHorizontal: 18,
    paddingVertical: 8,
    borderRadius: 16,
    shadowOpacity: 0.5,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 2 },
    elevation: 6,
  },
  shareCardTierText: {
    fontSize: 14,
    fontWeight: '800',
    color: '#FFFFFF',
    letterSpacing: 1.5,
  },
  shareCardReason: {
    fontSize: 15,
    fontWeight: '600',
    color: 'rgba(255,255,255,0.92)',
    textAlign: 'center',
    marginTop: 14,
    lineHeight: 21,
    paddingHorizontal: 12,
  },
  shareCardFlavor: {
    fontSize: 15,
    fontStyle: 'italic',
    color: 'rgba(255,255,255,0.82)',
    textAlign: 'center',
    marginTop: 8,
    lineHeight: 21,
  },
  shareCardEvidence: {
    fontSize: 14,
    color: 'rgba(255,255,255,0.72)',
    textAlign: 'center',
    marginTop: 12,
    lineHeight: 19,
    paddingHorizontal: 16,
  },
  shareCardDate: {
    fontSize: 13,
    color: 'rgba(255,255,255,0.6)',
    textAlign: 'center',
    marginTop: 16,
  },
  shareCardBrand: {
    position: 'absolute',
    top: 72,
    fontFamily: 'RubikMonoOne-Regular',
    fontSize: 26,
    color: 'rgba(255,255,255,0.92)',
    textAlign: 'center',
    letterSpacing: 1,
  },
  sheetHandle: {
    width: 36,
    height: 4,
    backgroundColor: Colors.border,
    borderRadius: 2,
    alignSelf: 'center',
    marginBottom: Spacing.md,
  },
  sheetTopRow: {
    alignItems: 'center',
    marginVertical: Spacing.sm,
  },
  sheetTitle: {
    fontSize: ms(24),
    fontWeight: '800',
    color: Colors.text,
    textAlign: 'center',
    marginTop: Spacing.sm,
  },
  sheetTierRow: {
    flexDirection: 'row',
    justifyContent: 'center',
    gap: 8,
    marginTop: 8,
    marginBottom: Spacing.sm,
  },
  tierChip: {
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 12,
    borderWidth: 1,
  },
  tierChipText: {
    fontSize: ms(12),
    fontWeight: '600',
  },
  metaChip: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
    backgroundColor: '#FFF3CD',
    borderWidth: 1,
    borderColor: '#FFD66B',
  },
  metaChipText: {
    fontSize: ms(12),
    fontWeight: '700',
    color: '#7A4E00',
  },
  sheetDescription: {
    fontSize: ms(14),
    color: Colors.textSecondary,
    textAlign: 'center',
    marginTop: 6,
    paddingHorizontal: Spacing.sm,
  },
  sheetFlavor: {
    fontSize: ms(13),
    fontStyle: 'italic',
    color: Colors.textMuted,
    textAlign: 'center',
    marginTop: 10,
    paddingHorizontal: Spacing.md,
  },
  // Улика «за какую музыку получено» — под flavor, тем же приглушённым тоном.
  sheetEvidence: {
    fontSize: ms(12),
    color: Colors.textMuted,
    textAlign: 'center',
    marginTop: 8,
    paddingHorizontal: Spacing.md,
  },
  sheetProgressRow: {
    marginTop: Spacing.lg,
    paddingHorizontal: Spacing.sm,
  },
  sheetProgressText: {
    fontSize: ms(13),
    color: Colors.textSecondary,
    marginBottom: 8,
    textAlign: 'center',
  },
  progressBar: {
    height: 6,
    backgroundColor: Colors.surface,
    borderRadius: 3,
    overflow: 'hidden',
  },
  progressBarFill: {
    height: '100%',
    borderRadius: 3,
  },
  sheetDate: {
    marginTop: Spacing.md,
    fontSize: ms(12),
    color: Colors.textMuted,
    textAlign: 'center',
  },
  sheetCloseBtn: {
    position: 'absolute',
    top: 8,
    right: 8,
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: Colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
  },
  howToRow: {
    marginTop: Spacing.lg,
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm,
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.md,
    marginHorizontal: Spacing.sm,
  },
  howToEyebrow: {
    fontSize: ms(11),
    fontWeight: '700',
    letterSpacing: 1.2,
    textTransform: 'uppercase',
    color: Colors.textMuted,
    marginBottom: 4,
  },
  howToText: {
    fontSize: ms(14),
    color: Colors.text,
    lineHeight: ms(19),
  },
  statsRow: {
    marginTop: Spacing.md,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    justifyContent: 'center',
  },
  statsText: {
    fontSize: ms(12),
    color: Colors.textMuted,
    fontWeight: '500',
  },
  shareBtn: {
    marginTop: Spacing.lg,
    backgroundColor: Colors.royalBlue || '#3B4BF5',
    paddingHorizontal: Spacing.lg,
    paddingVertical: 12,
    borderRadius: 14,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    alignSelf: 'center',
    gap: 8,
  },
  shareBtnText: {
    color: '#FFFFFF',
    fontWeight: '700',
    fontSize: ms(15),
  },
});
