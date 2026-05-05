/**
 * WebSocket subscription client for the flowforge-fastapi `/ws` endpoint.
 *
 * Behaviour:
 * - Connects to `<wsBaseUrl>/ws` with credentials (cookie auth).
 * - Parses the `hello` frame on connect.
 * - Re-emits every subsequent JSON envelope to subscribers.
 * - Reconnects automatically on close/error using exponential backoff with
 *   jitter, up to `maxReconnectAttempts` times (default: unlimited).
 * - Callers can stop the subscription by calling `.close()`.
 */

export type WsEnvelope = Record<string, unknown>;

export interface WsHelloFrame {
  type: "hello";
  user_id: string;
}

export type WsEventHandler = (envelope: WsEnvelope) => void;
export type WsConnectHandler = (hello: WsHelloFrame) => void;
export type WsErrorHandler = (err: Event) => void;

export interface FlowforgeWsOptions {
  /** WebSocket base URL, e.g. "ws://localhost:8000". Defaults to auto-deriving from window.location. */
  wsBaseUrl?: string;
  /** Path for the WS endpoint (default: "/ws"). */
  path?: string;
  /** Base reconnect delay ms (default: 500). */
  baseReconnectDelayMs?: number;
  /** Max reconnect attempts; 0 = unlimited (default: 0). */
  maxReconnectAttempts?: number;
  /** Called when the socket connects and the hello frame is received. */
  onConnect?: WsConnectHandler;
  /** Called for each non-hello envelope. */
  onEvent?: WsEventHandler;
  /** Called on socket errors. */
  onError?: WsErrorHandler;
  /**
   * WebSocket constructor override — inject a mock in tests.
   * Must match the browser `WebSocket` interface.
   */
  WebSocketImpl?: typeof WebSocket;
}

// ---------------------------------------------------------------------------
// FlowforgeWsClient
// ---------------------------------------------------------------------------

export class FlowforgeWsClient {
  private readonly wsBaseUrl: string;
  private readonly path: string;
  private readonly baseReconnectDelayMs: number;
  private readonly maxReconnectAttempts: number;
  private readonly onConnect?: WsConnectHandler;
  private readonly onEvent?: WsEventHandler;
  private readonly onError?: WsErrorHandler;
  private readonly WebSocketImpl: typeof WebSocket;

  private ws: WebSocket | null = null;
  private attempt = 0;
  private closed = false;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(opts: FlowforgeWsOptions = {}) {
    this.wsBaseUrl = opts.wsBaseUrl ?? deriveWsBase();
    this.path = opts.path ?? "/ws";
    this.baseReconnectDelayMs = opts.baseReconnectDelayMs ?? 500;
    this.maxReconnectAttempts = opts.maxReconnectAttempts ?? 0;
    this.onConnect = opts.onConnect;
    this.onEvent = opts.onEvent;
    this.onError = opts.onError;
    this.WebSocketImpl = opts.WebSocketImpl ?? WebSocket;
  }

  /** Open the connection. Idempotent — multiple calls are safe. */
  open(): void {
    if (this.closed || this.ws !== null) return;
    this._connect();
  }

  /** Permanently close the connection and stop reconnection. */
  close(): void {
    this.closed = true;
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.close(1000, "client closed");
      this.ws = null;
    }
  }

  /** True once `close()` has been called. */
  get isClosed(): boolean {
    return this.closed;
  }

  // -------------------------------------------------------------------------
  // Internal
  // -------------------------------------------------------------------------

  private _connect(): void {
    const url = `${this.wsBaseUrl}${this.path}`;
    const ws = new this.WebSocketImpl(url);
    this.ws = ws;

    ws.onopen = () => {
      // Reset backoff on successful connection.
      this.attempt = 0;
    };

    ws.onmessage = (event: MessageEvent) => {
      let envelope: WsEnvelope;
      try {
        envelope = JSON.parse(String(event.data)) as WsEnvelope;
      } catch {
        return;
      }

      if (envelope["type"] === "hello") {
        this.onConnect?.(envelope as unknown as WsHelloFrame);
      } else {
        this.onEvent?.(envelope);
      }
    };

    ws.onerror = (event: Event) => {
      this.onError?.(event);
    };

    ws.onclose = () => {
      this.ws = null;
      if (!this.closed) {
        this._scheduleReconnect();
      }
    };
  }

  private _scheduleReconnect(): void {
    if (this.closed) return;
    if (
      this.maxReconnectAttempts > 0 &&
      this.attempt >= this.maxReconnectAttempts
    ) {
      return;
    }

    this.attempt += 1;
    const delay =
      this.baseReconnectDelayMs * 2 ** Math.min(this.attempt - 1, 8) +
      Math.floor(Math.random() * this.baseReconnectDelayMs);

    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      if (!this.closed) {
        this._connect();
      }
    }, delay);
  }
}

// ---------------------------------------------------------------------------
// Helper
// ---------------------------------------------------------------------------

function deriveWsBase(): string {
  if (typeof window === "undefined") return "ws://localhost:8000";
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}`;
}
