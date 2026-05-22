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

export const CHART_COLORS = [
  "var(--chart-blue)",
  "var(--chart-indigo)",
  "var(--chart-violet)",
  "var(--chart-purple)",
  "var(--chart-pink)",
  "var(--chart-orange)",
  "var(--chart-green)",
  "var(--chart-teal)",
];

export const CHART_THEME = {
  axis: "var(--text-dim)",
  grid: "var(--border)",
  reference: "var(--border)",
  muted: "var(--text-muted)",
  primary: "var(--chart-blue)",
  secondary: "var(--chart-indigo)",
  positive: "var(--trend-up)",
  warning: "var(--chart-orange)",
  negative: "var(--trend-down)",
  neutral: "var(--chart-violet)",
};

export const CHART_LIMITS = {
  percentMin: 0,
  percentMax: 100,
  scoreMin: 0,
  scoreMax: 1,
  stockBubbleMin: 40,
  stockBubbleMax: 400,
  anomalyBubbleMin: 30,
  anomalyBubbleMax: 300,
};

function envNumber(key, fallback) {
  const value =
    typeof import.meta !== "undefined" ? import.meta.env?.[key] : undefined;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export const BUSINESS_THRESHOLDS = {
  stockDsiWarning: envNumber("VITE_STOCK_DSI_WARNING", 30),
  stockDsiSlow: envNumber("VITE_STOCK_DSI_SLOW", 90),
  stockScatterLimit: envNumber("VITE_STOCK_SCATTER_LIMIT", 40),
  topFamiliesLimit: envNumber("VITE_TOP_FAMILIES_LIMIT", 5),
  anomalyScore: envNumber("VITE_ANOMALY_SCORE_THRESHOLD", 0.8),
  bankReconciliationTarget: envNumber("VITE_BANK_RECONCILIATION_TARGET", 95),
};

function getSelectedCurrency() {
  try {
    const stored = JSON.parse(
      localStorage.getItem("finmag-parametres") || "{}",
    );
    const devise = stored?.state?.devise || "TND - Dinar Tunisien";
    if (devise.startsWith("EUR")) return { code: "EUR", rate: 0.3 };
    if (devise.startsWith("USD")) return { code: "USD", rate: 0.33 };
  } catch {}
  return { code: "TND", rate: 1 };
}

export const formatTND = (v = 0) => {
  const { code, rate } = getSelectedCurrency();
  return (
    new Intl.NumberFormat("fr-TN", {
      style: "decimal",
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(Number(v || 0) * rate) + ` ${code}`
  );
};

// API configuration (single source of truth)
export const API_BASE = ((typeof import.meta !== "undefined" && import.meta.env?.VITE_API_URL) || "").replace(/\/$/, "");
export const API_PREFIX = (typeof import.meta !== "undefined" && import.meta.env?.VITE_API_PREFIX) || "/api";
export const API_TIMEOUT_MS = Number((typeof import.meta !== "undefined" && import.meta.env?.VITE_API_TIMEOUT_MS) || 8000);
