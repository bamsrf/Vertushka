/**
 * ErrorBoundary — перехватывает ошибки компонентов, показывает fallback UI
 */
import React, { Component, ReactNode } from 'react';
import { View, Text, StyleSheet, Pressable } from 'react-native';
import { Icon } from '@/components/ui';
import { Colors, Typography, Spacing, BorderRadius } from '../constants/theme';
import { noteBadExperience } from '../lib/reviewPrompt';

interface Props {
  children: ReactNode;
  fallbackTitle?: string;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch() {
    // Экран только что развалился — просить за это звёзды нельзя. Флаг живёт
    // до конца сессии и глушит просьбу оценить приложение. Побочный эффект в
    // componentDidCatch, а не в getDerivedStateFromError: та обязана быть
    // чистой, её React зовёт и на фазе рендера, которую может выбросить.
    noteBadExperience();
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: undefined });
  };

  render() {
    if (!this.state.hasError) {
      return this.props.children;
    }

    const title = this.props.fallbackTitle ?? 'Что-то пошло не так';

    return (
      <View style={styles.container}>
        <Icon name="alert-circle-outline" size={52} color={Colors.textMuted} />
        <Text style={styles.title}>{title}</Text>
        <Text style={styles.subtitle}>
          {this.state.error?.message ?? 'Неизвестная ошибка'}
        </Text>
        <Pressable style={styles.button} onPress={this.handleRetry}>
          <Text style={styles.buttonText}>Попробовать снова</Text>
        </Pressable>
      </View>
    );
  }
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: Spacing.xl,
    backgroundColor: Colors.background,
    gap: Spacing.md,
  },
  title: {
    ...Typography.h4,
    color: Colors.text,
    textAlign: 'center',
  },
  subtitle: {
    ...Typography.bodySmall,
    color: Colors.textSecondary,
    textAlign: 'center',
  },
  button: {
    marginTop: Spacing.sm,
    paddingVertical: Spacing.sm,
    paddingHorizontal: Spacing.xl,
    backgroundColor: Colors.royalBlue,
    borderRadius: BorderRadius.md,
  },
  buttonText: {
    ...Typography.button,
    color: Colors.background,
  },
});
