import { createFileRoute } from "@tanstack/react-router";
import {
  useChartHeight,
  ChartCard,
  KPICardSkeleton,
} from "@/components/dashboard/ChartCard";
import { KPICard } from "@/components/dashboard/KPICard";
import { CustomTooltip } from "@/components/dashboard/CustomTooltip";
import { Banknote, CheckCircle } from "lucide-react";
import {
  BarChart,
  Bar,
  ComposedChart,
  LineChart,
  Line,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import {
  BUSINESS_THRESHOLDS,
  CHART_COLORS,
  CHART_LIMITS,
  CHART_THEME,
  formatTND,
} from "@/lib/dashboardConstants";
import { useFilters } from "@/store/useFilters";
import { useMemo } from "react";
import { api } from "@/lib/api";
import { useApiResource } from "@/hooks/useApiResource";

export const Route = createFileRoute("/finance")({
  component: FinancePage,
});

const priorityColor = {
  Chèque: CHART_THEME.primary,
  Traite: CHART_THEME.negative,
  Virement: CHART_THEME.positive,
};

function FinancePage() {
  const {
    year,
    quarter,
    month,
    depot,
    banque,
    modeBanque,
    getActiveMonthIndexes,
  } = useFilters();
  const chartH = useChartHeight();
  const activeIdx = getActiveMonthIndexes();

  // Wrap each fetcher in useMemo so its reference changes when filters change.
  // useApiResource watches the function reference: new ref → new fetch.
  const fetchCaisses = useMemo(
    () => () => api.caisse.caisses(),
    [year, quarter, month, depot],
  );
  const fetchFlux = useMemo(
    () => () => api.caisse.fluxDaily(),
    [year, quarter, month, depot],
  );
  const fetchNature = useMemo(
    () => () => api.caisse.mouvementsByType(),
    [year, quarter, month, depot],
  );
  const fetchRapproch = useMemo(
    () => () => api.banque.rapprochement(),
    [year, quarter, month, depot, banque, modeBanque],
  );
  const fetchBreakdown = useMemo(
    () => () => api.banque.rapprochementBreakdown(),
    [year, quarter, month, depot, banque, modeBanque],
  );

  const { data: caissesData, loading: caissesLoading } = useApiResource(
    fetchCaisses,
    [],
  );
  const { data: fluxData, loading: fluxLoading } = useApiResource(
    fetchFlux,
    [],
  );
  const { data: natureMvt, loading: natureLoading } = useApiResource(
    fetchNature,
    [],
  );
  const { data: rapprochementApi, loading: rapprochLoading } = useApiResource(
    fetchRapproch,
    [],
  );
  const { data: breakdownApi, loading: breakdownLoading } = useApiResource(
    fetchBreakdown,
    { totals: {}, banques: [], transactions: [] },
  );

  const kpiLoading = caissesLoading || rapprochLoading || breakdownLoading;
  const chartsLoading =
    caissesLoading ||
    fluxLoading ||
    natureLoading ||
    rapprochLoading ||
    breakdownLoading;

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

  const availableBanques = useMemo(
    () =>
      Array.isArray(breakdownApi?.banques)
        ? breakdownApi.banques.map((row) => row.banque).filter(Boolean)
        : [],
    [breakdownApi],
  );
  const availableModes = useMemo(() => {
    const fromTotals = Object.keys(breakdownApi?.totals ?? {});
    const fromRows = (
      Array.isArray(breakdownApi?.banques) ? breakdownApi.banques : []
    ).flatMap((row) => Object.keys(row).filter((key) => key !== "banque"));
    return [...new Set([...fromTotals, ...fromRows])].filter(Boolean);
  }, [breakdownApi]);
  const activeBanques = useMemo(
    () => (banque === "Toutes" ? availableBanques : [banque]),
    [availableBanques, banque],
  );
  const activeModes = useMemo(
    () => (modeBanque === "Tous" ? availableModes : [modeBanque]),
    [availableModes, modeBanque],
  );
  const natureChartData = useMemo(() => {
    let cumul = 0;
    return natureMvt.map((item, index) => {
      cumul += Number(item.value) || 0;
      return {
        ...item,
        label:
          (item.name || "").length > 14
            ? `${(item.name || "").slice(0, 14)}...`
            : item.name,
        cumul: Math.min(100, Number(cumul.toFixed(1))),
        fill: CHART_COLORS[index % CHART_COLORS.length],
      };
    });
  }, [natureMvt]);

  const currentTaux = useMemo(() => {
    if (!rapprochementApi.length) return 0;
    return Math.round(
      rapprochementApi.reduce((s, d) => s + d.taux, 0) /
        rapprochementApi.length,
    );
  }, [rapprochementApi]);

  const banqueMode = useMemo(() => {
    if (breakdownApi?.banques && breakdownApi.banques.length > 0) {
      return breakdownApi.banques;
    }
    const totals = breakdownApi?.totals ?? {};
    if (activeBanques.length === 0 || activeModes.length === 0) return [];
    return activeBanques.map((b) => {
      const row = { banque: b };
      activeModes.forEach((mo) => {
        row[mo] = Math.round((totals[mo] ?? 0) / activeBanques.length);
      });
      return row;
    });
  }, [activeBanques, activeModes, breakdownApi]);

  return (
    <div className="space-y-6">
      {/* ── 2 KPIs ── */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {kpiLoading ? (
          <>
            <KPICardSkeleton />
            <KPICardSkeleton />
          </>
        ) : (
          <>
            <KPICard
              label="Solde total de caisse"
              value={`${(soldeTotal / 1000).toFixed(0)} K DT`}
              subtitle={
                depot !== "Tous" ? depot : `${filteredCaisses.length} caisses`
              }
              icon={Banknote}
            />
            <KPICard
              label="Taux de rapprochement"
              value={`${currentTaux}%`}
              subtitle={
                banque !== "Toutes" ? banque : `${banqueMode.length} banque(s)`
              }
              icon={CheckCircle}
            />
          </>
        )}
      </div>

      {/* Section Caisse */}
      <div className="flex items-center gap-3">
        <span className="text-[11px] font-bold uppercase tracking-widest text-text-dim">
          Caisse
        </span>
        <div className="flex-1 h-px bg-border/30" />
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <ChartCard
          loading={chartsLoading}
          skeleton="bar"
          title="Flux journaliers débit / crédit"
        >
          <ResponsiveContainer width="100%" height={chartH}>
            <ComposedChart data={filteredFlux}>
              <CartesianGrid stroke={CHART_THEME.grid} strokeDasharray="3 3" />
              <XAxis
                dataKey="day"
                tick={{ fill: CHART_THEME.axis, fontSize: 9 }}
                axisLine={false}
                interval={3}
              />
              <YAxis
                yAxisId="left"
                tick={{ fill: CHART_THEME.axis, fontSize: 11 }}
                axisLine={false}
                tickFormatter={(v) => `${(v / 1000).toFixed(0)}K`}
              />
              <YAxis
                yAxisId="right"
                orientation="right"
                tick={{ fill: CHART_THEME.muted, fontSize: 11 }}
                axisLine={false}
                tickFormatter={(v) => `${(v / 1000).toFixed(0)}K`}
              />
              <Tooltip content={<CustomTooltip />} />
              <Legend
                wrapperStyle={{ fontSize: 12, color: CHART_THEME.muted }}
              />
              <ReferenceLine
                yAxisId="left"
                y={0}
                stroke={CHART_THEME.reference}
              />
              <Bar
                yAxisId="left"
                dataKey="credit"
                fill={CHART_THEME.primary}
                name="Crédit"
                radius={[2, 2, 0, 0]}
              />
              <Bar
                yAxisId="left"
                dataKey="debit"
                fill={CHART_THEME.negative}
                name="Débit"
                radius={[0, 0, 2, 2]}
              />
              <Line
                yAxisId="right"
                type="monotone"
                dataKey="cumul"
                stroke={CHART_THEME.neutral}
                strokeWidth={2}
                dot={false}
                name="Solde cumulé"
              />
            </ComposedChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          loading={chartsLoading}
          skeleton="line"
          title="Courbe des mouvements de caisse par nature"
        >
          <div className="h-[280px]">
            {natureChartData.length === 0 ? (
              <div className="h-full flex items-center justify-center text-text-dim italic text-xs">
                Aucune donnée disponible
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart
                  data={natureChartData}
                  margin={{ top: 8, right: 12, bottom: 10, left: 0 }}
                >
                  <CartesianGrid
                    stroke={CHART_THEME.grid}
                    strokeDasharray="3 3"
                  />
                  <XAxis
                    dataKey="label"
                    tick={{ fill: CHART_THEME.axis, fontSize: 9 }}
                    axisLine={false}
                    interval={0}
                    angle={-20}
                    textAnchor="end"
                    height={50}
                  />
                  <YAxis
                    yAxisId="left"
                    domain={[CHART_LIMITS.percentMin, CHART_LIMITS.percentMax]}
                    tick={{ fill: CHART_THEME.axis, fontSize: 10 }}
                    axisLine={false}
                    tickFormatter={(v) => `${v}%`}
                  />
                  <YAxis
                    yAxisId="right"
                    orientation="right"
                    domain={[CHART_LIMITS.percentMin, CHART_LIMITS.percentMax]}
                    tick={{ fill: CHART_THEME.muted, fontSize: 10 }}
                    axisLine={false}
                    tickFormatter={(v) => `${v}%`}
                  />
                  <Tooltip content={<CustomTooltip />} />
                  <Legend
                    wrapperStyle={{ fontSize: 11, color: CHART_THEME.muted }}
                  />
                  <Bar
                    yAxisId="left"
                    dataKey="value"
                    name="Part par nature"
                    radius={[4, 4, 0, 0]}
                    barSize={22}
                  >
                    {natureChartData.map((item) => (
                      <Cell key={item.name} fill={item.fill} />
                    ))}
                  </Bar>
                  <Line
                    yAxisId="right"
                    type="monotone"
                    dataKey="cumul"
                    name="Courbe cumulée"
                    stroke={CHART_THEME.warning}
                    strokeWidth={2.5}
                    dot={{ r: 3, fill: CHART_THEME.warning, strokeWidth: 0 }}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            )}
          </div>
          {natureChartData.length > 0 && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-2">
              {natureChartData.slice(0, 4).map((n) => (
                <div
                  key={n.name}
                  className="flex items-center justify-between gap-2 rounded-lg bg-background/40 border border-border/20 px-3 py-2"
                >
                  <span className="flex items-center gap-2 min-w-0">
                    <span
                      className="w-2 h-2 rounded-full flex-shrink-0"
                      style={{ background: n.fill }}
                    />
                    <span className="text-[10.5px] text-foreground truncate">
                      {n.name}
                    </span>
                  </span>
                  <span className="text-[10.5px] text-text-dim tabular-nums whitespace-nowrap">
                    {n.value}% · {formatTND(n.amount)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </ChartCard>
      </div>

      {/* Section Banque */}
      <div className="flex items-center gap-3">
        <span className="text-[11px] font-bold uppercase tracking-widest text-text-dim">
          Banque
        </span>
        <div className="flex-1 h-px bg-border/30" />
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <ChartCard
          loading={chartsLoading}
          skeleton="bar"
          title={
            banque !== "Toutes"
              ? `Bordereaux ${banque}`
              : "Bordereaux par banque"
          }
        >
          <ResponsiveContainer width="100%" height={chartH}>
            <BarChart data={banqueMode}>
              <CartesianGrid stroke={CHART_THEME.grid} strokeDasharray="3 3" />
              <XAxis
                dataKey="banque"
                tick={{ fill: CHART_THEME.axis, fontSize: 12 }}
                axisLine={false}
              />
              <YAxis
                tick={{ fill: CHART_THEME.axis, fontSize: 11 }}
                axisLine={false}
                tickFormatter={(v) => `${(v / 1000).toFixed(0)}K`}
              />
              <Tooltip content={<CustomTooltip />} />
              <Legend
                wrapperStyle={{ fontSize: 12, color: CHART_THEME.muted }}
              />
              {activeModes.map((m, i) => (
                <Bar
                  key={m}
                  dataKey={m}
                  stackId="mode"
                  fill={priorityColor[m]}
                  name={m}
                  radius={
                    i === activeModes.length - 1 ? [4, 4, 0, 0] : [0, 0, 0, 0]
                  }
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          loading={chartsLoading}
          skeleton="line"
          title="Taux de rapprochement bancaire"
        >
          <ResponsiveContainer width="100%" height={chartH}>
            <LineChart data={rapprochementApi}>
              <CartesianGrid stroke={CHART_THEME.grid} strokeDasharray="3 3" />
              <XAxis
                dataKey="month"
                tick={{ fill: CHART_THEME.axis, fontSize: 10 }}
                axisLine={false}
              />
              <YAxis
                domain={[CHART_LIMITS.percentMin, CHART_LIMITS.percentMax]}
                tick={{ fill: CHART_THEME.axis, fontSize: 10 }}
                axisLine={false}
                tickFormatter={(v) => `${v}%`}
              />
              <Tooltip content={<CustomTooltip />} />
              <ReferenceLine
                y={BUSINESS_THRESHOLDS.bankReconciliationTarget}
                stroke={CHART_THEME.positive}
                strokeDasharray="3 3"
                label={{
                  value: `${BUSINESS_THRESHOLDS.bankReconciliationTarget}%`,
                  fill: CHART_THEME.positive,
                  fontSize: 9,
                }}
              />
              <Line
                type="monotone"
                dataKey="taux"
                stroke={CHART_THEME.primary}
                strokeWidth={2}
                dot={{ r: 3 }}
                name="Taux rapproch."
              />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>
    </div>
  );
}
