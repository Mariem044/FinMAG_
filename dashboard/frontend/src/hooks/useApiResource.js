import { useState, useEffect } from "react";

/**
 * Hook simple pour appeler une API et gérer le loading
 */
export function useApiResource(fetcherFn, initialData = null, deps = []) {
  const [data, setData] = useState(initialData);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (typeof fetcherFn !== "function") return;

    setLoading(true);

    fetcherFn()
      .then((result) => {
        setData(result ?? initialData);
      })
      .catch((err) => {
        console.error("Erreur lors du chargement des données:", err);
      })
      .finally(() => {
        setLoading(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  // refresh function pour forcer un rechargement
  const refresh = () => {
    if (typeof fetcherFn !== "function") return;
    fetcherFn()
      .then((result) => setData(result ?? initialData))
      .catch(console.error);
  };

  return { data, loading, refresh };
}
