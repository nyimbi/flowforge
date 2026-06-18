"""SMTP email connector."""

from __future__ import annotations

import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from .base import ConnectorBase, ConnectorResult

_log = logging.getLogger(__name__)


class SMTPConnector(ConnectorBase):
	"""Send email via SMTP using aiosmtplib."""

	connector_id = "smtp"

	def __init__(
		self,
		*,
		host: str,
		port: int = 587,
		username: str = "",
		password: str = "",
		from_addr: str,
		use_tls: bool = True,
	) -> None:
		self._host = host
		self._port = port
		self._username = username
		self._password = password
		self._from = from_addr
		self._use_tls = use_tls

	async def execute(self, payload: dict[str, Any]) -> ConnectorResult:
		to = payload.get("to", "")
		subject = payload.get("subject", "(no subject)")
		body_text = payload.get("body", "")
		body_html = payload.get("body_html", "")
		if not to:
			return ConnectorResult(ok=False, error="SMTP: 'to' is required in payload")
		msg = MIMEMultipart("alternative")
		msg["Subject"] = subject
		msg["From"] = self._from
		msg["To"] = to
		msg.attach(MIMEText(body_text, "plain"))
		if body_html:
			msg.attach(MIMEText(body_html, "html"))
		try:
			import aiosmtplib
			await aiosmtplib.send(
				msg,
				hostname=self._host,
				port=self._port,
				username=self._username or None,
				password=self._password or None,
				start_tls=self._use_tls,
			)
			return ConnectorResult(ok=True, data={"to": to})
		except Exception as exc:
			_log.error("SMTPConnector.execute failed: %s", exc)
			return ConnectorResult(ok=False, error=str(exc))
