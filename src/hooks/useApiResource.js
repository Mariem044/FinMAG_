import { useEffect, useState } from "react";

function hasRows(value) {
  return Array.isArray(value) ? value.length > 0 : value !== null && value !== undefined;
}

export function useApiResource(fetcher, fallback, deps = []) {
  const [state, setState] = useState({
    data: fallback,
    error: null,
    loading: true,
    usingFallback: true,
  });

  useEffect(() => {
    let cancelled = false;

    setState((current) => ({ ...current, loading: true, error: null }));

    fetcher()
      .then((data) => {
        if (cancelled) return;
        const usableData = hasRows(data) ? data : fallback;
        setState({
          data: usableData,
          error: null,
          loading: false,
          usingFallback: usableData === fallback,
        });
      })
      .catch((error) => {
        if (cancelled) return;
        console.warn("API request failed; using fallback data.", error);
        setState({
          data: fallback,
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
