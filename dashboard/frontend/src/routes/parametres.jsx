import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { useParametres } from "@/store/useParametres";
import { api } from "@/lib/api";
import { useApiResource } from "@/hooks/useApiResource";

export const Route = createFileRoute("/parametres")({
  component: ParametresPage,
});

function ParametresPage() {
  const { langue, setLangue, devise, setDevise, locale } = useParametres();

  const [draft, setDraft] = useState({ langue, devise });
  const [saved, setSaved] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [etlAction, setEtlAction] = useState("");

  const {
    data: etlStatus,
    loading: etlLoading,
    error: etlError,
  } = useApiResource(api.etl.status, { running: false, lastRun: null, counts: {} }, [refreshKey]);

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
    setEtlAction("Démarrage en cours...");
    try {
      const result = await api.etl.run();
      setEtlAction(result.started ? "ETL démarré avec succès" : "ETL déjà en cours d'exécution");
      setRefreshKey((v) => v + 1);
    } catch {
      setEtlAction("Erreur lors du démarrage de l'ETL");
    }
  }

  return (
    <div className="space-y-6">
      <div className="max-w-2xl">
        <h1 className="text-3xl font-bold text-foreground mb-6">Paramètres</h1>

        <div className="bg-card border border-border rounded-xl p-6 space-y-6">
          {/* Paramètres généraux */}
          <section>
            <h2 className="text-lg font-semibold text-foreground mb-4">Général</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-foreground mb-2">
                  Langue
                </label>
                <select
                  value={draft.langue}
                  onChange={(e) => setDraft({ ...draft, langue: e.target.value })}
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground focus:border-primary outline-none"
                >
                  <option>Français</option>
                  <option>Arabe</option>
                  <option>Anglais</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-foreground mb-2">
                  Devise
                </label>
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

          {/* ETL */}
          <section className="border-t border-border pt-5">
            <h2 className="text-lg font-semibold text-foreground mb-4">Pipeline ETL</h2>
            <div className="rounded-lg border border-border bg-secondary/30 p-4 space-y-3">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                {["clients", "articles", "ventes", "reglements"].map((key) => (
                  <div key={key}>
                    <p className="text-text-dim uppercase text-[10px]">{key}</p>
                    <p className="text-foreground font-semibold">
                      {(etlStatus.counts?.[key] ?? 0).toLocaleString(locale())}
                    </p>
                  </div>
                ))}
              </div>
              <div className="text-sm text-text-dim">
                {etlError
                  ? "Service ETL non disponible"
                  : etlLoading
                    ? "Chargement..."
                    : etlStatus.lastRun
                      ? `Dernier run : ${etlStatus.lastRun.status} — ${etlStatus.lastRun.date}`
                      : "Aucun run enregistré"}
              </div>
              <div className="flex items-center justify-between gap-3">
                <span className="text-xs text-text-dim">{etlAction}</span>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setRefreshKey((v) => v + 1)}
                    className="px-3 py-2 border border-border rounded-lg text-foreground hover:bg-secondary transition-colors text-sm"
                  >
                    Rafraîchir
                  </button>
                  <button
                    type="button"
                    onClick={handleRunEtl}
                    disabled={etlStatus.running}
                    className="px-3 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors text-sm"
                  >
                    {etlStatus.running ? "ETL en cours..." : "Lancer l'ETL"}
                  </button>
                </div>
              </div>
            </div>
          </section>

          {/* Boutons Save/Cancel */}
          <div className="flex items-center justify-between pt-4">
            {saved ? (
              <span className="text-sm text-green-400 font-medium">Paramètres sauvegardés ✓</span>
            ) : (
              <span />
            )}
            <div className="flex gap-3">
              <button
                onClick={handleCancel}
                className="px-4 py-2 border border-border rounded-lg text-foreground hover:bg-secondary transition-colors"
              >
                Annuler
              </button>
              <button
                onClick={handleSave}
                className="px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors"
              >
                Sauvegarder
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
