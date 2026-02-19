/**
 * Экран сканера штрихкодов (центральный таб)
 */
import { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Alert,
  TouchableOpacity,
  Modal,
  FlatList,
} from 'react-native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Button } from '../../components/ui';
import { RecordCard } from '../../components/RecordCard';
import { useScannerStore, useCollectionStore } from '../../lib/store';
import { RecordSearchResult } from '../../lib/types';
import { Colors, Typography, Spacing, BorderRadius, Shadows } from '../../constants/theme';

export default function ScannerScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [permission, requestPermission] = useCameraPermissions();
  const [isScanning, setIsScanning] = useState(true);
  const [showResults, setShowResults] = useState(false);

  const { scanResults, isLoading, searchByBarcode, clearScan } = useScannerStore();
  const { addToCollection, addToWishlist, collectionItems } = useCollectionStore();

  const handleBarCodeScanned = async ({ data }: { data: string }) => {
    if (!isScanning || isLoading) return;
    
    setIsScanning(false);
    
    try {
      await searchByBarcode(data);
      setShowResults(true);
    } catch (error) {
      Alert.alert(
        'Не найдено',
        'Пластинка с таким штрихкодом не найдена в базе Discogs',
        [{ text: 'OK', onPress: () => setIsScanning(true) }]
      );
    }
  };

  const handleCloseResults = () => {
    setShowResults(false);
    clearScan();
    setIsScanning(true);
  };

  const handleRecordPress = (record: RecordSearchResult) => {
    setShowResults(false);
    router.push(`/record/${record.discogs_id}`);
  };

  const handleAddToCollection = async (record: RecordSearchResult) => {
    const alreadyInCollection = collectionItems.some(
      (item) => item.record.discogs_id === record.discogs_id
    );

    const doAdd = async () => {
      try {
        await addToCollection(record.discogs_id);
        Alert.alert('Готово!', `"${record.title}" добавлена в коллекцию`);
        handleCloseResults();
      } catch (error) {
        Alert.alert('Ошибка', 'Не удалось добавить в коллекцию');
      }
    };

    if (alreadyInCollection) {
      Alert.alert(
        'Уже в коллекции',
        `"${record.title}" уже есть в вашей коллекции. Добавить ещё одну копию?`,
        [
          { text: 'Отмена', style: 'cancel' },
          { text: 'Добавить', onPress: doAdd },
        ]
      );
    } else {
      await doAdd();
    }
  };

  const handleAddToWishlist = async (record: RecordSearchResult) => {
    try {
      await addToWishlist(record.discogs_id);
      Alert.alert('Готово!', `"${record.title}" добавлена в список желаний`);
      handleCloseResults();
    } catch (error) {
      Alert.alert('Ошибка', 'Не удалось добавить в список желаний');
    }
  };

  // Проверка разрешений
  if (!permission) {
    return (
      <View style={styles.centered}>
        <Text style={styles.message}>Загрузка...</Text>
      </View>
    );
  }

  if (!permission.granted) {
    return (
      <View style={[styles.centered, { paddingTop: insets.top }]}>
        <Ionicons name="camera-outline" size={64} color={Colors.textMuted} />
        <Text style={styles.title}>Доступ к камере</Text>
        <Text style={styles.message}>
          Для сканирования штрихкодов необходим доступ к камере
        </Text>
        <Button
          title="Разрешить доступ"
          onPress={requestPermission}
          style={styles.button}
        />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      {/* Камера */}
      <CameraView
        style={StyleSheet.absoluteFillObject}
        facing="back"
        barcodeScannerSettings={{
          barcodeTypes: ['ean13', 'ean8', 'upc_a', 'upc_e'],
        }}
        onBarcodeScanned={isScanning ? handleBarCodeScanned : undefined}
      />

      {/* Оверлей */}
      <View style={[styles.overlay, { paddingTop: insets.top }]}>
        {/* Заголовок */}
        <View style={styles.header}>
          <Text style={styles.headerTitle}>Сканирование</Text>
          <Text style={styles.headerSubtitle}>
            Наведите камеру на штрихкод пластинки
          </Text>
        </View>

        {/* Рамка сканера */}
        <View style={styles.scannerFrame}>
          <View style={[styles.corner, styles.cornerTopLeft]} />
          <View style={[styles.corner, styles.cornerTopRight]} />
          <View style={[styles.corner, styles.cornerBottomLeft]} />
          <View style={[styles.corner, styles.cornerBottomRight]} />
        </View>

        {/* Индикатор загрузки */}
        {isLoading && (
          <View style={styles.loadingContainer}>
            <Text style={styles.loadingText}>Поиск...</Text>
          </View>
        )}
      </View>

      {/* Модальное окно с результатами */}
      <Modal
        visible={showResults}
        animationType="slide"
        presentationStyle="pageSheet"
        onRequestClose={handleCloseResults}
      >
        <View style={[styles.resultsContainer, { paddingTop: insets.top }]}>
          <View style={styles.resultsHeader}>
            <Text style={styles.resultsTitle}>Найдено</Text>
            <TouchableOpacity onPress={handleCloseResults}>
              <Ionicons name="close" size={28} color={Colors.royalBlue} />
            </TouchableOpacity>
          </View>

          <FlatList
            data={scanResults}
            keyExtractor={(item) => item.discogs_id}
            contentContainerStyle={styles.resultsList}
            renderItem={({ item }) => (
              <RecordCard
                record={item}
                size="large"
                variant="compact"
                onPress={() => handleRecordPress(item)}
                onAddToCollection={() => handleAddToCollection(item)}
                onAddToWishlist={() => handleAddToWishlist(item)}
                showActions
              />
            )}
            ListEmptyComponent={
              <View style={styles.emptyResults}>
                <Text style={styles.emptyText}>Пластинка не найдена</Text>
              </View>
            }
          />
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.deepNavy,
  },
  centered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: Spacing.lg,
    backgroundColor: Colors.background,
  },
  title: {
    ...Typography.h3,
    color: Colors.deepNavy,
    marginTop: Spacing.md,
    marginBottom: Spacing.sm,
  },
  message: {
    ...Typography.body,
    color: Colors.textSecondary,
    textAlign: 'center',
    marginBottom: Spacing.lg,
  },
  button: {
    minWidth: 200,
  },
  overlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(0, 0, 0, 0.25)',
  },
  header: {
    alignItems: 'center',
    paddingTop: Spacing.xl,
    paddingHorizontal: Spacing.lg,
  },
  headerTitle: {
    ...Typography.h2,
    color: Colors.background,
    marginBottom: Spacing.xs,
  },
  headerSubtitle: {
    ...Typography.body,
    color: 'rgba(255, 255, 255, 0.8)',
    textAlign: 'center',
  },
  scannerFrame: {
    position: 'absolute',
    top: '30%',
    left: '15%',
    right: '15%',
    aspectRatio: 1.5,
  },
  corner: {
    position: 'absolute',
    width: 40,
    height: 40,
    borderColor: Colors.lavender,
  },
  cornerTopLeft: {
    top: 0,
    left: 0,
    borderTopWidth: 4,
    borderLeftWidth: 4,
    borderTopLeftRadius: 8,
  },
  cornerTopRight: {
    top: 0,
    right: 0,
    borderTopWidth: 4,
    borderRightWidth: 4,
    borderTopRightRadius: 8,
  },
  cornerBottomLeft: {
    bottom: 0,
    left: 0,
    borderBottomWidth: 4,
    borderLeftWidth: 4,
    borderBottomLeftRadius: 8,
  },
  cornerBottomRight: {
    bottom: 0,
    right: 0,
    borderBottomWidth: 4,
    borderRightWidth: 4,
    borderBottomRightRadius: 8,
  },
  loadingContainer: {
    position: 'absolute',
    bottom: '20%',
    left: 0,
    right: 0,
    alignItems: 'center',
  },
  loadingText: {
    ...Typography.body,
    color: Colors.deepNavy,
    backgroundColor: Colors.glassBg,
    paddingHorizontal: Spacing.lg,
    paddingVertical: Spacing.sm,
    borderRadius: BorderRadius.full,
    overflow: 'hidden',
    ...Shadows.sm,
  },
  resultsContainer: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  resultsHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: Spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: Colors.divider,
  },
  resultsTitle: {
    ...Typography.h2,
    color: Colors.deepNavy,
  },
  resultsList: {
    padding: Spacing.md,
  },
  emptyResults: {
    padding: Spacing.xl,
    alignItems: 'center',
  },
  emptyText: {
    ...Typography.body,
    color: Colors.textMuted,
  },
});
