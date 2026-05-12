export const MONTHS = [
  "Jan",
  "Fev",
  "Mar",
  "Avr",
  "Mai",
  "Jun",
  "Jul",
  "Aou",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

export const FAMILLES = [
  "Biscuits",
  "Boissons",
  "Conserves",
  "Produits Laitiers",
  "Confiserie",
  "Epicerie",
  "Huiles",
  "Pates",
];

export const CHART_COLORS = [
  "#3b82f6",
  "#6366f1",
  "#8b5cf6",
  "#a855f7",
  "#ec4899",
  "#f97316",
  "#22c55e",
  "#14b8a6",
];

function getSelectedCurrency() {
  try {
    const stored = JSON.parse(localStorage.getItem("finmag-parametres") || "{}");
    const devise = stored?.state?.devise || "TND - Dinar Tunisien";
    if (devise.startsWith("EUR")) return { code: "EUR", rate: 0.3 };
    if (devise.startsWith("USD")) return { code: "USD", rate: 0.33 };
  } catch {}
  return { code: "TND", rate: 1 };
}

export const formatTND = (v = 0) => {
  const { code, rate } = getSelectedCurrency();
  const value = Number(v || 0) * rate;
  const abs = Math.abs(value);
  const compact =
    abs >= 1000000
      ? `${(value / 1000000).toFixed(abs >= 10000000 ? 0 : 1)} M`
      : abs >= 1000
        ? `${(value / 1000).toFixed(abs >= 100000 ? 0 : 1)} K`
        : new Intl.NumberFormat("fr-TN", {
            style: "decimal",
            minimumFractionDigits: 0,
            maximumFractionDigits: 0,
          }).format(value);
  return `${compact} ${code}`;
};

export const formatNumber = (v = 0) => new Intl.NumberFormat("fr-TN").format(Number(v || 0));
export const formatPercent = (v = 0) => Number(v || 0).toFixed(1) + "%";
