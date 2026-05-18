import { createFileRoute } from "@tanstack/react-router";
import { useChartHeight, ChartCard, KPICardSkeleton } from "@/components/dashboard/ChartCard";
import { KPICard } from "@/components/dashboard/KPICard";
import { CustomTooltip } from "@/components/dashboard/CustomTooltip";
import { DollarSign, Percent, ShoppingCart, TrendingUp, Brain, Sparkles, Cpu, ShieldCheck } from "lucide-react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { CHART_COLORS, formatTND, MONTHS } from "@/lib/dashboardConstants";
import { useFilters } from "@/store/useFilters";
import { useMemo } from "react";
import { api } from "@/lib/api";
import { useApiResource } from "@/hooks/useApiResource";

export const Route = createFileRoute("/ventes")({
  component: VentesPage,
});

const toNumber = (value) => Number(value) || 0;

function VentesPage() {
  const { year, segment, depot, source, getActiveMonthIndexes } = useFilters();
  const caByMonthFn = useMemo(() => () => api.ventes.caByMonth(year), [year, segment, depot, source]);
  const caByRegionFn = useMemo(() => () => api.ventes.caByRegion(year), [year, segment, depot, source]);
  const topFamillesFn = useMemo(
    () => () => api.ventes.topFamilles(),
    [year, segment, depot, source],
  );
  
  const { data: monthlyData, loading: monthlyLoading } = useApiResource(caByMonthFn, []);
  const { data: familleData, loading: familleLoading } = useApiResource(topFamillesFn, []);
  const { data: regionData, loading: regionLoading } = useApiResource(caByRegionFn, []);

  const activeIdx = getActiveMonthIndexes();
  const activeIdxKey = activeIdx.join("");
  const chartH = useChartHeight();
  const kpiLoading = monthlyLoading || regionLoading;
  const chartsLoading = monthlyLoading || familleLoading || regionLoading;

  const monthlyRows = Array.isArray(monthlyData) ? monthlyData : [];
  const familleRows = Array.isArray(familleData) ? familleData : [];
  const regionRows = Array.isArray(regionData) ? regionData : [];

  const filteredMonthly = useMemo(
    () =>
      monthlyRows
        .filter(Boolean)
        .filter((_, i) => activeIdx.includes(i))
        .map((m) => ({
          ...m,
          month: m.month || "",
          ca: Math.round(toNumber(m.ca)),
          objectif: Math.round(toNumber(m.objectif)),
          caN1: Math.round(toNumber(m.caN1)),
        })),
    [activeIdxKey, monthlyRows],
  );



  const filteredRegions = useMemo(() => {
    const depotName = depot.replace("Depot ", "").replace("Dépôt ", "");
    const rows = depot === "Tous" ? regionRows : regionRows.filter((r) => r?.name === depotName);
    return rows
      .filter(Boolean)
      .map((r) => ({
        ...r,
        name: r.name || "Non renseigne",
        ca: Math.round(toNumber(r.ca)),
        clients: toNumber(r.clients),
        commandes: toNumber(r.commandes),
      }));
  }, [depot, regionRows]);

  const topFamilles = useMemo(
    () =>
      familleRows
        .filter(Boolean)
        .slice(0, 5)
        .map((f) => {
          const raw = f.name || "Sans famille";
          const words = raw.split(" ");
          const name = words.length > 3 ? words.slice(0, 3).join(" ") : raw;
          return {
            ...f,
            name,
            ca: Math.round(toNumber(f.ca)),
          };
        }),
    [familleRows],
  );

  const totalCA = filteredMonthly.reduce((s, m) => s + m.ca, 0);
  const totalObjectif = filteredMonthly.reduce((s, m) => s + m.objectif, 0);
  const totalCAN1 = filteredMonthly.reduce((s, m) => s + m.caN1, 0);
  const tauxObjectif = totalObjectif > 0 ? ((totalCA / totalObjectif) * 100).toFixed(1) : null;
  const croissance = totalCAN1 > totalCA * 0.1
    ? (((totalCA - totalCAN1) / totalCAN1) * 100).toFixed(1)
    : null;
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
              trend={croissance ? parseFloat(croissance) : undefined}
              subtitle="DW reel"
              icon={DollarSign}
            />
            <KPICard
              label="Nombre de Commandes"
              value={totalCommandes.toLocaleString("fr-TN")}
              trend={undefined}
              subtitle={depot !== "Tous" ? depot : "Tous depots"}
              icon={ShoppingCart}
            />
            <KPICard
              label="Taux vs Objectif"
              value={tauxObjectif ? `${tauxObjectif}%` : "-"}
              trend={tauxObjectif ? (parseFloat(tauxObjectif) >= 100 ? 2.1 : -1.4) : undefined}
              subtitle="CA realise / objectif"
              icon={Percent}
            />
            <KPICard
              label="Croissance vs N-1"
              value={croissance !== null ? `${croissance}%` : "N/A"}
              subtitle={croissance !== null ? "Comparaison annuelle" : "Données N-1 insuffisantes"}
              icon={TrendingUp}
            />
          </>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <ChartCard
          loading={chartsLoading}
          skeleton="line"
          key={`${segment}-${depot}-${source}-${activeIdxKey}`}
          title="Évolution du CA : Réel vs Objectif vs N-1"
        >
          <ResponsiveContainer width="100%" height={chartH}>
            <AreaChart data={filteredMonthly}>
              <CartesianGrid stroke="#2a2a2a" strokeDasharray="3 3" />
              <XAxis dataKey="month" interval={0} tick={{ fill: "#666", fontSize: 10 }} axisLine={false} />
              <YAxis
                tick={{ fill: "#666", fontSize: 10 }}
                axisLine={false}
                tickFormatter={(v) => `${(v / 1000).toFixed(0)}K`}
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
              <Line
                type="monotone"
                dataKey="objectif"
                stroke="#6366f1"
                strokeWidth={1.5}
                strokeDasharray="5 5"
                dot={false}
                name="Objectif Sage (110%)"
              />
            </AreaChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard loading={chartsLoading} skeleton="bar" title="Top familles de produits par CA">
          <ResponsiveContainer width="100%" height={chartH}>
            <BarChart data={topFamilles} layout="vertical">
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
                width={160}
              />
              <Tooltip content={<CustomTooltip />} />
              <Bar dataKey="ca" radius={[0, 4, 4, 0]} name="CA (DT)">
                {topFamilles.map((_, i) => (
                  <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          loading={chartsLoading}
          skeleton="bar"
          title={`CA par region${depot !== "Tous" ? ` - ${depot}` : ""}`}
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


      </div>
    </div>
  );
}

