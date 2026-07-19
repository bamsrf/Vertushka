/**
 * radarReopen — мостик между экранами для сценария «радар заполнен».
 *
 * Когда юзер на карточке пытается добавить 6-й релиз, получает 409 radar_limit
 * и уходит в /radar убрать лишнее. Сюда кладём данные шторки порога, чтобы после
 * возврата на карточку автоматически переоткрыть тот же ThresholdSheet.
 */
import { create } from 'zustand';
import type { ThresholdSheetData } from '../components/wishlist/ThresholdSheet';

interface RadarReopenState {
  pending: ThresholdSheetData | null;
  set: (data: ThresholdSheetData) => void;
  clear: () => void;
}

export const useRadarReopen = create<RadarReopenState>((set) => ({
  pending: null,
  set: (data) => set({ pending: data }),
  clear: () => set({ pending: null }),
}));
