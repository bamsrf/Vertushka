/**
 * GiftMatchModal — «кажется, эту пластинку вам подарили».
 *
 * Показывается, когда пользователь добавил в коллекцию пластинку, под которую
 * в его вишлисте висит активная бронь подарка. Частый случай: даритель
 * забронировал одну версию альбома, а подарил другой прессинг — тогда рядом
 * показываем и то, что лежало в вишлисте.
 *
 * «Да» — бронь закрывается, пункт уходит из вишлиста, даритель получает
 * подтверждение и ачивку. «Нет» — всё остаётся как было, но переспрашивать
 * по этой броне мы больше не будем.
 *
 * Имя дарителя здесь не показывается: бронь для получателя анонимна.
 */
import { useEffect, useRef, useState } from 'react';
import {
  View,
  Text,
  Animated,
  StyleSheet,
  TouchableOpacity,
  ActivityIndicator,
} from 'react-native';
import { Image } from 'expo-image';

import { Icon, RootModalOverlay } from '@/components/ui';
import { useCollectionStore } from '../lib/store';
import { resolveMediaUrl } from '../lib/api';
import { toast } from '../lib/toast';
import { analytics } from '../lib/analytics';
import { Colors, Spacing, BorderRadius } from '../constants/theme';

export function GiftMatchModal() {
  const pending = useCollectionStore((s) => s.pendingGiftMatch);
  const confirmGiftMatch = useCollectionStore((s) => s.confirmGiftMatch);
  const dismissGiftMatch = useCollectionStore((s) => s.dismissGiftMatch);
  const [isBusy, setIsBusy] = useState(false);

  // Знаменатель точности матчинга. Ключ — booking_id, а не факт наличия
  // pending: без него повторный рендер по любой причине слал бы показ заново
  // и раздувал знаменатель. Хук стоит выше раннего return — иначе порядок
  // хуков менялся бы между рендерами.
  const shownBookingId = pending?.match.booking_id;
  const matchKind = pending?.match.match_kind;
  useEffect(() => {
    if (!shownBookingId || !matchKind) return;
    analytics.giftMatchShown(matchKind);
  }, [shownBookingId, matchKind]);

  // Своё проявление: раньше его давал animationType="fade" у RN-модалки, но
  // на iOS диалог теперь рисуется в FullWindowOverlay — там анимации нет.
  // Один и тот же fade на обеих платформах, поэтому Android-модалка
  // смонтирована с animationType="none".
  const fade = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    if (!shownBookingId) {
      fade.setValue(0);
      return;
    }
    Animated.timing(fade, { toValue: 1, duration: 180, useNativeDriver: true }).start();
  }, [shownBookingId, fade]);

  if (!pending) return null;

  const { match, addedRecord } = pending;
  // Разные версии показываем парой, одинаковые — одной обложкой.
  const isDifferentVersion = match.match_kind !== 'exact';

  const handleConfirm = async () => {
    if (isBusy) return;
    setIsBusy(true);
    try {
      await confirmGiftMatch();
      toast.success('Подарок отмечен', 'Мы сообщим дарителю, что пластинка дошла');
    } catch (error: any) {
      toast.error(
        'Не удалось отметить',
        error?.response?.data?.detail || 'Попробуйте позже из раздела подарков'
      );
    } finally {
      setIsBusy(false);
    }
  };

  const handleDismiss = async () => {
    if (isBusy) return;
    setIsBusy(true);
    try {
      await dismissGiftMatch();
    } finally {
      setIsBusy(false);
    }
  };

  return (
    <RootModalOverlay onRequestClose={handleDismiss}>
      <Animated.View style={[styles.overlay, { opacity: fade }]}>
        <View style={styles.sheet}>
          <View style={styles.iconWrap}>
            <Icon name="gift" size={22} color={Colors.royalBlue} />
          </View>

          <Text style={styles.title}>Это подарок?</Text>
          <Text style={styles.subtitle}>
            {isDifferentVersion
              ? 'Похоже, вам подарили эту пластинку — в вашем вишлисте забронирована другая версия того же альбома.'
              : 'Эта пластинка забронирована кем-то как подарок вам.'}
          </Text>

          <View style={styles.covers}>
            <CoverTile
              label="Добавили"
              cover={addedRecord.cover_image_url}
              artist={addedRecord.artist}
              title={addedRecord.title}
              year={addedRecord.year}
            />
            {isDifferentVersion ? (
              <>
                <Icon name="swap-horizontal" size={16} color={Colors.textMuted} />
                <CoverTile
                  label="В вишлисте"
                  cover={match.wished_record.cover_image_url}
                  artist={match.wished_record.artist}
                  title={match.wished_record.title}
                  year={match.wished_record.year}
                />
              </>
            ) : null}
          </View>

          <Text style={styles.note}>
            Если да — уберём пластинку из вишлиста и сообщим дарителю, что подарок дошёл.
          </Text>

          <TouchableOpacity
            style={[styles.primaryBtn, isBusy && styles.btnBusy]}
            onPress={handleConfirm}
            disabled={isBusy}
            accessibilityRole="button"
          >
            {isBusy ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={styles.primaryBtnTxt}>Да, мне её подарили</Text>
            )}
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.ghostBtn}
            onPress={handleDismiss}
            disabled={isBusy}
            accessibilityRole="button"
          >
            <Text style={styles.ghostBtnTxt}>Нет, купил сам</Text>
          </TouchableOpacity>
        </View>
      </Animated.View>
    </RootModalOverlay>
  );
}

function CoverTile({
  label,
  cover,
  artist,
  title,
  year,
}: {
  label: string;
  cover?: string | null;
  artist: string;
  title: string;
  year?: number | null;
}) {
  return (
    <View style={styles.tile}>
      <Text style={styles.tileLabel}>{label}</Text>
      <View style={styles.tileCover}>
        {cover ? (
          <Image
            source={resolveMediaUrl(cover)}
            style={{ width: '100%', height: '100%' }}
            cachePolicy="disk"
          />
        ) : null}
      </View>
      <Text numberOfLines={1} style={styles.tileArtist}>
        {artist}
      </Text>
      <Text numberOfLines={2} style={styles.tileTitle}>
        {title}
        {year ? ` · ${year}` : ''}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: Colors.overlay,
    alignItems: 'center',
    justifyContent: 'center',
    padding: Spacing.lg,
  },
  sheet: {
    width: '100%',
    maxWidth: 400,
    backgroundColor: Colors.background,
    borderRadius: BorderRadius.lg,
    padding: Spacing.lg,
    alignItems: 'center',
  },
  iconWrap: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: Colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: Spacing.sm,
  },
  title: {
    fontSize: 19,
    fontWeight: '700',
    color: Colors.text,
    textAlign: 'center',
  },
  subtitle: {
    fontSize: 14,
    lineHeight: 20,
    color: Colors.textSecondary,
    textAlign: 'center',
    marginTop: 6,
  },
  covers: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: Spacing.sm,
    marginTop: Spacing.md,
    marginBottom: Spacing.sm,
  },
  tile: { width: 120, alignItems: 'center' },
  tileLabel: {
    fontSize: 11,
    color: Colors.textMuted,
    marginBottom: 4,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  tileCover: {
    width: 96,
    height: 96,
    borderRadius: BorderRadius.sm,
    overflow: 'hidden',
    backgroundColor: Colors.surface,
  },
  tileArtist: {
    fontSize: 12,
    fontWeight: '600',
    color: Colors.text,
    marginTop: 6,
    textAlign: 'center',
  },
  tileTitle: {
    fontSize: 11,
    color: Colors.textSecondary,
    textAlign: 'center',
  },
  note: {
    fontSize: 12,
    lineHeight: 17,
    color: Colors.textMuted,
    textAlign: 'center',
    marginTop: Spacing.xs,
    marginBottom: Spacing.md,
  },
  primaryBtn: {
    width: '100%',
    height: 48,
    borderRadius: BorderRadius.md,
    backgroundColor: Colors.royalBlue,
    alignItems: 'center',
    justifyContent: 'center',
  },
  btnBusy: { opacity: 0.55 },
  primaryBtnTxt: { color: '#fff', fontSize: 15, fontWeight: '600' },
  ghostBtn: {
    width: '100%',
    height: 44,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 4,
  },
  ghostBtnTxt: { color: Colors.textSecondary, fontSize: 14, fontWeight: '500' },
});
