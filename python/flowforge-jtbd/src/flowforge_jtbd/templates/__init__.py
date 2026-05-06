"""JTBD workflow template cache (E-27).

Per ``framework/docs/flowforge-evolution.md`` §12.

Provides :class:`TemplateCache` — a registry of parameterised workflow
skeletons that the incremental compiler can reuse across projects — and 12
starter templates covering the most common JTBD collaboration patterns.

Usage
-----
.. code-block:: python

    from flowforge_jtbd.templates import TemplateCache

    cache = TemplateCache.default()          # pre-loaded with 12 starters
    print(cache.list_ids())

    wf = cache.instantiate(
        "n_of_m_approval",
        {"required_approvals": 2, "total_approvers": 3,
         "workflow_key": "claim_approval", "subject_kind": "claim"},
    )
"""

from __future__ import annotations

from .cache import JtbdTemplate, TemplateCache, TemplateParameter

__all__ = ["JtbdTemplate", "TemplateCache", "TemplateParameter"]
