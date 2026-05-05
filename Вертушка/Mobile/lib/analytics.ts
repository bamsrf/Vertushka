/**
 * Аналитика — провайдер-агностик обёртка.
 * Провайдер по умолчанию — Amplitude, инициализируется в _layout.tsx через initAmplitude().
 */
import * as Amplitude from '@amplitude/analytics-react-native';

type AnalyticsProvider = {
  track: (event: string, properties?: Record<string, unknown>) => void;
  identify: (userId: string, properties?: Record<string, unknown>) => void;
  reset: () => void;
};

let provider: AnalyticsProvider | null = null;

export function setAnalyticsProvider(p: AnalyticsProvider) {
  provider = p;
}

export async function initAmplitude(apiKey: string): Promise<void> {
  if (!apiKey) return;
  await Amplitude.init(apiKey, undefined, {
    trackingOptions: { ipAddress: false },
  }).promise;
  setAnalyticsProvider({
    track: (event, properties) => {
      Amplitude.track(event, properties);
    },
    identify: (userId, properties) => {
      Amplitude.setUserId(userId);
      if (properties) {
        const id = new Amplitude.Identify();
        for (const [k, v] of Object.entries(properties)) {
          id.set(k, v as never);
        }
        Amplitude.identify(id);
      }
    },
    reset: () => {
      Amplitude.reset();
    },
  });
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
