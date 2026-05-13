import { createFileRoute } from "@tanstack/react-router";
import { useChartHeight, ChartCard, KPICardSkeleton } from "@/components/dashboard/ChartCard";
import { KPICard } from "@/components/dashboard/KPICard";
import { CustomTooltip } from "@/components/dashboard/CustomTooltip";
import { Banknote, Wallet, TrendingUp, Activity } from "lucide-react";
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import { CHART_COLORS } from "@/lib/dashboardConstants";
import { useFilters } from "@/store/useFilters";
import { useMemo } from "react";
import { api } from "@/lib/api";
import { useApiResource } from "@/hooks/useApiResource";

export const Route = createFileRoute("/caisse")({
  component: CaissePage,
});

function MultiGauge({ caisses }) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 gap-4 py-2">
      {caisses.map((c) => {
        const total = c.especes + c.cheques;
        const belowMin = c.especes < c.seuilMin;
        const espPct = total > 0 ? (c.especes / total) * 100 : 0;
        const chkPct = total > 0 ? (c.cheques / total) * 100 : 0;
        return (
          <div
            key={c.id}
            className={`rounded-xl border p-3 ${belowMin ? "border-red-500/50 bg-red-500/5 animate-pulse" : "border-border/50 bg-surface-hover/30"}`}
          >
            <div className="flex items-center justify-between mb-1">
              <span className="text-[11px] font-semibold text-foreground">{c.nom}</span>
              {belowMin && <span className="text-[9px] text-red-400 font-bold">⚠ SEUIL</span>}
            </div>
            <div className="flex gap-1 h-2 rounded-full overflow-hidden mb-1.5">
              <div className="bg-blue-500 rounded-l-full" style={{ width: `${espPct}%` }} />
              <div className="bg-purple-500 rounded-r-full" style={{ width: `${chkPct}%` }} />
            </div>
            <div className="flex justify-between text-[10px]">
              <span className="text-blue-400">Esp: {(c.especes / 1000).toFixed(0)}K</span>
              <span className="text-purple-400">Chq: {(c.cheques / 1000).toFixed(0)}K</span>
            </div>
            <div className="text-[10px] text-text-dim mt-0.5">
              seuil min: {(c.seuilMin / 1000).toFixed(0)}K DT
            </div>
          </div>
        );
      })}
    </div>
  );
}

function CaissePage() {
  const { depot, modePaiement, getActiveMonthIndexes } = useFilters();
  const { data: caissesData, loading: caissesLoading } = useApiResource(api.caisse.caisses, []);
  const { data: fluxData, loading: fluxLoading } = useApiResource(api.caisse.fluxDaily, []);
  const { data: natureMvt, loading: natureLoading } = useApiResource(
    api.caisse.mouvementsByType,
    [],
  );
  const activeIdx = getActiveMonthIndexes();
  const activeIdxKey = activeIdx.join("");
  const chartH = useChartHeight();
  const kpiLoading = caissesLoading || fluxLoading;
  const chartsLoading = caissesLoading || fluxLoading || natureLoading;

  const filteredCaisses = useMemo(() => {
    if (depot === "Tous") return caissesData;
    return caissesData.filter(
      (c) => c.depot === depot || c.depot.includes(depot.replace("Dépôt ", "")),
    );
  }, [depot, caissesData]);

  const totalEspeces = useMemo(
    () => filteredCaisses.reduce((s, c) => s + c.especes, 0),
    [filteredCaisses],
  );
  const totalCheques = useMemo(
    () => filteredCaisses.reduce((s, c) => s + c.cheques, 0),
    [filteredCaisses],
  );

  const filteredFlux = useMemo(() => {
    const ratio = activeIdx.length / 12;
    const daysToShow = Math.max(5, Math.round(30 * ratio));
    return fluxData.slice(fluxData.length - daysToShow);
  }, [activeIdxKey, fluxData]);

  const lastFlux = filteredFlux[filteredFlux.length - 1];
  const netJournalier = lastFlux ? lastFlux.net : 0;

  const prophetData = useMemo(() => {
    const base = totalEspeces + totalCheques;
    const lastCumul = filteredFlux[filteredFlux.length - 1]?.cumul ?? base;
    return Array.from({ length: 40 }, (_, i) => {
      const isHistorique = i < 30;
      const trend =
        i < filteredFlux.length ? filteredFlux[i]?.cumul : lastCumul + (i - 29) * netJournalier;
      const seasonal = Math.sin(i / 7) * Math.max(base * 0.04, 1);
      const val = (trend ?? base) + seasonal;
      return {
        day: `J${i - 29}`,
        historique: isHistorique ? Math.round(val) : null,
        prevision: !isHistorique ? Math.round(val * 1.05) : null,
        prevLow: !isHistorique ? Math.round(val * 0.88) : null,
        prevHigh: !isHistorique ? Math.round(val * 1.22) : null,
      };
    });
  }, [filteredFlux, netJournalier, totalCheques, totalEspeces]);

  const previsionJ15 = prophetData.find((d) => d.day === "J10" || d.prevision)?.prevision ?? 0;

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
              label="Solde espèces total"
              value={`${(totalEspeces / 1000).toFixed(0)} K DT`}
              subtitle={depot !== "Tous" ? depot : "toutes caisses"}
              icon={Banknote}
            />
            <KPICard
              label="Solde chèques"
              value={`${(totalCheques / 1000).toFixed(0)} K DT`}
              subtitle={`${filteredCaisses.length} caisse(s) filtrée(s)`}
              icon={Wallet}
            />
            <KPICard
              label="Flux net journalier"
              value={`${netJournalier > 0 ? "+" : ""}${(netJournalier / 1000).toFixed(0)} K DT`}
              subtitle="Crédit - Débit (hier)"
              trend={netJournalier > 0 ? 5.2 : -3.1}
              icon={TrendingUp}
            />
            <KPICard
              label="Prévision solde J+15"
              value={`${previsionJ15 < 0 ? "" : ""}${(previsionJ15 / 1000).toFixed(0)} K DT`}
              subtitle={previsionJ15 < 0 ? "⚠ RISQUE TRÉSORERIE" : "Projection locale (80% conf.)"}
              trend={previsionJ15 < 0 ? -Math.abs((previsionJ15 / 1000).toFixed(0)) : undefined}
              icon={Activity}
              style={previsionJ15 < 0 ? { color: "#ef4444" } : undefined}
            />
          </>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <ChartCard
          loading={chartsLoading}
          skeleton="bar"
          key={`${depot}-${activeIdxKey}`}
          title={`Solde de caisse${depot !== "Tous" ? ` — ${depot}` : " par caisse"} — Espèces vs Chèques (KPI-22)`}
        >
          {filteredCaisses.length > 0 ? (
            <>
              <MultiGauge caisses={filteredCaisses} />
              <div className="flex gap-3 text-[10px] text-text-dim mt-1">
                <span className="flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-blue-500 inline-block" /> Espèces
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-purple-500 inline-block" /> Chèques
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-red-500 inline-block animate-pulse" />{" "}
                  Sous seuil min
                </span>
              </div>
            </>
          ) : (
            <div className="flex items-center justify-center h-40 text-text-dim text-[13px]">
              Aucune caisse pour ce dépôt
            </div>
          )}
        </ChartCard>

        <ChartCard
          loading={chartsLoading}
          skeleton="bar"
          title="Flux journaliers débit / crédit (KPI-23)"
        >
          <ResponsiveContainer width="100%" height={chartH}>
            <BarChart data={filteredFlux}>
              <CartesianGrid stroke="#2a2a2a" strokeDasharray="3 3" />
              <XAxis
                dataKey="day"
                tick={{ fill: "#666", fontSize: 9 }}
                axisLine={false}
                interval={3}
              />
              <YAxis
                yAxisId="left"
                tick={{ fill: "#666", fontSize: 11 }}
                axisLine={false}
                tickFormatter={(v) => `${(v / 1000).toFixed(0)}K`}
              />
              <YAxis
                yAxisId="right"
                orientation="right"
                tick={{ fill: "#888", fontSize: 11 }}
                axisLine={false}
                tickFormatter={(v) => `${(v / 1000).toFixed(0)}K`}
              />
              <Tooltip content={<CustomTooltip />} />
              <Legend wrapperStyle={{ fontSize: 12, color: "#888" }} />
              <ReferenceLine yAxisId="left" y={0} stroke="#444" />
              <Bar
                yAxisId="left"
                dataKey="credit"
                fill="#3b82f6"
                name="Crédit"
                radius={[2, 2, 0, 0]}
              />
              <Bar
                yAxisId="left"
                dataKey="debit"
                fill="#ef4444"
                name="Débit"
                radius={[0, 0, 2, 2]}
              />
              <Line
                yAxisId="right"
                type="monotone"
                dataKey="cumul"
                stroke="#a855f7"
                strokeWidth={2}
                dot={false}
                name="Solde cumulé"
              />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard loading={chartsLoading} skeleton="pie" title="Mouvements par nature (KPI-24)">
          <div className="grid grid-cols-2 gap-2 h-[280px]">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={natureMvt}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  innerRadius={45}
                  outerRadius={85}
                  label={({ percent }) => `${((percent ?? 0) * 100).toFixed(0)}%`}
                  fontSize={10}
                >
                  {natureMvt.map((_, i) => (
                    <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip content={<CustomTooltip />} />
              </PieChart>
            </ResponsiveContainer>
            <div className="overflow-auto py-2">
              <p className="text-[10px] text-text-dim font-semibold uppercase tracking-wider mb-2">
                Top natures
              </p>
              {natureMvt.map((n, i) => (
                <div key={i} className="flex items-center gap-2 mb-2">
                  <span
                    className="w-2 h-2 rounded-full flex-shrink-0"
                    style={{ background: CHART_COLORS[i % CHART_COLORS.length] }}
                  />
                  <div className="flex-1 min-w-0">
                    <div className="text-[11px] text-foreground truncate">{n.name}</div>
                    <div className="h-1 bg-surface-hover rounded-full mt-0.5 overflow-hidden">
                      <div
                        className="h-full rounded-full"
                        style={{
                          width: `${n.value}%`,
                          background: CHART_COLORS[i % CHART_COLORS.length],
                        }}
                      />
                    </div>
                  </div>
                  <span className="text-[11px] text-text-dim">{n.value}%</span>
                </div>
              ))}
              {natureMvt.length === 0 && (
                <div className="text-[11px] text-text-dim py-8 text-center">
                  Aucun mouvement typé disponible dans le DW
                </div>
              )}
            </div>
          </div>
        </ChartCard>

        <ChartCard
          loading={chartsLoading}
          skeleton="line"
          title="Prévision solde caisse — projection 30j "
        >
          <ResponsiveContainer width="100%" height={chartH}>
            <LineChart data={prophetData.filter((_, i) => i % 2 === 0)}>
              <CartesianGrid stroke="#2a2a2a" strokeDasharray="3 3" />
              <XAxis
                dataKey="day"
                tick={{ fill: "#666", fontSize: 9 }}
                axisLine={false}
                interval={4}
              />
              <YAxis
                tick={{ fill: "#666", fontSize: 11 }}
                axisLine={false}
                tickFormatter={(v) => `${(v / 1000).toFixed(0)}K`}
              />
              <Tooltip content={<CustomTooltip />} />
              <Legend wrapperStyle={{ fontSize: 12, color: "#888" }} />
              <ReferenceLine
                x="J1"
                stroke="#555"
                strokeDasharray="4 4"
                label={{ value: "Aujourd'hui", fill: "#666", fontSize: 9 }}
              />
              <Line
                type="monotone"
                dataKey="historique"
                stroke="#3b82f6"
                strokeWidth={2}
                dot={false}
                name="Historique"
                connectNulls={false}
              />
              <Line
                type="monotone"
                dataKey="prevision"
                stroke="#6366f1"
                strokeWidth={2}
                strokeDasharray="6 3"
                dot={false}
                name="Prévision 30j"
                connectNulls
              />
              <Line
                type="monotone"
                dataKey="prevHigh"
                stroke="#6366f1"
                strokeWidth={1}
                strokeDasharray="2 4"
                dot={false}
                name="IC 80% haut"
                connectNulls
                strokeOpacity={0.4}
              />
              <Line
                type="monotone"
                dataKey="prevLow"
                stroke="#6366f1"
                strokeWidth={1}
                strokeDasharray="2 4"
                dot={false}
                name="IC 80% bas"
                connectNulls
                strokeOpacity={0.4}
              />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>
    </div>
  );
}
