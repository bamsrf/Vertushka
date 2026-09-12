/**
 * Dev-превью сторис «стоимость коллекции». НЕ входит в продовую навигацию:
 * роут открывается только вручную (vertushka://dev-story-preview?v=label)
 * и в проде рендерит заглушку.
 *
 * Зачем: смотреть все три вида сторис на фиксированных данных, не открывая экран стоимости реального аккаунта.
 * Рендерится тот же CollectionValueStory, что уходит в view-shot.
 */
import { View, Text, StyleSheet, useWindowDimensions } from 'react-native';
import { useLocalSearchParams } from 'expo-router';

import {
  CollectionValueStoryPreview,
  type CollectionStoryData,
  type CollectionStoryVariant,
} from '../components/share/CollectionValueStory';

const MOCK: CollectionStoryData = {
  username: 'vertushka_4U',
  totalRub: 331902,
  totalUsd: null,
  deltaRub: 50496,
  recordsCount: 72,
  oldestYear: 1970,
  favoriteDecade: '2020-е',
  top: [
    { title: 'Baile', artist: 'FBC, VHOOR', meta: 'FBC, VHOOR · 2026', priceRub: 13239, isCollectible: false },
    { title: 'Inside: Deluxe', artist: 'Bo Burnham', meta: 'Bo Burnham · 2022', priceRub: 10729, isCollectible: false },
    { title: 'Lateralus', artist: 'Tool', meta: 'Tool · 2011', priceRub: 9871, isCollectible: false },
  ],
};

const VARIANTS: CollectionStoryVariant[] = ['hifi', 'ivory', 'label'];

export default function DevStoryPreview() {
  const { v } = useLocalSearchParams<{ v?: string }>();
  const { width } = useWindowDimensions();

  if (!__DEV__) {
    return (
      <View style={styles.center}>
        <Text>Недоступно</Text>
      </View>
    );
  }

  const variant = VARIANTS.includes(v as CollectionStoryVariant) ? (v as CollectionStoryVariant) : 'label';

  return (
    <View style={styles.center}>
      <CollectionValueStoryPreview variant={variant} data={MOCK} width={width} />
    </View>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: '#000' },
});
