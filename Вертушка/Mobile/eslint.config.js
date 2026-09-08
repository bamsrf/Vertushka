// https://docs.expo.dev/guides/using-eslint/
//
// Baseline: `eslint-config-expo/flat` (ESLint 9, flat config). Ниже — только
// осознанные отступления. Правила из группы React Compiler выключены целиком:
// проект компилятор не использует, а идиомы RN/Reanimated
// (`useRef(new Animated.Value()).current`, `sharedValue.value = x`,
// `Math.random()` в useMemo для конфетти, глобальный счётчик id для SVG defs)
// дают сотни ложных ошибок без единого реального бага. Если React Compiler
// когда-нибудь включат — эти правила надо вернуть и чинить код под него.
//
// Политика гейта: ошибки = 0 (CI красный), варнинги допустимы и гасятся
// точечно по мере касания файлов, без массовых авто-fix'ов.
const { defineConfig } = require('eslint/config');
const expoConfig = require('eslint-config-expo/flat');
const globals = require('globals');

module.exports = defineConfig([
  expoConfig,
  {
    ignores: [
      'dist/*',
      '.expo/*',
      // CNG: нативные папки не коммитятся, но локально после prebuild лежат рядом.
      'ios/*',
      'android/*',
      // Снимки конфигурации для CI-гейта, не исходники.
      'ci/ios-baseline/*',
    ],
  },
  {
    rules: {
      // --- React Compiler (см. шапку файла) ---
      'react-hooks/refs': 'off',
      'react-hooks/immutability': 'off',
      'react-hooks/set-state-in-effect': 'off',
      'react-hooks/purity': 'off',
      'react-hooks/globals': 'off',
      'react-hooks/preserve-manual-memoization': 'off',

      // Компоненты экспортируются одновременно как named и default
      // (`export function X` + `export default X`) — правило считает
      // `import X from './X'` ошибкой, хотя это ровно задуманный API.
      'import/no-named-as-default': 'off',

      // `require('./assets/…')` — штатный способ подключать статические
      // ассеты (картинки, Lottie, шрифты) в React Native; заменять нечем.
      '@typescript-eslint/no-require-imports': 'off',
    },
  },
  {
    // Jest: setup-файл и тесты живут вне TS-проекта, глобалы `jest`/`it`/`expect`
    // ESLint иначе не знает.
    files: ['jest.setup.js', '__tests__/**/*.{js,ts,tsx}', '**/*.test.{js,ts,tsx}'],
    languageOptions: {
      globals: { ...globals.jest },
    },
  },
]);
