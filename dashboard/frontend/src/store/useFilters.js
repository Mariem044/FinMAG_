import { create } from "zustand";

// Filtres globaux du dashboard
export const useFilters = create((set, get) => ({
  year: new Date().getFullYear(),
  quarter: "Tous",
  month: "Tous",
  region: "Toutes",
  famille: "Toutes",
  segment: "Tous",
  depot: "Tous",
  banque: "Toutes",
  modeBanque: "Tous",

  setYear: (year) => set({ year }),
  setQuarter: (quarter) => set({ quarter }),
  setMonth: (month) => set({ month }),
  setRegion: (region) => set({ region }),
  setFamille: (famille) => set({ famille }),
  setSegment: (segment) => set({ segment }),
  setDepot: (depot) => set({ depot }),
  setBanque: (banque) => set({ banque }),
  setModeBanque: (modeBanque) => set({ modeBanque }),
  resetAll: () =>
    set({
      year: new Date().getFullYear(),
      quarter: "Tous",
      month: "Tous",
      region: "Toutes",
      famille: "Toutes",
      segment: "Tous",
      depot: "Tous",
      banque: "Toutes",
      modeBanque: "Tous",
    }),

  getActiveMonthIndexes: () => {
    const { quarter } = get();
    const match = /^Q([1-4])$/.exec(String(quarter));
    if (match) {
      const start = (Number(match[1]) - 1) * 3;
      return Array.from({ length: 3 }, (_, index) => start + index);
    }
    return Array.from({ length: 12 }, (_, index) => index);
  },
}));

// Export vide pour compatibilité avec DashboardLayout
export function useSyncFiltersWithUrl() {}
