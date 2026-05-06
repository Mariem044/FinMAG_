import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { useParametres } from "@/store/useParametres";

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

  function handleSave() {
    setLangue(draft.langue);
    setDevise(draft.devise);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  function handleCancel() {
    setDraft({ langue, devise });
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
