/**
 * Аналитика — провайдер-агностик обёртка.
 *
 * Чтобы подключить PostHog или Amplitude:
 *   1. Установить SDK: npx expo install posthog-react-native
 *   2. В _layout.tsx вызвать setAnalyticsProvider({ track, identify, reset })
 */

type AnalyticsProvider = {
  track: (event: string, properties?: Record<string, unknown>) => void;
  identify: (userId: string, properties?: Record<string, unknown>) => void;
  reset: () => void;
};

let provider: AnalyticsProvider | null = null;

export function setAnalyticsProvider(p: AnalyticsProvider) {
  provider = p;
}

function track(event: string, properties?: Record<string, unknown>) {
  if (__DEV__) {
    console.log(`[Analytics] ${event}`, properties ?? '');
  }
  provider?.track(event, properties);
}

export const analytics = {
  // --- Auth ---
  register: () => track('register'),
  login: (method: 'email' | 'apple' | 'google') => track('login', { method }),
  logout: () => {
    track('logout');
    provider?.reset();
  },
  identify: (userId: string) => provider?.identify(userId),

  // --- Scanner ---
  scanBarcode: (found: boolean) => track('scan_barcode', { found }),
  scanCover: (found: boolean) => track('scan_cover', { found }),

  // --- Collection & Wishlist ---
  addToCollection: (discogsId: string) => track('add_to_collection', { discogs_id: discogsId }),
  removeFromCollection: (discogsId: string) => track('remove_from_collection', { discogs_id: discogsId }),
  addToWishlist: (discogsId: string) => track('add_to_wishlist', { discogs_id: discogsId }),

  // --- Search ---
  search: (query: string, resultsCount?: number) =>
    track('search', { query, ...(resultsCount !== undefined && { results_count: resultsCount }) }),

  // --- Content ---
  viewRecord: (discogsId: string) => track('view_record', { discogs_id: discogsId }),
  viewArtist: (artistId: string) => track('view_artist', { artist_id: artistId }),

  // --- Social ---
  followUser: (targetUserId: string) => track('follow_user', { target_user_id: targetUserId }),
  bookGift: (recordId: string) => track('book_gift', { record_id: recordId }),
};
