import { createFileRoute } from "@tanstack/react-router";
import { useChartHeight, ChartCard } from "@/components/dashboard/ChartCard";
import { CustomTooltip } from "@/components/dashboard/CustomTooltip";
import {
  Brain,
  Cpu,
  Activity,
} from "lucide-react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from "recharts";
import { CHART_COLORS, CHART_THEME, MONTHS } from "@/lib/dashboardConstants";
import { useState, useMemo, useEffect } from "react";
import { api } from "@/lib/api";
import { useApiResource } from "@/hooks/useApiResource";

export const Route = createFileRoute("/predictions")({
  component: PredictionsStudioPage,
});

function normalizeModelId(name) {
  return String(name || "model")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

function formatMetric(value, formatter) {
  return Number.isFinite(value) && value > 0 ? formatter(value) : "-";
}

function SimpleGauge({ pct, color, label, value, subtext }) {
  const r = 52;
  const cx = 75;
  const cy = 68;
  const startA = Math.PI;
  const endA = 0;
  const valA = startA + (endA - startA) * Math.max(0, Math.min(pct, 1));
  const arc = (a, rr) => ({
    x: cx + rr * Math.cos(a),
    y: cy + rr * Math.sin(a),
  });
  const bg = `M ${arc(startA, r).x} ${arc(startA, r).y} A ${r} ${r} 0 0 1 ${arc(endA, r).x} ${arc(endA, r).y}`;
  const fill = `M ${arc(startA, r).x} ${arc(startA, r).y} A ${r} ${r} 0 ${pct > 0.5 ? 1 : 0} 1 ${arc(valA, r).x} ${arc(valA, r).y}`;

  return (
    <div className="flex flex-col items-center justify-center p-4 bg-surface/10 rounded-2xl border border-border/30 shadow-inner">
      <svg width={150} height={80} className="overflow-visible">
        <path
          d={bg}
          fill="none"
          stroke={CHART_THEME.grid}
          strokeWidth={8}
          strokeLinecap="round"
        />
        <path
          d={fill}
          fill="none"
          stroke={color}
          strokeWidth={8}
          strokeLinecap="round"
          className="transition-all duration-1000 ease-out"
        />
        <text
          x={cx}
          y={cy - 10}
          textAnchor="middle"
          fill="currentColor"
          fontSize={18}
          fontWeight="700"
          className="text-foreground font-sans"
        >
          {value}
        </text>
        <text
          x={cx}
          y={cy + 6}
          textAnchor="middle"
          fill="currentColor"
          fontSize={8}
          fontWeight="bold"
          className="text-text-dim uppercase tracking-wider"
        >
          {label}
        </text>
      </svg>
      {subtext && (
        <p className="text-[10px] text-text-dim mt-1.5 text-center leading-relaxed">
          {subtext}
        </p>
      )}
    </div>
  );
}

function PredictionsStudioPage() {
  const [activeTab, setActiveTab] = useState("");

  const forecastCaFn = useMemo(() => () => api.ml.forecastCa(), []);
  const {
    data: caData,
    loading: caLoading,
    refresh: refreshForecast,
  } = useApiResource(forecastCaFn, []);

  const rows = useMemo(() => (Array.isArray(caData) ? caData : []), [caData]);

  const modelSummaries = useMemo(() => {
    const summaries = new Map();

    rows.forEach((row) => {
      const modelName = String(row.model_name || "Modele").trim();
      const id = normalizeModelId(modelName);
      const existing = summaries.get(id) || {
        id,
        name: modelName,
        color: CHART_COLORS[summaries.size % CHART_COLORS.length],
        mape: null,
        mae: null,
        points: 0,
      };

      const mape = Number(row.mape);
      const mae = Number(row.mae);

      existing.points += 1;
      if (Number.isFinite(mape) && mape > 0) existing.mape = mape;
      if (Number.isFinite(mae) && mae > 0) existing.mae = mae;
      summaries.set(id, existing);
    });

    return Array.from(summaries.values());
  }, [rows]);

  useEffect(() => {
    if (modelSummaries.length === 0) {
      setActiveTab("");
      return;
    }
    if (!modelSummaries.some((model) => model.id === activeTab)) {
      setActiveTab(modelSummaries[0].id);
    }
  }, [activeTab, modelSummaries]);

  const activeModel =
    modelSummaries.find((model) => model.id === activeTab) ||
    modelSummaries[0] ||
    null;
  const maxMae = Math.max(...modelSummaries.map((model) => model.mae || 0), 1);

  const activeMetrics = useMemo(() => {
    if (!activeModel) {
      return { mape: "-", mae: "-", pctMape: 0, pctMae: 0 };
    }

    return {
      mape: formatMetric(activeModel.mape, (value) => `${value.toFixed(1)}%`),
      mae: formatMetric(
        activeModel.mae,
        (value) => `${(value / 1000000).toFixed(2)}M TND`,
      ),
      pctMape: Number.isFinite(activeModel.mape)
        ? Math.max(0, Math.min(1, 1 - activeModel.mape / 100))
        : 0,
      pctMae: Number.isFinite(activeModel.mae)
        ? Math.max(0, Math.min(1, 1 - activeModel.mae / maxMae))
        : 0,
    };
  }, [activeModel, maxMae]);

  const filteredCaData = useMemo(() => {
    if (!activeModel) return [];
    const hasModelColumn = rows.some((row) => row.model_name);
    if (!hasModelColumn || modelSummaries.length <= 1) return rows;
    return rows.filter(
      (row) => normalizeModelId(row.model_name) === activeModel.id,
    );
  }, [activeModel, modelSummaries.length, rows]);

  const mergedMonthlyData = useMemo(() => {
    return filteredCaData.map((row) => {
      const date = new Date(row.ds);
      const monthLabel = Number.isNaN(date.getTime())
        ? String(row.ds || "")
        : `${MONTHS[date.getMonth()]} ${String(date.getFullYear()).slice(-2)}`;

      return {
        month: monthLabel,
        ca: row.is_historical ? Math.round(row.yhat) : null,
        forecast: Math.round(row.yhat),
        lower: Math.round(row.yhat_lower),
        upper: Math.round(row.yhat_upper),
      };
    });
  }, [filteredCaData]);

  const chartH = useChartHeight();
  const activeColor = activeModel?.color || CHART_THEME.primary;

  return (
    <div className="space-y-6">

      {modelSummaries.length > 0 && (
        <div className="flex bg-background border border-border/40 p-1 rounded-xl shadow-inner w-max max-w-full overflow-x-auto">
          {modelSummaries.map((model) => (
            <button
              key={model.id}
              onClick={() => setActiveTab(model.id)}
              className={`flex items-center gap-2 px-4 py-2 text-[10px] font-bold rounded-lg transition-all cursor-pointer whitespace-nowrap ${
                activeTab === model.id
                  ? "bg-surface border border-border/30 shadow-sm"
                  : "text-text-dim hover:text-foreground"
              }`}
              style={
                activeTab === model.id ? { color: model.color } : undefined
              }
            >
              <Activity className="h-3.5 w-3.5" />
              {model.name}
            </button>
          ))}
        </div>
      )}

      <div className="space-y-4">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="space-y-4">
            <div className="bg-surface/20 border border-border/30 rounded-2xl p-5 shadow-sm space-y-4">
              <h4 className="text-[12px] font-semibold text-foreground flex items-center gap-1.5">
                <Cpu size={14} className="text-indigo-400" />
                Mesures de validation
              </h4>
              <div className="grid grid-cols-2 gap-3">
                <SimpleGauge
                  pct={activeMetrics.pctMape}
                  color={activeColor}
                  label="Erreur MAPE"
                  value={activeMetrics.mape}
                  subtext="Depuis ML_KPI05_CA_FORECAST"
                />
                <SimpleGauge
                  pct={activeMetrics.pctMae}
                  color={CHART_THEME.secondary}
                  label="MAE absolue"
                  value={activeMetrics.mae}
                  subtext="Depuis ML_KPI05_CA_FORECAST"
                />
              </div>
            </div>
          </div>

          <div className="lg:col-span-2">
            <ChartCard
              loading={caLoading}
              skeleton="line"
              title={`Previsions des ventes${activeModel ? ` : ${activeModel.name}` : ""}`}
            >
              <div className="p-3 bg-background border border-border/30 rounded-xl mb-3 flex items-center justify-between text-[9px] uppercase tracking-wider text-text-dim">
                <div className="flex gap-3">
                  <span className="flex items-center gap-1">
                    <span className="w-2 h-2 rounded-full bg-blue-500" /> CA
                    reel
                  </span>
                  {activeModel && (
                    <span className="flex items-center gap-1">
                      <span
                        className="w-2 h-2 rounded-full"
                        style={{
                          backgroundColor: activeColor,
                          border: "1px dashed currentColor",
                        }}
                      />
                      Prevision {activeModel.name}
                    </span>
                  )}
                </div>
                {activeModel && (
                  <span className="font-bold text-indigo-300 bg-indigo-500/10 border border-indigo-500/25 px-2 py-0.5 rounded">
                    {activeModel.points} points
                  </span>
                )}
              </div>

              {mergedMonthlyData.length === 0 ? (
                <div className="h-[250px] flex items-center justify-center text-text-dim italic text-xs">
                  Aucune donnee disponible depuis l'API.
                </div>
              ) : (
                <ResponsiveContainer width="100%" height={chartH}>
                  <AreaChart data={mergedMonthlyData}>
                    <CartesianGrid
                      stroke={CHART_THEME.grid}
                      strokeDasharray="3 3"
                    />
                    <XAxis
                      dataKey="month"
                      tick={{ fill: CHART_THEME.axis, fontSize: 9 }}
                      axisLine={false}
                    />
                    <YAxis
                      tick={{ fill: CHART_THEME.axis, fontSize: 9 }}
                      axisLine={false}
                      tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`}
                    />
                    <Tooltip content={<CustomTooltip />} />
                    <Legend wrapperStyle={{ fontSize: 9 }} />
                    <Area
                      type="monotone"
                      dataKey="upper"
                      stroke="none"
                      fill={activeColor}
                      fillOpacity={0.03}
                      name="Borne haute"
                    />
                    <Area
                      type="monotone"
                      dataKey="lower"
                      stroke="none"
                      fill={activeColor}
                      fillOpacity={0.03}
                      name="Borne basse"
                    />
                    <Area
                      type="monotone"
                      dataKey="forecast"
                      stroke={activeColor}
                      fill="none"
                      strokeWidth={1.5}
                      strokeDasharray="4 3"
                      name={`Prevision ${activeModel?.name || ""}`}
                    />
                    <Area
                      type="monotone"
                      dataKey="ca"
                      stroke={CHART_THEME.primary}
                      fill="none"
                      strokeWidth={2}
                      name="CA reel"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              )}
            </ChartCard>
          </div>
        </div>

        <div className="bg-surface/20 border border-border/30 rounded-2xl p-5 shadow-sm space-y-4">
          <div className="flex items-center justify-between border-b border-border/20 pb-2">
            <h4 className="text-[12px] font-bold text-foreground uppercase tracking-wider flex items-center gap-1.5">
              <Brain size={14} className="text-indigo-400" />
              Comparaison des algorithmes
            </h4>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-[11px]">
              <thead>
                <tr className="text-text-dim border-b border-border/20 font-semibold">
                  <th className="pb-2">Modele</th>
                  <th className="pb-2 text-center">Points</th>
                  <th className="pb-2 text-center">MAPE</th>
                  <th className="pb-2 text-center">MAE</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/10">
                {modelSummaries.length === 0 ? (
                  <tr>
                    <td className="py-4 text-text-dim text-center" colSpan={4}>
                      Aucun modele retourne par l'API.
                    </td>
                  </tr>
                ) : (
                  modelSummaries.map((model) => (
                    <tr
                      key={model.id}
                      className="hover:bg-surface/10 transition-colors"
                    >
                      <td
                        className="py-3 font-bold"
                        style={{ color: model.color }}
                      >
                        {model.name}
                      </td>
                      <td className="py-3 text-center text-text-dim">
                        {model.points}
                      </td>
                      <td
                        className="py-3 text-center font-bold"
                        style={{ color: model.color }}
                      >
                        {formatMetric(
                          model.mape,
                          (value) => `${value.toFixed(1)}%`,
                        )}
                      </td>
                      <td className="py-3 text-center text-text-dim">
                        {formatMetric(
                          model.mae,
                          (value) => `${(value / 1000000).toFixed(2)}M TND`,
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
