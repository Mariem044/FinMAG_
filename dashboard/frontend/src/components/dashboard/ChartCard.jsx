import { memo } from "react";

// Squelettes de chargement haute-fidélité pour les graphiques
function ChartSkeleton({ type }) {
  if (type === "bar") {
    return (
      <div className="w-full flex items-end justify-between gap-3 h-[200px] md:h-[280px] pt-4 px-2 animate-pulse">
        {[40, 75, 55, 90, 60, 45, 80, 95, 30, 65, 85, 50].map((height, i) => (
          <div key={i} className="flex-1 flex flex-col items-center gap-1.5 h-full justify-end">
            <div 
              className="w-full bg-gradient-to-t from-primary/10 to-primary/30 rounded-t-md transition-all duration-500" 
              style={{ height: `${height}%` }}
            />
            <div className="w-6 h-2 bg-border/40 rounded-sm" />
          </div>
        ))}
      </div>
    );
  }

  if (type === "pie") {
    return (
      <div className="w-full flex items-center justify-center gap-8 h-[200px] md:h-[280px] animate-pulse">
        <div className="relative w-40 h-40 md:w-44 md:h-44 rounded-full border-[16px] border-surface-hover flex items-center justify-center">
          <div className="absolute inset-0 rounded-full border-[16px] border-primary/20 border-t-primary/40 border-r-primary/30 animate-spin" style={{ animationDuration: '3s' }} />
        </div>
        <div className="flex flex-col gap-3 flex-1 max-w-[150px]">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-primary/30" />
              <div className="h-3 bg-border/50 rounded flex-1" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (type === "line") {
    return (
      <div className="w-full h-[200px] md:h-[280px] relative pt-4 animate-pulse flex flex-col justify-between">
        {/* Lignes de grille */}
        <div className="absolute inset-0 flex flex-col justify-between pointer-events-none opacity-20 py-6">
          <div className="border-b border-dashed border-border w-full" />
          <div className="border-b border-dashed border-border w-full" />
          <div className="border-b border-dashed border-border w-full" />
          <div className="border-b border-dashed border-border w-full" />
        </div>
        {/* Tracé de ligne mock */}
        <svg className="w-full h-[180px] text-primary/20" viewBox="0 0 100 30" preserveAspectRatio="none">
          <path
            d="M 0 20 Q 20 5 40 22 T 80 10 T 100 15 L 100 30 L 0 30 Z"
            fill="currentColor"
            className="opacity-30"
          />
          <path
            d="M 0 20 Q 20 5 40 22 T 80 10 T 100 15"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
          />
        </svg>
        <div className="flex justify-between px-1">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div key={i} className="w-8 h-2 bg-border/40 rounded-sm" />
          ))}
        </div>
      </div>
    );
  }

  // Type scatter ou par défaut
  return (
    <div className="w-full h-[200px] md:h-[280px] relative pt-4 animate-pulse flex flex-col justify-between">
      <div className="absolute inset-0 flex flex-col justify-between pointer-events-none opacity-20 py-6">
        <div className="border-b border-dashed border-border w-full" />
        <div className="border-b border-dashed border-border w-full" />
        <div className="border-b border-dashed border-border w-full" />
      </div>
      <div className="relative flex-1">
        {/* Mock points */}
        <div className="absolute top-[20%] left-[15%] w-3 h-3 rounded-full bg-primary/40" />
        <div className="absolute top-[40%] left-[35%] w-3 h-3 rounded-full bg-emerald-500/40" />
        <div className="absolute top-[65%] left-[55%] w-3 h-3 rounded-full bg-primary/30" />
        <div className="absolute top-[30%] left-[75%] w-3 h-3 rounded-full bg-red-500/40" />
        <div className="absolute top-[50%] left-[85%] w-3 h-3 rounded-full bg-primary/40" />
      </div>
      <div className="flex justify-between px-1">
        {[1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="w-8 h-2 bg-border/40 rounded-sm" />
        ))}
      </div>
    </div>
  );
}

// Carte de graphique premium
export const ChartCard = memo(function ChartCard({ title, children, loading = false, skeleton = "line" }) {
  return (
    <div className="group relative bg-gradient-to-br from-card via-card/95 to-card/80 border border-border/50 rounded-xl p-4 md:p-5 shadow-lg shadow-black/10 hover:shadow-xl hover:shadow-primary/5 hover:border-primary/30 transition-all duration-500 ease-out transform hover:-translate-y-0.5 backdrop-blur-sm">
      {/* Ligne de surbrillance sur le dessus */}
      <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-primary/0 via-primary/40 to-primary/0 opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
      
      <h3 className="text-[13px] md:text-[14px] font-bold text-foreground/90 tracking-wide mb-5 group-hover:text-foreground transition-colors duration-300">
        {title}
      </h3>
      
      <div className="relative z-10">
        {loading ? (
          <ChartSkeleton type={skeleton} />
        ) : (
          <div className="animate-fade-in">
            {children}
          </div>
        )}
      </div>
    </div>
  );
});

// Placeholder KPI quand les données chargent (haute fidélité)
export function KPICardSkeleton() {
  return (
    <div className="relative bg-gradient-to-br from-card via-card/95 to-card/80 border border-border/50 rounded-xl p-5 flex items-start justify-between gap-4 animate-pulse overflow-hidden">
      <div className="flex-1 space-y-3.5">
        {/* Label */}
        <div className="h-3 w-2/3 bg-border/50 rounded-md" />
        {/* Valeur */}
        <div className="h-7 w-1/2 bg-border/70 rounded-md" />
        {/* Sous-titre */}
        <div className="h-3 w-3/4 bg-border/40 rounded-md" />
      </div>
      {/* Icône */}
      <div className="w-12 h-12 rounded-xl bg-border/40 flex-shrink-0" />
    </div>
  );
}

// Hauteur du graphique selon l'écran
export function useChartHeight(desktop = 280, mobile = 200) {
  return window.innerWidth < 768 ? mobile : desktop;
}
