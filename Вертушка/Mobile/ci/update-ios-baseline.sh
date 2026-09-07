#!/usr/bin/env bash
# Осознанное обновление baseline iOS-конфига (см. check-ios-baseline.sh).
# Делает чистый prebuild и перезаписывает ci/ios-baseline/. Diff baseline
# прикладывается к PR с меткой ios-config-change — ревьюер видит, что именно
# изменилось в iOS.
set -euo pipefail
cd "$(dirname "$0")/.."
MOBILE_DIR="$(pwd)"
WORK="$(mktemp -d)"
if [ -d ios ]; then
  mv ios "$WORK/ios.bak"
  trap 'rm -rf "$MOBILE_DIR/ios"; mv "$WORK/ios.bak" "$MOBILE_DIR/ios"; rm -rf "$WORK"' EXIT
else
  trap 'rm -rf "$MOBILE_DIR/ios" "$WORK"' EXIT
fi
npx expo prebuild -p ios --no-install --clean
bash ci/snapshot-ios.sh ci/ios-baseline
echo "baseline обновлён: git diff ci/ios-baseline"
