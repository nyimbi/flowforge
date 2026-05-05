/**
 * useTenantQueryKey — host-pluggable React Query key builder.
 *
 * This is a standalone hook that does NOT depend on a specific tenant resolver.
 * The host application provides a `getTenantId` function (async or sync) and
 * this hook resolves it once, caches it, and exposes a stable `build()` helper
 * for constructing namespaced React Query keys.
 *
 * Example:
 * ```tsx
 * const { build, tenantId, tenantReady } = useTenantQueryKey({
 *   getTenantId: () => fetchCurrentTenantId(token),
 *   react,
 * });
 * const key = build("instances", { def_key: "claim-intake" });
 * // => ["flowforge", "tenant:<id>", "instances", { def_key: "claim-intake" }]
 * ```
 */

// ---------------------------------------------------------------------------
// Minimal React hooks contract (same pattern as useFlowforgeWorkflow)
// ---------------------------------------------------------------------------

type Dispatch<A> = (action: A) => void;
type SetStateAction<S> = S | ((prev: S) => S);

interface ReactHooks {
  useState<S>(init: S | (() => S)): [S, Dispatch<SetStateAction<S>>];
  useEffect(effect: () => void | (() => void), deps?: unknown[]): void;
  useCallback<T extends (...args: never[]) => unknown>(fn: T, deps: unknown[]): T;
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type TenantQueryKeyBuilder = (
  resource: string,
  params?: Record<string, unknown>,
) => readonly unknown[];

export interface UseTenantQueryKeyOptions {
  /**
   * Async (or sync) function that returns the current tenant ID string.
   * Called once on mount and whenever `enabled` flips to true.
   */
  getTenantId: () => string | Promise<string>;
  /** React hooks injected by caller. */
  react: ReactHooks;
  /** Skip resolution when false (e.g. no auth token yet). Default: true. */
  enabled?: boolean;
}

export interface UseTenantQueryKeyResult {
  tenantId: string;
  tenantReady: boolean;
  build: TenantQueryKeyBuilder;
}

// ---------------------------------------------------------------------------
// Key builder helper (pure, exported for testing)
// ---------------------------------------------------------------------------

export function buildTenantQueryKey(
  tenantId: string,
  resource: string,
  params?: Record<string, unknown>,
): readonly unknown[] {
  const base = ["flowforge", `tenant:${tenantId}`, resource] as const;
  return params ? [...base, params] : base;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useTenantQueryKey({
  getTenantId,
  react,
  enabled = true,
}: UseTenantQueryKeyOptions): UseTenantQueryKeyResult {
  const { useState, useEffect, useCallback } = react;

  const [tenantId, setTenantId] = useState<string>("unknown");

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;

    Promise.resolve(getTenantId())
      .then((id) => {
        if (!cancelled) setTenantId(id);
      })
      .catch(() => {
        // leave tenantId as "unknown"
      });

    return () => {
      cancelled = true;
    };
  }, [enabled]);

  const tenantReady = tenantId !== "unknown";

  const build: TenantQueryKeyBuilder = useCallback(
    (resource: string, params?: Record<string, unknown>) =>
      buildTenantQueryKey(tenantId, resource, params),
    [tenantId],
  );

  return { tenantId, tenantReady, build };
}
