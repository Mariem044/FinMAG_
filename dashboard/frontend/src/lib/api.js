import { useFilters } from "../store/useFilters";

const BASE = ((typeof import.meta !== "undefined" && import.meta.env?.VITE_API_URL) || "").replace(
  /\/$/,
  "",
);

const TIMEOUT_MS = Number(
  (typeof import.meta !== "undefined" && import.meta.env?.VITE_API_TIMEOUT_MS) || 8000,
);

function url(path) {
  return `${BASE}${path}`;
}

// fetchWithTimeout : fait un appel HTTP avec un timeout de sécurité.
// On n'utilise PLUS de cache global (pendingRequests) car il bloquait
// les re-fetches quand un filtre changeait en plein chargement.
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

// get : construit l'URL en ajoutant automatiquement les filtres globaux.
// Si l'URL contient déjà un paramètre (ex: ?year=2026), il n'est PAS ajouté en double.
function get(path) {
  try {
    const filters = useFilters.getState();
    const filterParams = {};

    const keys = [
      "year", "quarter", "month", "region", "famille", "segment",
      "depot", "banque", "modeBanque", "modePaiement", "source",
      "horizonPrev", "statutArticle"
    ];

    keys.forEach(key => {
      const val = filters[key];
      if (val !== undefined && val !== null && val !== "") {
        filterParams[key] = String(val);
      }
    });

    const urlObj = new URL(path, window.location.origin);
    Object.entries(filterParams).forEach(([k, v]) => {
      // N'ajoute le param que s'il n'existe PAS déjà dans l'URL
      // (evite le doublon ?year=2026&year=2026)
      if (!urlObj.searchParams.has(k)) {
        urlObj.searchParams.append(k, v);
      }
    });

    path = urlObj.pathname + urlObj.search;
  } catch (err) {
    console.warn("Error building query params in api.js get():", err);
  }

  return fetchWithTimeout(path);
}

function post(path) {
  return fetchWithTimeout(path, { method: "POST" });
}

export const api = {
  health: () => get("/api/health"),
  filters: () => get("/api/dashboard/filters"),

  etl: {
    status: () => get("/api/etl/status"),
    run: () => post("/api/etl/run"),
  },

  ml: {
    status: () => get("/api/ml/status"),
    run: () => post("/api/ml/run"),
    forecastCa: () => get("/api/ml/forecast-ca"),
  },

  dashboard: {
    kpis: (year) => get(`/api/dashboard/kpis${year ? `?year=${year}` : ""}`),
    caByMonth: (year) => get(`/api/ventes/ca-by-month${year ? `?year=${year}` : ""}`),
    topFamilles: (year) => get(`/api/ventes/top-familles${year ? `?year=${year}` : ""}`),
    articles: (year) => get(`/api/produits/articles${year ? `?year=${year}` : ""}`),
  },

  tresorerie: {
    summary: () => get("/api/tresorerie/summary"),
    aging: () => get("/api/tresorerie/aging"),
  },

  acteurs: {
    clients: () => get("/api/acteurs/clients"),
    aging: () => get("/api/acteurs/aging"),
    fournisseurs: () => get("/api/acteurs/fournisseurs"),
    fournisseurConcentration: () => get("/api/acteurs/fournisseur-concentration"),
  },

  banque: {
    rapprochement: () => get("/api/banque/rapprochement"),
    rapprochementBreakdown: () => get("/api/banque/rapprochement-breakdown"),
  },

  caisse: {
    caisses: () => get("/api/caisse/caisses"),
    fluxDaily: () => get("/api/caisse/flux-daily"),
    mouvementsByType: () => get("/api/caisse/mouvements-by-type"),
  },

  fiscalite: {
    kpis: () => get("/api/fiscalite/kpis"),
    tvaByMonth: () => get("/api/fiscalite/tva-by-month"),
    anomalies: () => get("/api/fiscalite/anomalies"),
  },
};
