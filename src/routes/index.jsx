import { createFileRoute } from "@tanstack/react-router";
import {
  useChartHeight,
  ChartCard,
  useSimulatedLoading,
  KPICardSkeleton,
} from "@/components/dashboard/ChartCard";
import { KPICard } from "@/components/dashboard/KPICard";
import { CustomTooltip } from "@/components/dashboard/CustomTooltip";
import { DollarSign, ShoppingCart, Users, Percent, TrendingUp } from "lucide-react";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import {
  caByMonth,
  topFamilles,
  caByRegion,
  CHART_COLORS,
  formatTND,
  formatPercent,
} from "@/data/mockData";

export const Route = createFileRoute("/")({
  component: OverviewPage,
});

function OverviewPage() {
  const totalCA = caByMonth.reduce((s, m) => s + m.ca, 0);
  const chartH = useChartHeight();
  const kpiLoading = useSimulatedLoading(500);
  const chartsLoading = useSimulatedLoading(900);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
        {kpiLoading ? (
          <>
            <KPICardSkeleton />
            <KPICardSkeleton />
            <KPICardSkeleton />
            <KPICardSkeleton />
            <KPICardSkeleton />
          </>
        ) : (
          <>
            <KPICard
              label="Chiffre d'Affaires Total"
              value={formatTND(totalCA)}
              trend={8.2}
              icon={DollarSign}
            />
            <KPICard
              label="Nombre de Commandes"
              value="2 847"
              trend={5.1}
              icon={ShoppingCart}
            />
            <KPICard label="Clients Actifs" value="312" trend={3.4} icon={Users} />
            <KPICard
              label="Taux de Recouvrement"
              value={formatPercent(78.5)}
              trend={-2.1}
              icon={Percent}
            />
            <KPICard
              label="Marge Brute"
              value={formatPercent(24.3)}
              trend={1.8}
              icon={TrendingUp}
            />
          </>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <ChartCard loading={chartsLoading} skeleton="line" title="Évolution mensuelle du CA">
          <ResponsiveContainer width="100%" height={chartH}>
            <LineChart data={caByMonth}>
              <CartesianGrid stroke="#2a2a2a" strokeDasharray="3 3" />
              <XAxis dataKey="month" tick={{ fill: "#666", fontSize: 11 }} axisLine={false} />
              <YAxis
                tick={{ fill: "#666", fontSize: 11 }}
                axisLine={false}
                tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`}
              />
              <Tooltip content={<CustomTooltip />} />
              <Line
                type="monotone"
                dataKey="ca"
                stroke="#3b82f6"
                strokeWidth={2}
                dot={false}
                name="CA"
              />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard loading={chartsLoading} skeleton="bar" title="Top 5 familles de produits par CA">
          <ResponsiveContainer width="100%" height={chartH}>
            <BarChart data={topFamilles} layout="vertical">
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
                width={100}
              />
              <Tooltip content={<CustomTooltip />} />
              <Bar dataKey="ca" fill="#3b82f6" radius={[0, 4, 4, 0]} name="CA" />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard loading={chartsLoading} skeleton="pie" title="Répartition CA par région">
          <ResponsiveContainer width="100%" height={chartH}>
            <PieChart>
              <Pie
                data={caByRegion}
                dataKey="ca"
                nameKey="name"
                cx="50%"
                cy="50%"
                outerRadius={100}
                label={({ name, percent }) => `${name} ${((percent ?? 0) * 100).toFixed(0)}%`}
                labelLine={false}
                fontSize={11}
              >
                {caByRegion.map((_, i) => (
                  <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip content={<CustomTooltip />} />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard loading={chartsLoading} skeleton="line" title="Ventes vs Objectifs">
          <ResponsiveContainer width="100%" height={chartH}>
            <AreaChart data={caByMonth}>
              <CartesianGrid stroke="#2a2a2a" strokeDasharray="3 3" />
              <XAxis dataKey="month" tick={{ fill: "#666", fontSize: 11 }} axisLine={false} />
              <YAxis
                tick={{ fill: "#666", fontSize: 11 }}
                axisLine={false}
                tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`}
              />
              <Tooltip content={<CustomTooltip />} />
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
              <Legend wrapperStyle={{ fontSize: 12, color: "#888" }} />
            </AreaChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>
    </div>
  );
}
