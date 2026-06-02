// Финальные PNG-дизайны пинов (512×512). Ключ — icon_slug ачивки.
// Источник — _raw/*.png (2048²), ресайз через sips -Z 512.
// Показываются ТОЛЬКО для открытых ачивок (см. AchievementPin.pickAsset).
import type { ImageSourcePropType } from 'react-native';

export const DESIGN_PNGS: Record<string, ImageSourcePropType> = {
  a1_first_record: require('./a1_first_record.png'),
  a2_first_wishlist: require('./a2_first_wishlist.png'),
  a3_avatar: require('./a3_avatar.png'),
  a4_public_profile: require('./a4_public_profile.png'),
  b1_starter: require('./b1_starter.png'),
  b2_collector: require('./b2_collector.png'),
  b3_archivist: require('./b3_archivist.png'),
  b4_curator: require('./b4_curator.png'),
  b5_keeper: require('./b5_keeper.png'),
  c3_collectible_x1: require('./c3_collectible_x1.png'),
  d3_country_x30: require('./d3_country_x30.png'),
  r_self_titled: require('./r_self_titled.png'),
  r_thirty_three: require('./r_thirty_three.png'),
};
