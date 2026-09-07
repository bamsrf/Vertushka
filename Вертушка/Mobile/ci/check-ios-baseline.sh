#!/usr/bin/env bash
# Гейт «iOS-конфиг не изменился».
#
# Делает чистый `expo prebuild -p ios --no-install` во временную папку и
# сравнивает сгенерированные файлы iOS-проекта с зафиксированным baseline в
# ci/ios-baseline/. Любая правка app.json / config-плагина / зависимости,
# которая меняет Info.plist, entitlements, storyboard splash, Podfile или
# набор image-ассетов, делает гейт красным.
#
# Если изменение iOS осознанное — обновить baseline: `bash ci/update-ios-baseline.sh`
# и приложить diff к PR с меткой ios-config-change.
#
# Запускается из Mobile/. Не требует macOS: pods вне darwin пропускаются.
set -euo pipefail

cd "$(dirname "$0")/.."
MOBILE_DIR="$(pwd)"
BASELINE="$MOBILE_DIR/ci/ios-baseline"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# Prebuild пишет в ./ios; локально там может лежать рабочая копия — прячем её.
if [ -d ios ]; then
  mv ios "$WORK/ios.bak"
  trap 'rm -rf "$MOBILE_DIR/ios"; mv "$WORK/ios.bak" "$MOBILE_DIR/ios"; rm -rf "$WORK"' EXIT
fi

npx expo prebuild -p ios --no-install --clean >"$WORK/prebuild.log" 2>&1 || {
  cat "$WORK/prebuild.log"; echo "::error::expo prebuild -p ios упал"; exit 1;
}

bash ci/snapshot-ios.sh "$WORK/actual"

if diff -ru "$BASELINE" "$WORK/actual" >"$WORK/diff.txt"; then
  echo "iOS-конфиг совпадает с baseline"
else
  cat "$WORK/diff.txt"
  echo "::error::iOS-конфиг отличается от ci/ios-baseline. Осознанно? bash ci/update-ios-baseline.sh + метка ios-config-change"
  exit 1
fi
