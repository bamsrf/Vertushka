// Нужен для jest (jest-expo). Metro использует ту же preset по умолчанию.
module.exports = function (api) {
  api.cache(true);
  return { presets: ['babel-preset-expo'] };
};
