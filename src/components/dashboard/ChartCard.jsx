import { useIsMobile } from "@/hooks/use-mobile";
import { Skeleton } from "@/components/ui/skeleton";
import { useEffect, useState } from "react";

/**
 * Shimmer skeleton variants for different chart types.
 * Used internally by ChartCard when `loading` prop is true.
 */

function BarChartSkeleton({ bars = 7, horizontal = false }) {
  const heights = [65, 85, 50, 95, 70, 80, 55];
  if (horizontal) {
    return (
      <div className="flex flex-col gap-3 justify-center h-full px-2 py-4">
        {Array.from({ length: bars }).map((_, i) => (
          <div key={i} className="flex items-center gap-3">
            <Skeleton className="h-3 w-16 flex-shrink-0 rounded" />
            <Skeleton
              className="h-5 rounded"
              style={{ width: `${heights[i % heights.length]}%`, animationDelay: `${i * 80}ms` }}
            />
          </div>
        ))}
      </div>
    );
  }
  return (
    <div className="flex items-end justify-between gap-2 h-full px-2 pb-6 pt-2">
      {Array.from({ length: bars }).map((_, i) => (
        <div key={i} className="flex-1 flex flex-col items-center gap-1.5">
          <Skeleton
            className="w-full rounded-t"
            style={{ height: `${heights[i % heights.length]}%`, animationDelay: `${i * 70}ms` }}
          />
          <Skeleton className="h-2 w-6 rounded" style={{ animationDelay: `${i * 70 + 20}ms` }} />
        </div>
      ))}
    </div>
  );
}

function LineChartSkeleton() {
  return (
    <div className="relative h-full w-full px-2 py-4 overflow-hidden">
      {/* Y-axis ticks */}
      <div className="absolute left-0 top-4 bottom-8 flex flex-col justify-between">
        {[0, 1, 2, 3, 4].map((i) => (
          <Skeleton key={i} className="h-2 w-8 rounded" style={{ animationDelay: `${i * 60}ms` }} />
        ))}
      </div>
      {/* SVG wave lines */}
      <svg
        className="absolute inset-0 w-full h-full opacity-20"
        preserveAspectRatio="none"
        viewBox="0 0 300 100"
      >
        <polyline
          points="10,70 50,45 90,60 130,30 170,50 210,25 250,40 290,20"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          className="text-primary"
          strokeDasharray="300"
          strokeDashoffset="300"
          style={{
            animation: "skeletonLine 1.8s ease-in-out infinite alternate",
          }}
        />
        <polyline
          points="10,80 50,65 90,75 130,55 170,70 210,50 250,65 290,45"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          className="text-muted-foreground"
          strokeDasharray="300"
          strokeDashoffset="300"
          style={{
            animation: "skeletonLine 2s ease-in-out 0.3s infinite alternate",
          }}
        />
      </svg>
      {/* Horizontal grid lines */}
      <div className="absolute inset-x-10 top-4 bottom-8 flex flex-col justify-between pointer-events-none">
        {[0, 1, 2, 3, 4].map((i) => (
          <Skeleton
            key={i}
            className="h-px w-full opacity-30 rounded-none"
            style={{ animationDelay: `${i * 50}ms` }}
          />
        ))}
      </div>
      {/* X-axis ticks */}
      <div className="absolute bottom-0 left-10 right-2 flex justify-between">
        {[0, 1, 2, 3, 4, 5, 6].map((i) => (
          <Skeleton key={i} className="h-2 w-5 rounded" style={{ animationDelay: `${i * 60}ms` }} />
        ))}
      </div>
    </div>
  );
}

function AreaChartSkeleton() {
  return (
    <div className="relative h-full w-full px-2 py-4 overflow-hidden">
      <svg
        className="absolute inset-0 w-full h-full"
        preserveAspectRatio="none"
        viewBox="0 0 300 100"
      >
        <defs>
          <linearGradient id="skelAreaGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="hsl(var(--primary) / 0.12)" />
            <stop offset="100%" stopColor="hsl(var(--primary) / 0)" />
          </linearGradient>
        </defs>
        <path
          d="M10,70 C50,45 90,60 130,30 C170,10 210,25 250,40 L290,20 L290,95 L10,95 Z"
          fill="url(#skelAreaGrad)"
          className="opacity-60"
          style={{ animation: "skelPulse 2s ease-in-out infinite" }}
        />
        <polyline
          points="10,70 50,45 90,60 130,30 170,15 210,25 250,40 290,20"
          fill="none"
          stroke="hsl(var(--primary) / 0.3)"
          strokeWidth="2"
        />
      </svg>
      <div className="absolute bottom-0 left-10 right-2 flex justify-between">
        {[0, 1, 2, 3, 4, 5, 6].map((i) => (
          <Skeleton key={i} className="h-2 w-5 rounded" style={{ animationDelay: `${i * 60}ms` }} />
        ))}
      </div>
    </div>
  );
}

function PieChartSkeleton() {
  return (
    <div className="flex items-center justify-center gap-6 h-full py-4">
      {/* Donut ring */}
      <div className="relative flex-shrink-0">
        <svg width={140} height={140} viewBox="0 0 140 140">
          <circle cx={70} cy={70} r={52} fill="none" stroke="hsl(var(--primary) / 0.08)" strokeWidth={20} />
          <circle
            cx={70} cy={70} r={52}
            fill="none"
            stroke="hsl(var(--primary) / 0.18)"
            strokeWidth={20}
            strokeDasharray="327"
            strokeDashoffset="82"
            style={{ animation: "skelPulse 1.8s ease-in-out infinite" }}
          />
          <circle
            cx={70} cy={70} r={52}
            fill="none"
            stroke="hsl(var(--muted-foreground) / 0.10)"
            strokeWidth={20}
            strokeDasharray="327"
            strokeDashoffset="163"
            strokeLinecap="round"
            style={{ animation: "skelPulse 2s ease-in-out 0.4s infinite" }}
          />
        </svg>
      </div>
      {/* Legend lines */}
      <div className="flex flex-col gap-2.5">
        {[70, 55, 45, 60, 40].map((w, i) => (
          <div key={i} className="flex items-center gap-2">
            <Skeleton className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ animationDelay: `${i * 80}ms` }} />
            <Skeleton className="h-2.5 rounded" style={{ width: w, animationDelay: `${i * 80 + 20}ms` }} />
          </div>
        ))}
      </div>
    </div>
  );
}

function ScatterChartSkeleton() {
  // Generate stable dot positions using a seeded pattern
  const dots = Array.from({ length: 20 }, (_, i) => ({
    x: 10 + ((i * 37 + 13) % 80),
    y: 10 + ((i * 53 + 7) % 75),
    r: 3 + (i % 3),
    delay: i * 50,
  }));
  return (
    <div className="relative h-full w-full px-2 py-4 overflow-hidden">
      <svg className="absolute inset-0 w-full h-full" preserveAspectRatio="none" viewBox="0 0 100 100">
        {dots.map((d, i) => (
          <circle
            key={i}
            cx={d.x}
            cy={d.y}
            r={d.r}
            fill="hsl(var(--primary) / 0.25)"
            style={{ animation: `skelPulse 2s ease-in-out ${d.delay}ms infinite` }}
          />
        ))}
        {/* Reference lines */}
        <line x1="50" y1="5" x2="50" y2="95" stroke="hsl(var(--border))" strokeWidth="0.5" strokeDasharray="3 2" />
        <line x1="5" y1="50" x2="95" y2="50" stroke="hsl(var(--border))" strokeWidth="0.5" strokeDasharray="3 2" />
      </svg>
    </div>
  );
}

function TableSkeleton({ rows = 6 }) {
  return (
    <div className="space-y-0">
      {/* Header */}
      <div className="flex gap-3 px-3 py-2 border-b border-border/40">
        {[120, 80, 90, 70, 100].map((w, i) => (
          <Skeleton key={i} className="h-2.5 rounded" style={{ width: w, animationDelay: `${i * 40}ms` }} />
        ))}
      </div>
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className={`flex gap-3 px-3 py-2.5 border-b border-border/20 ${i % 2 === 1 ? "bg-secondary/10" : ""}`}
        >
          {[120, 80, 90, 70, 100].map((w, j) => (
            <Skeleton
              key={j}
              className="h-2 rounded"
              style={{ width: w * (0.6 + (j * i % 4) * 0.1), animationDelay: `${(i * 5 + j) * 35}ms` }}
            />
          ))}
        </div>
      ))}
    </div>
  );
}

function GaugeSkeleton() {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-3 py-4">
      <svg width={160} height={90} viewBox="0 0 160 90">
        <path
          d="M 15 80 A 65 65 0 0 1 145 80"
          fill="none"
          stroke="hsl(var(--primary) / 0.08)"
          strokeWidth={13}
          strokeLinecap="round"
        />
        <path
          d="M 15 80 A 65 65 0 0 1 100 25"
          fill="none"
          stroke="hsl(var(--primary) / 0.22)"
          strokeWidth={13}
          strokeLinecap="round"
          style={{ animation: "skelPulse 1.8s ease-in-out infinite" }}
        />
        <Skeleton className="rounded-full" x={68} y={60} width={24} height={12} />
      </svg>
      <Skeleton className="h-3 w-24 rounded" />
    </div>
  );
}

/**
 * ChartSkeleton — auto-selects the right skeleton variant based on `variant` prop.
 *
 * Supported variants:
 *   "bar"      – vertical grouped/stacked bars
 *   "bar-h"    – horizontal bar chart
 *   "line"     – line chart with axis ticks
 *   "area"     – area/filled chart
 *   "pie"      – donut + legend
 *   "scatter"  – scatter plot with reference lines
 *   "table"    – tabular data with header row
 *   "gauge"    – semicircular gauge
 *   "kpi"      – compact KPI card row
 */
export function ChartSkeleton({ variant = "bar", height }) {
  const style = height ? { height } : {};
  return (
    <div className="w-full animate-in fade-in-0 duration-300" style={style}>
      {variant === "bar"     && <BarChartSkeleton />}
      {variant === "bar-h"   && <BarChartSkeleton horizontal />}
      {variant === "line"    && <LineChartSkeleton />}
      {variant === "area"    && <AreaChartSkeleton />}
      {variant === "pie"     && <PieChartSkeleton />}
      {variant === "scatter" && <ScatterChartSkeleton />}
      {variant === "table"   && <TableSkeleton />}
      {variant === "gauge"   && <GaugeSkeleton />}
    </div>
  );
}

/**
 * KPICardSkeleton — matches the exact layout of KPICard.
 */
export function KPICardSkeleton() {
  return (
    <div className="relative bg-gradient-to-br from-card via-card/95 to-card/80 border border-border/50 rounded-lg md:rounded-xl p-3 md:p-4 lg:p-5 flex flex-col gap-2.5 overflow-hidden">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1 space-y-2">
          <Skeleton className="h-2.5 w-24 rounded" />
          <Skeleton className="h-7 w-32 rounded" />
          <Skeleton className="h-2 w-20 rounded" />
          <Skeleton className="h-5 w-28 rounded-md" />
        </div>
        <Skeleton className="w-10 h-10 md:w-12 md:h-12 rounded-xl flex-shrink-0" />
      </div>
    </div>
  );
}

/**
 * useSimulatedLoading — returns `true` for a simulated delay, then flips to `false`.
 * Simulates async data fetching so skeletons appear naturally on page mount.
 *
 * @param {number} delay  ms before resolving (default: random 600–1100ms)
 */
export function useSimulatedLoading(delay) {
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const ms = delay ?? 800;
    const t = setTimeout(() => setLoading(false), ms);
    return () => clearTimeout(t);
  }, [delay]);
  return loading;
}

/**
 * ChartCard — wraps chart content with a consistent card shell.
 *
 * Props:
 *   title       {string}  Card heading
 *   subtitle    {string}  Optional sub-heading
 *   loading     {boolean} When true, renders skeleton instead of children
 *   skeleton    {string}  Variant passed to ChartSkeleton ("bar" | "line" | "area" | "pie" | …)
 *   minHeight   {number}  Minimum height in px applied to the skeleton wrapper
 *   className   {string}  Extra classes on the root element
 */
export function ChartCard({
  title,
  subtitle,
  children,
  loading = false,
  skeleton = "bar",
  minHeight,
  className = "",
}) {
  return (
    <div
      className={`
        group relative bg-gradient-to-br from-card via-card/98 to-card/95 border border-border/60 rounded-xl md:rounded-2xl p-4 md:p-5 lg:p-6
        hover:border-primary/50 hover:shadow-lg hover:shadow-primary/25
        transition-all duration-500 ease-out transform hover:scale-[1.02] hover:-translate-y-1
        overflow-hidden backdrop-blur-sm before:absolute before:inset-0 before:bg-gradient-to-br before:from-primary/5 before:to-transparent before:opacity-0 hover:before:opacity-100 before:transition-opacity before:duration-500
        ${className}
      `.trim()}
    >
      {/* Header */}
      <div className="mb-4 md:mb-5 relative z-10 flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          {loading ? (
            <div className="space-y-2">
              <Skeleton className="h-4 w-48 rounded" />
              {subtitle !== undefined && <Skeleton className="h-3 w-32 rounded" />}
            </div>
          ) : (
            <>
              <h3 className="text-[14px] md:text-[16px] font-bold text-foreground leading-tight group-hover:text-primary transition-colors duration-300">
                {title}
              </h3>
              {subtitle && (
                <p className="text-[12px] text-muted-foreground mt-1.5 group-hover:text-foreground/80 transition-colors duration-300">
                  {subtitle}
                </p>
              )}
            </>
          )}
        </div>
        <div className="w-8 h-8 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-all duration-300 group-hover:scale-110 flex-shrink-0">
          <div className="w-2 h-2 rounded-full bg-primary animate-pulse" />
        </div>
      </div>

      {/* Content */}
      <div className="relative z-10" style={minHeight && loading ? { minHeight } : {}}>
        {loading ? (
          <ChartSkeleton variant={skeleton} height={minHeight} />
        ) : (
          <div className="animate-in fade-in-0 duration-500">
            {children}
          </div>
        )}
      </div>

      {/* Keyframe styles injected once */}
      <style>{`
        @keyframes skelPulse {
          0%, 100% { opacity: 0.4; }
          50%       { opacity: 1; }
        }
        @keyframes skeletonLine {
          from { stroke-dashoffset: 300; }
          to   { stroke-dashoffset: 0; }
        }
      `}</style>
    </div>
  );
}

/**
 * useChartHeight — returns a chart height appropriate for the screen size.
 */
export function useChartHeight(desktop = 280, mobile = 200) {
  const isMobile = useIsMobile();
  return isMobile ? mobile : desktop;
}
