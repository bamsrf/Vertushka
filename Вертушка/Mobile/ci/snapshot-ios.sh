#!/usr/bin/env bash
# Снимок iOS-конфига из сгенерированного ./ios в папку $1.
# Текстовые файлы копируются как есть (storyboard — с вырезанными
# рандомными id), бинарные ассеты — как список «путь размер md5».
# Плюс `expo config --type introspect` секции ios и plugins.
set -euo pipefail
OUT="${1:?usage: snapshot-ios.sh <out-dir>}"
rm -rf "$OUT"; mkdir -p "$OUT"

APP_DIR="$(find ios -maxdepth 1 -mindepth 1 -type d ! -name Pods ! -name '*.xcodeproj' ! -name '*.xcworkspace' | head -1)"
[ -n "$APP_DIR" ] || { echo "нет ios/<App>/"; exit 1; }

cp ios/Podfile "$OUT/Podfile"
cp ios/Podfile.properties.json "$OUT/Podfile.properties.json"
cp "$APP_DIR/Info.plist" "$OUT/Info.plist"
cp "$APP_DIR"/*.entitlements "$OUT/App.entitlements"
cp "$APP_DIR/PrivacyInfo.xcprivacy" "$OUT/PrivacyInfo.xcprivacy"
cp "$APP_DIR/AppDelegate.swift" "$OUT/AppDelegate.swift"
cp "$APP_DIR/Supporting/Expo.plist" "$OUT/Expo.plist"
sed -E 's/ id="[^"]*"//g' "$APP_DIR/SplashScreen.storyboard" >"$OUT/SplashScreen.storyboard"

# Ассеты: имя, размер, md5 — без бинарников в git.
( cd "$APP_DIR/Images.xcassets" && find . -type f | sort | while read -r f; do
    printf '%s %s %s\n' "$f" "$(wc -c <"$f" | tr -d ' ')" "$(md5sum "$f" 2>/dev/null | cut -d' ' -f1 || md5 -q "$f")"
  done ) >"$OUT/Images.xcassets.manifest"

npx expo config --type introspect --json \
  | node -e '
    let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{
      const c=JSON.parse(s);
      const pick={ios:c.ios, plugins:c.plugins, runtimeVersion:c.runtimeVersion, updates:c.updates,
                  newArchEnabled:c.newArchEnabled, version:c.version, sdkVersion:c.sdkVersion};
      process.stdout.write(JSON.stringify(pick,null,2)+"\n");
    });' >"$OUT/introspect-ios.json"
