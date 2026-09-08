/**
 * Подмена `react-native` для кода приложения (см. metro.config.js, M3).
 *
 * Отдаёт настоящий модуль react-native, но `Text` и `TextInput` — из
 * `scaledText.tsx`, с дефолтным `maxFontSizeMultiplier`. Proxy, а не
 * `{ ...RN, Text }`: index react-native — объект из ленивых геттеров, и
 * перечисление ключей дёрнуло бы их все разом (часть из них — предупреждения
 * об удалённых модулях). Babel компилирует `import { Text } from 'react-native'`
 * в обращение `_reactNative.Text` в момент использования — get-ловушка это
 * ловит.
 *
 * Файлы в lib/fontScale/ alias'ом не накрываются, поэтому `require` ниже
 * получает настоящий react-native.
 */
const RN = require('react-native');
const { Text, TextInput } = require('./scaledText');

module.exports = new Proxy(RN, {
  get(target, key, receiver) {
    if (key === 'Text') return Text;
    if (key === 'TextInput') return TextInput;
    return Reflect.get(target, key, receiver);
  },
});
