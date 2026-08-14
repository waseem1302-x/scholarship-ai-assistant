import { useCallback, useEffect, useRef, useState } from "react";

export interface ServerQueryState<T> {
  data: T | null;
  error: unknown;
  isLoading: boolean;
  reload: () => void;
}

/**
 * Small, dependency-free query boundary for reads that need cancellation and reload.
 * It centralizes the lifecycle contract without making business state client-canonical.
 */
export function useServerQuery<T>(
  key: string,
  loader: (signal: AbortSignal) => Promise<T>,
  enabled = true,
): ServerQueryState<T> {
  const loaderRef = useRef(loader);
  loaderRef.current = loader;
  const [reloadVersion, setReloadVersion] = useState(0);
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [isLoading, setIsLoading] = useState(enabled);

  useEffect(() => {
    if (!enabled) {
      setIsLoading(false);
      return;
    }
    const controller = new AbortController();
    setIsLoading(true);
    setError(null);
    void loaderRef.current(controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) setData(value);
      })
      .catch((requestError: unknown) => {
        if (!controller.signal.aborted) setError(requestError);
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsLoading(false);
      });
    return () => controller.abort();
  }, [enabled, key, reloadVersion]);

  const reload = useCallback(() => setReloadVersion((value) => value + 1), []);
  return { data, error, isLoading, reload };
}
