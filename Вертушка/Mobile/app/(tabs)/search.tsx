/**
 * Экран поиска по Discogs
 */
import { useState, useCallback, useEffect, useRef } from 'react';
import {
  View,
  StyleSheet,
  TextInput,
  TouchableOpacity,
  Alert,
  Text,
  Image,
  Modal,
  ScrollView,
  Animated,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { AnimatedGradientText } from '../../components/AnimatedGradientText';
import { RecordGrid } from '../../components/RecordGrid';
import { useSearchStore, useCollectionStore, useUserSearchStore, useAuthStore } from '../../lib/store';
import { api } from '../../lib/api';
import { MasterSearchResult, ReleaseSearchResult, ArtistSearchResult, UserWithStats } from '../../lib/types';
import { Colors, Typography, Spacing, BorderRadius, Gradients } from '../../constants/theme';

function getFormatDisplayInfo(format?: string): { label: string; verb: string } {
  if (!format) return { label: 'Винил', verb: 'добавлен' };
  const f = format.toLowerCase();
  if (f.includes('cassette')) return { label: 'Кассета', verb: 'добавлена' };
  if (f.includes('box set')) return { label: 'Бокс-сет', verb: 'добавлен' };
  if (f.includes('cd')) return { label: 'CD', verb: 'добавлен' };
  return { label: 'Винил', verb: 'добавлен' };
}

// Маппинг форматов для отображения на русском
const FORMAT_OPTIONS = [
  { value: undefined, label: 'Все' },
  { value: 'Vinyl', label: 'Винил' },
  { value: 'CD', label: 'CD' },
  { value: 'Cassette', label: 'Кассета' },
  { value: 'Box Set', label: 'Бокс-сет' },
  { value: 'File', label: 'Цифровой' },
];

// Основные страны (показываются по умолчанию)
const MAIN_COUNTRIES = [
  { value: undefined, label: 'Все' },
  { value: 'US', label: 'США' },
  { value: 'UK', label: 'Великобритания' },
  { value: 'Germany', label: 'Германия' },
  { value: 'Japan', label: 'Япония' },
  { value: 'Russia', label: 'Россия' },
];

// Все страны (показываются при нажатии "Показать все")
const ALL_COUNTRIES = [
  ...MAIN_COUNTRIES,
  { value: 'France', label: 'Франция' },
  { value: 'Italy', label: 'Италия' },
  { value: 'Netherlands', label: 'Нидерланды' },
  { value: 'Canada', label: 'Канада' },
  { value: 'Australia', label: 'Австралия' },
  { value: 'Sweden', label: 'Швеция' },
  { value: 'Spain', label: 'Испания' },
  { value: 'Brazil', label: 'Бразилия' },
  { value: 'Poland', label: 'Польша' },
  { value: 'Belgium', label: 'Бельгия' },
  { value: 'Austria', label: 'Австрия' },
  { value: 'Denmark', label: 'Дания' },
  { value: 'Finland', label: 'Финляндия' },
  { value: 'Norway', label: 'Норвегия' },
  { value: 'Greece', label: 'Греция' },
  { value: 'Portugal', label: 'Португалия' },
  { value: 'Czechoslovakia', label: 'Чехословакия' },
  { value: 'Yugoslavia', label: 'Югославия' },
  { value: 'USSR', label: 'СССР' },
];

// Опции года (декады)
const YEAR_OPTIONS = [
  { value: undefined, label: 'Все годы' },
  { value: '2020s', label: '2020-е', min: 2020, max: 2029 },
  { value: '2010s', label: '2010-е', min: 2010, max: 2019 },
  { value: '2000s', label: '2000-е', min: 2000, max: 2009 },
  { value: '1990s', label: '1990-е', min: 1990, max: 1999 },
  { value: '1980s', label: '1980-е', min: 1980, max: 1989 },
  { value: '1970s', label: '1970-е', min: 1970, max: 1979 },
  { value: '1960s', label: '1960-е', min: 1960, max: 1969 },
  { value: '1950s', label: '1950-е и ранее', min: 0, max: 1959 },
];

export default function SearchScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { user } = useAuthStore();
  const [searchInput, setSearchInput] = useState('');
  const [isFocused, setIsFocused] = useState(false);
  const [inputFocused, setInputFocused] = useState(false);
  const [showFilters, setShowFilters] = useState(false);
  const [showAllCountries, setShowAllCountries] = useState(false);
  const [selectedDecade, setSelectedDecade] = useState<string | undefined>(undefined);

  // Временные фильтры для модалки (применяются только при закрытии)
  const [tempFilters, setTempFilters] = useState<{ format?: string; country?: string; year?: number }>({});

  // Анимация для модала фильтров
  const overlayOpacity = useRef(new Animated.Value(0)).current;
  const slideAnim = useRef(new Animated.Value(300)).current;

  const {
    query,
    results,
    artistResults,
    filters,
    isLoading,
    hasMore,
    searchHistory,
    search,
    loadMore,
    clearResults,
    setFilters,
    clearFilters,
    loadHistory,
    removeFromHistory,
    clearHistory,
  } = useSearchStore();

  const { addToCollection, addToWishlist, collectionItems } = useCollectionStore();

  const {
    results: userResults,
    isLoading: isUserSearchLoading,
    search: searchUsers,
    clearResults: clearUserResults,
  } = useUserSearchStore();

  // Режим поиска пользователей: запрос начинается с @
  const isUserSearch = searchInput.startsWith('@');

  // Открытие модалки фильтров
  const openFilters = useCallback(() => {
    // Загружаем текущие фильтры во временный стейт
    setTempFilters(filters);

    // Восстанавливаем выбранную декаду на основе текущего года в фильтрах
    if (filters.year) {
      const decade = YEAR_OPTIONS.find((option) =>
        option.value && 'min' in option && filters.year! >= option.min! && filters.year! <= option.max!
      );
      setSelectedDecade(decade?.value);
    } else {
      setSelectedDecade(undefined);
    }

    setShowFilters(true);
    Animated.parallel([
      Animated.timing(overlayOpacity, {
        toValue: 1,
        duration: 250,
        useNativeDriver: true,
      }),
      Animated.timing(slideAnim, {
        toValue: 0,
        duration: 300,
        useNativeDriver: true,
      }),
    ]).start();
  }, [overlayOpacity, slideAnim, filters]);

  // Закрытие модалки фильтров с применением фильтров
  const closeFilters = useCallback(async () => {
    // Применяем временные фильтры к основному стору
    setFilters(tempFilters);

    Animated.parallel([
      Animated.timing(overlayOpacity, {
        toValue: 0,
        duration: 200,
        useNativeDriver: true,
      }),
      Animated.timing(slideAnim, {
        toValue: 300,
        duration: 250,
        useNativeDriver: true,
      }),
    ]).start(() => {
      setShowFilters(false);
    });

    // Применяем фильтры к поиску
    if (searchInput.trim()) {
      await search(searchInput.trim());
    }
  }, [overlayOpacity, slideAnim, tempFilters, setFilters, searchInput, search]);

  // Загружаем историю при монтировании
  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  const handleSearch = useCallback(async () => {
    const trimmed = searchInput.trim();
    if (!trimmed) return;

    try {
      if (trimmed.startsWith('@')) {
        // Режим поиска пользователей — ищем без @
        const userQuery = trimmed.slice(1).trim();
        if (userQuery.length > 0) {
          clearResults();
          await searchUsers(userQuery);
        }
      } else {
        await Promise.all([
          search(trimmed),
          searchUsers(trimmed),
        ]);
      }
    } catch (error: any) {
      const message = error?.response?.status === 503
        ? 'Сервис временно недоступен. Попробуйте позже.'
        : error?.message || 'Ошибка при поиске';
      Alert.alert('Ошибка', message);
    }
  }, [searchInput, search, searchUsers, clearResults]);

  const handleClear = useCallback(() => {
    setSearchInput('');
    clearResults();
    clearUserResults();
    clearFilters();
    setTempFilters({});
    setSelectedDecade(undefined);
  }, [clearResults, clearFilters]);

  // Проверка активных фильтров
  const hasActiveFilters = !!(filters.format || filters.country || filters.year);

  // Проверка активных временных фильтров (для модалки)
  const hasTempFilters = !!(tempFilters.format || tempFilters.country || tempFilters.year || selectedDecade);

  // Автосброс фильтров при изменении поискового запроса
  const handleSearchInputChange = useCallback((text: string) => {
    // Переключение между режимами: очищаем неактуальные результаты
    const wasUserSearch = searchInput.startsWith('@');
    const willBeUserSearch = text.startsWith('@');

    if (wasUserSearch && !willBeUserSearch) {
      clearUserResults();
    } else if (!wasUserSearch && willBeUserSearch) {
      clearResults();
      clearFilters();
    }

    // Если пользователь начинает вводить новый запрос и были активные фильтры - сбрасываем их
    if (!willBeUserSearch && text !== searchInput && (filters.format || filters.country || filters.year)) {
      clearFilters();
    }
    setSearchInput(text);
  }, [searchInput, filters.format, filters.country, filters.year, clearFilters, clearResults, clearUserResults]);

  const handleHistoryItemPress = useCallback(async (historyQuery: string) => {
    setSearchInput(historyQuery);
    try {
      if (historyQuery.startsWith('@')) {
        const userQuery = historyQuery.slice(1).trim();
        if (userQuery.length > 0) {
          clearResults();
          await searchUsers(userQuery);
        }
      } else {
        await Promise.all([
          search(historyQuery),
          searchUsers(historyQuery),
        ]);
      }
    } catch (error: any) {
      const message = error?.response?.status === 503
        ? 'Сервис временно недоступен. Попробуйте позже.'
        : error?.message || 'Ошибка при поиске';
      Alert.alert('Ошибка', message);
    }
  }, [search, searchUsers, clearResults]);

  const handleRemoveHistoryItem = useCallback((historyQuery: string) => {
    removeFromHistory(historyQuery);
  }, [removeFromHistory]);

  const handleClearHistory = useCallback(() => {
    Alert.alert(
      'Очистить историю',
      'Вы уверены, что хотите удалить всю историю поиска?',
      [
        { text: 'Отмена', style: 'cancel' },
        { text: 'Очистить', style: 'destructive', onPress: clearHistory },
      ]
    );
  }, [clearHistory]);

  const handleBlur = useCallback(() => {
    setTimeout(() => setIsFocused(false), 150);
  }, []);

  const handleRecordPress = (record: MasterSearchResult | ReleaseSearchResult) => {
    // Если это MasterSearchResult - переходим на страницу мастера
    if ('master_id' in record) {
      router.push(`/master/${record.master_id}`);
    } else if ('release_id' in record) {
      // Если это ReleaseSearchResult - переходим на страницу релиза
      router.push(`/record/${record.release_id}`);
    }
  };

  const handleAddToCollection = async (record: MasterSearchResult | ReleaseSearchResult) => {
    const discogsId = 'main_release_id' in record ? record.main_release_id : record.release_id;

    const alreadyInCollection = collectionItems.some(
      (item) => item.record.discogs_id === discogsId
    );

    const doAdd = async () => {
      try {
        await addToCollection(discogsId);
        const format = 'format' in record ? record.format : undefined;
        const fmt = getFormatDisplayInfo(format);
        Alert.alert('Готово!', `"${record.title}" ${fmt.verb} в коллекцию`);
      } catch (error: any) {
        const message = error?.response?.data?.detail || error?.message || 'Не удалось добавить в коллекцию';
        Alert.alert('Ошибка', message);
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

  const handleAddToWishlist = async (record: MasterSearchResult | ReleaseSearchResult) => {
    try {
      const discogsId = 'main_release_id' in record ? record.main_release_id : record.release_id;
      await addToWishlist(discogsId);
      const format = 'format' in record ? record.format : undefined;
      const fmt = getFormatDisplayInfo(format);
      Alert.alert('Готово!', `"${record.title}" ${fmt.verb} в список желаний`);
    } catch (error: any) {
      const message = error?.response?.data?.detail || error?.message || 'Не удалось добавить в список желаний';
      Alert.alert('Ошибка', message);
    }
  };

  const handleArtistPress = (artist: ArtistSearchResult) => {
    router.push(`/artist/${artist.artist_id}`);
  };

  const handleUserPress = (user: UserWithStats) => {
    router.push(`/user/${user.username}`);
  };

  // Поиск артиста по имени и переход на его страницу
  const handleArtistNamePress = useCallback(async (artistName: string) => {
    try {
      const response = await api.searchArtists(artistName, 1, 1);
      if (response.results.length > 0) {
        router.push(`/artist/${response.results[0].artist_id}`);
      } else {
        Alert.alert('Не найдено', `Артист "${artistName}" не найден`);
      }
    } catch (error) {
      console.error('Error searching artist:', error);
      Alert.alert('Ошибка', 'Не удалось найти артиста');
    }
  }, [router]);

  // Обновление временных фильтров без закрытия модалки
  const updateTempFilter = useCallback((key: 'format' | 'country' | 'year', value: string | number | undefined) => {
    setTempFilters(prev => ({
      ...prev,
      [key]: value,
    }));
  }, []);

  // Очистка всех временных фильтров (применится при закрытии модалки)
  const handleClearAllFilters = useCallback(() => {
    setTempFilters({});
    setSelectedDecade(undefined);
  }, []);

  // Показываем историю только когда поле в фокусе, пустое и нет результатов
  const shouldShowHistory = isFocused && searchInput === '' && results.length === 0 && artistResults.length === 0 && searchHistory.length > 0;

  // Показываем только самого релевантного артиста (первого в списке)
  const topArtist = artistResults.length > 0 ? artistResults[0] : null;

  const SearchHistory = shouldShowHistory ? (
    <View style={styles.historyContainer}>
      <View style={styles.historyHeader}>
        <Text style={styles.historyTitle}>Вы искали ранее</Text>
        <TouchableOpacity onPress={handleClearHistory}>
          <Text style={styles.clearHistoryButton}>Очистить</Text>
        </TouchableOpacity>
      </View>
      {searchHistory.map((item, index) => (
        <View key={`${item}-${index}`} style={styles.historyItem}>
          <TouchableOpacity
            style={styles.historyItemButton}
            onPress={() => handleHistoryItemPress(item)}
            activeOpacity={0.7}
          >
            <Ionicons name="time-outline" size={18} color={Colors.periwinkle} />
            <Text style={styles.historyItemText}>{item}</Text>
          </TouchableOpacity>
          <TouchableOpacity
            onPress={() => handleRemoveHistoryItem(item)}
            hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
            activeOpacity={0.7}
          >
            <Ionicons name="close" size={18} color={Colors.textMuted} />
          </TouchableOpacity>
        </View>
      ))}
    </View>
  ) : null;

  const FilterModal = showFilters ? (
    <Modal
      visible={showFilters}
      transparent
      animationType="none"
      onRequestClose={closeFilters}
    >
      <View style={styles.modalContainer}>
        <Animated.View
          style={[styles.modalOverlay, { opacity: overlayOpacity }]}
        >
          <TouchableOpacity style={styles.modalOverlayPressable} onPress={closeFilters} activeOpacity={1} />
        </Animated.View>
        <Animated.View
          style={[
            styles.modalContent,
            { transform: [{ translateY: slideAnim }] }
          ]}
        >
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>Фильтры</Text>
            <TouchableOpacity onPress={closeFilters}>
              <Ionicons name="close" size={24} color={Colors.text} />
            </TouchableOpacity>
          </View>

          <ScrollView style={styles.modalBody}>
            {/* Формат */}
            <Text style={styles.filterLabel}>Формат</Text>
            <View style={styles.filterOptions}>
              {FORMAT_OPTIONS.map((option) => {
                const isSelected = option.value === undefined ? !tempFilters.format : tempFilters.format === option.value;
                return (
                  <TouchableOpacity
                    key={option.label}
                    style={[styles.filterOption, isSelected && styles.filterOptionSelected]}
                    onPress={() => updateTempFilter('format', option.value)}
                  >
                    <Text style={[styles.filterOptionText, isSelected && styles.filterOptionTextSelected]}>
                      {option.label}
                    </Text>
                  </TouchableOpacity>
                );
              })}
            </View>

            {/* Страна */}
            <View style={styles.filterLabelRow}>
              <Text style={styles.filterLabel}>Страна</Text>
              <TouchableOpacity onPress={() => setShowAllCountries(!showAllCountries)}>
                <Text style={styles.showAllButton}>
                  {showAllCountries ? 'Скрыть' : 'Показать все'}
                </Text>
              </TouchableOpacity>
            </View>
            <View style={styles.filterOptions}>
              {(showAllCountries ? ALL_COUNTRIES : MAIN_COUNTRIES).map((option) => {
                const isSelected = option.value === undefined ? !tempFilters.country : tempFilters.country === option.value;
                return (
                  <TouchableOpacity
                    key={option.label}
                    style={[styles.filterOption, isSelected && styles.filterOptionSelected]}
                    onPress={() => updateTempFilter('country', option.value)}
                  >
                    <Text style={[styles.filterOptionText, isSelected && styles.filterOptionTextSelected]}>
                      {option.label}
                    </Text>
                  </TouchableOpacity>
                );
              })}
            </View>

            {/* Год (декады) */}
            <Text style={styles.filterLabel}>Год издания</Text>
            <View style={styles.filterOptions}>
              {YEAR_OPTIONS.map((option) => {
                const isSelected = option.value === undefined ? !selectedDecade : selectedDecade === option.value;
                return (
                  <TouchableOpacity
                    key={option.label}
                    style={[styles.filterOption, isSelected && styles.filterOptionSelected]}
                    onPress={() => {
                      setSelectedDecade(option.value);
                      // Для Discogs API отправляем конкретный год (середину декады) или undefined
                      const yearValue = option.value && 'min' in option ? Math.floor((option.min! + option.max!) / 2) : undefined;
                      updateTempFilter('year', yearValue);
                    }}
                  >
                    <Text style={[styles.filterOptionText, isSelected && styles.filterOptionTextSelected]}>
                      {option.label}
                    </Text>
                  </TouchableOpacity>
                );
              })}
            </View>

            {/* Кнопка очистки */}
            {hasTempFilters && (
              <TouchableOpacity
                style={styles.clearFiltersButton}
                onPress={handleClearAllFilters}
              >
                <Text style={styles.clearFiltersText}>Очистить все фильтры</Text>
              </TouchableOpacity>
            )}
          </ScrollView>
        </Animated.View>
      </View>
    </Modal>
  ) : null;

  const handleProfilePress = () => {
    router.push('/profile');
  };

  const SearchHeader = (
    <View style={styles.searchContainer}>
      {/* Title row + avatar */}
      <View style={styles.topRow}>
        <AnimatedGradientText style={Typography.heroTitle}>Поиск</AnimatedGradientText>
        <TouchableOpacity style={styles.profileButton} onPress={handleProfilePress}>
          {user?.avatar_url ? (
            <Image source={{ uri: user.avatar_url }} style={styles.avatar} />
          ) : (
            <LinearGradient
              colors={[Colors.royalBlue, Colors.periwinkle]}
              style={styles.avatarPlaceholder}
            >
              <Ionicons name="disc" size={20} color={Colors.background} />
            </LinearGradient>
          )}
        </TouchableOpacity>
      </View>

      {/* Search input — pill style */}
      <View style={styles.searchRow}>
        <View style={[styles.searchInputContainer, inputFocused && styles.searchInputFocused]}>
          <Ionicons name="search" size={20} color={Colors.royalBlue} />
          <TextInput
            style={styles.searchInput}
            value={searchInput}
            onChangeText={handleSearchInputChange}
            placeholder={isUserSearch ? "Имя пользователя..." : "Артист, альбом или @username"}
            placeholderTextColor={Colors.textMuted}
            returnKeyType="search"
            onSubmitEditing={handleSearch}
            onFocus={() => { setIsFocused(true); setInputFocused(true); }}
            onBlur={() => { handleBlur(); setInputFocused(false); }}
            autoCapitalize="none"
            autoCorrect={false}
          />
          {searchInput.length > 0 && (
            <TouchableOpacity onPress={handleClear}>
              <Ionicons name="close-circle" size={20} color={Colors.textMuted} />
            </TouchableOpacity>
          )}
        </View>
        {!isUserSearch && (
          <TouchableOpacity
            style={[styles.filterButton, hasActiveFilters && styles.filterButtonActive]}
            onPress={openFilters}
          >
            <Ionicons name="options-outline" size={20} color={hasActiveFilters ? Colors.background : Colors.text} />
          </TouchableOpacity>
        )}
      </View>

      {SearchHistory}
    </View>
  );

  // Рендер списка пользователей (общий для обоих режимов)
  const renderUserList = (users: UserWithStats[], limit?: number) => {
    const displayUsers = limit ? users.slice(0, limit) : users;
    return displayUsers.map((u) => (
      <TouchableOpacity
        key={u.id}
        style={styles.userCard}
        onPress={() => handleUserPress(u)}
        activeOpacity={0.8}
      >
        <View style={styles.userImageContainer}>
          {u.avatar_url ? (
            <Image
              source={{ uri: u.avatar_url }}
              style={styles.topArtistImage}
              resizeMode="cover"
            />
          ) : (
            <View style={styles.userPlaceholder}>
              <Ionicons name="person" size={24} color={Colors.textMuted} />
            </View>
          )}
        </View>
        <View style={styles.userInfo}>
          <Text style={styles.userLabel}>@{u.username}</Text>
          <Text style={styles.userName} numberOfLines={1}>
            {u.display_name || u.username}
          </Text>
        </View>
        <Text style={styles.userStatText}>{u.collection_count} пластинок</Text>
        <Ionicons name="chevron-forward" size={24} color={Colors.textMuted} />
      </TouchableOpacity>
    ));
  };

  const HeaderContent = isUserSearch ? (
    // Режим поиска пользователей (@)
    <View>
      {SearchHeader}

      {userResults.length > 0 && (
        <View>
          <Text style={styles.sectionTitle}>Пользователи</Text>
          {renderUserList(userResults)}
        </View>
      )}

      {isUserSearchLoading && userResults.length === 0 && (
        <View style={styles.loadingContainer}>
          <Text style={styles.loadingText}>Поиск пользователей...</Text>
        </View>
      )}

      {!isUserSearchLoading && userResults.length === 0 && searchInput.length > 1 && (
        <View style={styles.emptyContainer}>
          <Text style={styles.emptyText}>
            Пользователь не найден
          </Text>
        </View>
      )}

      {searchInput === '@' && (
        <View style={styles.emptyContainer}>
          <Text style={styles.emptyText}>
            Введите имя пользователя после @
          </Text>
        </View>
      )}
    </View>
  ) : (
    // Обычный режим поиска
    <View>
      {SearchHeader}

      {topArtist && (
        <TouchableOpacity
          onPress={() => handleArtistPress(topArtist)}
          activeOpacity={0.8}
        >
          <LinearGradient
            colors={Gradients.blue as [string, string]}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 1 }}
            style={styles.topArtistCard}
          >
            <View style={styles.topArtistImageContainer}>
              {(topArtist.cover_image_url || topArtist.thumb_image_url) ? (
                <Image
                  source={{ uri: topArtist.cover_image_url || topArtist.thumb_image_url }}
                  style={styles.topArtistImage}
                  resizeMode="cover"
                />
              ) : (
                <View style={styles.topArtistPlaceholder}>
                  <Ionicons name="person-outline" size={32} color="rgba(255,255,255,0.7)" />
                </View>
              )}
            </View>
            <View style={styles.topArtistInfo}>
              <Text style={styles.topArtistLabel}>Артист</Text>
              <Text style={styles.topArtistName} numberOfLines={1}>{topArtist.name}</Text>
            </View>
            <View style={styles.artistArrowBg}>
              <Ionicons name="chevron-forward" size={20} color="#FFFFFF" />
            </View>
          </LinearGradient>
        </TouchableOpacity>
      )}

      {/* Пользователи */}
      {userResults.length > 0 && (
        <View>
          <Text style={styles.sectionTitle}>Пользователи</Text>
          {renderUserList(userResults, 3)}
        </View>
      )}

      {results.length > 0 && (
        <Text style={styles.sectionTitle}>Релизы</Text>
      )}

      {isLoading && results.length === 0 && artistResults.length === 0 && (
        <View style={styles.loadingContainer}>
          <Text style={styles.loadingText}>Загрузка...</Text>
        </View>
      )}

      {!isLoading && results.length === 0 && artistResults.length === 0 && query && (
        <View style={styles.emptyContainer}>
          <Text style={styles.emptyText}>
            Ничего не найдено. Попробуйте изменить запрос.
          </Text>
        </View>
      )}

      {!isLoading && results.length === 0 && artistResults.length === 0 && !query && (
        <View style={styles.emptyContainer}>
          <Text style={styles.emptyText}>
            Введите название альбома, артиста или @username
          </Text>
        </View>
      )}
    </View>
  );

  return (
    <KeyboardAvoidingView
      style={[styles.container, { paddingTop: insets.top }]}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <RecordGrid
        data={isUserSearch ? [] : results}
        onRecordPress={handleRecordPress}
        onArtistPress={handleArtistNamePress}
        onAddToCollection={handleAddToCollection}
        onAddToWishlist={handleAddToWishlist}
        showActions
        isLoading={isUserSearch ? false : isLoading}
        onEndReached={!isUserSearch && hasMore ? loadMore : undefined}
        emptyMessage=""
        ListHeaderComponent={HeaderContent}
        cardVariant="compact"
      />

      {FilterModal}
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  searchContainer: {
    paddingBottom: Spacing.md,
  },
  topRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 4,
  },
  profileButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    overflow: 'hidden',
    borderWidth: 2,
    borderColor: Colors.lavender,
  },
  avatar: {
    width: '100%',
    height: '100%',
  },
  avatarPlaceholder: {
    width: '100%',
    height: '100%',
    alignItems: 'center',
    justifyContent: 'center',
  },
  searchRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
    marginTop: Spacing.md,
  },
  searchInputContainer: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#F5F5F7',
    borderRadius: 26,
    paddingHorizontal: Spacing.md,
    height: 52,
    gap: Spacing.sm,
    borderWidth: 2,
    borderColor: 'transparent',
  },
  searchInputFocused: {
    borderColor: Colors.royalBlue,
  },
  searchInput: {
    flex: 1,
    minWidth: 0,
    fontSize: 16,
    color: Colors.text,
    padding: 0,
    margin: 0,
    textAlignVertical: 'center',
  },
  filterButton: {
    width: 52,
    height: 52,
    borderRadius: 26,
    backgroundColor: '#F5F5F7',
    alignItems: 'center',
    justifyContent: 'center',
  },
  filterButtonActive: {
    backgroundColor: Colors.royalBlue,
  },
  historyContainer: {
    marginTop: Spacing.md,
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.md,
    padding: Spacing.md,
  },
  historyHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: Spacing.sm,
  },
  historyTitle: {
    ...Typography.bodyBold,
    color: Colors.text,
  },
  clearHistoryButton: {
    ...Typography.caption,
    color: Colors.royalBlue,
  },
  historyItem: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: Spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border,
  },
  historyItemButton: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
  },
  historyItemText: {
    ...Typography.body,
    color: Colors.text,
    flex: 1,
  },
  modalContainer: {
    flex: 1,
    justifyContent: 'flex-end',
  },
  modalOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
  },
  modalOverlayPressable: {
    flex: 1,
  },
  modalContent: {
    backgroundColor: Colors.background,
    borderTopLeftRadius: BorderRadius.xl,
    borderTopRightRadius: BorderRadius.xl,
    maxHeight: '80%',
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: Spacing.lg,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border,
  },
  modalTitle: {
    ...Typography.h3,
    color: Colors.text,
  },
  modalBody: {
    padding: Spacing.lg,
  },
  filterLabel: {
    ...Typography.bodyBold,
    color: Colors.text,
    marginBottom: Spacing.sm,
    marginTop: Spacing.md,
  },
  filterLabelRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: Spacing.md,
    marginBottom: Spacing.sm,
  },
  showAllButton: {
    ...Typography.caption,
    color: Colors.royalBlue,
  },
  filterOptions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.sm,
  },
  filterOption: {
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm,
    borderRadius: BorderRadius.md,
    backgroundColor: Colors.surface,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  filterOptionSelected: {
    backgroundColor: Colors.royalBlue,
    borderColor: Colors.royalBlue,
  },
  filterOptionText: {
    ...Typography.body,
    color: Colors.text,
  },
  filterOptionTextSelected: {
    color: Colors.background,
    fontWeight: '600',
  },
  clearFiltersButton: {
    marginTop: Spacing.xl,
    padding: Spacing.md,
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.md,
    alignItems: 'center',
  },
  clearFiltersText: {
    ...Typography.body,
    color: Colors.error,
    fontWeight: '600',
  },
  sectionTitle: {
    ...Typography.h2,
    color: Colors.text,
    marginBottom: Spacing.md,
  },
  topArtistCard: {
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: BorderRadius.lg,
    padding: Spacing.md,
    marginBottom: Spacing.lg,
  },
  topArtistImageContainer: {
    width: 72,
    height: 72,
    borderRadius: 36,
    borderWidth: 3,
    borderColor: '#FFFFFF',
    overflow: 'hidden',
  },
  topArtistImage: {
    width: '100%',
    height: '100%',
  },
  topArtistPlaceholder: {
    width: '100%',
    height: '100%',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(255,255,255,0.15)',
  },
  topArtistInfo: {
    flex: 1,
    marginLeft: Spacing.md,
  },
  topArtistLabel: {
    ...Typography.caption,
    color: 'rgba(255,255,255,0.7)',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  topArtistName: {
    fontSize: 22,
    fontFamily: 'Inter_700Bold',
    color: '#FFFFFF',
    marginTop: 2,
  },
  artistArrowBg: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: 'rgba(255,255,255,0.2)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  userCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.lg,
    padding: Spacing.md,
    marginBottom: Spacing.sm,
  },
  userImageContainer: {
    width: 48,
    height: 48,
    borderRadius: 24,
    overflow: 'hidden',
    backgroundColor: Colors.background,
  },
  userPlaceholder: {
    width: '100%',
    height: '100%',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: Colors.background,
  },
  userInfo: {
    flex: 1,
    marginLeft: Spacing.md,
  },
  userLabel: {
    ...Typography.caption,
    color: Colors.textMuted,
    letterSpacing: 0.3,
  },
  userName: {
    ...Typography.bodyBold,
    color: Colors.text,
    marginTop: 2,
  },
  userStatText: {
    ...Typography.caption,
    color: Colors.textMuted,
    marginRight: Spacing.xs,
  },
  loadingContainer: {
    padding: Spacing.xl,
    alignItems: 'center',
  },
  loadingText: {
    ...Typography.body,
    color: Colors.textSecondary,
  },
  emptyContainer: {
    padding: Spacing.xl,
    alignItems: 'center',
  },
  emptyText: {
    ...Typography.body,
    color: Colors.textMuted,
    textAlign: 'center',
  },
});
