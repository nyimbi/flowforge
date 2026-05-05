"""Generator modules. Each exposes a ``generate(bundle, [jtbd])`` callable.

Per-JTBD generators take ``(NormalizedBundle, NormalizedJTBD)`` and emit
one file per JTBD. Per-bundle generators take ``(NormalizedBundle,)`` and
emit one shared aggregate file.
"""

from __future__ import annotations
