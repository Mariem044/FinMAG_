import { useEffect, useRef, useState } from "react";

/**
 * useApiResource — fetches data from an API endpoint and manages loading/error state.
 *
 * @param {Function} fetcher   — async function that returns a Promise<data>
 * @param {*}        initialData — default value used before the first successful fetch
 * @param {Array}    deps       — extra dependencies that should trigger a re-fetch
 *                               (in addition to `fetcher` identity changes)
 *
 * Fixes vs original:
 * 1. `initialData` is captured once via useRef so it never causes re-renders.
 * 2. `fetcher` is included in the effect dependency array, so changing the
 *    fetcher function (e.g. different endpoint) automatically re-fetches.
 * 3. A cancelled flag prevents setState after unmount.
 * 4. The state is reset to loading on every new fetch cycle.
 */
export function useApiResource(fetcher, initialData, deps = []) {
  // Capture initialData once — avoids the infinite-loop caused by inline [] / {}
  const initialDataRef = useRef(initialData);

  const [state, setState] = useState({
    data: initialDataRef.current,
    error: null,
    loading: true,
    hasRealData: false,
  });

  useEffect(() => {
    let cancelled = false;

    setState((prev) => ({ ...prev, loading: true, error: null }));

    fetcher()
      .then((data) => {
        if (cancelled) return;
        setState({
          data: data ?? initialDataRef.current,
          error: null,
          loading: false,
          hasRealData: true,
        });
      })
      .catch((error) => {
        if (cancelled) return;
        // Only log in dev to avoid noise in production
        if (import.meta.env?.DEV) {
          console.warn("[useApiResource] fetch failed:", error?.message ?? error);
        }
        setState({
          data: initialDataRef.current,
          error,
          loading: false,
          hasRealData: false,
        });
      });

    return () => {
      cancelled = true;
    };
  }, [fetcher, ...deps]);

  return state;
}
