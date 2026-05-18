import { useEffect, useState } from "react";
import { useNavigate, useSearch } from "@tanstack/react-router";
import { create } from "zustand";

export const FILTER_DEFAULTS = {
  year: Number(import.meta.env?.VITE_DEFAULT_YEAR) || 2024,
  quarter: import.meta.env?.VITE_DEFAULT_QUARTER || "Tous",
  month: "Tous",
  region: "Toutes",
  famille: "Toutes",
  segment: "Tous",
  depot: "Tous",
  banque: "Toutes",
  modeBanque: "Tous",
  modePaiement: "Tous",
  source: import.meta.env?.VITE_DEFAULT_SOURCE || "MAG_2020 + GRT_MAG",
  horizonPrev: import.meta.env?.VITE_DEFAULT_HORIZON || "30j",
  statutArticle: "Tous",
};

const FILTER_KEYS = Object.keys(FILTER_DEFAULTS);

function cleanValue(val) {
  if (typeof val === "string") {
    return val.replace(/^["']|["']$/g, "");
  }
  return val;
}

function readSearchValue(search, key) {
  const value = search?.[key];
  if (Array.isArray(value)) return cleanValue(value[0]);
  return cleanValue(value);
}

function filtersFromSearch(search) {
  return FILTER_KEYS.reduce((next, key) => {
    const raw = readSearchValue(search, key);
    if (raw === undefined || raw === null || raw === "") {
      next[key] = FILTER_DEFAULTS[key];
      return next;
    }
    next[key] = key === "year" ? Number(raw) || FILTER_DEFAULTS.year : String(raw);
    return next;
  }, {});
}

function filtersToSearch(filters) {
  return FILTER_KEYS.reduce((next, key) => {
    next[key] = String(filters[key] ?? FILTER_DEFAULTS[key]);
    return next;
  }, {});
}

function sameFilterSearch(search, filters) {
  const target = filtersToSearch(filters);
  return FILTER_KEYS.every((key) => String(readSearchValue(search, key) ?? "") === target[key]);
}

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

export function useSyncFiltersWithUrl() {
  // Disabled URL synchronization to prevent state resets and keep state 100% stable
}
