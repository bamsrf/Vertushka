/**
 * Экран сканера штрихкодов и распознавания обложки (центральный таб)
 */
import { useState, useRef, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Alert,
  TouchableOpacity,
  Modal,
  FlatList,
  ActivityIndicator,
} from 'react-native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { useRouter, useFocusEffect } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import * as ImageManipulator from 'expo-image-manipulator';
import { Button, SegmentedControl } from '../../components/ui';
import { RecordCard } from '../../components/RecordCard';
import { useScannerStore, useCollectionStore } from '../../lib/store';
import { RecordSearchResult, ScanMode } from '../../lib/types';
import { Colors, Typography, Spacing, BorderRadius, Shadows } from '../../constants/theme';

function getFormatDisplayInfo(format?: string): { label: string; verb: string } {
  if (!format) return { label: 'Винил', verb: 'добавлен' };
  const f = format.toLowerCase();
  if (f.includes('cassette')) return { label: 'Кассета', verb: 'добавлена' };
  if (f.includes('box set')) return { label: 'Бокс-сет', verb: 'добавлен' };
  if (f.includes('cd')) return { label: 'CD', verb: 'добавлен' };
  return { label: 'Винил', verb: 'добавлен' };
}

export default function ScannerScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const cameraRef = useRef<CameraView>(null);
  const [permission, requestPermission] = useCameraPermissions();
  const [isScanning, setIsScanning] = useState(true);
  const [showResults, setShowResults] = useState(false);

  const {
    scanMode,
    setScanMode,
    scanResults,
    recognizedInfo,
    isLoading,
    searchByBarcode,
    searchByCover,
    clearScan,
  } = useScannerStore();
  const { addToCollection, addToWishlist, collectionItems, wishlistItems } = useCollectionStore();

  const handleBarCodeScanned = async ({ data }: { data: string }) => {
    if (!isScanning || isLoading) return;

    setIsScanning(false);

    try {
      await searchByBarcode(data);
      setShowResults(true);
    } catch (error) {
      Alert.alert(
        'Не найдено',
        'Винил с таким штрихкодом не найден в базе Discogs',
        [{ text: 'OK', onPress: () => setIsScanning(true) }]
      );
    }
  };

  const handleTakePhoto = async () => {
    if (!cameraRef.current || isLoading) return;

    try {
      const photo = await cameraRef.current.takePictureAsync({
        quality: 0.7,
      });

      if (!photo?.uri) return;

      const manipulated = await ImageManipulator.manipulateAsync(
        photo.uri,
        [{ resize: { width: 1024 } }],
        { compress: 0.5, format: ImageManipulator.SaveFormat.JPEG, base64: true }
      );

      if (!manipulated.base64) return;

      await searchByCover(manipulated.base64);
      setShowResults(true);
    } catch (error: any) {
      const message = error?.response?.data?.detail || 'Не удалось распознать обложку. Попробуйте сфотографировать ещё раз.';
      Alert.alert('Не распознано', message, [{ text: 'OK' }]);
    }
  };

  const handleCloseResults = () => {
    setShowResults(false);
    clearScan();
    setIsScanning(true);
  };

  // ID пластинки, на детали которой ушли (null = не уходили)
  const viewedDetailId = useRef<string | null>(null);

  useFocusEffect(
    useCallback(() => {
      if (!viewedDetailId.current || scanResults.length === 0) return;

      const id = viewedDetailId.current;
      viewedDetailId.current = null;

      // Если пластинку добавили в коллекцию или вишлист — закрываем список
      const addedToCollection = collectionItems.some(
        (item) => item.record.discogs_id === id
      );
      const addedToWishlist = wishlistItems.some(
        (item) => item.record.discogs_id === id
      );

      if (addedToCollection || addedToWishlist) {
        clearScan();
        setIsScanning(true);
      } else {
        setShowResults(true);
      }
    }, [scanResults.length, collectionItems, wishlistItems])
  );

  const handleRecordPress = (record: RecordSearchResult) => {
    viewedDetailId.current = record.discogs_id;
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
        const fmt = getFormatDisplayInfo(record.format_type);
        Alert.alert('Готово!', `"${record.title}" ${fmt.verb} в коллекцию`);
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
      const fmt = getFormatDisplayInfo(record.format_type);
      Alert.alert('Готово!', `"${record.title}" ${fmt.verb} в список желаний`);
      handleCloseResults();
    } catch (error) {
      Alert.alert('Ошибка', 'Не удалось добавить в список желаний');
    }
  };

  const handleModeChange = (mode: ScanMode) => {
    setScanMode(mode);
    setShowResults(false);
    setIsScanning(true);
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
        ref={cameraRef}
        style={StyleSheet.absoluteFillObject}
        facing="back"
        barcodeScannerSettings={
          scanMode === 'barcode'
            ? { barcodeTypes: ['ean13', 'ean8', 'upc_a', 'upc_e'] }
            : undefined
        }
        onBarcodeScanned={
          scanMode === 'barcode' && isScanning ? handleBarCodeScanned : undefined
        }
      />

      {/* Оверлей */}
      <View style={[styles.overlay, { paddingTop: insets.top }]}>
        {/* Заголовок + переключатель режимов */}
        <View style={styles.header}>
          <Text style={styles.headerTitle}>Сканирование</Text>
          <SegmentedControl<ScanMode>
            segments={[
              { key: 'barcode', label: 'Штрихкод' },
              { key: 'cover', label: 'Обложка' },
            ]}
            selectedKey={scanMode}
            onSelect={handleModeChange}
            style={styles.modeSwitch}
            disabled={isLoading}
          />
          <Text style={styles.headerSubtitle}>
            {scanMode === 'barcode'
              ? 'Наведите камеру на штрихкод пластинки'
              : 'Сфотографируйте обложку пластинки'}
          </Text>
        </View>

        {/* Рамка сканера */}
        <View style={[
          styles.scannerFrame,
          scanMode === 'cover' && styles.scannerFrameSquare,
        ]}>
          <View style={[styles.corner, styles.cornerTopLeft]} />
          <View style={[styles.corner, styles.cornerTopRight]} />
          <View style={[styles.corner, styles.cornerBottomLeft]} />
          <View style={[styles.corner, styles.cornerBottomRight]} />
        </View>

        {/* Кнопка затвора (режим обложки) */}
        {scanMode === 'cover' && !isLoading && (
          <View style={styles.shutterContainer}>
            <TouchableOpacity
              style={styles.shutterButton}
              onPress={handleTakePhoto}
              activeOpacity={0.7}
            >
              <View style={styles.shutterInner} />
            </TouchableOpacity>
          </View>
        )}

        {/* Индикатор загрузки */}
        {isLoading && (
          <View style={styles.loadingContainer}>
            <View style={styles.loadingPill}>
              <ActivityIndicator size="small" color={Colors.deepNavy} />
              <Text style={styles.loadingText}>
                {scanMode === 'barcode' ? 'Поиск...' : 'Распознавание...'}
              </Text>
            </View>
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

          {/* Баннер распознавания (режим обложки) */}
          {recognizedInfo && (
            <View style={styles.recognizedBanner}>
              <Ionicons name="sparkles" size={16} color={Colors.royalBlue} />
              <Text style={styles.recognizedText} numberOfLines={1}>
                {recognizedInfo.artist}
                {recognizedInfo.album ? ` — ${recognizedInfo.album}` : ''}
              </Text>
            </View>
          )}

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
                <Text style={styles.emptyText}>Ничего не найдено</Text>
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
  modeSwitch: {
    marginTop: Spacing.sm,
    marginHorizontal: Spacing.md,
    alignSelf: 'stretch',
  },
  headerSubtitle: {
    ...Typography.body,
    color: 'rgba(255, 255, 255, 0.8)',
    textAlign: 'center',
    marginTop: Spacing.sm,
  },
  scannerFrame: {
    position: 'absolute',
    top: '30%',
    left: '15%',
    right: '15%',
    aspectRatio: 1.5,
  },
  scannerFrameSquare: {
    aspectRatio: 1,
    left: '18%',
    right: '18%',
    top: '28%',
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
  shutterContainer: {
    position: 'absolute',
    bottom: '12%',
    left: 0,
    right: 0,
    alignItems: 'center',
  },
  shutterButton: {
    width: 72,
    height: 72,
    borderRadius: 36,
    backgroundColor: 'rgba(255, 255, 255, 0.3)',
    borderWidth: 4,
    borderColor: Colors.background,
    alignItems: 'center',
    justifyContent: 'center',
  },
  shutterInner: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: Colors.background,
  },
  loadingContainer: {
    position: 'absolute',
    bottom: '20%',
    left: 0,
    right: 0,
    alignItems: 'center',
  },
  loadingPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
    backgroundColor: Colors.glassBg,
    paddingHorizontal: Spacing.lg,
    paddingVertical: Spacing.sm,
    borderRadius: BorderRadius.full,
    ...Shadows.sm,
  },
  loadingText: {
    ...Typography.body,
    color: Colors.deepNavy,
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
  recognizedBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.xs,
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm,
    backgroundColor: Colors.surface,
    borderBottomWidth: 1,
    borderBottomColor: Colors.divider,
  },
  recognizedText: {
    ...Typography.bodySmall,
    color: Colors.textSecondary,
    flex: 1,
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
