import { create } from "zustand";

export const FILTER_DEFAULTS = {
  year: 2024,
  quarter: "Tous",
  month: "Tous",
  region: "Toutes",
  famille: "Toutes",
  segment: "Tous",
  depot: "Tous",
  banque: "Toutes",
  modeBanque: "Tous",
  modePaiement: "Tous",
  source: "MAG_2020 + GRT_MAG",
  horizonPrev: "30j",
  statutArticle: "Tous",
};

export const useFilters = create((set, get) => ({
  ...FILTER_DEFAULTS,

  setYear: (year) => set({ year }),
  setQuarter: (quarter) => set({ quarter }),
  setMonth: (month) => set({ month }),
  setRegion: (region) => set({ region }),
  setFamille: (famille) => set({ famille }),
  setSegment: (segment) => set({ segment }),
  setDepot: (depot) => set({ depot }),
  setBanque: (banque) => set({ banque }),
  setModeBanque: (modeBanque) => set({ modeBanque }),
  setModePaiement: (modePaiement) => set({ modePaiement }),
  setSource: (source) => set({ source }),
  setHorizonPrev: (horizonPrev) => set({ horizonPrev }),
  setStatutArticle: (statutArticle) => set({ statutArticle }),
  resetAll: () => set({ ...FILTER_DEFAULTS }),

  getActiveMonthIndexes: () => {
    const { quarter } = get();
    if (quarter === "Q1") return [0, 1, 2];
    if (quarter === "Q2") return [3, 4, 5];
    if (quarter === "Q3") return [6, 7, 8];
    if (quarter === "Q4") return [9, 10, 11];
    return [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11];
  },
}));
