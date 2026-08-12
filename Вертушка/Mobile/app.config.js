/**
 * Динамический конфиг поверх app.json.
 *
 * Всё статическое живёт в app.json — он остаётся единственным источником правды
 * для permissions, плагинов и privacy manifest. Здесь только то, что зависит от
 * окружения и не должно лежать в git.
 *
 * AMPLITUDE_API_KEY подхватывается из Mobile/.env локально (Expo CLI грузит .env
 * до вычисления конфига) и из env билд-профиля в eas.json — на сборках.
 */
const appJson = require('./app.json');

module.exports = () => ({
  ...appJson.expo,
  extra: {
    ...appJson.expo.extra,
    amplitudeApiKey: process.env.AMPLITUDE_API_KEY ?? '',
  },
});
