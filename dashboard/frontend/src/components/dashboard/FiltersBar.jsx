import { Filter, Calendar, Building2, Users, X } from "lucide-react";
import { useFilters } from "@/store/useFilters";
import { useState, useEffect } from "react";
import { api } from "@/lib/api";

const DEPOTS = ["Tous", "Tunis Nord", "Tunis Sud", "Sfax", "Sousse", "Nabeul", "Bizerte"];
const SEGMENTS = ["Tous", "DÉTAILLANTS", "SEMI-GROS", "HORECA", "GROSSISTES"];
const QUARTERS = ["Tous", "Q1", "Q2", "Q3", "Q4"];

function SelectFilter({ label, value, onChange, options }) {
  return (
    <div className="flex items-center gap-1.5 bg-surface-hover border border-border rounded-lg px-2.5 py-1.5">
      <span className="text-[10px] text-text-dim font-medium hidden sm:block">{label}:</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="bg-transparent text-[11px] text-foreground font-medium outline-none cursor-pointer"
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
  const filters = useFilters();
  const [years, setYears] = useState([2026, 2025, 2024, 2023]);

  // Charger les années disponibles depuis l'API
  useEffect(() => {
    api.filters()
      .then((data) => {
        if (data?.years) setYears(data.years);
      })
      .catch(() => {
        // utiliser les années par défaut
      });
  }, []);

  // Filtres actifs (pour afficher les chips)
  const activeFilters = [
    filters.quarter !== "Tous" && { key: "quarter", label: "Période", value: filters.quarter, reset: () => filters.setQuarter("Tous") },
    filters.depot !== "Tous" && { key: "depot", label: "Dépôt", value: filters.depot, reset: () => filters.setDepot("Tous") },
    filters.segment !== "Tous" && { key: "segment", label: "Segment", value: filters.segment, reset: () => filters.setSegment("Tous") },
  ].filter(Boolean);

  return (
    <div className="flex flex-wrap items-center gap-2 px-3 py-2 mb-4 border border-border rounded-xl bg-background sticky top-14 z-10">
      {/* Icône filtres */}
      <div className="flex items-center gap-1.5 text-text-dim pr-2 border-r border-border">
        <Filter size={13} />
        <span className="text-[10px] font-semibold uppercase tracking-wider">Filtres</span>
        {activeFilters.length > 0 && (
          <span className="w-4 h-4 rounded-full bg-primary text-white text-[9px] font-bold flex items-center justify-center">
            {activeFilters.length}
          </span>
        )}
      </div>

      {/* Année */}
      <SelectFilter
        label="Année"
        value={filters.year}
        onChange={(v) => filters.setYear(Number(v))}
        options={years.map(String)}
      />

      {/* Trimestre */}
      <SelectFilter
        label="Période"
        value={filters.quarter}
        onChange={filters.setQuarter}
        options={QUARTERS}
      />

      {/* Dépôt */}
      <SelectFilter
        label="Dépôt"
        value={filters.depot}
        onChange={filters.setDepot}
        options={DEPOTS}
      />

      {/* Segment */}
      <SelectFilter
        label="Segment"
        value={filters.segment}
        onChange={filters.setSegment}
        options={SEGMENTS}
      />

      {/* Chips filtres actifs */}
      {activeFilters.length > 0 && (
        <div className="w-full flex items-center gap-2 pt-1 mt-1 border-t border-border flex-wrap">
          {activeFilters.map((f) => (
            <span
              key={f.key}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-primary/15 border border-primary/30 text-primary text-[11px] font-semibold"
            >
              {f.label}: {f.value}
              <button onClick={f.reset} className="hover:bg-primary/20 rounded-full p-0.5">
                <X size={10} />
              </button>
            </span>
          ))}
          <button
            onClick={filters.resetAll}
            className="text-[11px] text-text-dim hover:text-red-400 font-medium ml-auto"
          >
            Réinitialiser
          </button>
        </div>
      )}
    </div>
  );
}
