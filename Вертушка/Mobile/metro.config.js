// Metro — дефолт Expo плюс один alias (M3 в ANDROID_PORT_PLAN):
// `react-native` для кода приложения резолвится в lib/fontScale/reactNativeShim.js,
// где `Text`/`TextInput` получают дефолтный `maxFontSizeMultiplier`.
// Прежний `Text.defaultProps` на RN 0.86 не работает, а править 120 файлов
// импортов ради одного пропа — лишний диф на iOS.
//
// Alias действует только на исходники приложения (не node_modules, не сам
// shim) и только на ios/android: на web Expo сам подставляет react-native-web.
const path = require('path');
const { getDefaultConfig } = require('expo/metro-config');

const config = getDefaultConfig(__dirname);

const SHIM_DIR = path.resolve(__dirname, 'lib', 'fontScale');
const SHIM_PATH = path.join(SHIM_DIR, 'reactNativeShim.js');

const upstreamResolve = config.resolver.resolveRequest;

config.resolver.resolveRequest = (context, moduleName, platform) => {
  const resolve = upstreamResolve ?? context.resolveRequest;
  if (
    moduleName === 'react-native' &&
    (platform === 'ios' || platform === 'android') &&
    !context.originModulePath.includes(`${path.sep}node_modules${path.sep}`) &&
    !context.originModulePath.startsWith(SHIM_DIR)
  ) {
    return { type: 'sourceFile', filePath: SHIM_PATH };
  }
  return resolve(context, moduleName, platform);
};

module.exports = config;
