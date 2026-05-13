import { createFileRoute } from "@tanstack/react-router";
import { useChartHeight, ChartCard, KPICardSkeleton } from "@/components/dashboard/ChartCard";
import { KPICard } from "@/components/dashboard/KPICard";
import { CustomTooltip } from "@/components/dashboard/CustomTooltip";
import { Boxes, AlertTriangle, Clock, Bell } from "lucide-react";
import {
  ScatterChart,
  Scatter,
  Treemap,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ZAxis,
  ReferenceLine,
} from "recharts";
import { FAMILLES, CHART_COLORS, formatTND } from "@/lib/dashboardConstants";
import { useFilters } from "@/store/useFilters";
import { useMemo } from "react";
import { api } from "@/lib/api";
import { useApiResource } from "@/hooks/useApiResource";

export const Route = createFileRoute("/produits")({
  component: ProduitsPage,
});

function rotationColor(r) {
  if (r < 0.33) return "#ef4444";
  if (r < 0.66) return "#f97316";
  return "#22c55e";
}

function priorityBadge(p) {
  const map = {
    CRITIQUE: "bg-red-500/20 text-red-400 border border-red-500/30",
    URGENT: "bg-orange-500/20 text-orange-400 border border-orange-500/30",
    ATTENTION: "bg-yellow-500/20 text-yellow-400 border border-yellow-500/30",
  };
  return map[p] || "";
}

function GaugeChart({ value, target, label }) {
  const pct = Math.min(value / 100, 1);
  const r = 70,
    cx = 100,
    cy = 90;
  const startA = Math.PI,
    endA = 0;
  const valA = startA + (endA - startA) * pct;
  const arcX = (a, rr) => cx + rr * Math.cos(a);
  const arcY = (a, rr) => cy + rr * Math.sin(a);
  const bgPath = `M ${arcX(startA, r)} ${arcY(startA, r)} A ${r} ${r} 0 0 1 ${arcX(endA, r)} ${arcY(endA, r)}`;
  const valPath = `M ${arcX(startA, r)} ${arcY(startA, r)} A ${r} ${r} 0 ${pct > 0.5 ? 1 : 0} 1 ${arcX(valA, r)} ${arcY(valA, r)}`;
  const color = value < target ? "#22c55e" : value < target * 1.5 ? "#f97316" : "#ef4444";
  return (
    <div className="flex flex-col items-center">
      <svg width={200} height={110}>
        <path d={bgPath} fill="none" stroke="#2a2a2a" strokeWidth={14} strokeLinecap="round" />
        <path d={valPath} fill="none" stroke={color} strokeWidth={14} strokeLinecap="round" />
        <line
          x1={cx}
          y1={cy}
          x2={arcX(valA, r - 18)}
          y2={arcY(valA, r - 18)}
          stroke={color}
          strokeWidth={2}
          strokeLinecap="round"
        />
        <circle cx={cx} cy={cy} r={4} fill={color} />
        <text x={cx} y={cy - 18} textAnchor="middle" fill={color} fontSize={22} fontWeight="bold">
          {value}%
        </text>
        <text x={cx} y={cy - 4} textAnchor="middle" fill="#666" fontSize={10}>
          objectif &lt; {target}%
        </text>
        <text x={cx} y={105} textAnchor="middle" fill="#888" fontSize={11}>
          {label}
        </text>
      </svg>
    </div>
  );
}

function ProduitsPage() {
  const { famille, statutArticle, horizonPrev, depot, getActiveMonthIndexes } = useFilters();
  const { data: articles, loading: articlesLoading } = useApiResource(api.produits.articles, []);
  const { data: stockAlerts, loading: alertsLoading } = useApiResource(api.produits.alerts, []);
  const activeIdx = getActiveMonthIndexes();
  const chartH = useChartHeight();
  const kpiLoading = articlesLoading || alertsLoading;
  const chartsLoading = articlesLoading || alertsLoading;

  const filteredArticles = useMemo(() => {
    return articles.filter((a) => {
      if (famille !== "Toutes" && a.famille !== famille) return false;
      if (statutArticle === "En sommeil" && a.qteVendue > 100) return false;
      if (statutArticle === "Actifs uniquement" && a.qteVendue === 0) return false;
      return true;
    });
  }, [famille, statutArticle]);

  const treemapData = useMemo(() => {
    const totals = new Map();
    for (const article of filteredArticles) {
      const key = article.famille || "Sans famille";
      const current = totals.get(key) || { size: 0, qteVendue: 0, stock: 0 };
      current.size += Math.round((article.stock || 0) * (article.prixMoyen || 0));
      current.qteVendue += article.qteVendue || 0;
      current.stock += article.stock || 0;
      totals.set(key, current);
    }

    const rows = Array.from(totals.entries()).map(([name, values], i) => ({
      name,
      size: values.size,
      rotation: values.stock > 0 ? Math.min(1, values.qteVendue / values.stock) : 0,
      fill: CHART_COLORS[i % CHART_COLORS.length],
    }));

    if (famille !== "Toutes") return rows.filter((row) => row.name === famille);
    return rows.length
      ? rows
      : FAMILLES.map((name, i) => ({
          name,
          size: 0,
          rotation: 0,
          fill: CHART_COLORS[i % CHART_COLORS.length],
        }));
  }, [famille, filteredArticles]);

  const alertes = useMemo(() => {
    return stockAlerts
      .filter((a) => famille === "Toutes" || a.famille === famille)
      .sort((a, b) => {
        const order = { CRITIQUE: 0, URGENT: 1, ATTENTION: 2 };
        return order[a.priorite] - order[b.priorite];
      });
  }, [famille, stockAlerts]);

  const dsiScatter = useMemo(() => {
    return filteredArticles.slice(0, 40).map((a) => ({
      dsi: Math.round(a.dsi || 0),
      ca: a.ca,
      stockVal: Math.round((a.stock || 0) * (a.prixMoyen || 0)),
      name: a.designation,
    }));
  }, [filteredArticles]);

  const valeurStock = filteredArticles.reduce((s, a) => s + (a.stock || 0) * (a.prixMoyen || 0), 0);
  const nbRuptures = alertes.filter((a) => a.stockActuel < a.seuil).length;
  const dsiMoyen = Math.round(
    dsiScatter.reduce((s, d) => s + d.dsi, 0) / Math.max(dsiScatter.length, 1),
  );
  const nbAlertes = alertes.filter(
    (a) => a.priorite === "CRITIQUE" || a.priorite === "URGENT",
  ).length;
  const txRupture = parseFloat(
    ((nbRuptures / Math.max(filteredArticles.length, 1)) * 100).toFixed(1),
  );

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {kpiLoading ? (
          <>
            <KPICardSkeleton />
            <KPICardSkeleton />
            <KPICardSkeleton />
            <KPICardSkeleton />
          </>
        ) : (
          <>
            <KPICard
              label="Valeur stock"
              value={`${(valeurStock / 1000000).toFixed(1)} MDT`}
              subtitle={famille !== "Toutes" ? famille : "Tous dépôts"}
              icon={Boxes}
            />
            <KPICard
              label="Articles en rupture"
              value={String(nbRuptures)}
              subtitle={`sur ${filteredArticles.length} actifs (${txRupture}%)`}
              trend={-1.1}
              icon={AlertTriangle}
            />
            <KPICard
              label="DSI moyen (rotation)"
              value={`${dsiMoyen}j`}
              subtitle="Days Sales of Inventory"
              icon={Clock}
            />
            <KPICard
              label="Alertes restock actives"
              value={String(nbAlertes)}
              subtitle={`à commander sous ${horizonPrev}`}
              icon={Bell}
            />
          </>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <ChartCard
          loading={chartsLoading}
          skeleton="bar"
          key={`${famille}-${statutArticle}-${horizonPrev}`}
          title={`Valeur stock par famille${famille !== "Toutes" ? ` — ${famille}` : ""} (KPI-11)`}
        >
          <ResponsiveContainer width="100%" height={chartH}>
            <Treemap
              data={treemapData}
              dataKey="size"
              nameKey="name"
              stroke="#1a1a1a"
              content={({ x, y, width, height, name, rotation }) => (
                <g>
                  <rect
                    x={x}
                    y={y}
                    width={width}
                    height={height}
                    fill={rotationColor(rotation ?? 0.5)}
                    stroke="#111"
                    strokeWidth={2}
                    rx={3}
                    opacity={0.85}
                  />
                  {width > 40 && height > 20 && (
                    <text
                      x={x + width / 2}
                      y={y + height / 2}
                      textAnchor="middle"
                      fill="#fff"
                      fontSize={10}
                      dominantBaseline="middle"
                    >
                      {name}
                    </text>
                  )}
                </g>
              )}
            />
          </ResponsiveContainer>
          <div className="flex gap-4 text-[10px] text-text-dim mt-1 justify-end">
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-red-500 inline-block" /> Rotation lente
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-orange-500 inline-block" /> Moyenne
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-green-500 inline-block" /> Rapide
            </span>
          </div>
        </ChartCard>

        <ChartCard
          loading={chartsLoading}
          skeleton="table"
          title={`Alertes réapprovisionnement — horizon ${horizonPrev} (KPI-12)`}
        >
          <div className="overflow-auto max-h-[280px]">
            <table className="w-full text-[11px]">
              <thead className="sticky top-0 bg-background">
                <tr className="text-text-dim border-b border-border">
                  <th className="text-left py-1 px-2">Article</th>
                  <th className="text-right py-1 px-2">Stock</th>
                  <th className="text-right py-1 px-2">Seuil</th>
                  <th className="text-center py-1 px-2">Rupture</th>
                  <th className="text-center py-1 px-2">Priorité</th>
                </tr>
              </thead>
              <tbody>
                {alertes.map((row, i) => (
                  <tr key={i} className="border-b border-border/30 hover:bg-surface-hover/30">
                    <td className="py-1.5 px-2">
                      <div className="font-medium text-foreground">{row.article}</div>
                      <div className="text-text-dim text-[10px]">{row.fournisseur}</div>
                    </td>
                    <td
                      className={`py-1.5 px-2 text-right font-semibold ${row.stockActuel < row.seuil ? "text-red-400" : "text-foreground"}`}
                    >
                      {row.stockActuel}
                    </td>
                    <td className="py-1.5 px-2 text-right text-text-dim">{row.seuil}</td>
                    <td className="py-1.5 px-2 text-center text-text-dim text-[10px]">
                      {row.dateRupture}
                    </td>
                    <td className="py-1.5 px-2 text-center">
                      <span
                        className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${priorityBadge(row.priorite)}`}
                      >
                        {row.priorite}
                      </span>
                    </td>
                  </tr>
                ))}
                {alertes.length === 0 && (
                  <tr>
                    <td colSpan={5} className="py-8 text-center text-text-dim text-[12px]">
                      Aucune alerte pour cette famille
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </ChartCard>

        <ChartCard
          loading={chartsLoading}
          skeleton="gauge"
          title="Taux de rupture & tension stock (KPI-14)"
        >
          <div className="flex items-start gap-4 h-[280px]">
            <div className="flex flex-col items-center justify-center flex-shrink-0 pt-4">
              <GaugeChart value={txRupture} target={3} label="Taux rupture" />
            </div>
            <div className="flex-1 overflow-auto">
              <p className="text-[10px] text-text-dim font-semibold uppercase tracking-wider mb-2 mt-2">
                Top articles en tension (réservé/dispo &gt; 80%)
              </p>
              {alertes.slice(0, 10).map((a, i) => {
                const ratio = Math.round((a.ratioTension || 0) * 100);
                return (
                  <div key={i} className="flex items-center gap-2 mb-1.5">
                    <span className="text-[10px] text-text-dim w-16 flex-shrink-0">
                      {a.article}
                    </span>
                    <div className="flex-1 h-2 bg-surface-hover rounded-full overflow-hidden">
                      <div
                        className="h-full rounded-full"
                        style={{
                          width: `${ratio}%`,
                          background: ratio > 90 ? "#ef4444" : ratio > 80 ? "#f97316" : "#22c55e",
                        }}
                      />
                    </div>
                    <span
                      className={`text-[10px] font-medium w-8 text-right ${ratio > 90 ? "text-red-400" : ratio > 80 ? "text-orange-400" : "text-green-400"}`}
                    >
                      {ratio}%
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </ChartCard>

        <ChartCard
          loading={chartsLoading}
          skeleton="scatter"
          title="Rotation stocks — DSI vs CA par article (KPI-13)
        "
        >
          <ResponsiveContainer width="100%" height={chartH}>
            <ScatterChart margin={{ top: 10, right: 10, bottom: 20, left: 10 }}>
              <CartesianGrid stroke="#2a2a2a" strokeDasharray="3 3" />
              <XAxis
                dataKey="dsi"
                name="DSI (j)"
                tick={{ fill: "#666", fontSize: 11 }}
                axisLine={false}
                label={{
                  value: "DSI (jours)",
                  position: "insideBottom",
                  offset: -10,
                  fill: "#555",
                  fontSize: 11,
                }}
              />
              <YAxis
                dataKey="ca"
                name="CA"
                tick={{ fill: "#666", fontSize: 11 }}
                axisLine={false}
                tickFormatter={(v) => `${(v / 1000).toFixed(0)}K`}
              />
              <ZAxis dataKey="stockVal" range={[40, 400]} name="Valeur stock" />
              <Tooltip content={<CustomTooltip />} />
              <ReferenceLine
                x={dsiMoyen}
                stroke="#444"
                strokeDasharray="4 4"
                label={{ value: "DSI moy.", fill: "#555", fontSize: 10, position: "top" }}
              />
              <Scatter
                data={dsiScatter}
                fill="#3b82f6"
                opacity={0.7}
                shape={(props) => {
                  const { cx, cy, payload } = props;
                  const avgCa =
                    filteredArticles.reduce((s, a) => s + a.ca, 0) /
                    Math.max(filteredArticles.length, 1);
                  const isStar = payload.dsi < dsiMoyen && payload.ca > avgCa;
                  const isSlow = payload.dsi >= dsiMoyen && payload.ca <= avgCa;
                  return (
                    <circle
                      cx={cx}
                      cy={cy}
                      r={6}
                      fill={isStar ? "#22c55e" : isSlow ? "#ef4444" : "#3b82f6"}
                      opacity={0.75}
                    />
                  );
                }}
              />
            </ScatterChart>
          </ResponsiveContainer>
          <div className="flex gap-4 text-[10px] text-text-dim mt-1 justify-end">
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-green-500 inline-block" /> Star / Fast
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-blue-500 inline-block" /> Normal
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-red-500 inline-block" /> Sleeping / Slow
            </span>
          </div>
        </ChartCard>
      </div>
    </div>
  );
}
