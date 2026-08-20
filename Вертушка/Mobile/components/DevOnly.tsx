/**
 * Гейт служебных экранов (app/dev/*).
 *
 * Экраны-песочницы уезжают в релизный бандл вместе со всем остальным: кнопки
 * на них в проде нет (ссылка в профиле уже под `__DEV__`), но deep link вида
 * `vertushka://dev/icons` открывает их у любого, кто знает адрес. Guideline
 * 2.3.1 запрещает скрытую и недокументированную функциональность, и трактуют
 * его широко — закрыть дешевле, чем объясняться на ревью.
 *
 * Почему обёртка, а не `if (!__DEV__) return ...` внутри компонента: ранний
 * выход пришлось бы ставить после всех хуков (иначе ломается их порядок), то
 * есть экран всё равно исполнялся бы — с подписками, таймерами и запросами.
 * Обёртка подменяет компонент целиком: в проде тело экрана не вызывается.
 */
import type { ComponentType } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { Colors } from '../constants/theme';

function DevOnlyStub() {
  return (
    <View style={styles.stub}>
      <Text style={styles.text}>Dev-only</Text>
    </View>
  );
}

export function withDevOnly<P extends object>(Screen: ComponentType<P>): ComponentType<P> {
  return __DEV__ ? Screen : DevOnlyStub;
}

const styles = StyleSheet.create({
  stub: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: Colors.background },
  text: { fontSize: 13, color: Colors.textSecondary },
});
