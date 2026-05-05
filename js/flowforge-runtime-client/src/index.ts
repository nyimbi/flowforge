/**
 * @flowforge/runtime-client
 *
 * Typed REST + WebSocket client for the flowforge-fastapi backend.
 *
 * Public surface:
 * - `FlowforgeClient` — REST client (startInstance, sendEvent, getInstance, listDefs, …)
 * - `FlowforgeWsClient` — WebSocket subscription client with exponential-backoff reconnect
 * - `useFlowforgeWorkflow` — React hook combining REST + WS for a single instance
 * - `useTenantQueryKey` — host-pluggable React Query key builder
 * - Zod schemas and TypeScript types for all API shapes
 */

export {
  FlowforgeClient,
  FlowforgeApiError,
  // schemas
  defSummarySchema,
  instanceViewSchema,
  fireResultViewSchema,
  validateResponseSchema,
  listDefsResponseSchema,
} from "./client.js";

export type {
  DefSummary,
  InstanceView,
  FireResultView,
  ValidateResponse,
  CreateInstanceBody,
  FireEventBody,
  ValidateBody,
  FlowforgeClientOptions,
} from "./client.js";

export { FlowforgeWsClient } from "./ws.js";
export type {
  WsEnvelope,
  WsHelloFrame,
  WsEventHandler,
  WsConnectHandler,
  WsErrorHandler,
  FlowforgeWsOptions,
} from "./ws.js";

export { useFlowforgeWorkflow } from "./hooks/useFlowforgeWorkflow.js";
export type {
  UseFlowforgeWorkflowOptions,
  UseFlowforgeWorkflowResult,
} from "./hooks/useFlowforgeWorkflow.js";

export {
  useTenantQueryKey,
  buildTenantQueryKey,
} from "./hooks/useTenantQueryKey.js";
export type {
  UseTenantQueryKeyOptions,
  UseTenantQueryKeyResult,
  TenantQueryKeyBuilder,
} from "./hooks/useTenantQueryKey.js";
