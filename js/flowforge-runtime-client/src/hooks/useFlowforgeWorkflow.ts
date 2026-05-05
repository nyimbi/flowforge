/**
 * useFlowforgeWorkflow — React hook that combines REST polling with optional
 * WebSocket updates for a single workflow instance.
 *
 * Usage:
 *
 * ```tsx
 * const { instance, sendEvent, isLoading, error } = useFlowforgeWorkflow({
 *   client,
 *   instanceId: "01HZ...",
 * });
 * ```
 *
 * The hook keeps `instance` fresh by re-fetching on WS state-change events
 * when a `wsClient` is provided. Without a WS client it falls back to a
 * plain polling pattern driven by the caller refreshing `instanceId`.
 *
 * NOTE: This file has no runtime dependency on React itself so it can be
 * imported in Node test environments without a DOM shim. Callers in a browser
 * context should use it alongside React 18+.
 */

import type { FlowforgeClient, InstanceView, FireEventBody, FireResultView } from "../client.js";
import type { FlowforgeWsClient, WsEnvelope } from "../ws.js";

// ---------------------------------------------------------------------------
// Minimal React type declarations so this file compiles without importing
// React at the type level (avoids peer dep being required at build time).
// ---------------------------------------------------------------------------

type Dispatch<A> = (action: A) => void;
type SetStateAction<S> = S | ((prev: S) => S);

interface ReactHooks {
  useState<S>(init: S | (() => S)): [S, Dispatch<SetStateAction<S>>];
  useEffect(effect: () => void | (() => void), deps?: unknown[]): void;
  useCallback<T extends (...args: never[]) => unknown>(fn: T, deps: unknown[]): T;
}

// ---------------------------------------------------------------------------
// Options & result
// ---------------------------------------------------------------------------

export interface UseFlowforgeWorkflowOptions {
  client: FlowforgeClient;
  instanceId: string | null | undefined;
  /** Optional live WS client; when provided, state-change events trigger a re-fetch. */
  wsClient?: FlowforgeWsClient;
  /** React hooks injected by the caller — allows usage without a direct React import. */
  react: ReactHooks;
}

export interface UseFlowforgeWorkflowResult {
  instance: InstanceView | null;
  isLoading: boolean;
  error: Error | null;
  /**
   * Send an event and optimistically update the local state on success.
   * @param body - event name + optional payload
   * @param idempotencyKey - caller-supplied idempotency key
   */
  sendEvent: (body: FireEventBody, idempotencyKey: string) => Promise<FireResultView>;
  /** Manually re-fetch the instance snapshot. */
  refresh: () => void;
}

// ---------------------------------------------------------------------------
// Hook implementation
// ---------------------------------------------------------------------------

export function useFlowforgeWorkflow({
  client,
  instanceId,
  wsClient,
  react,
}: UseFlowforgeWorkflowOptions): UseFlowforgeWorkflowResult {
  const { useState, useEffect, useCallback } = react;

  const [instance, setInstance] = useState<InstanceView | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);

  const refresh = useCallback(() => {
    setRefreshToken((t) => t + 1);
  }, []);

  // Fetch the instance snapshot whenever instanceId or refreshToken changes.
  useEffect(() => {
    if (!instanceId) {
      setInstance(null);
      return;
    }
    let cancelled = false;
    setIsLoading(true);
    setError(null);

    client
      .getInstance(instanceId)
      .then((data) => {
        if (!cancelled) {
          setInstance(data);
          setIsLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err : new Error(String(err)));
          setIsLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [instanceId, refreshToken]);

  // Subscribe to WS events that target this instance and trigger re-fetches.
  useEffect(() => {
    if (!wsClient || !instanceId) return;

    const handler = (envelope: WsEnvelope) => {
      if (
        envelope["instance_id"] === instanceId &&
        (envelope["type"] === "instance.state_changed" ||
          envelope["type"] === "instance.created")
      ) {
        refresh();
      }
    };

    const prevHandler = wsClient["onEvent" as keyof typeof wsClient] as
      | ((e: WsEnvelope) => void)
      | undefined;

    // Chain handlers — we don't replace an existing onEvent, we compose.
    (wsClient as unknown as { _hookHandlers: Set<(e: WsEnvelope) => void> })[
      "_hookHandlers"
    ] ??= new Set();
    const hookHandlers = (
      wsClient as unknown as { _hookHandlers: Set<(e: WsEnvelope) => void> }
    )["_hookHandlers"];
    hookHandlers.add(handler);

    return () => {
      hookHandlers.delete(handler);
    };
  }, [wsClient, instanceId, refresh]);

  const sendEvent = useCallback(
    async (body: FireEventBody, idempotencyKey: string): Promise<FireResultView> => {
      if (!instanceId) throw new Error("no instanceId");
      const result = await client.sendEvent(instanceId, body, idempotencyKey);
      setInstance(result.instance);
      return result;
    },
    [client, instanceId],
  );

  return { instance, isLoading, error, sendEvent, refresh };
}
