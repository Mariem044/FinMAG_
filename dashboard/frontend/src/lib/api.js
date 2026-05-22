import { useFilters } from "../store/useFilters";
import { API_BASE, API_PREFIX, API_TIMEOUT_MS } from "./dashboardConstants";

const BASE = API_BASE || "";
const TIMEOUT_MS = Number(API_TIMEOUT_MS || 8000);

function apiPath(path) {
  return `${API_PREFIX}${path}`;
}

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
      "depot", "banque"
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
  health: () => get(apiPath("/health")),
  filters: () => get(apiPath("/dashboard/filters")),

  etl: {
    status: () => get(apiPath("/etl/status")),
    run: () => post(apiPath("/etl/run")),
  },

  ml: {
    status: () => get(apiPath("/ml/status")),
    run: () => post(apiPath("/ml/run")),
    forecastCa: () => get(apiPath("/ml/forecast-ca")),
  },

  dashboard: {
    kpis: (year) => get(apiPath(`/dashboard/kpis${year ? `?year=${year}` : ""}`)),
    caByMonth: (year) => get(apiPath(`/ventes/ca-by-month${year ? `?year=${year}` : ""}`)),
    topFamilles: (year) => get(apiPath(`/ventes/top-familles${year ? `?year=${year}` : ""}`)),
    articles: (year) => get(apiPath(`/produits/articles${year ? `?year=${year}` : ""}`)),
  },

  tresorerie: {
    summary: () => get(apiPath("/tresorerie/summary")),
    aging: () => get(apiPath("/tresorerie/aging")),
  },



  banque: {
    rapprochement: () => get(apiPath("/banque/rapprochement")),
    rapprochementBreakdown: () => get(apiPath("/banque/rapprochement-breakdown")),
  },

  caisse: {
    caisses: () => get(apiPath("/caisse/caisses")),
    fluxDaily: () => get(apiPath("/caisse/flux-daily")),
    mouvementsByType: () => get(apiPath("/caisse/mouvements-by-type")),
  },

  fiscalite: {
    kpis: () => get(apiPath("/fiscalite/kpis")),
    tvaByMonth: () => get(apiPath("/fiscalite/tva-by-month")),
    anomalies: () => get(apiPath("/fiscalite/anomalies")),
  },
};
