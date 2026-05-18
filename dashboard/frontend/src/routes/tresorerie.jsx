import { createFileRoute } from "@tanstack/react-router";
import { useChartHeight, ChartCard, KPICardSkeleton } from "@/components/dashboard/ChartCard";
import { KPICard } from "@/components/dashboard/KPICard";
import { CustomTooltip } from "@/components/dashboard/CustomTooltip";
import { Banknote, AlertCircle, Clock, TrendingUp, Brain, Cpu, ShieldCheck, Sparkles } from "lucide-react";
import {
  BarChart,
  Bar,
  ComposedChart,
  Line,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
  PieChart,
  Pie,
} from "recharts";
import { MONTHS, CHART_COLORS, formatTND } from "@/lib/dashboardConstants";
import { useFilters } from "@/store/useFilters";
import { useMemo, useState } from "react";
import { api } from "@/lib/api";
import { useApiResource } from "@/hooks/useApiResource";

export const Route = createFileRoute("/tresorerie")({
  component: TresorerietPage,
});

const toNumber = (value) => Number(value) || 0;

function TresorerietPage() {
  const { modePaiement, horizonPrev, getActiveMonthIndexes, segment, depot, source } = useFilters();

  const { data: summary, loading: summaryLoading } = useApiResource(
    api.tresorerie.summary,
    {
      encaissements: 0,
      impayes: 0,
      delai_moyen: 0,
      taux_recouvrement: 0,
    },
    [modePaiement, horizonPrev, segment, depot, source]
  );
  const { data: encaissementsData, loading: encaissementsLoading } = useApiResource(
    api.tresorerie.encaissementsByMode,
    [],
    [modePaiement, horizonPrev, segment, depot, source]
  );
  const { data: agingData, loading: agingLoading } = useApiResource(
    api.tresorerie.aging,
    [],
    [modePaiement, horizonPrev, segment, depot, source]
  );

  const activeIdx = getActiveMonthIndexes();
  const activeIdxKey = activeIdx.join("");
  const chartH = useChartHeight();
  const kpiLoading = summaryLoading || encaissementsLoading;
  const chartsLoading = encaissementsLoading || agingLoading;
  const encaissementRows = Array.isArray(encaissementsData) ? encaissementsData : [];
  const agingRows = Array.isArray(agingData) ? agingData : [];

  const encaissementsMode = useMemo(() => {
    const rows =
      modePaiement === "Tous"
        ? encaissementRows
        : encaissementRows.filter((e) => e?.mode === modePaiement);
    return rows
      .filter(Boolean)
      .map((row) => ({
        ...row,
        mode: row.mode || "Non renseigne",
        mag: source === "GRT_MAG" ? 0 : toNumber(row.mag),
        grt: source === "MAG_2020" ? 0 : toNumber(row.grt),
        rapprochement: toNumber(row.rapprochement),
      }))
      .filter((row) => row.mag + row.grt > 0);
  }, [modePaiement, source, encaissementRows]);

  const donutData = encaissementsMode.map((d) => ({
    name: d.mode || "Non renseigne",
    value: d.mag + d.grt,
  }));

  const horizonMonths = useMemo(
    () => (horizonPrev === "30j" ? 3 : horizonPrev === "60j" ? 6 : 9),
    [horizonPrev]
  );

  // Projections de flux de trésorerie à horizon 30/60/90 jours
  const finalForecastData = useMemo(() => {
    const baseEncaissements =
      encaissementsMode.reduce((sum, row) => sum + row.mag + row.grt, 0) || summary.encaissements;
    const baseDecaissements = summary.impayes;
    let solde = baseEncaissements - baseDecaissements;

    return MONTHS.slice(0, horizonMonths)
      .map((month, i) => {
        const monthFactor = 0.72 + (i % 4) * 0.08;
        const encaissements = Math.round((baseEncaissements / horizonMonths) * monthFactor);
        const decaissements = -Math.round(
          (baseDecaissements / horizonMonths) * (1.05 - (i % 3) * 0.05),
        );
        solde += encaissements + decaissements;
        return { month, encaissements, decaissements, solde, confiance: 70 };
      })
      .filter((_, i) => activeIdx.includes(i) || i < horizonMonths);
  }, [encaissementsMode, horizonMonths, summary, activeIdx, activeIdxKey]);

  const filteredEnc = encaissementsMode.reduce((s, e) => s + e.mag + e.grt, 0);
  const totalEnc = summary.encaissements || filteredEnc;
  const impayes = summary.impayes || 0;

  const safeAgingData = useMemo(
    () =>
      agingRows.filter(Boolean).map((row) => ({
        client: row.client || "Client",
        "0-30j": toNumber(row["0-30j"]),
        "31-60j": toNumber(row["31-60j"]),
        "61-90j": toNumber(row["61-90j"]),
        ">90j": toNumber(row[">90j"]),
      })),
    [agingRows],
  );

  const gt90 = safeAgingData.reduce((sum, row) => sum + row[">90j"], 0);
  const tauxRecouv =
    modePaiement === "Tous"
      ? Math.round(summary.taux_recouvrement || 0)
      : (encaissementsMode[0]?.rapprochement ?? 0);

  const { data: impayesFournisseurs } = useApiResource(
    api.tresorerie.impayesFournisseurs,
    [],
    [modePaiement, horizonPrev, segment, depot, source]
  );
  const impayesFournisseurRows = Array.isArray(impayesFournisseurs) ? impayesFournisseurs : [];
  const safeImpayesFournisseurs = useMemo(
    () =>
      impayesFournisseurRows.filter(Boolean).map((row) => ({
        fournisseur: row.fournisseur || "Fournisseur",
        montant: toNumber(row.montant),
        delaiEffectif: toNumber(row.delaiEffectif),
        delaiContractuel: toNumber(row.delaiContractuel),
        etat: row.etat || "En cours",
      })),
    [impayesFournisseurRows],
  );

  const meanConfidence = useMemo(() => {
    if (finalForecastData.length === 0) return 0;
    const sum = finalForecastData.reduce((s, r) => s + (r.confiance || 0), 0);
    return Math.round(sum / finalForecastData.length);
  }, [finalForecastData]);

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
              label="Encaissements clients"
              value={formatTND(totalEnc)}
              trend={undefined}
              icon={Banknote}
            />
            <KPICard
              label="Créances impayées"
              value={formatTND(Math.round(impayes))}
              subtitle={`dont ${formatTND(gt90)} > 90j`}
              trend={undefined}
              icon={AlertCircle}
            />
            <KPICard
              label="Délai moyen règlement"
              value={`${summary.delai_moyen || 0}j`}
              icon={Clock}
            />
            <KPICard
              label="Taux recouvrement"
              value={`${tauxRecouv}%`}
              trend={undefined}
              icon={TrendingUp}
            />
          </>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <ChartCard
          loading={chartsLoading}
          skeleton="pie"
          key={`${modePaiement}-${horizonPrev}-${source}-${activeIdxKey}-${depot}-${segment}`}
          title={`Encaissements par mode — ${source}${modePaiement !== "Tous" ? ` (${modePaiement})` : ""}`}
        >
          <div className="grid grid-cols-2 gap-2 h-[280px]">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={donutData}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  innerRadius={50}
                  outerRadius={90}
                  label={({ name, percent }) => `${name} ${((percent ?? 0) * 100).toFixed(0)}%`}
                  fontSize={10}
                >
                  {donutData.map((_, i) => (
                    <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip content={<CustomTooltip />} />
              </PieChart>
            </ResponsiveContainer>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={encaissementsMode} layout="vertical">
                <XAxis type="number" tick={{ fill: "#666", fontSize: 10 }} axisLine={false} />
                <YAxis
                  type="category"
                  dataKey="mode"
                  tick={{ fill: "#999", fontSize: 10 }}
                  axisLine={false}
                  width={55}
                />
                <Tooltip content={<CustomTooltip />} />
                <Legend wrapperStyle={{ fontSize: 10, color: "#888" }} />
                <Bar dataKey="mag" fill="#3b82f6" name="MAG" radius={[0, 2, 2, 0]} />
                <Bar dataKey="grt" fill="#6366f1" name="GRT" radius={[0, 2, 2, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </ChartCard>

        <ChartCard
          loading={chartsLoading}
          skeleton="bar"
          key={`forecast-${modePaiement}-${horizonPrev}-${source}-${depot}-${segment}`}
          title="Flux de Trésorerie Prévisionnel"
        >
          <ResponsiveContainer width="100%" height={chartH}>
            <ComposedChart data={finalForecastData}>
              <CartesianGrid stroke="#2a2a2a" strokeDasharray="3 3" />
              <XAxis dataKey="month" tick={{ fill: "#666", fontSize: 10 }} axisLine={false} />
              <YAxis
                tick={{ fill: "#666", fontSize: 10 }}
                axisLine={false}
                tickFormatter={(v) => `${(v / 1000).toFixed(0)}K`}
              />
              <Tooltip content={<CustomTooltip />} />
              <Legend wrapperStyle={{ fontSize: 11, color: "#888" }} />
              <ReferenceLine y={0} stroke="#555" />
              <Bar
                dataKey="encaissements"
                fill="#10b981"
                name="Entrées Prévues"
                radius={[4, 4, 0, 0]}
              />
              <Bar
                dataKey="decaissements"
                fill="#ef4444"
                name="Outstanding / Échéances"
                radius={[4, 4, 0, 0]}
              />
              <Line
                type="monotone"
                dataKey="solde"
                stroke="#06b6d4"
                strokeWidth={2.5}
                dot={{ r: 4, fill: "#06b6d4" }}
                name="Encours Cumulé"
              />
            </ComposedChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          loading={chartsLoading}
          skeleton="bar"
          key={`aging-${modePaiement}-${horizonPrev}-${source}-${depot}-${segment}`}
          title="Vieillissement des créances — Aging"
        >
          <ResponsiveContainer width="100%" height={chartH}>
            <BarChart data={safeAgingData}>
              <CartesianGrid stroke="#2a2a2a" strokeDasharray="3 3" />
              <XAxis dataKey="client" tick={{ fill: "#666", fontSize: 10 }} axisLine={false} />
              <YAxis
                tick={{ fill: "#666", fontSize: 10 }}
                axisLine={false}
                tickFormatter={(v) => `${(v / 1000).toFixed(0)}K`}
              />
              <Tooltip content={<CustomTooltip />} />
              <Legend wrapperStyle={{ fontSize: 11, color: "#888" }} />
              <Bar dataKey="0-30j" stackId="age" fill="#22c55e" name="0-30j" />
              <Bar dataKey="31-60j" stackId="age" fill="#f97316" name="31-60j" />
              <Bar dataKey="61-90j" stackId="age" fill="#a855f7" name="61-90j" />
              <Bar dataKey=">90j" stackId="age" fill="#ef4444" name=">90j" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>


      </div>

      <div className="grid grid-cols-1 gap-4">
        <ChartCard
          loading={chartsLoading}
          skeleton="table"
          key={`impayes-fourn-${modePaiement}-${horizonPrev}-${source}-${depot}-${segment}`}
          title="Impayés fournisseurs & Délais"
        >
          <div className="overflow-auto max-h-[280px]">
            <table className="w-full text-[11px]">
              <thead className="sticky top-0 bg-background">
                <tr className="text-text-dim border-b border-border">
                  <th className="text-left py-1 px-2">Fournisseur</th>
                  <th className="text-right py-1 px-2">Montant</th>
                  <th className="text-center py-1 px-2">État</th>
                  <th className="text-center py-1 px-2">Délai eff.</th>
                  <th className="text-center py-1 px-2">Écart</th>
                </tr>
              </thead>
              <tbody>
                {safeImpayesFournisseurs.map((row, i) => {
                  const ecart = row.delaiEffectif - row.delaiContractuel;
                  return (
                    <tr key={i} className="border-b border-border/30 hover:bg-surface-hover/30">
                      <td className="py-1.5 px-2 text-foreground">{row.fournisseur}</td>
                      <td className="py-1.5 px-2 text-right text-foreground">
                        {formatTND(row.montant)}
                      </td>
                      <td className="py-1.5 px-2 text-center">
                        <span
                          className={`px-1.5 py-0.5 rounded text-[10px] ${row.etat === "Contentieux" ? "bg-red-500/20 text-red-400" : row.etat === "Partiel" ? "bg-orange-500/20 text-orange-400" : "bg-blue-500/20 text-blue-400"}`}
                        >
                          {row.etat}
                        </span>
                      </td>
                      <td className="py-1.5 px-2 text-center">{row.delaiEffectif}j</td>
                      <td
                        className={`py-1.5 px-2 text-center font-medium ${ecart > 0 ? "text-red-400" : "text-green-400"}`}
                      >
                        {ecart > 0 ? `+${ecart}j` : `${ecart}j`}
                      </td>
                    </tr>
                  );
                })}
                {safeImpayesFournisseurs.length === 0 && (
                  <tr>
                    <td colSpan={5} className="py-8 px-2 text-center text-text-dim">
                      Aucun impayé-fournisseur disponible dans le DW
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </ChartCard>
      </div>
    </div>
  );
}

