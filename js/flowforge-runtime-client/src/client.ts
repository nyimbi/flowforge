/**
 * REST client for the flowforge-fastapi backend.
 *
 * Auth model: cookie session (browser handles the cookie jar automatically).
 * Mutating requests echo the CSRF token from the `flowforge_csrf` cookie as
 * the `X-CSRF-Token` header (double-submit-cookie pattern).
 *
 * Idempotency: callers pass an `idempotencyKey` on writes; the client sends
 * it as `Idempotency-Key`. Generate one per user action (not per retry).
 *
 * Retry/backoff: transient failures (network errors, 5xx) are retried up to
 * `maxAttempts` times with exponential backoff + jitter.
 */

import { z } from "zod";

// ---------------------------------------------------------------------------
// Error
// ---------------------------------------------------------------------------

export class FlowforgeApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "FlowforgeApiError";
  }
}

// ---------------------------------------------------------------------------
// Zod schemas — mirror the Pydantic models in router_designer.py /
// router_runtime.py exactly.
// ---------------------------------------------------------------------------

export const defSummarySchema = z.object({
  key: z.string(),
  version: z.string(),
  subject_kind: z.string(),
  initial_state: z.string(),
  states: z.array(z.string()),
});

export const instanceViewSchema = z.object({
  id: z.string(),
  def_key: z.string(),
  def_version: z.string(),
  state: z.string(),
  context: z.record(z.unknown()),
  history: z.array(z.string()),
  saga: z.array(z.record(z.unknown())),
  created_entities: z.array(z.tuple([z.string(), z.record(z.unknown())])),
});

export const fireResultViewSchema = z.object({
  instance: instanceViewSchema,
  matched_transition_id: z.string().nullable(),
  new_state: z.string(),
  terminal: z.boolean(),
  audit_event_kinds: z.array(z.string()),
  outbox_kinds: z.array(z.string()),
});

export const validateResponseSchema = z.object({
  ok: z.boolean(),
  errors: z.array(z.string()),
  warnings: z.array(z.string()),
});

export const listDefsResponseSchema = z.object({
  defs: z.array(defSummarySchema),
});

export type DefSummary = z.infer<typeof defSummarySchema>;
export type InstanceView = z.infer<typeof instanceViewSchema>;
export type FireResultView = z.infer<typeof fireResultViewSchema>;
export type ValidateResponse = z.infer<typeof validateResponseSchema>;

// ---------------------------------------------------------------------------
// Request body types
// ---------------------------------------------------------------------------

export interface CreateInstanceBody {
  def_key: string;
  def_version?: string;
  initial_context?: Record<string, unknown>;
  tenant_id?: string;
  instance_id?: string;
}

export interface FireEventBody {
  event: string;
  payload?: Record<string, unknown>;
  tenant_id?: string;
}

export interface ValidateBody {
  definition: Record<string, unknown>;
  strict?: boolean;
}

// ---------------------------------------------------------------------------
// Client options
// ---------------------------------------------------------------------------

export interface FlowforgeClientOptions {
  /** Base URL of the flowforge-fastapi backend, e.g. "http://localhost:8000". */
  baseUrl?: string;
  /** Max attempts for retryable failures (default: 3). */
  maxAttempts?: number;
  /** Base delay ms for exponential backoff (default: 150). */
  baseDelayMs?: number;
  /** Request timeout ms (default: 30_000). */
  timeoutMs?: number;
  /**
   * Override the CSRF token reader. Defaults to reading the `flowforge_csrf`
   * cookie from `document.cookie`. Inject a stub in tests.
   */
  getCsrfToken?: () => string | undefined;
}

// ---------------------------------------------------------------------------
// CSRF helper
// ---------------------------------------------------------------------------

const CSRF_COOKIE = "flowforge_csrf";

function readCsrfFromCookie(): string | undefined {
  if (typeof document === "undefined") return undefined;
  const match = document.cookie
    .split(";")
    .map((c) => c.trim())
    .find((c) => c.startsWith(`${CSRF_COOKIE}=`));
  return match ? decodeURIComponent(match.slice(CSRF_COOKIE.length + 1)) : undefined;
}

// ---------------------------------------------------------------------------
// Backoff
// ---------------------------------------------------------------------------

function isRetryable(status: number): boolean {
  return status === 0 || status >= 500;
}

async function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// ---------------------------------------------------------------------------
// FlowforgeClient
// ---------------------------------------------------------------------------

export class FlowforgeClient {
  private readonly baseUrl: string;
  private readonly maxAttempts: number;
  private readonly baseDelayMs: number;
  private readonly timeoutMs: number;
  private readonly getCsrfToken: () => string | undefined;

  constructor(opts: FlowforgeClientOptions = {}) {
    this.baseUrl = opts.baseUrl ?? "";
    this.maxAttempts = Math.max(1, opts.maxAttempts ?? 3);
    this.baseDelayMs = opts.baseDelayMs ?? 150;
    this.timeoutMs = opts.timeoutMs ?? 30_000;
    this.getCsrfToken = opts.getCsrfToken ?? readCsrfFromCookie;
  }

  // -------------------------------------------------------------------------
  // Core fetch with retry/backoff
  // -------------------------------------------------------------------------

  private async fetch<T>(
    method: string,
    path: string,
    schema: z.ZodType<T>,
    opts: {
      body?: unknown;
      idempotencyKey?: string;
      /** Skip CSRF header (GET/HEAD/OPTIONS handled automatically). */
      skipCsrf?: boolean;
    } = {},
  ): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    const isMutating = !["GET", "HEAD", "OPTIONS"].includes(method.toUpperCase());
    const csrfToken = isMutating && !opts.skipCsrf ? this.getCsrfToken() : undefined;

    const headers: Record<string, string> = {
      Accept: "application/json",
    };
    if (opts.body !== undefined) {
      headers["Content-Type"] = "application/json";
    }
    if (csrfToken) {
      headers["X-CSRF-Token"] = csrfToken;
    }
    if (opts.idempotencyKey) {
      headers["Idempotency-Key"] = opts.idempotencyKey;
    }

    let lastError: FlowforgeApiError | null = null;

    for (let attempt = 1; attempt <= this.maxAttempts; attempt++) {
      const controller = new AbortController();
      const timerId = setTimeout(() => controller.abort(), this.timeoutMs);

      try {
        const response = await fetch(url, {
          method,
          headers,
          credentials: "include", // send session cookies
          body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
          signal: controller.signal,
        });

        clearTimeout(timerId);

        if (!response.ok) {
          const detail = await extractDetail(response);
          const err = new FlowforgeApiError(response.status, detail);
          if (!isRetryable(response.status) || attempt === this.maxAttempts) {
            throw err;
          }
          lastError = err;
        } else {
          const json: unknown = await response.json();
          return schema.parse(json);
        }
      } catch (err) {
        clearTimeout(timerId);
        if (err instanceof FlowforgeApiError) {
          throw err; // already classified non-retryable above
        }
        // Network error / abort
        const msg = err instanceof Error ? err.message : String(err);
        lastError = new FlowforgeApiError(0, msg);
        if (attempt === this.maxAttempts) {
          throw lastError;
        }
      }

      const delay =
        this.baseDelayMs * 2 ** (attempt - 1) +
        Math.floor(Math.random() * this.baseDelayMs);
      await sleep(delay);
    }

    throw lastError ?? new FlowforgeApiError(0, "request failed after retries");
  }

  // -------------------------------------------------------------------------
  // Designer endpoints
  // -------------------------------------------------------------------------

  /** List all registered workflow definitions. */
  listDefs(): Promise<DefSummary[]> {
    return this.fetch("GET", "/defs", listDefsResponseSchema).then((r) => r.defs);
  }

  /** Fetch a single definition by key (and optional version). */
  getDef(key: string, version?: string): Promise<Record<string, unknown>> {
    const qs = version ? `?version=${encodeURIComponent(version)}` : "";
    return this.fetch("GET", `/defs/${encodeURIComponent(key)}${qs}`, z.record(z.unknown()));
  }

  /** Validate a workflow definition JSON. */
  validateDef(body: ValidateBody): Promise<ValidateResponse> {
    return this.fetch("POST", "/defs/validate", validateResponseSchema, { body });
  }

  /** Fetch the full workflow catalog. */
  getCatalog(): Promise<Record<string, unknown>> {
    return this.fetch("GET", "/catalog", z.record(z.unknown()));
  }

  // -------------------------------------------------------------------------
  // Runtime endpoints
  // -------------------------------------------------------------------------

  /**
   * Create a new workflow instance.
   *
   * @param body - must include `def_key`; other fields are optional.
   * @param idempotencyKey - caller-supplied key to prevent duplicate creation.
   */
  startInstance(body: CreateInstanceBody, idempotencyKey: string): Promise<InstanceView> {
    return this.fetch("POST", "/instances", instanceViewSchema, {
      body,
      idempotencyKey,
    });
  }

  /**
   * Send an event to an existing instance.
   *
   * @param instanceId - the instance UUID.
   * @param body - must include `event`; `payload` and `tenant_id` are optional.
   * @param idempotencyKey - caller-supplied key to prevent duplicate fires.
   */
  sendEvent(
    instanceId: string,
    body: FireEventBody,
    idempotencyKey: string,
  ): Promise<FireResultView> {
    return this.fetch(
      "POST",
      `/instances/${encodeURIComponent(instanceId)}/events`,
      fireResultViewSchema,
      { body, idempotencyKey },
    );
  }

  /**
   * Read the current snapshot of an instance.
   */
  getInstance(instanceId: string): Promise<InstanceView> {
    return this.fetch(
      "GET",
      `/instances/${encodeURIComponent(instanceId)}`,
      instanceViewSchema,
    );
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function extractDetail(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as Record<string, unknown>;
    if (typeof body["detail"] === "string") return body["detail"];
    if (typeof body["message"] === "string") return body["message"];
  } catch {
    // ignore
  }
  return response.statusText || `HTTP ${response.status}`;
}
