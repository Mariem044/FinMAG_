import { createFileRoute } from "@tanstack/react-router";
import { useChartHeight, ChartCard, useSimulatedLoading, KPICardSkeleton } from "@/components/dashboard/ChartCard";
import { KPICard } from "@/components/dashboard/KPICard";
import { CustomTooltip } from "@/components/dashboard/CustomTooltip";
import { DollarSign, ShoppingCart, TrendingUp, Percent } from "lucide-react";
import {
  LineChart, Line, BarChart, Bar, AreaChart, Area,
  XAxis, YAxis, CartesianGrid, Tooltip,
  Legend, ResponsiveContainer, Cell,
} from "recharts";
import {
  caByMonth, topFamilles, caByRegion, CHART_COLORS, formatTND, MONTHS,
} from "@/data/mockData";
import { useFilters } from "@/store/useFilters";
import { useMemo } from "react";

export const Route = createFileRoute("/ventes")({
  component: VentesPage,
});

// Stable seed data — generated once at module load to avoid re-randomising on every render
const MONTHLY_DATA = MONTHS.map((m) => ({
  month: m,
  ca:        Math.round(800000 + Math.random() * 600000),
  objectif:  Math.round(900000 + Math.random() * 300000),
  caN1:      Math.round(700000 + Math.random() * 500000),
}));

const FAMILLE_DATA = ["Biscuits", "Boissons", "Conserves", "Produits Laitiers", "Confiserie", "Épicerie", "Huiles", "Pâtes"].map((f) => ({
  name: f,
  ca:   Math.round(400000 + Math.random() * 1500000),
})).sort((a, b) => b.ca - a.ca);

const REGION_DATA = ["Tunis", "Sfax", "Sousse", "Nabeul", "Bizerte", "Gabès", "Kairouan", "Monastir"].map((r) => ({
  name:      r,
  ca:        Math.round(300000 + Math.random() * 1400000),
  commandes: Math.round(100 + Math.random() * 500),
}));

function VentesPage() {
  const { segment, depot, source, getActiveMonthIndexes } = useFilters();
  const activeIdx = getActiveMonthIndexes();
  const chartH = useChartHeight();
  const kpiLoading = useSimulatedLoading(500);
  const chartsLoading = useSimulatedLoading(900);
  const sourceRatio = source === "MAG_2020" ? 0.68 : source === "GRT_MAG" ? 0.32 : 1;

  // Filter monthly data by active quarter/months
  const filteredMonthly = useMemo(
    () => MONTHLY_DATA
      .filter((_, i) => activeIdx.includes(i))
      .map((m) => ({
        ...m,
        ca: Math.round(m.ca * sourceRatio),
        objectif: Math.round(m.objectif * sourceRatio),
        caN1: Math.round(m.caN1 * sourceRatio),
      })),
    [activeIdx, sourceRatio],
  );

  // Filter region data by depot
  const filteredRegions = useMemo(() => {
    const rows = depot === "Tous"
      ? REGION_DATA
      : REGION_DATA.filter((r) => r.name === depot.replace("Dépôt ", ""));
    return rows.map((r) => ({ ...r, ca: Math.round(r.ca * sourceRatio) }));
  }, [depot, sourceRatio]);

  const totalCA = filteredMonthly.reduce((s, m) => s + m.ca, 0);
  const totalObjectif = filteredMonthly.reduce((s, m) => s + m.objectif, 0);
  const tauxObjectif = totalObjectif > 0 ? ((totalCA / totalObjectif) * 100).toFixed(1) : "—";
  const totalCommandes = filteredRegions.reduce((s, r) => s + r.commandes, 0);

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
              label="CA Total"
              value={formatTND(totalCA)}
              trend={8.2}
              subtitle={source}
              icon={DollarSign}
            />
            <KPICard
              label="Nombre de Commandes"
              value={totalCommandes.toLocaleString("fr-TN")}
              trend={5.1}
              subtitle={depot !== "Tous" ? depot : "Tous dépôts"}
              icon={ShoppingCart}
            />
            <KPICard
              label="Taux vs Objectif"
              value={`${tauxObjectif}%`}
              trend={parseFloat(tauxObjectif) >= 100 ? 2.1 : -1.4}
              subtitle="CA réalisé / objectif"
              icon={Percent}
            />
            <KPICard
              label="Croissance vs N-1"
              value="+8.2%"
              trend={8.2}
              subtitle="Comparaison annuelle"
              icon={TrendingUp}
            />
          </>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* CA Evolution */}
        <ChartCard loading={chartsLoading} skeleton="line" key={`${segment}-${depot}-${source}-${activeIdx.join("")}`} title="Évolution mensuelle du CA vs Objectif (KPI-01)">
          <ResponsiveContainer width="100%" height={chartH}>
            <AreaChart data={filteredMonthly}>
              <CartesianGrid stroke="#2a2a2a" strokeDasharray="3 3" />
              <XAxis dataKey="month" tick={{ fill: "#666", fontSize: 11 }} axisLine={false} />
              <YAxis
                tick={{ fill: "#666", fontSize: 11 }}
                axisLine={false}
                tickFormatter={(v) => `${(v / 1000).toFixed(0)}K`}
              />
              <Tooltip content={<CustomTooltip />} />
              <Legend wrapperStyle={{ fontSize: 12, color: "#888" }} />
              <Area
                type="monotone"
                dataKey="ca"
                stroke="#3b82f6"
                fill="#3b82f6"
                fillOpacity={0.15}
                name="CA Réalisé"
              />
              <Area
                type="monotone"
                dataKey="objectif"
                stroke="#6366f1"
                fill="none"
                strokeDasharray="5 5"
                name="Objectif"
              />
              <Line
                type="monotone"
                dataKey="caN1"
                stroke="#f97316"
                strokeWidth={1.5}
                strokeDasharray="3 3"
                dot={false}
                name="CA N-1"
              />
            </AreaChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* Top Familles */}
        <ChartCard loading={chartsLoading} skeleton="bar" title="Top familles de produits par CA (KPI-02)">
          <ResponsiveContainer width="100%" height={chartH}>
            <BarChart data={FAMILLE_DATA.slice(0, 6).map((f) => ({ ...f, ca: Math.round(f.ca * sourceRatio) }))} layout="vertical">
              <CartesianGrid stroke="#2a2a2a" strokeDasharray="3 3" horizontal={false} />
              <XAxis
                type="number"
                tick={{ fill: "#666", fontSize: 11 }}
                axisLine={false}
                tickFormatter={(v) => `${(v / 1000).toFixed(0)}K`}
              />
              <YAxis
                type="category"
                dataKey="name"
                tick={{ fill: "#999", fontSize: 11 }}
                axisLine={false}
                width={100}
              />
              <Tooltip content={<CustomTooltip />} />
              <Bar dataKey="ca" radius={[0, 4, 4, 0]} name="CA (DT)">
                {FAMILLE_DATA.slice(0, 6).map((_, i) => (
                  <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* CA by Region */}
        <ChartCard
          loading={chartsLoading}
          skeleton="bar"
          title={`CA par région${depot !== "Tous" ? ` — ${depot}` : ""} (KPI-03)`}
        >
          <ResponsiveContainer width="100%" height={chartH}>
            <BarChart data={filteredRegions}>
              <CartesianGrid stroke="#2a2a2a" strokeDasharray="3 3" />
              <XAxis dataKey="name" tick={{ fill: "#666", fontSize: 11 }} axisLine={false} />
              <YAxis
                tick={{ fill: "#666", fontSize: 11 }}
                axisLine={false}
                tickFormatter={(v) => `${(v / 1000).toFixed(0)}K`}
              />
              <Tooltip content={<CustomTooltip />} />
              <Bar dataKey="ca" name="CA (DT)" radius={[4, 4, 0, 0]}>
                {filteredRegions.map((_, i) => (
                  <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* Monthly trend */}
        <ChartCard loading={chartsLoading} skeleton="line" title="Tendance mensuelle CA vs N-1 (KPI-04)">
          <ResponsiveContainer width="100%" height={chartH}>
            <LineChart data={filteredMonthly}>
              <CartesianGrid stroke="#2a2a2a" strokeDasharray="3 3" />
              <XAxis dataKey="month" tick={{ fill: "#666", fontSize: 11 }} axisLine={false} />
              <YAxis
                tick={{ fill: "#666", fontSize: 11 }}
                axisLine={false}
                tickFormatter={(v) => `${(v / 1000).toFixed(0)}K`}
              />
              <Tooltip content={<CustomTooltip />} />
              <Legend wrapperStyle={{ fontSize: 12, color: "#888" }} />
              <Line
                type="monotone"
                dataKey="ca"
                stroke="#3b82f6"
                strokeWidth={2}
                dot={{ r: 3 }}
                name="CA 2024"
              />
              <Line
                type="monotone"
                dataKey="caN1"
                stroke="#f97316"
                strokeWidth={2}
                strokeDasharray="4 4"
                dot={false}
                name="CA 2023"
              />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>
    </div>
  );
}
