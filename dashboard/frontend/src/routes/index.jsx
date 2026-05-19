import { createFileRoute } from "@tanstack/react-router";
import {
  useChartHeight,
  ChartCard,
  KPICardSkeleton,
} from "@/components/dashboard/ChartCard";
import { KPICard } from "@/components/dashboard/KPICard";
import { CustomTooltip } from "@/components/dashboard/CustomTooltip";
import { DollarSign, TrendingUp, Boxes } from "lucide-react";
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ZAxis,
  ReferenceLine,
} from "recharts";
import { CHART_COLORS, formatTND } from "@/lib/dashboardConstants";
import { useMemo } from "react";
import { api } from "@/lib/api";
import { useApiResource } from "@/hooks/useApiResource";
import { useFilters } from "@/store/useFilters";

export const Route = createFileRoute("/")({
  component: OverviewPage,
});

function rotationColor(dsi) {
  if (dsi > 90) return "#ef4444";
  if (dsi > 30) return "#f97316";
  return "#22c55e";
}

function OverviewPage() {
  const { year, quarter, segment, depot, source } = useFilters();

  const kpisFn = useMemo(() => () => api.dashboard.kpis(year), [year, quarter, segment, depot, source]);
  const caByMonthFn = useMemo(() => () => api.dashboard.caByMonth(year), [year, quarter, segment, depot, source]);
  const topFamillesFn = useMemo(() => () => api.dashboard.topFamilles(year), [year, quarter, segment, depot, source]);
  const articlesFn = useMemo(() => () => api.dashboard.articles(year), [year, quarter, segment, depot, source]);

  const { data: kpis, loading: kpisLoading } = useApiResource(kpisFn, {
    ca_total: 0,
    nb_commandes: 0,
    nb_clients_actifs: 0,
    taux_recouvrement: 0,
    marge_brute_pct: null,
    ca_avec_cout: 0,
    marge_brute_growth_pct: null,
    ca_growth_pct: 0,
  });
  const { data: caByMonth, loading: caLoading } = useApiResource(caByMonthFn, []);
  const { data: topFamilles, loading: famillesLoading } = useApiResource(topFamillesFn, []);
  const { data: articles, loading: articlesLoading } = useApiResource(articlesFn, []);

  const chartH = useChartHeight();
  const kpiLoading = kpisLoading;
  const chartsLoading = caLoading || famillesLoading || articlesLoading;

  // Stock KPIs
  const valeurStock = useMemo(
    () => articles.reduce((s, a) => s + (a.stock || 0) * (a.prixMoyen || 0), 0),
    [articles]
  );

  const dsiScatter = useMemo(
    () =>
      articles.slice(0, 40).map((a) => ({
        dsi: Math.round(a.dsi || 0),
        ca: a.ca,
        stockVal: Math.round((a.stock || 0) * (a.prixMoyen || 0)),
        name: a.designation,
      })),
    [articles]
  );

  const dsiMoyen = Math.round(
    dsiScatter.reduce((s, d) => s + d.dsi, 0) / Math.max(dsiScatter.length, 1)
  );

  const topFamillesClean = useMemo(
    () =>
      topFamilles.slice(0, 5).map((f) => ({
        ...f,
        name: (f.name || "").length > 18 ? (f.name || "").substring(0, 18) + "…" : f.name,
      })),
    [topFamilles]
  );

  return (
    <div className="space-y-6">
      {/* ── KPIs ── */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {kpiLoading ? (
          <>
            <KPICardSkeleton />
            <KPICardSkeleton />
            <KPICardSkeleton />
          </>
        ) : (
          <>
            {/* KPI 1 : CA Total */}
            <KPICard
              label="CA Total"
              value={
                kpis.ca_total >= 1_000_000
                  ? `${(kpis.ca_total / 1_000_000).toFixed(1)} MDT`
                  : `${(kpis.ca_total / 1_000).toFixed(0)} KDT`
              }
              trend={kpis.ca_growth_pct ?? 0}
              sparkline={caByMonth.map((m) => m.ca)}
              icon={DollarSign}
              subtitle="Chiffre d'affaires HT"
            />
            {/* KPI 2 : Marge Brute */}
            <KPICard
              label="Marge Brute"
              value={
                kpis.marge_brute_pct === null
                  ? "N/A"
                  : `${kpis.marge_brute_pct.toFixed(1)}%`
              }
              subtitle={
                kpis.marge_brute_pct === null
                  ? "Coûts d'achat non saisis"
                  : `${((kpis.ca_avec_cout || 0) / 1_000_000).toFixed(1)} MDT couverts`
              }
              trend={kpis.marge_brute_pct !== null ? (kpis.marge_brute_growth_pct ?? 0) : undefined}
              icon={TrendingUp}
            />
            {/* KPI 3 : Valeur Stock */}
            <KPICard
              label="Valeur Stock"
              value={`${(valeurStock / 1_000_000).toFixed(1)} MDT`}
              subtitle={`DSI moyen : ${dsiMoyen}j`}
              icon={Boxes}
            />
          </>
        )}
      </div>

      {/* ── Section label ── */}
      <div className="flex items-center gap-3">
        <span className="text-[11px] font-bold uppercase tracking-widest text-text-dim">
          Ventes & CA
        </span>
        <div className="flex-1 h-px bg-border/30" />
      </div>

      {/* ── Graphiques Ventes ── */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <ChartCard
          loading={chartsLoading}
          skeleton="line"
          key={`ca-month-${year}`}
          title="Évolution mensuelle du CA : Réel vs Objectif vs N-1"
        >
          <ResponsiveContainer width="100%" height={chartH}>
            <AreaChart data={caByMonth}>
              <CartesianGrid stroke="#2a2a2a" strokeDasharray="3 3" />
              <XAxis dataKey="month" interval={0} tick={{ fill: "#666", fontSize: 10 }} axisLine={false} />
              <YAxis
                tick={{ fill: "#666", fontSize: 10 }}
                axisLine={false}
                tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`}
              />
              <Tooltip content={<CustomTooltip />} />
              <Legend wrapperStyle={{ fontSize: 11, color: "#888" }} />
              <Area
                type="monotone"
                dataKey="ca"
                stroke="#3b82f6"
                fill="#3b82f6"
                fillOpacity={0.12}
                strokeWidth={2}
                name="CA Réel"
              />
              <Area
                type="monotone"
                dataKey="caN1"
                stroke="#94a3b8"
                fill="none"
                strokeWidth={1.5}
                strokeDasharray="4 4"
                name="CA N-1"
              />
              <Area
                type="monotone"
                dataKey="objectif"
                stroke="#6366f1"
                fill="none"
                strokeDasharray="5 5"
                name="Objectif"
              />
            </AreaChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          loading={chartsLoading}
          skeleton="bar"
          key={`top-familles-${year}`}
          title="Top 5 familles par CA"
        >
          <ResponsiveContainer width="100%" height={chartH}>
            <BarChart data={topFamillesClean} layout="vertical">
              <CartesianGrid stroke="#2a2a2a" strokeDasharray="3 3" horizontal={false} />
              <XAxis
                type="number"
                tick={{ fill: "#666", fontSize: 11 }}
                axisLine={false}
                tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`}
              />
              <YAxis
                type="category"
                dataKey="name"
                tick={{ fill: "#666", fontSize: 11 }}
                axisLine={false}
                width={160}
              />
              <Tooltip content={<CustomTooltip />} />
              <Bar dataKey="ca" fill="#3b82f6" radius={[0, 4, 4, 0]} name="CA" />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {/* ── Section label ── */}
      <div className="flex items-center gap-3">
        <span className="text-[11px] font-bold uppercase tracking-widest text-text-dim">
          Stock & Produits
        </span>
        <div className="flex-1 h-px bg-border/30" />
      </div>

      {/* ── Graphique Stock ── */}
      <div className="grid grid-cols-1 gap-4">
        <ChartCard
          loading={chartsLoading}
          skeleton="scatter"
          key={`rotation-${year}`}
          title="Rotation Stocks — DSI vs CA par article"
        >
          <ResponsiveContainer width="100%" height={chartH}>
            <ScatterChart margin={{ top: 10, right: 10, bottom: 20, left: 10 }}>
              <CartesianGrid stroke="#2a2a2a" strokeDasharray="3 3" />
              <XAxis
                dataKey="dsi"
                name="DSI (j)"
                tick={{ fill: "#666", fontSize: 10 }}
                axisLine={false}
                label={{ value: "DSI (jours)", position: "insideBottom", offset: -10, fill: "#555", fontSize: 10 }}
              />
              <YAxis
                dataKey="ca"
                name="CA"
                tick={{ fill: "#666", fontSize: 10 }}
                axisLine={false}
                tickFormatter={(v) => `${(v / 1000).toFixed(0)}K`}
              />
              <ZAxis dataKey="stockVal" range={[40, 400]} name="Valeur stock" />
              <Tooltip content={<CustomTooltip />} />
              <ReferenceLine
                x={dsiMoyen}
                stroke="#444"
                strokeDasharray="4 4"
                label={{ value: "DSI moy.", fill: "#555", fontSize: 9, position: "top" }}
              />
              <Scatter
                data={dsiScatter}
                fill="#3b82f6"
                opacity={0.7}
                shape={(props) => {
                  const { cx, cy, payload } = props;
                  const avgCa = articles.reduce((s, a) => s + a.ca, 0) / Math.max(articles.length, 1);
                  const isStar = payload.dsi < dsiMoyen && payload.ca > avgCa;
                  const isSlow = payload.dsi >= dsiMoyen && payload.ca <= avgCa;
                  return (
                    <circle
                      cx={cx}
                      cy={cy}
                      r={5}
                      fill={isStar ? "#10b981" : isSlow ? "#ef4444" : "#3b82f6"}
                      opacity={0.75}
                    />
                  );
                }}
              />
            </ScatterChart>
          </ResponsiveContainer>
          <div className="flex gap-4 text-[9.5px] text-text-dim mt-1 justify-end">
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
