import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { useParametres } from "@/store/useParametres";
import { api } from "@/lib/api";
import { useApiResource } from "@/hooks/useApiResource";

export const Route = createFileRoute("/parametres")({
  component: ParametresPage,
});

function ParametresPage() {
  const {
    langue, setLangue,
    devise, setDevise,
    t,
  } = useParametres();

  const [draft, setDraft] = useState({
    langue,
    devise,
  });

  const [saved, setSaved] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [etlAction, setEtlAction] = useState("");
  const { data: etlStatus, loading: etlLoading, error: etlError } = useApiResource(
    api.etl.status,
    { running: false, lastRun: null, counts: {} },
    [refreshKey],
  );

  function handleSave() {
    setLangue(draft.langue);
    setDevise(draft.devise);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  function handleCancel() {
    setDraft({ langue, devise });
  }

  async function handleRunEtl() {
    setEtlAction("Démarrage ETL...");
    try {
      const result = await api.etl.run();
      setEtlAction(result.started ? "ETL lancé en arrière-plan." : "ETL déjà en cours.");
      setRefreshKey((v) => v + 1);
    } catch {
      setEtlAction("Impossible de lancer l'ETL depuis l'API.");
    }
  }

  return (
    <div className="space-y-6">
      <div className="max-w-2xl">
        <h1 className="text-3xl font-bold text-foreground mb-6">{t("params.title")}</h1>

        <div className="bg-card border border-border rounded-xl p-6 space-y-6">

          {/* Préférences générales */}
          <section>
            <h2 className="text-lg font-semibold text-foreground mb-4">{t("params.general")}</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-foreground mb-2">{t("params.langue")}</label>
                <select
                  value={draft.langue}
                  onChange={(e) => setDraft({ ...draft, langue: e.target.value })}
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground focus:border-primary outline-none"
                >
                  <option>Français</option>
                  <option>English</option>
                  <option>العربية</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-foreground mb-2">{t("params.devise")}</label>
                <select
                  value={draft.devise}
                  onChange={(e) => setDraft({ ...draft, devise: e.target.value })}
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground focus:border-primary outline-none"
                >
                  <option>TND - Dinar Tunisien</option>
                  <option>EUR - Euro</option>
                  <option>USD - Dollar</option>
                </select>
              </div>
            </div>
          </section>

          <section className="border-t border-border pt-5">
            <h2 className="text-lg font-semibold text-foreground mb-4">Données réelles ETL</h2>
            <div className="rounded-lg border border-border bg-secondary/30 p-4 space-y-3">
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-sm">
                {["clients", "articles", "ventes", "reglements", "ecritures"].map((key) => (
                  <div key={key}>
                    <p className="text-text-dim uppercase text-[10px]">{key}</p>
                    <p className="text-foreground font-semibold">
                      {(etlStatus.counts?.[key] ?? 0).toLocaleString("fr-TN")}
                    </p>
                  </div>
                ))}
              </div>
              <div className="text-sm text-text-dim">
                {etlError
                  ? "API indisponible: les tableaux ne peuvent pas charger les données DW."
                  : etlLoading
                    ? "Lecture du statut ETL..."
                    : etlStatus.lastRun
                      ? `Dernier run: ${etlStatus.lastRun.status} - ${etlStatus.lastRun.date}`
                      : "Aucun run ETL trouvé dans ETL_AUDIT."}
              </div>
              <div className="flex items-center justify-between gap-3">
                <span className="text-xs text-text-dim">{etlAction}</span>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setRefreshKey((v) => v + 1)}
                    className="px-3 py-2 border border-border rounded-lg text-foreground hover:bg-secondary transition-colors text-sm"
                  >
                    Actualiser
                  </button>
                  <button
                    type="button"
                    onClick={handleRunEtl}
                    disabled={etlStatus.running}
                    className="px-3 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors text-sm"
                  >
                    {etlStatus.running ? "ETL en cours" : "Lancer ETL"}
                  </button>
                </div>
              </div>
            </div>
          </section>

          {/* Actions */}
          <div className="flex items-center justify-between pt-4">
            {saved ? (
              <span className="text-sm text-green-400 font-medium">{t("params.saved")}</span>
            ) : (
              <span />
            )}
            <div className="flex gap-3">
              <button
                onClick={handleCancel}
                className="px-4 py-2 border border-border rounded-lg text-foreground hover:bg-secondary transition-colors"
              >
                {t("params.cancel")}
              </button>
              <button
                onClick={handleSave}
                className="px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors"
              >
                {t("params.save")}
              </button>
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}
