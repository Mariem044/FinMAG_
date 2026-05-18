import { useFilters } from "../store/useFilters";

const BASE = ((typeof import.meta !== "undefined" && import.meta.env?.VITE_API_URL) || "").replace(
  /\/$/,
  "",
);

const TIMEOUT_MS = Number(
  (typeof import.meta !== "undefined" && import.meta.env?.VITE_API_TIMEOUT_MS) || 8000,
);

const pendingRequests = new Map();

function url(path) {
  return `${BASE}${path}`;
}

async function fetchWithTimeout(path, options = {}) {
  const requestUrl = url(path);
  if (pendingRequests.has(requestUrl)) {
    return pendingRequests.get(requestUrl);
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), TIMEOUT_MS);
  const request = (async () => {
    try {
      const res = await fetch(requestUrl, {
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
      pendingRequests.delete(requestUrl);
    }
  })();

  pendingRequests.set(requestUrl, request);
  return request;
}

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

const _health = () => get("/api/health");
const _filters = () => get("/api/dashboard/filters");

const _etlStatus = () => get("/api/etl/status");
const _etlRun = () => post("/api/etl/run");

const _mlStatus = () => get("/api/ml/status");
const _mlRun = () => post("/api/ml/run");
const _mlForecastCa = () => get("/api/ml/forecast-ca");
const _mlForecastTresorerie = () => get("/api/ml/forecast-tresorerie");
const _mlProduitsAlerts = () => get("/api/ml/produits-alerts");
const _mlRfmSegments = () => get("/api/ml/rfm-segments");
const _mlLogs = () => get("/api/ml/logs");

const _dashboardKpis = (year) => get(`/api/dashboard/kpis${year ? `?year=${year}` : ""}`);
const _dashboardCaByMonth = (year) => get(`/api/ventes/ca-by-month${year ? `?year=${year}` : ""}`);
const _dashboardTopFamilles = (year) => get(`/api/ventes/top-familles${year ? `?year=${year}` : ""}`);
const _dashboardCaByRegion = (year) =>
  get(`/api/ventes/ca-by-region${year ? `?year=${year}` : ""}`);

const _ventesCaByMonth = (year) => get(`/api/ventes/ca-by-month${year ? `?year=${year}` : ""}`);
const _ventesTopFamilles = (year) => get(`/api/ventes/top-familles${year ? `?year=${year}` : ""}`);
const _ventesCaByRegion = (year) => get(`/api/ventes/ca-by-region${year ? `?year=${year}` : ""}`);
const _tresorerieSummary = () => get("/api/tresorerie/summary");
const _tresorerieImpayes = () => get("/api/tresorerie/impayes");
const _tresorerieImpayesFournisseurs = () => get("/api/tresorerie/impayes-fournisseurs");
const _tresorerieEncaissements = () => get("/api/tresorerie/encaissements-by-mode");
const _tresorerieAging = () => get("/api/tresorerie/aging");

const _produitsArticles = () => get("/api/produits/articles");
const _produitsAlerts = () => get("/api/produits/stock-alerts");

const _acteursClients = () => get("/api/acteurs/clients");
const _acteursRfm = () => get("/api/acteurs/rfm");
const _acteursAging = () => get("/api/acteurs/aging");
const _acteursFournisseurs = () => get("/api/acteurs/fournisseurs");
const _acteursFournisseurConcentration = () => get("/api/acteurs/fournisseur-concentration");
const _acteursLivreurs = () => get("/api/acteurs/livreurs");

const _banqueRapprochement = () => get("/api/banque/rapprochement");
const _banqueRapprochementBreakdown = () => get("/api/banque/rapprochement-breakdown");

const _caisseCaisses = () => get("/api/caisse/caisses");
const _caisseFluxDaily = () => get("/api/caisse/flux-daily");
const _caisseMouvementsByType = () => get("/api/caisse/mouvements-by-type");

const _fiscaliteKpis = () => get("/api/fiscalite/kpis");
const _fiscaliteJournaux = () => get("/api/fiscalite/journaux");
const _fiscaliteTvaByMonth = () => get("/api/fiscalite/tva-by-month");
const _fiscaliteAnomalies = () => get("/api/fiscalite/anomalies");
const _fiscaliteBalanceByMonth = () => get("/api/fiscalite/balance-by-month");
const _fiscaliteEcritures = () => get("/api/fiscalite/ecritures");

const _notifications = () => get("/api/notifications");

const _assistantSummary = () => get("/api/assistant/summary");

const _search = (query) => get(`/api/search?q=${encodeURIComponent(query)}`);

export const api = {
  health: _health,
  filters: _filters,

  etl: {
    status: _etlStatus,
    run: _etlRun,
  },

  ml: {
    status: _mlStatus,
    run: _mlRun,
    forecastCa: _mlForecastCa,
    forecastTresorerie: _mlForecastTresorerie,
    produitsAlerts: _mlProduitsAlerts,
    rfmSegments: _mlRfmSegments,
    logs: _mlLogs,
  },

  dashboard: {
    kpis: _dashboardKpis,
    caByMonth: _dashboardCaByMonth,
    topFamilles: _dashboardTopFamilles,
    caByRegion: _dashboardCaByRegion,
  },

  ventes: {
    caByMonth: _ventesCaByMonth,
    topFamilles: _ventesTopFamilles,
    caByRegion: _ventesCaByRegion,
  },

  tresorerie: {
    summary: _tresorerieSummary,
    impayes: _tresorerieImpayes,
    impayesFournisseurs: _tresorerieImpayesFournisseurs,
    encaissementsByMode: _tresorerieEncaissements,
    aging: _tresorerieAging,
  },

  produits: {
    articles: _produitsArticles,
    alerts: _produitsAlerts,
  },

  acteurs: {
    clients: _acteursClients,
    rfm: _acteursRfm,
    aging: _acteursAging,
    fournisseurs: _acteursFournisseurs,
    fournisseurConcentration: _acteursFournisseurConcentration,
    livreurs: _acteursLivreurs,
  },

  banque: {
    rapprochement: _banqueRapprochement,
    rapprochementBreakdown: _banqueRapprochementBreakdown,
  },

  caisse: {
    caisses: _caisseCaisses,
    fluxDaily: _caisseFluxDaily,
    mouvementsByType: _caisseMouvementsByType,
  },

  fiscalite: {
    kpis: _fiscaliteKpis,
    journaux: _fiscaliteJournaux,
    tvaByMonth: _fiscaliteTvaByMonth,
    anomalies: _fiscaliteAnomalies,
    balanceByMonth: _fiscaliteBalanceByMonth,
    ecritures: _fiscaliteEcritures,
  },

  search: _search,
  notifications: _notifications,
  assistantSummary: _assistantSummary,
};
