import { useEffect, useMemo, useRef, useState } from "react";
import { useFilters } from "@/store/useFilters";

const DEFAULT_CACHE_TTL_MS = 30_000;
const resourceCache = new Map();
const pendingResources = new Map();
const fetcherIds = new WeakMap();
let fetcherIdSeq = 0;

function getFetcherId(fetcher) {
  if (typeof fetcher !== "function") {
    return "missing-fetcher";
  }
  if (!fetcherIds.has(fetcher)) {
    fetcherIdSeq += 1;
    fetcherIds.set(fetcher, fetcher.name || `fetcher-${fetcherIdSeq}`);
  }
  return fetcherIds.get(fetcher);
}

function getCacheKey(fetcher, deps, options) {
  if (options.cacheKey) return options.cacheKey;
  return `${getFetcherId(fetcher)}:${JSON.stringify(deps ?? [])}`;
}

function normalizeArgs(deps, options) {
  if (Array.isArray(deps)) return { deps, options: options ?? {} };
  return { deps: [], options: deps ?? {} };
}

export function useApiResource(fetcher, initialData, deps = [], options = {}) {
  const { deps: effectDeps, options: normalizedOptions } = normalizeArgs(deps, options);
  const ttlMs = normalizedOptions.cacheTtlMs ?? normalizedOptions.ttlMs ?? DEFAULT_CACHE_TTL_MS;
  const initialDataRef = useRef(initialData);

  const filters = useFilters();
  const filterValues = useMemo(() => [
    filters.year, filters.quarter, filters.month, filters.region,
    filters.famille, filters.segment, filters.depot, filters.banque,
    filters.modeBanque, filters.modePaiement, filters.source,
    filters.horizonPrev, filters.statutArticle
  ], [
    filters.year, filters.quarter, filters.month, filters.region,
    filters.famille, filters.segment, filters.depot, filters.banque,
    filters.modeBanque, filters.modePaiement, filters.source,
    filters.horizonPrev, filters.statutArticle
  ]);

  const cacheKey = useMemo(
    () => getCacheKey(fetcher, [...effectDeps, ...filterValues], normalizedOptions),
    [fetcher, normalizedOptions.cacheKey, ...effectDeps, ...filterValues],
  );

  const cached = resourceCache.get(cacheKey);
  const [state, setState] = useState({
    data: cached?.data ?? initialDataRef.current,
    error: null,
    loading: !cached,
    hasRealData: Boolean(cached),
  });

  useEffect(() => {
    let cancelled = false;
    if (typeof fetcher !== "function") {
      setState({
        data: initialDataRef.current,
        error: new Error("API fetcher is not configured."),
        loading: false,
        hasRealData: false,
      });
      return () => {
        cancelled = true;
      };
    }

    const cachedEntry = resourceCache.get(cacheKey);
    const now = Date.now();
    const hasCachedData = Boolean(cachedEntry);
    const isFresh = hasCachedData && now - cachedEntry.timestamp < ttlMs;

    if (hasCachedData) {
      setState({
        data: cachedEntry.data ?? initialDataRef.current,
        error: null,
        loading: false,
        hasRealData: true,
      });
      if (isFresh) {
        return () => {
          cancelled = true;
        };
      }
    } else {
      setState((prev) => ({ ...prev, loading: true, error: null }));
    }

    const pending =
      pendingResources.get(cacheKey) ??
      fetcher().finally(() => {
        pendingResources.delete(cacheKey);
      });

    if (!pendingResources.has(cacheKey)) {
      pendingResources.set(cacheKey, pending);
    }

    pending
      .then((data) => {
        if (cancelled) return;
        const resolvedData = data ?? initialDataRef.current;
        resourceCache.set(cacheKey, { data: resolvedData, timestamp: Date.now() });
        setState({
          data: resolvedData,
          error: null,
          loading: false,
          hasRealData: true,
        });
      })
      .catch((error) => {
        if (cancelled) return;
        if (import.meta.env?.DEV) {
          console.warn("[useApiResource] fetch failed:", error?.message ?? error);
        }
        const fallback = resourceCache.get(cacheKey);
        setState({
          data: fallback?.data ?? initialDataRef.current,
          error,
          loading: false,
          hasRealData: Boolean(fallback),
        });
      });

    return () => {
      cancelled = true;
    };
  }, [cacheKey, fetcher, ttlMs]);

  return state;
}
