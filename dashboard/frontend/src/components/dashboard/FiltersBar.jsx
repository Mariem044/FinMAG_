import { useLocation } from "@tanstack/react-router";
import { Filter, Calendar, Building2, Users, Database, ChevronDown, X } from "lucide-react";
import { useFilters } from "@/store/useFilters";
import { useParametres } from "@/store/useParametres";
import { useIsMobile } from "@/hooks/use-mobile";
import { useState, useEffect } from "react";
import { FILTER_DEFAULTS } from "@/store/useFilters";
import { api } from "@/lib/api";

const PERIODS_FR = [
  {
    label: "Jan 2024 – Déc 2024",
    label_en: "Jan 2024 – Dec 2024",
    label_ar: "يناير 2024 – ديسمبر 2024",
    quarter: "Tous",
  },
  { label: "Q1 2024", label_en: "Q1 2024", label_ar: "الربع الأول 2024", quarter: "Q1" },
  { label: "Q2 2024", label_en: "Q2 2024", label_ar: "الربع الثاني 2024", quarter: "Q2" },
  { label: "Q3 2024", label_en: "Q3 2024", label_ar: "الربع الثالث 2024", quarter: "Q3" },
  { label: "Q4 2024", label_en: "Q4 2024", label_ar: "الربع الرابع 2024", quarter: "Q4" },
];

const DEPOTS = [
  "Tous",
  "Tunis Nord",
  "Tunis Sud",
  "Sfax",
  "Sousse",
  "Nabeul",
  "Bizerte",
  "Dépôt Central",
];
const SEGMENTS = ["Tous", "DÉTAILLANTS", "SEMI-GROS", "HORECA", "GROSSISTES", "DISTRIBUTEUR"];
const SOURCES = ["MAG_2020 + GRT_MAG", "MAG_2020", "GRT_MAG"];

const DOMAIN_EXTRA = {
  "/tresorerie": [
    {
      storeKey: "modePaiement",
      labelKey: "filters.mode",
      options: ["Tous", "Chèque", "Espèce", "RS", "Traite", "Virement"],
    },
    { storeKey: "horizonPrev", labelKey: "filters.horizon", options: ["30j", "60j", "90j"] },
  ],
  "/produits": [
    {
      storeKey: "famille",
      labelKey: "filters.famille",
      options: [
        "Toutes",
        "Biscuits",
        "Boissons",
        "Conserves",
        "Produits Laitiers",
        "Confiserie",
        "Épicerie",
        "Huiles",
        "Pâtes",
      ],
    },
    {
      storeKey: "statutArticle",
      labelKey: "filters.statut",
      options: ["Tous", "Actifs uniquement", "En sommeil"],
    },
    { storeKey: "horizonPrev", labelKey: "filters.horizon", options: ["30j", "60j", "90j"] },
  ],
  "/banque": [
    {
      storeKey: "banque",
      labelKey: "filters.banque",
      options: ["Toutes", "AMEN", "ZITOUNA", "QNB", "BT"],
    },
    {
      storeKey: "modeBanque",
      labelKey: "filters.modeBanque",
      options: ["Tous", "Chèque", "Traite", "Virement"],
    },
  ],
  "/acteurs": [
    {
      storeKey: "segment",
      labelKey: "filters.segment",
      options: ["Tous", "Grand compte", "PME", "Petit client"],
    },
  ],
  "/ventes": [
    {
      storeKey: "segment",
      labelKey: "filters.segment",
      options: ["Tous", "Grand compte", "PME", "Petit client"],
    },
  ],
};

const FILTER_LABELS = {
  quarter: "Période",
  depot: "Dépôt",
  segment: "Segment",
  famille: "Famille",
  modePaiement: "Mode paiement",
  source: "Source",
  horizonPrev: "Horizon",
  statutArticle: "Statut",
  banque: "Banque",
  modeBanque: "Mode banque",
};

function FilterChip({ label, value, onRemove }) {
  return (
    <span className="animate-in fade-in-0 zoom-in-95 duration-200 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-primary/15 border border-primary/30 text-primary text-[11px] font-semibold">
      {label}: {value}
      <button
        onClick={onRemove}
        className="hover:bg-primary/20 rounded-full p-0.5 transition-colors"
        aria-label={`Retirer le filtre ${label}`}
      >
        <X size={10} />
      </button>
    </span>
  );
}

function SelectFilter({ label, value, onChange, options, icon: Icon, id }) {
  const selectId = id || `filter-${label.replace(/\s+/g, "-").toLowerCase()}`;
  return (
    <div className="flex items-center gap-1.5 bg-surface-hover/60 border border-border/60 rounded-lg px-2.5 py-1.5 min-w-0">
      {Icon && <Icon size={12} className="text-text-dim flex-shrink-0" aria-hidden="true" />}
      <span
        className="text-[10px] text-text-dim font-medium whitespace-nowrap hidden sm:block"
        aria-hidden="true"
      >
        {label}:
      </span>
      <label htmlFor={selectId} className="sr-only">
        {label}
      </label>
      <select
        id={selectId}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="bg-transparent text-[11px] text-foreground font-medium outline-none cursor-pointer min-w-0 max-w-[110px] sm:max-w-none truncate focus:ring-2 focus:ring-primary/50 focus:ring-offset-1 rounded"
      >
        {options.map((o) => (
          <option key={o} value={o} className="bg-background">
            {o}
          </option>
        ))}
      </select>
    </div>
  );
}

export function FiltersBar() {
  const location = useLocation();
  const path = location.pathname;
  const filters = useFilters();
  const { t, langue } = useParametres();
  const isMobile = useIsMobile();
  const extraDefs = DOMAIN_EXTRA[path] || [];
  const showSource = path === "/ventes" || path === "/tresorerie";
  const [expanded, setExpanded] = useState(false);

  const [dynamicOptions, setDynamicOptions] = useState(null);

  useEffect(() => {
    let active = true;
    api.filters()
      .then((data) => {
        if (active) setDynamicOptions(data);
      })
      .catch((err) => console.warn("Failed to load dynamic filters:", err));
    return () => {
      active = false;
    };
  }, []);

  const depots = dynamicOptions?.depots || DEPOTS;
  const segments = dynamicOptions?.segments || SEGMENTS;
  const families = dynamicOptions?.familles || [
    "Toutes",
    "Biscuits",
    "Boissons",
    "Conserves",
    "Produits Laitiers",
    "Confiserie",
    "Épicerie",
    "Huiles",
    "Pâtes",
  ];

  const processedExtraDefs = extraDefs.map((def) => {
    if (def.storeKey === "famille") {
      return { ...def, options: families };
    }
    if (def.storeKey === "modePaiement") {
      return { ...def, options: dynamicOptions?.modes_paiement || def.options };
    }
    return def;
  });

  const activeFilters = [
    filters.quarter !== FILTER_DEFAULTS.quarter && {
      key: "quarter",
      label: "Période",
      value: filters.quarter,
      reset: () => filters.setQuarter(FILTER_DEFAULTS.quarter),
    },
    filters.depot !== FILTER_DEFAULTS.depot && {
      key: "depot",
      label: "Dépôt",
      value: filters.depot,
      reset: () => filters.setDepot(FILTER_DEFAULTS.depot),
    },
    filters.segment !== FILTER_DEFAULTS.segment && {
      key: "segment",
      label: "Segment",
      value: filters.segment,
      reset: () => filters.setSegment(FILTER_DEFAULTS.segment),
    },
    filters.famille !== FILTER_DEFAULTS.famille && {
      key: "famille",
      label: "Famille",
      value: filters.famille,
      reset: () => filters.setFamille(FILTER_DEFAULTS.famille),
    },
    filters.modePaiement !== FILTER_DEFAULTS.modePaiement && {
      key: "modePaiement",
      label: "Mode paiement",
      value: filters.modePaiement,
      reset: () => filters.setModePaiement(FILTER_DEFAULTS.modePaiement),
    },
    showSource &&
      filters.source !== FILTER_DEFAULTS.source && {
        key: "source",
        label: "Source",
        value: filters.source,
        reset: () => filters.setSource(FILTER_DEFAULTS.source),
      },
    filters.horizonPrev !== FILTER_DEFAULTS.horizonPrev && {
      key: "horizonPrev",
      label: "Horizon",
      value: filters.horizonPrev,
      reset: () => filters.setHorizonPrev(FILTER_DEFAULTS.horizonPrev),
    },
    filters.banque !== FILTER_DEFAULTS.banque && {
      key: "banque",
      label: "Banque",
      value: filters.banque,
      reset: () => filters.setBanque(FILTER_DEFAULTS.banque),
    },
    filters.modeBanque !== FILTER_DEFAULTS.modeBanque && {
      key: "modeBanque",
      label: "Mode banque",
      value: filters.modeBanque,
      reset: () => filters.setModeBanque(FILTER_DEFAULTS.modeBanque),
    },
    filters.statutArticle !== FILTER_DEFAULTS.statutArticle && {
      key: "statutArticle",
      label: "Statut",
      value: filters.statutArticle,
      reset: () => filters.setStatutArticle(FILTER_DEFAULTS.statutArticle),
    },
  ].filter(Boolean);

  const yearsList = dynamicOptions?.years || [2026, 2025, 2024, 2023, 2022, 2021, 2020];

  const dynamicPeriods = yearsList.flatMap((y) => [
    {
      label: `Jan ${y} – Déc ${y}`,
      label_en: `Jan ${y} – Dec ${y}`,
      label_ar: `يناير ${y} – ديسمبر ${y}`,
      quarter: "Tous",
      year: y,
    },
    { label: `Q1 ${y}`, label_en: `Q1 ${y}`, label_ar: `الربع الأول ${y}`, quarter: "Q1", year: y },
    { label: `Q2 ${y}`, label_en: `Q2 ${y}`, label_ar: `الربع الثاني ${y}`, quarter: "Q2", year: y },
    { label: `Q3 ${y}`, label_en: `Q3 ${y}`, label_ar: `الربع الثالث ${y}`, quarter: "Q3", year: y },
    { label: `Q4 ${y}`, label_en: `Q4 ${y}`, label_ar: `الربع الرابع ${y}`, quarter: "Q4", year: y },
  ]);

  const langKey = langue === "English" ? "label_en" : langue === "العربية" ? "label_ar" : "label";
  const periodLabels = dynamicPeriods.map((p) => p[langKey]);

  const currentPeriodLabel = (() => {
    const found = dynamicPeriods.find((p) => p.quarter === filters.quarter && p.year === filters.year);
    return found ? found[langKey] : periodLabels.find((l) => l.includes(String(filters.year))) || periodLabels[0];
  })();

  const handlePeriodChange = (label) => {
    const idx = periodLabels.indexOf(label);
    if (idx >= 0) {
      const p = dynamicPeriods[idx];
      filters.setQuarter(p.quarter);
      filters.setYear(p.year);
    }
  };

  const allFilters = (
    <>
      <SelectFilter
        id="filter-period"
        label={t("filters.period")}
        value={currentPeriodLabel}
        onChange={handlePeriodChange}
        options={periodLabels}
        icon={Calendar}
      />
      <SelectFilter
        id="filter-depot"
        label={t("filters.depot")}
        value={filters.depot}
        onChange={filters.setDepot}
        options={depots}
        icon={Building2}
      />
      {!processedExtraDefs.some((d) => d.storeKey === "segment") && (
        <SelectFilter
          id="filter-segment"
          label={t("filters.segment")}
          value={filters.segment}
          onChange={filters.setSegment}
          options={segments}
          icon={Users}
        />
      )}
      {showSource && (
        <SelectFilter
          id="filter-source"
          label={t("filters.source")}
          value={filters.source}
          onChange={filters.setSource}
          options={SOURCES}
          icon={Database}
        />
      )}
      {processedExtraDefs.map((def) => (
        <SelectFilter
          key={def.storeKey}
          id={`filter-${def.storeKey}`}
          label={t(def.labelKey)}
          value={filters[def.storeKey]}
          onChange={(v) => {
            const setter = "set" + def.storeKey.charAt(0).toUpperCase() + def.storeKey.slice(1);
            if (typeof filters[setter] === "function") filters[setter](v);
          }}
          options={def.options}
        />
      ))}
    </>
  );

  if (isMobile) {
    return (
      <div
        className="mb-4 border border-border/40 rounded-xl bg-background/40 backdrop-blur-sm sticky top-14 z-10"
        role="search"
        aria-label={t("filters.label")}
      >
        <button
          onClick={() => setExpanded(!expanded)}
          className="w-full flex items-center justify-between px-3 py-2.5"
          aria-expanded={expanded}
          aria-controls="filters-panel"
        >
          <div className="flex items-center gap-2 text-text-dim">
            <Filter size={13} aria-hidden="true" />
            <span className="text-[10px] font-semibold uppercase tracking-wider">
              {t("filters.label")}
            </span>
          </div>
          <ChevronDown
            size={14}
            className={`text-text-dim transition-transform duration-200 ${expanded ? "rotate-180" : ""}`}
            aria-hidden="true"
          />
        </button>

        {expanded && (
          <fieldset
            id="filters-panel"
            className="px-3 pb-3 pt-1 border-t border-border/40 flex flex-wrap gap-2"
          >
            <legend className="sr-only">{t("filters.label")}</legend>
            {allFilters}

            {activeFilters.length > 0 && (
              <div className="w-full flex items-center gap-2 pt-1 mt-1 border-t border-border/40 flex-wrap">
                {activeFilters.map((f) => (
                  <FilterChip key={f.key} label={f.label} value={f.value} onRemove={f.reset} />
                ))}
                <button
                  onClick={filters.resetAll}
                  className="text-[11px] text-text-dim hover:text-red-400 font-medium transition-colors ml-auto"
                >
                  Réinitialiser tout
                </button>
              </div>
            )}
          </fieldset>
        )}
      </div>
    );
  }

  return (
    <fieldset
      className="flex flex-wrap items-center gap-2 px-3 py-2 mb-4 border border-border/40 rounded-xl bg-background/40 backdrop-blur-sm sticky top-14 z-10"
      role="search"
      aria-label={t("filters.label")}
    >
      <legend className="sr-only">{t("filters.label")}</legend>

      <div
        className="flex items-center gap-1.5 text-text-dim pr-2 border-r border-border/60 flex-shrink-0"
        aria-hidden="true"
      >
        <Filter size={13} />
        <span className="text-[10px] font-semibold uppercase tracking-wider">
          {t("filters.label")}
        </span>
        {activeFilters.length > 0 && (
          <span className="w-4 h-4 rounded-full bg-primary text-white text-[9px] font-bold flex items-center justify-center">
            {activeFilters.length}
          </span>
        )}
      </div>

      {allFilters}

      {activeFilters.length > 0 && (
        <div className="w-full flex items-center gap-2 pt-1 mt-1 border-t border-border/40 flex-wrap">
          {activeFilters.map((f) => (
            <FilterChip key={f.key} label={f.label} value={f.value} onRemove={f.reset} />
          ))}
          <button
            onClick={filters.resetAll}
            className="text-[11px] text-text-dim hover:text-red-400 font-medium transition-colors ml-auto"
          >
            Réinitialiser tout
          </button>
        </div>
      )}
    </fieldset>
  );
}
