/**
 * Google Sign In спрятан до лучших времён: кнопка не показывается
 * (SocialAuthButtons.tsx), а нативный SDK не должен попадать в сборку —
 * лишний третий SDK в бинаре тянет за собой GoogleSignIn/GoogleUtilities/
 * AppCheckCore и свою поверхность в App Privacy ради выключенной функции.
 *
 * Пакет при этом остаётся в package.json намеренно: Metro резолвит
 * require() статически, и без установленного модуля сломается сам бандл.
 * Здесь мы отключаем именно автолинковку нативной части — JS-код живой,
 * `require` возвращает модуль-заглушку без нативного биндинга, кнопка
 * скрыта. Вернуть Google-вход = удалить этот файл и блок expo.autolinking
 * из package.json, вернуть плагин в app.json.
 */
module.exports = {
  dependencies: {
    '@react-native-google-signin/google-signin': {
      platforms: {
        ios: null,
        android: null,
      },
    },
  },
};
