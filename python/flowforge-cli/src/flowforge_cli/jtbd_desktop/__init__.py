"""Desktop JTBD editor support for the Flowforge CLI."""

from .document import (
	JtbdDocument,
	build_ai_authoring_prompt,
	build_template_from_jtbd,
	create_default_bundle,
	create_default_jtbd,
	create_jtbd_from_prompt,
	create_jtbd_from_template,
	create_template_library,
	normalise_id,
	verify_generation,
)

__all__ = [
	"JtbdDocument",
	"build_ai_authoring_prompt",
	"build_template_from_jtbd",
	"create_default_bundle",
	"create_default_jtbd",
	"create_jtbd_from_prompt",
	"create_jtbd_from_template",
	"create_template_library",
	"normalise_id",
	"verify_generation",
]
