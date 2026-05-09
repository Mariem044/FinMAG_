const BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";
const TIMEOUT_MS = Number(import.meta.env.VITE_API_TIMEOUT_MS || 8000);

async function get(path) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(`${BASE}${path}`, { signal: controller.signal });
    if (!res.ok) throw new Error(`API error ${res.status}`);
    return res.json();
  } finally {
    clearTimeout(timeout);
  }
}

export const api = {
  health: () => get("/api/health"),
  dashboard: {
    kpis: () => get("/api/dashboard/kpis"),
    caByMonth: () => get("/api/ventes/ca-by-month"),
    topFamilles: () => get("/api/ventes/top-familles"),
    caByRegion: () => get("/api/ventes/ca-by-region"),
  },
  ventes: {
    caByMonth: () => get("/api/ventes/ca-by-month"),
    topFamilles: () => get("/api/ventes/top-familles"),
    caByRegion: () => get("/api/ventes/ca-by-region"),
  },
  tresorerie: {
    summary: () => get("/api/tresorerie/summary"),
    impayes: () => get("/api/tresorerie/impayes"),
    encaissementsByMode: () => get("/api/tresorerie/encaissements-by-mode"),
    aging: () => get("/api/tresorerie/aging"),
  },
  produits: {
    articles: () => get("/api/produits/articles"),
    alerts: () => get("/api/produits/stock-alerts"),
  },
  acteurs: {
    clients: () => get("/api/acteurs/clients"),
  },
  banque: {
    rapprochement: () => get("/api/banque/rapprochement"),
  },
  caisse: {
    caisses: () => get("/api/caisse/caisses"),
    fluxDaily: () => get("/api/caisse/flux-daily"),
  },
  fiscalite: {
    kpis: () => get("/api/fiscalite/kpis"),
    journaux: () => get("/api/fiscalite/journaux"),
    tvaByMonth: () => get("/api/fiscalite/tva-by-month"),
    anomalies: () => get("/api/fiscalite/anomalies"),
    balanceByMonth: () => get("/api/fiscalite/balance-by-month"),
    ecritures: () => get("/api/fiscalite/ecritures"),
  },
  search: (query) => get(`/api/search-q=${encodeURIComponent(query)}`),
  notifications: () => get("/api/notifications"),
  assistantSummary: () => get("/api/assistant/summary"),
};
