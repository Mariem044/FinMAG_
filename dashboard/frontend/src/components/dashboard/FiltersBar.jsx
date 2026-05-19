import { Calendar, ChevronDown, RotateCcw } from "lucide-react";
import { useFilters } from "@/store/useFilters";
import { useState, useEffect } from "react";
import { api } from "@/lib/api";

const QUARTERS = ["Tous", "Q1", "Q2", "Q3", "Q4"];

export function FiltersBar() {
  const filters = useFilters();
  const [years, setYears] = useState([]);

  // Charger les années disponibles depuis l'API
  useEffect(() => {
    api
      .filters()
      .then((data) => {
        if (data?.years && data.years.length > 0) {
          setYears(data.years);
          const maxYear = Math.max(...data.years);
          if (
            !data.years.includes(filters.year) ||
            filters.year === new Date().getFullYear()
          ) {
            filters.setYear(maxYear);
          }
        }
      })
      .catch((err) => {
        console.error("Erreur de chargement des filtres :", err);
        setYears([new Date().getFullYear()]);
      });
  }, []);

  const defaultYear =
    years.length > 0 ? Math.max(...years) : new Date().getFullYear();
  const isFilterActive =
    filters.quarter !== "Tous" || filters.year !== defaultYear;

  const handleReset = () => {
    filters.setQuarter("Tous");
    filters.setYear(defaultYear);
  };

  return (
    <div className="relative flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-3 mb-6 border border-border/50 rounded-2xl bg-gradient-to-b from-card via-card/95 to-card/90 shadow-lg shadow-black/10 backdrop-blur-sm sticky top-[56px] z-20 animate-fade-in">
      {/* Ligne lumineuse en haut au survol */}
      <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-primary/0 via-primary/30 to-primary/0 pointer-events-none" />

      {/* Titre / Badge de filtre */}
      <div className="flex items-center gap-2">
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-primary/10 border border-primary/20 text-primary">
          <Calendar size={13} className="animate-slow-pulse" />
          <span className="text-[10px] font-bold uppercase tracking-wider">
            Filtres Temporels
          </span>
        </div>
      </div>

      {/* Sélecteurs de date */}
      <div className="flex flex-wrap items-center gap-4 sm:gap-6">
        {/* Choix de l'Année */}
        <div className="flex items-center gap-2">
          <span className="text-[11px] text-text-dim font-bold uppercase tracking-wider">
            Année
          </span>
          <div className="relative">
            <select
              value={filters.year}
              onChange={(e) => filters.setYear(Number(e.target.value))}
              className="appearance-none bg-surface border border-border/60 hover:border-primary/50 text-[11px] font-bold text-foreground pl-3 pr-8 py-1.5 rounded-xl outline-none cursor-pointer transition-all duration-300 hover:shadow-md hover:shadow-primary/5 min-w-[80px]"
            >
              {years.map((y) => (
                <option
                  key={y}
                  value={y}
                  className="bg-popover text-foreground"
                >
                  {y}
                </option>
              ))}
            </select>
            <div className="absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none text-text-dim">
              <ChevronDown size={11} />
            </div>
          </div>
        </div>

        {/* Choix du Trimestre (Pills) */}
        <div className="flex items-center gap-2">
          <span className="text-[11px] text-text-dim font-bold uppercase tracking-wider">
            Période
          </span>
          <div className="flex bg-surface/50 border border-border/60 rounded-xl p-0.5 shadow-inner">
            {QUARTERS.map((q) => {
              const active = filters.quarter === q;
              return (
                <button
                  key={q}
                  onClick={() => filters.setQuarter(q)}
                  className={`px-3 py-1 rounded-lg text-[10px] font-bold transition-all duration-300 ${
                    active
                      ? "bg-primary text-white shadow-md shadow-primary/20"
                      : "text-text-muted hover:text-foreground hover:bg-surface-hover/40"
                  }`}
                >
                  {q}
                </button>
              );
            })}
          </div>
        </div>

        {/* Bouton Réinitialiser */}
        {isFilterActive && (
          <button
            onClick={handleReset}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-dashed border-border hover:border-red-500/40 hover:bg-red-500/10 text-[10px] text-text-dim hover:text-red-400 font-bold transition-all duration-300 cursor-pointer"
          >
            <RotateCcw size={11} />
            Réinitialiser
          </button>
        )}
      </div>
    </div>
  );
}
