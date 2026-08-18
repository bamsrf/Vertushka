/**
 * Настройки профиля (карточки, статистика, избранные)
 */
import { useEffect, useState, useCallback, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  Animated,
  Pressable,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Icon, Toggle } from '@/components/ui';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useProfileStore, useCollectionStore } from '../../lib/store';
import { toast } from '../../lib/toast';
import { Colors, Typography, Spacing, BorderRadius } from '../../constants/theme';
import { CollectionItem } from '../../lib/types';
import { RecordCard } from '../../components/RecordCard';

function SettingRow({ label, description, value, settingKey, onToggle, disabled }: {
  label: string;
  description?: string;
  value: boolean;
  settingKey: string;
  onToggle: (key: string, value: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <View style={styles.settingRow}>
      <View style={styles.settingInfo}>
        <Text style={styles.settingLabel}>{label}</Text>
        {description && <Text style={styles.settingDescription}>{description}</Text>}
      </View>
      <Toggle
        value={value}
        onValueChange={(val) => onToggle(settingKey, val)}
        disabled={disabled}
      />
    </View>
  );
}

export default function ShareProfileScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { collectionItems } = useCollectionStore();
  const { settings, isLoading, isSaving, fetchSettings, updateSettings, updateHighlights } = useProfileStore();
  const [selectingHighlights, setSelectingHighlights] = useState(false);
  const [selectedHighlights, setSelectedHighlights] = useState<Set<string>>(new Set());

  useEffect(() => {
    fetchSettings();
  }, []);

  useEffect(() => {
    if (settings?.highlight_record_ids) {
      setSelectedHighlights(new Set(settings.highlight_record_ids));
    }
  }, [settings?.highlight_record_ids]);

  const handleToggle = useCallback(async (key: string, value: boolean) => {
    try {
      await updateSettings({ [key]: value });
    } catch {
      toast.error('Не удалось сохранить настройку');
    }
  }, [updateSettings]);

  const handleToggleHighlight = useCallback((itemId: string) => {
    setSelectedHighlights(prev => {
      const next = new Set(prev);
      if (next.has(itemId)) {
        next.delete(itemId);
      } else if (next.size < 4) {
        next.add(itemId);
      } else {
        toast.info('Можно выбрать не более 4 избранных пластинок');
      }
      return next;
    });
  }, []);

  const handleSaveHighlights = useCallback(async () => {
    try {
      await updateHighlights(Array.from(selectedHighlights));
      setSelectingHighlights(false);
      toast.success('Избранные пластинки обновлены');
    } catch {
      toast.error('Не удалось сохранить');
    }
  }, [selectedHighlights, updateHighlights]);

  if (isLoading && !settings) {
    return (
      <View style={[styles.container, styles.center, { paddingTop: insets.top }]}>
        <ActivityIndicator size="large" color={Colors.royalBlue} />
      </View>
    );
  }

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backButton}>
          <Icon name="arrow-back" size={24} color={Colors.royalBlue} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Настройки профиля</Text>
        <View style={styles.placeholder} />
      </View>

      <ScrollView
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
      >
        {/* Активация профиля */}
        <Text style={styles.sectionTitle}>Публичный профиль</Text>
        <View style={styles.section}>
          <SettingRow
            label="Активировать профиль"
            description="Ваш профиль будет доступен по ссылке"
            value={settings?.is_active ?? false}
            settingKey="is_active"
            onToggle={handleToggle}
            disabled={isSaving}
          />
        </View>

        {/* Настройки карточек */}
        <Text style={styles.sectionTitle}>Информация на карточках</Text>
        <View style={styles.section}>
          <SettingRow
            label="Год выпуска"
            value={settings?.show_record_year ?? true}
            settingKey="show_record_year"
            onToggle={handleToggle}
            disabled={isSaving}
          />
          <SettingRow
            label="Лейбл"
            value={settings?.show_record_label ?? true}
            settingKey="show_record_label"
            onToggle={handleToggle}
            disabled={isSaving}
          />
          <SettingRow
            label="Формат"
            value={settings?.show_record_format ?? true}
            settingKey="show_record_format"
            onToggle={handleToggle}
            disabled={isSaving}
          />
          <SettingRow
            label="Цены пластинок"
            description="Показывать примерную стоимость"
            value={settings?.show_record_prices ?? false}
            settingKey="show_record_prices"
            onToggle={handleToggle}
            disabled={isSaving}
          />
        </View>


        {/* Избранные пластинки */}
        <Text style={styles.sectionTitle}>Избранные пластинки</Text>
        <Text style={styles.sectionDescription}>
          Выберите до 4 пластинок, которые будут выделены на вашем профиле
        </Text>

        {!selectingHighlights ? (
          <TouchableOpacity
            style={styles.highlightsButton}
            onPress={() => setSelectingHighlights(true)}
          >
            <Icon name="star-outline" size={20} color={Colors.royalBlue} />
            <Text style={styles.highlightsButtonText}>
              Выбрать избранные ({selectedHighlights.size}/4)
            </Text>
          </TouchableOpacity>
        ) : (
          <View>
            <View style={styles.highlightsHeader}>
              <Text style={styles.highlightsCount}>
                Выбрано: {selectedHighlights.size}/4
              </Text>
              <View style={styles.highlightsActions}>
                <TouchableOpacity
                  style={styles.highlightsCancelButton}
                  onPress={() => {
                    setSelectingHighlights(false);
                    if (settings?.highlight_record_ids) {
                      setSelectedHighlights(new Set(settings.highlight_record_ids));
                    }
                  }}
                >
                  <Text style={styles.highlightsCancelText}>Отмена</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={styles.highlightsSaveButton}
                  onPress={handleSaveHighlights}
                >
                  <Text style={styles.highlightsSaveText}>Сохранить</Text>
                </TouchableOpacity>
              </View>
            </View>

            <View style={styles.highlightsGrid}>
              {collectionItems.map((item: CollectionItem) => (
                <TouchableOpacity
                  key={item.id}
                  style={[
                    styles.highlightItem,
                    selectedHighlights.has(item.record.id) && styles.highlightItemSelected,
                  ]}
                  onPress={() => handleToggleHighlight(item.record.id)}
                >
                  <RecordCard
                    record={item.record}
                    isSelectionMode
                    isSelected={selectedHighlights.has(item.record.id)}
                    onToggleSelection={() => handleToggleHighlight(item.record.id)}
                  />
                </TouchableOpacity>
              ))}
            </View>
          </View>
        )}

        <View style={{ height: insets.bottom + Spacing.xl }} />
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  center: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: Spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: Colors.divider,
  },
  headerTitle: {
    ...Typography.h4,
    color: Colors.royalBlue,
  },
  backButton: {
    width: 36,
    height: 36,
    alignItems: 'center',
    justifyContent: 'center',
  },
  placeholder: {
    width: 36,
    height: 36,
  },
  content: {
    padding: Spacing.lg,
  },
  sectionTitle: {
    ...Typography.h4,
    color: Colors.royalBlue,
    marginBottom: Spacing.sm,
    marginTop: Spacing.md,
  },
  sectionDescription: {
    ...Typography.bodySmall,
    color: Colors.textSecondary,
    marginBottom: Spacing.md,
  },
  section: {
    backgroundColor: Colors.background,
    borderRadius: BorderRadius.lg,
    borderWidth: 1,
    borderColor: Colors.border,
    overflow: 'hidden',
    marginBottom: Spacing.md,
  },
  settingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: Spacing.md,
    paddingHorizontal: Spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: Colors.divider,
  },
  settingInfo: {
    flex: 1,
    marginRight: Spacing.md,
  },
  settingLabel: {
    ...Typography.body,
    color: Colors.text,
  },
  settingDescription: {
    ...Typography.caption,
    color: Colors.textSecondary,
    marginTop: 2,
  },
  highlightsButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
    paddingVertical: Spacing.md,
    paddingHorizontal: Spacing.lg,
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.md,
    marginBottom: Spacing.md,
  },
  highlightsButtonText: {
    ...Typography.body,
    color: Colors.royalBlue,
  },
  highlightsHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: Spacing.md,
  },
  highlightsCount: {
    ...Typography.bodyBold,
    color: Colors.text,
  },
  highlightsActions: {
    flexDirection: 'row',
    gap: Spacing.sm,
  },
  highlightsCancelButton: {
    paddingVertical: Spacing.sm,
    paddingHorizontal: Spacing.md,
    borderRadius: BorderRadius.md,
    backgroundColor: Colors.surface,
  },
  highlightsCancelText: {
    ...Typography.buttonSmall,
    color: Colors.textSecondary,
  },
  highlightsSaveButton: {
    paddingVertical: Spacing.sm,
    paddingHorizontal: Spacing.md,
    borderRadius: BorderRadius.md,
    backgroundColor: Colors.royalBlue,
  },
  highlightsSaveText: {
    ...Typography.buttonSmall,
    color: Colors.background,
  },
  highlightsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
  },
  highlightItem: {
    marginBottom: Spacing.sm,
  },
  highlightItemSelected: {
    opacity: 1,
  },
});
