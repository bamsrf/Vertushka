/**
 * Общий каркас для статических правовых экранов (Условия / Политика).
 * Требование App Store 5.1.1(i) + 1.2: правовые тексты доступны внутри приложения.
 */
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, Linking } from 'react-native';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Icon } from '@/components/ui';
import { Colors, Typography, Spacing } from '../constants/theme';
import { ms } from '../lib/responsive';

export const SUPPORT_EMAIL = 'support@vinyl-vertushka.store';

export interface LegalSection {
  heading?: string;
  paragraphs: string[];
}

export function LegalScreen({
  title,
  effectiveDate,
  sections,
  webUrl,
}: {
  title: string;
  effectiveDate: string;
  sections: LegalSection[];
  webUrl: string;
}) {
  const router = useRouter();
  const insets = useSafeAreaInsets();

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backButton}>
          <Icon name="arrow-back" size={24} color={Colors.royalBlue} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>{title}</Text>
        <View style={styles.placeholder} />
      </View>

      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <Text style={styles.date}>Дата вступления в силу: {effectiveDate}</Text>

        {sections.map((section, i) => (
          <View key={i}>
            {section.heading ? <Text style={styles.heading}>{section.heading}</Text> : null}
            {section.paragraphs.map((p, j) => (
              <Text key={j} style={styles.paragraph}>
                {p}
              </Text>
            ))}
          </View>
        ))}

        <Text style={styles.heading}>Контакты</Text>
        <Text style={styles.paragraph}>
          По всем вопросам и жалобам:{' '}
          <Text style={styles.link} onPress={() => Linking.openURL(`mailto:${SUPPORT_EMAIL}`)}>
            {SUPPORT_EMAIL}
          </Text>
        </Text>
        <Text style={styles.paragraph}>
          Актуальная версия документа:{' '}
          <Text style={styles.link} onPress={() => Linking.openURL(webUrl)}>
            {webUrl.replace('https://', '')}
          </Text>
        </Text>
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
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: Spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: Colors.divider,
  },
  headerTitle: { ...Typography.h4, fontSize: ms(17), color: Colors.royalBlue },
  backButton: { width: 36, height: 36, alignItems: 'center', justifyContent: 'center' },
  placeholder: { width: 36, height: 36 },
  content: { padding: Spacing.lg },
  date: {
    ...Typography.caption,
    color: Colors.textMuted,
    marginBottom: Spacing.lg,
  },
  heading: {
    ...Typography.h4,
    color: Colors.deepNavy,
    marginTop: Spacing.lg,
    marginBottom: Spacing.sm,
  },
  paragraph: {
    ...Typography.body,
    color: Colors.textSecondary,
    marginBottom: Spacing.sm,
    lineHeight: 22,
  },
  link: {
    color: Colors.royalBlue,
    fontWeight: '600',
  },
});
