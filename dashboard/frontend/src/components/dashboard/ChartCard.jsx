import { memo } from "react";

// Carte de graphique simple
export const ChartCard = memo(function ChartCard({ title, children, loading = false }) {
  return (
    <div className="bg-card border border-border rounded-xl p-4 md:p-5">
      <h3 className="text-[14px] font-bold text-foreground mb-4">{title}</h3>
      <div>
        {loading ? (
          <div className="flex items-center justify-center h-48 text-text-dim text-sm">
            Chargement...
          </div>
        ) : (
          children
        )}
      </div>
    </div>
  );
});

// Placeholder KPI quand les données chargent
export function KPICardSkeleton() {
  return (
    <div className="bg-card border border-border rounded-xl p-4">
      <div className="text-text-dim text-sm">Chargement...</div>
    </div>
  );
}

// Hauteur du graphique selon l'écran
export function useChartHeight(desktop = 280, mobile = 200) {
  return window.innerWidth < 768 ? mobile : desktop;
}
