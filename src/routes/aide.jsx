import { createFileRoute } from "@tanstack/react-router";
import { Clock, HelpCircle, Mail, Phone } from "lucide-react";
import { useParametres } from "@/store/useParametres";

export const Route = createFileRoute("/aide")({
  component: AidePage,
});

const faqKeys = [
  {
    question_fr: "Comment acceder aux donnees de mes ventes ?",
    question_en: "How do I access my sales data?",
    question_ar: "Comment acceder aux donnees de mes ventes ?",
    answer_fr:
      "Cliquez sur le module Ventes dans le menu pour acceder au tableau de bord commercial.",
    answer_en: "Click Sales in the menu to access the sales dashboard.",
    answer_ar:
      "Cliquez sur le module Ventes dans le menu pour acceder au tableau de bord commercial.",
  },
  {
    question_fr: "Comment exporter les donnees ?",
    question_en: "How do I export data?",
    question_ar: "Comment exporter les donnees ?",
    answer_fr:
      "Les tableaux de donnees peuvent etre exportes avec le bouton Exporter CSV affiche au-dessus du tableau.",
    answer_en: "Data tables can be exported with the Export CSV button shown above the table.",
    answer_ar:
      "Les tableaux de donnees peuvent etre exportes avec le bouton Exporter CSV affiche au-dessus du tableau.",
  },
  {
    question_fr: "Quelle est la frequence de mise a jour des donnees ?",
    question_en: "How often is data updated?",
    question_ar: "Quelle est la frequence de mise a jour des donnees ?",
    answer_fr:
      "Les donnees sont synchronisees depuis les bases MAG_2020 et GRT_MAG. Les rapports sont generes quotidiennement.",
    answer_en:
      "Data is synchronized from the MAG_2020 and GRT_MAG databases. Reports are generated daily.",
    answer_ar:
      "Les donnees sont synchronisees depuis les bases MAG_2020 et GRT_MAG. Les rapports sont generes quotidiennement.",
  },
  {
    question_fr: "Comment entrer dans l'application ?",
    question_en: "How do I enter the app?",
    question_ar: "Comment entrer dans l'application ?",
    answer_fr:
      "Depuis la page d'accueil, choisissez un role puis cliquez sur Entrer. Aucun email ni mot de passe n'est necessaire.",
    answer_en: "From the home page, choose a role and click Enter. No email or password is needed.",
    answer_ar:
      "Depuis la page d'accueil, choisissez un role puis cliquez sur Entrer. Aucun email ni mot de passe n'est necessaire.",
  },
  {
    question_fr: "Que signifie le score d'attrition ?",
    question_en: "What does the attrition score mean?",
    question_ar: "Que signifie le score d'attrition ?",
    answer_fr:
      "Le score d'attrition est un score local de risque. Un score superieur a 0.5 indique un client a surveiller.",
    answer_en:
      "The attrition score is a local risk score. A score above 0.5 indicates a client to watch.",
    answer_ar:
      "Le score d'attrition est un score local de risque. Un score superieur a 0.5 indique un client a surveiller.",
  },
];

function AidePage() {
  const { t, langue } = useParametres();

  const qKey =
    langue === "English" ? "question_en" : langue === "العربية" ? "question_ar" : "question_fr";
  const aKey =
    langue === "English" ? "answer_en" : langue === "العربية" ? "answer_ar" : "answer_fr";

  const hoursLines = t("aide.hoursDetail").split("\n");

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h1 className="text-3xl font-bold text-foreground mb-2">{t("aide.title")}</h1>
        <p className="text-muted-foreground">{t("aide.subtitle")}</p>
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        <div className="bg-card border border-border rounded-xl p-6">
          <div className="flex items-start gap-4">
            <div className="w-12 h-12 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
              <Mail size={24} className="text-primary" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-foreground mb-2">
                {t("aide.emailSupport")}
              </h3>
              <p className="text-sm text-muted-foreground mb-3">{t("aide.emailDesc")}</p>
              <a
                href={`mailto:${import.meta.env?.VITE_SUPPORT_EMAIL || "support@magdistribution.tn"}`}
                className="text-primary hover:underline text-sm font-medium"
              >
                support@siad.tn
              </a>
            </div>
          </div>
        </div>

        <div className="bg-card border border-border rounded-xl p-6">
          <div className="flex items-start gap-4">
            <div className="w-12 h-12 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
              <Phone size={24} className="text-primary" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-foreground mb-2">
                {t("aide.phoneSupport")}
              </h3>
              <p className="text-sm text-muted-foreground mb-3">{t("aide.phoneDesc")}</p>
              <a
                href={`tel:${import.meta.env?.VITE_SUPPORT_PHONE || "+21671234567"}`}
                className="text-primary hover:underline text-sm font-medium"
              >
                +216 71 123 456
              </a>
            </div>
          </div>
        </div>
      </div>

      <div className="bg-card border border-border rounded-xl p-6">
        <h2 className="text-2xl font-bold text-foreground mb-6 flex items-center gap-2">
          <HelpCircle size={24} />
          {t("aide.faq")}
        </h2>
        <div className="space-y-3">
          {faqKeys.map((item, index) => (
            <details key={index} className="border border-border rounded-lg overflow-hidden">
              <summary className="px-4 py-3 cursor-pointer hover:bg-secondary/50 font-medium text-foreground">
                {item[qKey]}
              </summary>
              <div className="px-4 py-3 border-t border-border bg-secondary/30 text-sm text-muted-foreground">
                {item[aKey]}
              </div>
            </details>
          ))}
        </div>
      </div>

      <div className="bg-primary/5 border border-primary/20 rounded-xl p-6">
        <div className="flex items-start gap-3">
          <Clock size={20} className="text-primary flex-shrink-0 mt-1" />
          <div>
            <h3 className="font-semibold text-foreground mb-2">{t("aide.hours")}</h3>
            <p className="text-sm text-muted-foreground">
              {hoursLines.map((line, i) => (
                <span key={i}>
                  {line}
                  {i < hoursLines.length - 1 && <br />}
                </span>
              ))}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
