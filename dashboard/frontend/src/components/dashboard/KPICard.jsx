import { memo } from "react";
import { TrendingUp, TrendingDown } from "lucide-react";

function generateSparklinePath(data, width, height) {
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  return data
    .map((val, i) => {
      const x = (i / (data.length - 1)) * width;
      const y = height - ((val - min) / range) * (height - 4) - 2;
      return `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");
}

export const KPICard = memo(function KPICard({ label, value, trend, subtitle, icon: Icon, sparkline }) {
  const hasTrend = Number.isFinite(trend);
  const safeTrend = hasTrend ? trend : 0;
  const isPositive = hasTrend ? safeTrend >= 0 : (sparkline && sparkline[sparkline.length - 1] >= sparkline[0]);
  const trendDirection = isPositive ? "up" : "down";
  const trendAbs = Math.abs(safeTrend).toFixed(1);

  const trendAriaLabel =
    hasTrend
      ? `${isPositive ? "Hausse" : "Baisse"} de ${trendAbs}% par rapport à N-1`
      : undefined;

  const sparklineId = label ? label.replace(/[^a-zA-Z0-9]/g, '-') : Math.random().toString(36).substring(7);

  return (
    <article
      className="group relative bg-gradient-to-br from-card via-card/95 to-card/80 border border-border/50 rounded-lg md:rounded-xl p-3 md:p-4 lg:p-5 flex flex-col gap-2.5 hover:shadow-lg hover:shadow-primary/25 hover:border-primary/50 transition-all duration-500 ease-out transform hover:-translate-y-1 overflow-hidden backdrop-blur-sm before:absolute before:inset-0 before:bg-gradient-to-br before:from-primary/5 before:to-transparent before:opacity-0 hover:before:opacity-100 before:transition-opacity before:duration-500"
      aria-label={`${label}: ${value}${hasTrend ? `, ${trendAriaLabel}` : ""}`}
    >
      <div
        className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-primary/0 via-primary/80 to-primary/0 opacity-0 group-hover:opacity-100 transition-opacity duration-300"
        aria-hidden="true"
      />
      <div
        className="absolute -top-2 -right-2 w-20 h-20 bg-gradient-to-br from-primary/20 to-transparent rounded-full opacity-0 group-hover:opacity-100 transition-all duration-700 blur-2xl"
        aria-hidden="true"
      />

      <div className="flex items-start justify-between gap-4 relative z-10">
        <div className="min-w-0 flex-1">
          <p className="text-[10px] md:text-[12px] font-semibold text-muted-foreground uppercase tracking-wider mb-2 line-clamp-2 group-hover:text-foreground transition-colors duration-300">
            {label}
          </p>

          <div className="relative">
            <p
              className="text-lg md:text-xl lg:text-2xl font-bold text-foreground leading-tight truncate group-hover:scale-105 transition-transform duration-300 origin-left"
              aria-hidden="true"
            >
              {value}
            </p>
            <div
              className="absolute inset-0 bg-gradient-to-r from-primary/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500 blur-sm"
              aria-hidden="true"
            />
          </div>

          {subtitle && (
            <p className="text-[10px] text-muted-foreground mt-1 truncate">{subtitle}</p>
          )}

          {hasTrend && (
            <div
              className={`flex items-center gap-1.5 mt-2 text-[11px] md:text-[12px] font-medium px-2 py-1 rounded-md ${
                isPositive
                  ? "text-trend-up bg-trend-up/10 border border-trend-up/20"
                  : "text-trend-down bg-trend-down/10 border border-trend-down/20"
              } transition-all duration-300 hover:scale-105 w-max`}
              aria-label={trendAriaLabel}
              role="status"
            >
              <span
                className={`inline-flex items-center justify-center w-4 h-4 rounded-full ${
                  isPositive ? "bg-trend-up/20" : "bg-trend-down/20"
                } mr-1`}
              >
                {isPositive ? (
                  <TrendingUp size={10} aria-hidden="true" />
                ) : (
                  <TrendingDown size={10} aria-hidden="true" />
                )}
              </span>

              <span aria-hidden="true" className="font-semibold">
                {isPositive ? "+" : ""}
                {safeTrend.toFixed(1)}% par rapport à N-1
              </span>

              <span className="sr-only">
                {isPositive ? "Hausse" : "Baisse"} de {trendAbs}% par rapport à N-1
              </span>
            </div>
          )}
        </div>

        <div
          className="w-10 h-10 md:w-12 md:h-12 rounded-xl bg-gradient-to-br from-primary/25 via-primary/15 to-primary/10 border border-primary/40 shadow-lg shadow-primary/25 flex items-center justify-center flex-shrink-0 group-hover:from-primary/40 group-hover:via-primary/25 group-hover:to-primary/15 group-hover:shadow-2xl group-hover:shadow-primary/40 transition-all duration-500 group-hover:rotate-12 group-hover:scale-110 relative overflow-hidden"
          aria-hidden="true"
        >
          <div className="absolute inset-0 bg-gradient-to-br from-white/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
          <Icon
            size={18}
            className="text-primary group-hover:scale-125 transition-transform duration-500 relative z-10 drop-shadow-sm"
          />
        </div>
      </div>

      {sparkline && sparkline.length > 1 && (
        <div className="w-full h-8 mt-2 relative overflow-hidden rounded opacity-80 group-hover:opacity-100 transition-opacity duration-300 z-10">
          <svg className="w-full h-full" viewBox="0 0 100 30" preserveAspectRatio="none">
            <defs>
              <linearGradient id={`gradient-${sparklineId}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={isPositive ? '#10b981' : '#ef4444'} stopOpacity="0.25" />
                <stop offset="100%" stopColor={isPositive ? '#10b981' : '#ef4444'} stopOpacity="0.0" />
              </linearGradient>
            </defs>
            <path
              d={generateSparklinePath(sparkline, 100, 30)}
              fill="none"
              stroke={isPositive ? '#10b981' : '#ef4444'}
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <path
              d={`${generateSparklinePath(sparkline, 100, 30)} L 100 30 L 0 30 Z`}
              fill={`url(#gradient-${sparklineId})`}
            />
          </svg>
        </div>
      )}
    </article>
  );
});
