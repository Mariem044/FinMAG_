import { useEffect, useState } from "react";

export function useApiResource(fetcher, initialData, deps = []) {
  const [state, setState] = useState({
    data: initialData,
    error: null,
    loading: true,
    usingFallback: false,
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
          usingFallback: false,
        });
      })
      .catch((error) => {
        if (cancelled) return;
        console.warn("API request failed.", error);
        setState({
          data: initialData,
          error,
          loading: false,
          usingFallback: true,
        });
      });

    return () => {
      cancelled = true;
    };
  }, deps);

  return state;
}
