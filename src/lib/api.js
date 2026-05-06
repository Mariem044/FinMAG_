const BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

async function get(path) {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json();
}

export const api = {
  dashboard: {
    kpis:       () => get("/api/dashboard/kpis"),
    caByMonth:  () => get("/api/ventes/ca-by-month"),
  },
  tresorerie: {
    impayes:    () => get("/api/tresorerie/impayes"),
  },
  produits: {
    alerts:     () => get("/api/produits/stock-alerts"),
  },
};