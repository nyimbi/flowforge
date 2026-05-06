"""RFC-8785-aligned canonical JSON for ``spec_hash``.

Every JTBD-spec carries a ``spec_hash`` of the shape
``sha256:<64 hex chars>`` computed over the canonical JSON encoding of
its body. Two CLIs invoking this helper on logically-identical specs
MUST produce byte-identical output; this module's tests pin the
property on a fixture matrix.

The encoding rules (per ``framework/docs/jtbd-editor-arch.md`` §23.2):

* Object keys sorted lexicographically by code-point order.
* UTF-8 strings, Unicode passed through untouched (ASCII-escape
  disabled — ``ensure_ascii=False``); control characters JSON-escape
  per RFC-8259.
* Integers in shortest decimal form, no leading zeros, no plus sign.
* Floats are forbidden in spec bodies; the encoder raises
  :class:`CanonicalJsonError` on a bare ``float``. Boolean ``True`` /
  ``False`` and ``None`` are accepted as JSON ``true`` / ``false`` /
  ``null``.
* Arrays preserve order; whitespace omitted between tokens.
* No trailing newline.

The helper is permissive about input shapes: pydantic models are
``model_dump`` (mode='json') first; ``dict`` / ``list`` / scalars pass
through directly. NaN / Infinity float values are rejected — they have
no canonical JSON representation.
"""

from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from typing import Any

from pydantic import BaseModel


class CanonicalJsonError(ValueError):
	"""Raised when a value cannot be canonical-JSON-encoded."""


def _normalise(value: Any) -> Any:
	"""Recursively normalise *value* into JSON-safe primitives.

	The transformer enforces:

	* No floats. Money + percentages must be integers (cents, basis
	  points). Bare ``float`` raises.
	* No NaN / Infinity (would slip past a naïve ``isinstance`` check
	  but break canonical equivalence under reload).
	* Pydantic models go through ``model_dump(mode='json')`` so the
	  same alias / by-name policy used at the boundary applies.
	* Strings are NFC-normalised.
	* Tuples become lists; sets are forbidden (order undefined).
	"""
	if isinstance(value, BaseModel):
		return _normalise(value.model_dump(mode="json", exclude_none=False))
	if value is None or isinstance(value, bool):
		return value
	if isinstance(value, int):
		return value
	if isinstance(value, float):
		if math.isnan(value) or math.isinf(value):
			raise CanonicalJsonError(
				f"NaN/Infinity float values have no canonical JSON form: {value!r}"
			)
		raise CanonicalJsonError(
			"floats are forbidden in canonical JSON; use integers (cents,"
			f" basis points) — got {value!r}"
		)
	if isinstance(value, str):
		# NFC keeps the same logical string from hashing differently
		# under different normalisation forms.
		return unicodedata.normalize("NFC", value)
	if isinstance(value, (list, tuple)):
		return [_normalise(item) for item in value]
	if isinstance(value, dict):
		out: dict[str, Any] = {}
		for key, sub in value.items():
			if not isinstance(key, str):
				raise CanonicalJsonError(
					f"object keys must be strings; got {type(key).__name__}"
				)
			out[unicodedata.normalize("NFC", key)] = _normalise(sub)
		return out
	if isinstance(value, set) or isinstance(value, frozenset):
		raise CanonicalJsonError(
			"sets have no defined element order; convert to list first"
		)
	# bytes / Decimal / datetime fall through here; reject explicitly
	# rather than letting json.dumps coerce silently.
	raise CanonicalJsonError(
		f"unsupported type for canonical JSON: {type(value).__name__}"
	)


def canonical_json(obj: Any) -> bytes:
	"""Encode *obj* to canonical JSON bytes.

	Pydantic models are serialised through ``model_dump(mode='json')``
	first; nested ``dict`` / ``list`` / primitive values go straight
	through ``_normalise``.

	The output is deterministic — keys sorted, no whitespace, no
	trailing newline — and safe to feed into a SHA-256 digest for
	content-addressed identity.
	"""
	normalised = _normalise(obj)
	return json.dumps(
		normalised,
		ensure_ascii=False,
		sort_keys=True,
		separators=(",", ":"),
		allow_nan=False,
	).encode("utf-8")


def spec_hash(obj: Any) -> str:
	"""Return ``"sha256:<64 hex chars>"`` for the canonical JSON of *obj*.

	The prefix is part of the persisted format so future hash-algorithm
	migrations can be detected without an out-of-band marker.
	"""
	digest = hashlib.sha256(canonical_json(obj)).hexdigest()
	return f"sha256:{digest}"


__all__ = [
	"CanonicalJsonError",
	"canonical_json",
	"spec_hash",
]
