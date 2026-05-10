// src/lib/api.js

const BASE = (
typeof import.meta !== "undefined" && import.meta.env?.VITE_API_URL) || ""
).replace(/\/$/, "");

const TIMEOUT_MS = Number(
  (typeof import.meta !== "undefined" && import.meta.env?.VITE_API_TIMEOUT_MS) || 8000
);

function url(path) {
  return `${BASE}${path}`;
}

async function fetchWithTimeout(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(url(path), {
      headers: { Accept: "application/json" },
      ...options,
      signal: controller.signal,
    });
    if (!res.ok) {
      const body = await res.text().catch(() => "");
      throw new Error(`API error ${res.status}${body ? `: ${body}` : ""}`);
    }
    return res.json();
  } finally {
    clearTimeout(timeout);
  }
}

function get(path) {
  return fetchWithTimeout(path);
}

function post(path) {
  return fetchWithTimeout(path, { method: "POST" });
}

export const api = {
  health: () => get("/api/health"),

  etl: {
    status: () => get("/api/etl/status"),
    run:    () => post("/api/etl/run"),
  },

  dashboard: {
    kpis:        () => get("/api/dashboard/kpis"),
    caByMonth:   () => get("/api/ventes/ca-by-month"),
    topFamilles: () => get("/api/ventes/top-familles"),
    caByRegion:  () => get("/api/ventes/ca-by-region"),
  },

  ventes: {
    caByMonth:   () => get("/api/ventes/ca-by-month"),
    topFamilles: () => get("/api/ventes/top-familles"),
    caByRegion:  () => get("/api/ventes/ca-by-region"),
  },

  tresorerie: {
    summary:            () => get("/api/tresorerie/summary"),
    impayes:            () => get("/api/tresorerie/impayes"),
    encaissementsByMode:() => get("/api/tresorerie/encaissements-by-mode"),
    aging:              () => get("/api/tresorerie/aging"),
  },

  produits: {
    articles: () => get("/api/produits/articles"),
    alerts:   () => get("/api/produits/stock-alerts"),
  },

  acteurs: {
    clients:                () => get("/api/acteurs/clients"),
    rfm:                    () => get("/api/acteurs/rfm"),
    aging:                  () => get("/api/acteurs/aging"),
    fournisseurs:           () => get("/api/acteurs/fournisseurs"),
    fournisseurConcentration:() => get("/api/acteurs/fournisseur-concentration"),
  },

  banque: {
    rapprochement: () => get("/api/banque/rapprochement"),
  },

  caisse: {
    caisses:          () => get("/api/caisse/caisses"),
    fluxDaily:        () => get("/api/caisse/flux-daily"),
    mouvementsByType: () => get("/api/caisse/mouvements-by-type"),
  },

  fiscalite: {
    kpis:         () => get("/api/fiscalite/kpis"),
    journaux:     () => get("/api/fiscalite/journaux"),
    tvaByMonth:   () => get("/api/fiscalite/tva-by-month"),
    anomalies:    () => get("/api/fiscalite/anomalies"),
    balanceByMonth:() => get("/api/fiscalite/balance-by-month"),
    ecritures:    () => get("/api/fiscalite/ecritures"),
  },

  search:          (query) => get(`/api/search?q=${encodeURIComponent(query)}`),
  notifications:   () => get("/api/notifications"),
  assistantSummary:() => get("/api/assistant/summary"),
};