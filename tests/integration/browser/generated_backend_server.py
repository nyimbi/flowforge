"""Browser e2e bridge for the generated insurance-claim FastAPI router.

The browser integration test needs a real HTTP origin, but this repository
does not require uvicorn for local integration gates. This bridge exposes the
generated FastAPI router through ``http.server`` while forwarding requests into
Starlette's ``TestClient``. The request still exercises generated FastAPI
dependency injection, idempotency checks, and the generated domain service.
"""

from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from starlette.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[3]
GENERATED_BACKEND_SRC = (
	REPO_ROOT / "examples" / "insurance_claim" / "generated" / "backend" / "src"
)
sys.path.insert(0, str(GENERATED_BACKEND_SRC))

from flowforge.ports.types import Principal  # noqa: E402
from insurance_claim_demo.adapters.claim_intake_adapter import (  # noqa: E402
	reset_runtime_state,
)
from insurance_claim_demo.claim_intake.idempotency import (  # noqa: E402
	reset_idempotency_store,
)
from insurance_claim_demo.routers import claim_intake_router  # noqa: E402


REQUEST_LOG: list[dict[str, Any]] = []


async def _principal() -> Principal:
	return Principal(user_id="browser-e2e", roles=("claims-officer",))


def _build_app() -> FastAPI:
	reset_runtime_state()
	reset_idempotency_store()
	app = FastAPI(title="flowforge browser e2e generated backend")
	app.include_router(claim_intake_router.router)
	app.dependency_overrides[claim_intake_router.require_principal] = _principal
	return app


CLIENT = TestClient(_build_app())


class Handler(BaseHTTPRequestHandler):
	server_version = "FlowForgeBrowserE2E/1.0"

	def log_message(self, fmt: str, *args: object) -> None:
		sys.stderr.write("browser-e2e-backend: " + fmt % args + "\n")

	def _send_cors(self) -> None:
		origin = self.headers.get("Origin", "*")
		self.send_header("Access-Control-Allow-Origin", origin)
		self.send_header("Vary", "Origin")
		self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
		self.send_header(
			"Access-Control-Allow-Headers",
			"Content-Type,Idempotency-Key,X-Tenant-Id",
		)

	def _send_json(self, status_code: int, body: dict[str, Any]) -> None:
		payload = json.dumps(body, sort_keys=True).encode("utf-8")
		self.send_response(status_code)
		self._send_cors()
		self.send_header("Content-Type", "application/json")
		self.send_header("Content-Length", str(len(payload)))
		self.end_headers()
		self.wfile.write(payload)

	def do_OPTIONS(self) -> None:  # noqa: N802
		self.send_response(204)
		self._send_cors()
		self.send_header("Content-Length", "0")
		self.end_headers()

	def do_GET(self) -> None:  # noqa: N802
		if self.path == "/healthz":
			self._send_json(200, {"ok": True})
			return
		if self.path == "/__flowforge_browser_e2e/requests":
			self._send_json(200, {"requests": REQUEST_LOG})
			return
		self._send_json(404, {"detail": "not found"})

	def do_POST(self) -> None:  # noqa: N802
		content_length = int(self.headers.get("Content-Length", "0"))
		raw_body = self.rfile.read(content_length)
		forwarded_headers = {
			key: value
			for key, value in self.headers.items()
			if key.lower() in {"content-type", "idempotency-key", "x-tenant-id"}
		}
		response = CLIENT.post(
			self.path,
			content=raw_body,
			headers=forwarded_headers,
		)
		try:
			request_body: Any = json.loads(raw_body.decode("utf-8"))
		except json.JSONDecodeError:
			request_body = raw_body.decode("utf-8", errors="replace")
		try:
			response_body: Any = response.json()
		except ValueError:
			response_body = response.text
		REQUEST_LOG.append(
			{
				"method": "POST",
				"path": self.path,
				"headers": {key.lower(): value for key, value in forwarded_headers.items()},
				"request_body": request_body,
				"status_code": response.status_code,
				"response_body": response_body,
			}
		)
		body = response.content
		self.send_response(response.status_code)
		self._send_cors()
		self.send_header(
			"Content-Type",
			response.headers.get("content-type", "application/json"),
		)
		self.send_header("Content-Length", str(len(body)))
		self.end_headers()
		self.wfile.write(body)


def main() -> int:
	parser = argparse.ArgumentParser()
	parser.add_argument("--host", default="127.0.0.1")
	parser.add_argument("--port", type=int, default=0)
	parser.add_argument("--url-file", type=Path)
	args = parser.parse_args()

	server = ThreadingHTTPServer((args.host, args.port), Handler)
	url = f"http://{args.host}:{server.server_address[1]}"
	if args.url_file is not None:
		args.url_file.write_text(url, encoding="utf-8")
	print(f"browser-e2e generated backend listening on {url}", flush=True)
	try:
		server.serve_forever()
	except KeyboardInterrupt:
		pass
	finally:
		server.server_close()
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
