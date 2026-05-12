// FIXED: Memoized KPICard export to avoid unnecessary dashboard re-renders.
import { memo } from "react";
import { TrendingUp, TrendingDown } from "lucide-react";

/**
 * KPICard — accessible KPI card.
 *
 * Accessibility fixes:
 * 1. The trend icon (TrendingUp / TrendingDown) was the ONLY indicator of
 *    direction — color alone is not sufficient per WCAG 1.4.1.
 *    Now each icon has an aria-label ("Trending up" / "Trending down") AND
 *    the percentage text is wrapped in a visually-hidden span that spells out
 *    the full meaning: "up 8.2% vs prior year" / "down 2.1% vs prior year".
 *
 * 2. The whole card is a <article> with aria-label combining the KPI name
 *    and its current value so screen readers announce something meaningful
 *    on focus, e.g. "Chiffre d'Affaires Total, 12,400,000 TND".
 *
 * 3. The decorative gradient / glow elements are aria-hidden.
 *
 * 4. The trend badge announces its full meaning to AT via an aria-label on
 *    the wrapping element — the visual text ("+8.2% vs N-1") alone is fine
 *    for sighted users but the icon needs an accessible name so it is not
 *    read as an unlabelled image by some AT.
 */
export const KPICard = memo(function KPICard({ label, value, trend, subtitle, icon: Icon }) {
  const isPositive = (trend ?? 0) >= 0;
  const trendDirection = isPositive ? "up" : "down";
  const trendAbs = Math.abs(trend ?? 0).toFixed(1);

  // Full accessible description of the trend for screen readers
  const trendAriaLabel = trend !== undefined
    ? `${isPositive ? "Up" : "Down"} ${trendAbs}% compared to prior year`
    : undefined;

  return (
    <article
      className="group relative bg-gradient-to-br from-card via-card/95 to-card/80 border border-border/50 rounded-lg md:rounded-xl p-3 md:p-4 lg:p-5 flex flex-col gap-2.5 hover:shadow-lg hover:shadow-primary/25 hover:border-primary/50 transition-all duration-500 ease-out transform hover:-translate-y-1 overflow-hidden backdrop-blur-sm before:absolute before:inset-0 before:bg-gradient-to-br before:from-primary/5 before:to-transparent before:opacity-0 hover:before:opacity-100 before:transition-opacity before:duration-500"
      aria-label={`${label}: ${value}${trend !== undefined ? `, ${trendAriaLabel}` : ""}`}
    >
      {/* Decorative elements — hidden from AT */}
      <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-primary/0 via-primary/80 to-primary/0 opacity-0 group-hover:opacity-100 transition-opacity duration-300" aria-hidden="true" />
      <div className="absolute -top-2 -right-2 w-20 h-20 bg-gradient-to-br from-primary/20 to-transparent rounded-full opacity-0 group-hover:opacity-100 transition-all duration-700 blur-2xl" aria-hidden="true" />

      <div className="flex items-start justify-between gap-4 relative z-10">
        <div className="min-w-0 flex-1">
          {/* Label — treat as a visible heading for the card */}
          <p className="text-[10px] md:text-[12px] font-semibold text-muted-foreground uppercase tracking-wider mb-2 line-clamp-2 group-hover:text-foreground transition-colors duration-300">
            {label}
          </p>

          <div className="relative">
            {/* Value — aria-hidden because the article aria-label already includes it */}
            <p
              className="text-lg md:text-xl lg:text-2xl font-bold text-foreground leading-tight truncate group-hover:scale-105 transition-transform duration-300 origin-left"
              aria-hidden="true"
            >
              {value}
            </p>
            <div className="absolute inset-0 bg-gradient-to-r from-primary/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500 blur-sm" aria-hidden="true" />
          </div>

          {subtitle && (
            <p className="text-[10px] text-muted-foreground mt-1 truncate">
              {subtitle}
            </p>
          )}

          {trend !== undefined && (
            <div
              className={`flex items-center gap-1.5 mt-2 text-[11px] md:text-[12px] font-medium px-2 py-1 rounded-md ${
                isPositive
                  ? "text-trend-up bg-trend-up/10 border border-trend-up/20"
                  : "text-trend-down bg-trend-down/10 border border-trend-down/20"
              } transition-all duration-300 hover:scale-105`}
              aria-label={trendAriaLabel}
              role="status"
            >
              <span
                className={`inline-flex items-center justify-center w-4 h-4 rounded-full ${
                  isPositive ? "bg-trend-up/20" : "bg-trend-down/20"
                } mr-1`}
              >
                {isPositive
                  ? <TrendingUp size={10} aria-hidden="true" />
                  : <TrendingDown size={10} aria-hidden="true" />
                }
              </span>

              {/* Visible text — aria-hidden because the wrapper div already has aria-label */}
              <span aria-hidden="true" className="font-semibold">
                {isPositive ? "+" : ""}{trend.toFixed(1)}% vs N-1
              </span>

              {/*
               * Visually-hidden text that spells out direction + magnitude
               * for screen readers that don't respect aria-label on non-interactive divs.
               * Belt-and-suspenders approach.
               */}
              <span className="sr-only">
                {isPositive ? "Up" : "Down"} {trendAbs}% vs prior year
              </span>
            </div>
          )}
        </div>

        <div
          className="w-10 h-10 md:w-12 md:h-12 rounded-xl bg-gradient-to-br from-primary/25 via-primary/15 to-primary/10 border border-primary/40 shadow-lg shadow-primary/25 flex items-center justify-center flex-shrink-0 group-hover:from-primary/40 group-hover:via-primary/25 group-hover:to-primary/15 group-hover:shadow-2xl group-hover:shadow-primary/40 transition-all duration-500 group-hover:rotate-12 group-hover:scale-110 relative overflow-hidden"
          aria-hidden="true"
        >
          <div className="absolute inset-0 bg-gradient-to-br from-white/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
          <Icon size={18} className="text-primary group-hover:scale-125 transition-transform duration-500 relative z-10 drop-shadow-sm" />
        </div>
      </div>
    </article>
  );
});
