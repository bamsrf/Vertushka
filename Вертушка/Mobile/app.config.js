/**
 * Динамический конфиг поверх app.json.
 *
 * Всё статическое живёт в app.json — он остаётся единственным источником правды
 * для permissions, плагинов и privacy manifest. Здесь только то, что зависит от
 * окружения и не должно лежать в git.
 */
const appJson = require('./app.json');

/**
 * Выбор Amplitude-проекта: прод-ключ бьёт dev-ключ.
 *
 * С выходом в стор прод-проект перестал быть песочницей — в нём живые люди, и
 * проклик разработчика там уже не «плюс одно событие», а смещённая воронка.
 * Поэтому окружения разведены по двум переменным:
 *
 * - `AMPLITUDE_API_KEY`     — прод. Лежит в EAS-окружении `production` и
 *                             НЕ должен лежать в локальном `Mobile/.env`.
 * - `AMPLITUDE_API_KEY_DEV` — dev-проект. Локальный `.env` и EAS-окружения
 *                             `development` / `preview`.
 *
 * Порядок именно такой, а не «dev важнее», из-за OTA: `npm run update:prod`
 * (`eas update --environment production`) подтягивает серверный
 * `AMPLITUDE_API_KEY`, но локальный `.env` с dev-ключом при этом тоже
 * загружается. Если бы dev выигрывал, любая публикация обновления с машины
 * разработчика тихо переводила бы прод-аудиторию в dev-проект.
 *
 * Обратная сторона: `eas update` БЕЗ `--environment production` уведёт события
 * в dev-проект. Раньше в этом случае аналитика просто выключалась — теперь
 * врёт, что стало ещё одной причиной публиковать только через `update:prod`.
 * См. docs/plans/product/ANALYTICS_PLAN.md.
 */
const prodKey = process.env.AMPLITUDE_API_KEY ?? '';
const devKey = process.env.AMPLITUDE_API_KEY_DEV ?? '';
const amplitudeApiKey = prodKey || devKey;

module.exports = () => ({
  ...appJson.expo,
  extra: {
    ...appJson.expo.extra,
    amplitudeApiKey,
    // Какой проект в итоге выбран. Нужно только для dev-предупреждения в
    // _layout.tsx: без явной метки «локальный билд пишет в прод» никак не
    // отличить от «локальный билд пишет в dev» — ключи выглядят одинаково.
    amplitudeEnv: amplitudeApiKey ? (prodKey ? 'prod' : 'dev') : 'none',
  },
});
