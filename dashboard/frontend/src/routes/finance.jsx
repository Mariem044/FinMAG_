import { createFileRoute } from "@tanstack/react-router";
import { useChartHeight, ChartCard, KPICardSkeleton } from "@/components/dashboard/ChartCard";
import { KPICard } from "@/components/dashboard/KPICard";
import { CustomTooltip } from "@/components/dashboard/CustomTooltip";
import { Banknote, CheckCircle, Receipt } from "lucide-react";
import {
  BarChart, Bar, ComposedChart, LineChart, Line,
  PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, ReferenceLine,
} from "recharts";
import { CHART_COLORS } from "@/lib/dashboardConstants";
import { useFilters } from "@/store/useFilters";
import { useMemo } from "react";
import { api } from "@/lib/api";
import { useApiResource } from "@/hooks/useApiResource";

export const Route = createFileRoute("/finance")({
  component: FinancePage,
});

const ALL_BANQUES = ["AMEN", "ZITOUNA", "QNB", "BT"];
const ALL_MODES = ["Chèque", "Traite", "Virement"];
const priorityColor = { Chèque: "#3b82f6", Traite: "#ef4444", Virement: "#22c55e" };

function FinancePage() {
  const { depot, banque, modeBanque, getActiveMonthIndexes } = useFilters();
  const chartH = useChartHeight();
  const activeIdx = getActiveMonthIndexes();

  const { data: caissesData, loading: caissesLoading } = useApiResource(api.caisse.caisses, []);
  const { data: fluxData, loading: fluxLoading } = useApiResource(api.caisse.fluxDaily, []);
  const { data: natureMvt, loading: natureLoading } = useApiResource(api.caisse.mouvementsByType, []);
  const { data: rapprochementApi, loading: rapprochLoading } = useApiResource(api.banque.rapprochement, []);
  const { data: breakdownApi, loading: breakdownLoading } = useApiResource(
    api.banque.rapprochementBreakdown,
    { totals: { Chèque: 0, Traite: 0, Virement: 0 }, transactions: [] }
  );

  const kpiLoading = caissesLoading || rapprochLoading || breakdownLoading;
  const chartsLoading = caissesLoading || fluxLoading || natureLoading || rapprochLoading || breakdownLoading;

  const filteredCaisses = useMemo(() => {
    if (depot === "Tous") return caissesData;
    return caissesData.filter((c) => c.depot === depot || c.depot.includes(depot.replace("Dépôt ", "")));
  }, [depot, caissesData]);

  const totalEspeces = useMemo(() => filteredCaisses.reduce((s, c) => s + c.especes, 0), [filteredCaisses]);
  const totalCheques = useMemo(() => filteredCaisses.reduce((s, c) => s + c.cheques, 0), [filteredCaisses]);
  const soldeTotal = totalEspeces + totalCheques;

  const alignedFlux = useMemo(() => {
    if (fluxData.length === 0) return [];
    const lastRawCumul = fluxData[fluxData.length - 1]?.cumul ?? 0;
    const offset = soldeTotal - lastRawCumul;
    return fluxData.map((d) => ({ ...d, cumul: d.cumul + offset }));
  }, [soldeTotal, fluxData]);

  const filteredFlux = useMemo(() => {
    const ratio = activeIdx.length / 12;
    const daysToShow = Math.max(5, Math.round(30 * ratio));
    return alignedFlux.slice(alignedFlux.length - daysToShow);
  }, [activeIdx, alignedFlux]);

  const activeBanques = useMemo(() => (banque === "Toutes" ? ALL_BANQUES : [banque]), [banque]);
  const activeModes = useMemo(() => (modeBanque === "Tous" ? ALL_MODES : [modeBanque]), [modeBanque]);

  const currentTaux = useMemo(() => {
    if (!rapprochementApi.length) return 0;
    return Math.round(rapprochementApi.reduce((s, d) => s + d.taux, 0) / rapprochementApi.length);
  }, [rapprochementApi]);

  const agiosData = useMemo(() =>
    rapprochementApi.map((row, i) => ({
      bordereau: `BR-${String(i + 1).padStart(3, "0")}`,
      banque: activeBanques[i % activeBanques.length],
      agios: row.agios ?? 0,
      nbJour: row.nbJour ?? 0,
    })), [activeBanques, rapprochementApi]);

  const totalAgios = agiosData.reduce((sum, r) => sum + r.agios, 0);

  const banqueMode = useMemo(() => {
    const totals = breakdownApi?.totals ?? { Chèque: 0, Traite: 0, Virement: 0 };
    return activeBanques.map((b) => {
      const row = { banque: b };
      activeModes.forEach((mo) => { row[mo] = Math.round((totals[mo] ?? 0) / activeBanques.length); });
      return row;
    });
  }, [activeBanques, activeModes, breakdownApi]);

  return (
    <div className="space-y-6">
      {/* ── 3 KPIs ── */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {kpiLoading ? (<><KPICardSkeleton /><KPICardSkeleton /><KPICardSkeleton /></>) : (
          <>
            <KPICard label="Solde Caisse Total"
              value={`${(soldeTotal / 1000).toFixed(0)} K DT`}
              subtitle={depot !== "Tous" ? depot : `${filteredCaisses.length} caisses`}
              icon={Banknote} />
            <KPICard label="Taux Rapprochement"
              value={`${currentTaux}%`}
              subtitle={banque !== "Toutes" ? banque : "4 banques"}
              icon={CheckCircle} />
            <KPICard label="Agios & Frais Bancaires"
              value={`${totalAgios.toLocaleString("fr-TN")} DT`}
              subtitle="Cumulé période"
              icon={Receipt} />
          </>
        )}
      </div>

      {/* Section Caisse */}
      <div className="flex items-center gap-3">
        <span className="text-[11px] font-bold uppercase tracking-widest text-text-dim">Caisse</span>
        <div className="flex-1 h-px bg-border/30" />
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <ChartCard loading={chartsLoading} skeleton="bar" title="Flux journaliers débit / crédit">
          <ResponsiveContainer width="100%" height={chartH}>
            <ComposedChart data={filteredFlux}>
              <CartesianGrid stroke="#2a2a2a" strokeDasharray="3 3" />
              <XAxis dataKey="day" tick={{ fill: "#666", fontSize: 9 }} axisLine={false} interval={3} />
              <YAxis yAxisId="left" tick={{ fill: "#666", fontSize: 11 }} axisLine={false}
                tickFormatter={(v) => `${(v / 1000).toFixed(0)}K`} />
              <YAxis yAxisId="right" orientation="right" tick={{ fill: "#888", fontSize: 11 }}
                axisLine={false} tickFormatter={(v) => `${(v / 1000).toFixed(0)}K`} />
              <Tooltip content={<CustomTooltip />} />
              <Legend wrapperStyle={{ fontSize: 12, color: "#888" }} />
              <ReferenceLine yAxisId="left" y={0} stroke="#444" />
              <Bar yAxisId="left" dataKey="credit" fill="#3b82f6" name="Crédit" radius={[2, 2, 0, 0]} />
              <Bar yAxisId="left" dataKey="debit" fill="#ef4444" name="Débit" radius={[0, 0, 2, 2]} />
              <Line yAxisId="right" type="monotone" dataKey="cumul" stroke="#a855f7"
                strokeWidth={2} dot={false} name="Solde cumulé" />
            </ComposedChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard loading={chartsLoading} skeleton="pie" title="Mouvements caisse par nature">
          <div className="grid grid-cols-2 gap-2 h-[280px]">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={natureMvt} dataKey="value" nameKey="name"
                  cx="50%" cy="50%" innerRadius={45} outerRadius={85}
                  label={({ percent }) => `${((percent ?? 0) * 100).toFixed(0)}%`} fontSize={10}>
                  {natureMvt.map((_, i) => <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
                </Pie>
                <Tooltip content={<CustomTooltip />} />
              </PieChart>
            </ResponsiveContainer>
            <div className="overflow-auto py-2">
              {natureMvt.map((n, i) => (
                <div key={i} className="flex items-center gap-2 mb-2">
                  <span className="w-2 h-2 rounded-full flex-shrink-0"
                    style={{ background: CHART_COLORS[i % CHART_COLORS.length] }} />
                  <div className="flex-1 min-w-0">
                    <div className="text-[11px] text-foreground truncate">{n.name}</div>
                    <div className="h-1 bg-surface-hover rounded-full mt-0.5 overflow-hidden">
                      <div className="h-full rounded-full"
                        style={{ width: `${n.value}%`, background: CHART_COLORS[i % CHART_COLORS.length] }} />
                    </div>
                  </div>
                  <span className="text-[11px] text-text-dim">{n.value}%</span>
                </div>
              ))}
            </div>
          </div>
        </ChartCard>
      </div>

      {/* Section Banque */}
      <div className="flex items-center gap-3">
        <span className="text-[11px] font-bold uppercase tracking-widest text-text-dim">Banque</span>
        <div className="flex-1 h-px bg-border/30" />
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <ChartCard loading={chartsLoading} skeleton="bar"
          title={`Bordereaux${banque !== "Toutes" ? ` — ${banque}` : " par banque"}`}>
          <ResponsiveContainer width="100%" height={chartH}>
            <BarChart data={banqueMode}>
              <CartesianGrid stroke="#2a2a2a" strokeDasharray="3 3" />
              <XAxis dataKey="banque" tick={{ fill: "#666", fontSize: 12 }} axisLine={false} />
              <YAxis tick={{ fill: "#666", fontSize: 11 }} axisLine={false}
                tickFormatter={(v) => `${(v / 1000).toFixed(0)}K`} />
              <Tooltip content={<CustomTooltip />} />
              <Legend wrapperStyle={{ fontSize: 12, color: "#888" }} />
              {activeModes.map((m, i) => (
                <Bar key={m} dataKey={m} stackId="mode" fill={priorityColor[m]} name={m}
                  radius={i === activeModes.length - 1 ? [4, 4, 0, 0] : [0, 0, 0, 0]} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard loading={chartsLoading} skeleton="line" title="Taux de rapprochement bancaire">
          <ResponsiveContainer width="100%" height={chartH}>
            <LineChart data={rapprochementApi}>
              <CartesianGrid stroke="#2a2a2a" strokeDasharray="3 3" />
              <XAxis dataKey="month" tick={{ fill: "#666", fontSize: 10 }} axisLine={false} />
              <YAxis domain={[80, 100]} tick={{ fill: "#666", fontSize: 10 }}
                axisLine={false} tickFormatter={(v) => `${v}%`} />
              <Tooltip content={<CustomTooltip />} />
              <ReferenceLine y={95} stroke="#22c55e" strokeDasharray="3 3"
                label={{ value: "95%", fill: "#22c55e", fontSize: 9 }} />
              <Line type="monotone" dataKey="taux" stroke="#3b82f6"
                strokeWidth={2} dot={{ r: 3 }} name="Taux rapproch." />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>
    </div>
  );
}
