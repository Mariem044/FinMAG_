import { useState, useEffect } from "react";

/**
 * Hook simple pour appeler une API et gérer le loading.
 *
 * POURQUOI fetcherFn dans les deps ?
 *   Les pages créent la fonction avec useMemo([...filtres]).
 *   Quand un filtre change => useMemo crée une nouvelle fonction
 *   => fetcherFn change => useEffect se relance => nouvel appel API.
 *   C'est le pattern recommandé pour que les filtres re-déclenchent le fetch.
 */
export function useApiResource(fetcherFn, initialData = null) {
  const [data, setData] = useState(initialData);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (typeof fetcherFn !== "function") return;

    let cancelled = false; // évite les mises à jour sur un composant démonté
    setLoading(true);

    fetcherFn()
      .then((result) => {
        if (!cancelled) setData(result ?? initialData);
      })
      .catch((err) => {
        if (!cancelled) console.error("Erreur lors du chargement des données:", err);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; }; // cleanup si le composant se démonte
  // fetcherFn est une nouvelle référence quand les filtres changent (useMemo)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fetcherFn]);

  // refresh : force un rechargement manuel
  const refresh = () => {
    if (typeof fetcherFn !== "function") return;
    fetcherFn()
      .then((result) => setData(result ?? initialData))
      .catch(console.error);
  };

  return { data, loading, refresh };
}
