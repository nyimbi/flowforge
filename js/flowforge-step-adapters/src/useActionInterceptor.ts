/**
 * useActionInterceptor — action interception hook.
 *
 * Wraps an onAction callback with an ordered chain of interceptors.
 * Each interceptor can:
 *   - Allow the action through (proceed: true)
 *   - Cancel the action (proceed: false)
 *   - Replace the payload (proceed: true, payload: newPayload)
 *
 * Interceptors run in registration order. If any returns { proceed: false }
 * the chain halts and onAction is never called.
 */
import { useCallback, useRef } from "react";
import type { StepActionInterceptResult, StepActionPayload } from "@flowforge/types";

export type ActionInterceptor = (
  payload: StepActionPayload,
) => StepActionInterceptResult | Promise<StepActionInterceptResult>;

export interface UseActionInterceptorOptions {
  onAction: (payload: StepActionPayload) => void | Promise<void>;
  interceptors?: ActionInterceptor[];
}

export interface UseActionInterceptorResult {
  /** Drop-in replacement for onAction — runs the interceptor chain first. */
  interceptedOnAction: (payload: StepActionPayload) => Promise<void>;
  /** Add an interceptor at the end of the chain (stable reference). */
  addInterceptor: (fn: ActionInterceptor) => void;
  /** Remove a previously added interceptor by reference equality. */
  removeInterceptor: (fn: ActionInterceptor) => void;
}

export function useActionInterceptor({
  onAction,
  interceptors: initialInterceptors = [],
}: UseActionInterceptorOptions): UseActionInterceptorResult {
  const chainRef = useRef<ActionInterceptor[]>([...initialInterceptors]);
  const onActionRef = useRef(onAction);
  onActionRef.current = onAction;

  const interceptedOnAction = useCallback(
    async (payload: StepActionPayload): Promise<void> => {
      let current = payload;
      for (const interceptor of chainRef.current) {
        const result = await interceptor(current);
        if (!result.proceed) {
          return;
        }
        if (result.payload) {
          current = result.payload;
        }
      }
      await onActionRef.current(current);
    },
    [],
  );

  const addInterceptor = useCallback((fn: ActionInterceptor): void => {
    chainRef.current = [...chainRef.current, fn];
  }, []);

  const removeInterceptor = useCallback((fn: ActionInterceptor): void => {
    chainRef.current = chainRef.current.filter((i) => i !== fn);
  }, []);

  return { interceptedOnAction, addInterceptor, removeInterceptor };
}
