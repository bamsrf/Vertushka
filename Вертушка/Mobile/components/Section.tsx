/**
 * Section — обёртка с заголовком и опциональной свёрткой.
 * Состояние свёрнутости хранится в Zustand по `id` и переживает уход с экрана.
 */
import { ReactNode, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Platform,
  LayoutAnimation,
  UIManager,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Colors } from '../constants/theme';
import { useSectionsStore } from '../lib/store';

if (Platform.OS === 'android' && UIManager.setLayoutAnimationEnabledExperimental) {
  UIManager.setLayoutAnimationEnabledExperimental(true);
}

interface SectionProps {
  id: string;
  title?: string;
  collapsible?: boolean;
  defaultCollapsed?: boolean;
  rightAction?: ReactNode;
  children: ReactNode;
}

export function Section({
  id,
  title,
  collapsible,
  defaultCollapsed,
  rightAction,
  children,
}: SectionProps) {
  const collapsed = useSectionsStore((s) => s.collapsedSections[id] ?? !!defaultCollapsed);
  const toggle = useSectionsStore((s) => s.toggleSection);
  const initSection = useSectionsStore((s) => s.initSection);

  useEffect(() => {
    if (defaultCollapsed) initSection(id, true);
  }, [id, defaultCollapsed, initSection]);

  const handleToggle = () => {
    LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
    toggle(id);
  };

  if (!title) {
    return <View style={styles.container}>{children}</View>;
  }

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity
          style={styles.headerLeft}
          onPress={collapsible ? handleToggle : undefined}
          activeOpacity={collapsible ? 0.7 : 1}
          disabled={!collapsible}
        >
          {collapsible && (
            <Ionicons
              name={collapsed ? 'chevron-forward' : 'chevron-down'}
              size={16}
              color={Colors.textSecondary}
              style={styles.chevron}
            />
          )}
          <Text style={styles.title}>{title}</Text>
        </TouchableOpacity>
        {rightAction ? <View>{rightAction}</View> : null}
      </View>
      {!collapsed && <View>{children}</View>}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    marginBottom: 16,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 20,
    marginBottom: 8,
  },
  headerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
  },
  chevron: {
    marginRight: 4,
    marginLeft: -2,
  },
  title: {
    fontSize: 14,
    fontWeight: '600',
    color: Colors.text,
    letterSpacing: 0.2,
  },
});
