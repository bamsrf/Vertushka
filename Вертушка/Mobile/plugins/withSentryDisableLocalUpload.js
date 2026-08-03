/**
 * Отключает загрузку source maps в Sentry для локальных сборок.
 *
 * Проблема. Build phase «Bundle React Native code and images» вызывает
 * scripts/sentry-xcode.sh из @sentry/react-native, тот зовёт sentry-cli, а
 * sentry-cli не находит организацию: ios/sentry.properties пишется плагином
 * Sentry и ждёт SENTRY_ORG / SENTRY_PROJECT / SENTRY_AUTH_TOKEN из окружения.
 * Возврат 1 — и вся сборка красная, хотя код скомпилировался.
 *
 * EAS этого не видит: в eas.json те же флаги заданы через env. Ломается
 * только локальный путь — кнопка ▶ в Xcode и `npx expo run:ios`.
 *
 * Почему именно .xcode.env.local. sentry-xcode.sh:51 проверяет
 * SENTRY_DISABLE_AUTO_UPLOAD как переменную ШЕЛЛА. Файл
 * .env.sentry-build-plugin сюда не годится: строка 16 того же скрипта лишь
 * передаёт его путь внутрь sentry-cli через SENTRY_DOTENV_PATH, а сам скрипт
 * его не подключает. Зато build phase явно делает `source .xcode.env.local`
 * до вызова Sentry — туда переменная и доходит.
 *
 * Почему плагин, а не файл руками. ios/ в .gitignore и стирается при
 * `expo prebuild`. Плагин переживает regenerate и лежит в git, так что на
 * свежем клоне грабли не повторяются.
 *
 * Прод-загрузку source maps это не трогает: она идёт через EAS, где
 * SENTRY_AUTH_TOKEN есть.
 *
 * См. docs/plans/APPSTORE_LAUNCH_PLAN.md §4.4.
 */
const { withDangerousMod } = require('expo/config-plugins');
const fs = require('fs');
const path = require('path');

const LINE = 'export SENTRY_DISABLE_AUTO_UPLOAD=true';

const withSentryDisableLocalUpload = (config) =>
  withDangerousMod(config, [
    'ios',
    (cfg) => {
      const envPath = path.join(cfg.modRequest.platformProjectRoot, '.xcode.env.local');
      const existing = fs.existsSync(envPath) ? fs.readFileSync(envPath, 'utf8') : '';

      // Идемпотентность: prebuild может пройти много раз, дубли не нужны.
      if (existing.includes('SENTRY_DISABLE_AUTO_UPLOAD')) return cfg;

      const prefix = existing && !existing.endsWith('\n') ? '\n' : '';
      fs.writeFileSync(envPath, `${existing}${prefix}${LINE}\n`);
      return cfg;
    },
  ]);

module.exports = withSentryDisableLocalUpload;
