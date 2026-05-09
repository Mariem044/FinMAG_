import { useEffect, useState } from "react";

export function useApiResource(fetcher, initialData, deps = []) {
  const [state, setState] = useState({
    data: initialData,
    error: null,
    loading: true,
    hasRealData: false,
  });

  useEffect(() => {
    let cancelled = false;

    setState((current) => ({ ...current, loading: true, error: null }));

    fetcher()
      .then((data) => {
        if (cancelled) return;
        setState({
          data: data ?? initialData,
          error: null,
          loading: false,
          hasRealData: true,
        });
      })
      .catch((error) => {
        if (cancelled) return;
        console.error("Real-data API request failed.", error);
        setState({
          data: initialData,
          error,
          loading: false,
          hasRealData: false,
        });
      });

    return () => {
      cancelled = true;
    };
  }, deps);

  return state;
}
