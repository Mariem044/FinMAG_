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
  return fetchWithTimeout(path);
}

function post(path) {
  return fetchWithTimeout(path, { method: "POST" });
}

const _health = () => get("/api/health");

const _etlStatus = () => get("/api/etl/status");
const _etlRun = () => post("/api/etl/run");

const _dashboardKpis = () => get("/api/dashboard/kpis");
const _dashboardCaByMonth = (year) => get(`/api/ventes/ca-by-month${year ? `?year=${year}` : ""}`);
const _dashboardTopFamilles = () => get("/api/ventes/top-familles");
const _dashboardCaByRegion = (year) =>
  get(`/api/ventes/ca-by-region${year ? `?year=${year}` : ""}`);

const _ventesCaByMonth = (year) => get(`/api/ventes/ca-by-month${year ? `?year=${year}` : ""}`);
const _ventesTopFamilles = () => get("/api/ventes/top-familles");
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

const _banqueRapprochement = () => get("/api/banque/rapprochement");

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

  etl: {
    status: _etlStatus,
    run: _etlRun,
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
  },

  banque: {
    rapprochement: _banqueRapprochement,
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
