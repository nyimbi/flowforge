/**
 * DOM normalisation per ADR-001 — visual regression invariants.
 *
 * The CI-gating artifact for the visual regression suite is the rendered
 * DOM, not pixels. ADR-001 mandates four normalisation rules so the
 * resulting bytes are deterministic across Chromium minor versions:
 *
 *   1. strip every ``data-react-*`` attribute (React-internal hydration
 *      attributes drift between minor versions)
 *   2. normalise whitespace (collapse runs of \s+ to a single space; trim
 *      text node edges; strip blank lines between elements)
 *   3. sort the ``class`` token list alphabetically (browser preserves
 *      authoring order; sorting kills ordering noise)
 *   4. sort element attributes alphabetically (Chromium serialises in
 *      authoring order, which can drift between Playwright versions)
 *
 * The function takes a raw HTML string (typically from
 * ``page.evaluate(() => document.documentElement.outerHTML)``) and
 * returns a normalised HTML string suitable for byte-equality comparison
 * against a checked-in baseline.
 *
 * Design notes:
 *  * We use a forgiving HTML tokenizer rather than a full DOM parser
 *    because Playwright's serialised output is well-formed, and a full
 *    parser would couple this module to a runtime dependency. The
 *    tokenizer below handles every shape Chromium emits: void elements,
 *    text nodes, attribute escaping, comments, and the doctype prologue.
 *  * Comments are dropped entirely. They are not part of the visible
 *    surface and React-DevTools sometimes emits commentary that drifts
 *    between dev/prod builds.
 *  * Inline ``<style>`` and ``<script>`` content is preserved as-is
 *    (sorted attribute headers; body untouched). Sorting CSS or JS
 *    bytes would break the underlying meaning.
 */

interface ParsedAttribute {
	readonly name: string;
	readonly value: string;
	readonly hasValue: boolean;
}

interface ParsedTag {
	readonly name: string;
	readonly attrs: ParsedAttribute[];
	readonly selfClosing: boolean;
}

const VOID_ELEMENTS = new Set<string>([
	"area",
	"base",
	"br",
	"col",
	"embed",
	"hr",
	"img",
	"input",
	"link",
	"meta",
	"param",
	"source",
	"track",
	"wbr",
]);

const PRESERVE_BODY_ELEMENTS = new Set<string>(["script", "style", "pre", "textarea", "code"]);

/**
 * Normalise a raw HTML string per ADR-001.
 *
 * @param raw - Raw outerHTML from Playwright's ``document.documentElement``.
 * @returns Normalised HTML suitable for byte-equality comparison.
 */
export function normaliseDom(raw: string): string {
	const tokens = tokenise(raw);
	const out: string[] = [];
	let preserveDepth = 0;

	for (const tok of tokens) {
		if (tok.kind === "comment") {
			// ADR-001 §"normalise whitespace": comments dropped.
			continue;
		}
		if (tok.kind === "doctype") {
			out.push(tok.text.trim());
			continue;
		}
		if (tok.kind === "open" || tok.kind === "void") {
			const formatted = formatOpenTag(tok.parsed);
			out.push(formatted);
			if (
				tok.kind === "open" &&
				PRESERVE_BODY_ELEMENTS.has(tok.parsed.name.toLowerCase())
			) {
				preserveDepth += 1;
			}
			continue;
		}
		if (tok.kind === "close") {
			out.push(`</${tok.name.toLowerCase()}>`);
			if (PRESERVE_BODY_ELEMENTS.has(tok.name.toLowerCase()) && preserveDepth > 0) {
				preserveDepth -= 1;
			}
			continue;
		}
		if (tok.kind === "text") {
			if (preserveDepth > 0) {
				// Inside <style>/<script>/<pre>: preserve verbatim.
				out.push(tok.text);
				continue;
			}
			const collapsed = tok.text.replace(/\s+/g, " ");
			if (collapsed === " " || collapsed === "") {
				// Drop pure-whitespace text nodes between elements; they're
				// formatting noise from Chromium's serialiser.
				continue;
			}
			out.push(collapsed);
		}
	}
	return out.join("");
}

interface CommentToken {
	kind: "comment";
}
interface DoctypeToken {
	kind: "doctype";
	text: string;
}
interface OpenToken {
	kind: "open" | "void";
	parsed: ParsedTag;
}
interface CloseToken {
	kind: "close";
	name: string;
}
interface TextToken {
	kind: "text";
	text: string;
}

type Token = CommentToken | DoctypeToken | OpenToken | CloseToken | TextToken;

function tokenise(raw: string): Token[] {
	const tokens: Token[] = [];
	let i = 0;
	const n = raw.length;
	while (i < n) {
		const ch = raw[i];
		if (ch === "<") {
			// Comment?
			if (raw.startsWith("<!--", i)) {
				const end = raw.indexOf("-->", i + 4);
				if (end < 0) {
					// Malformed; treat rest as text.
					tokens.push({ kind: "text", text: raw.slice(i) });
					break;
				}
				tokens.push({ kind: "comment" });
				i = end + 3;
				continue;
			}
			// Doctype / declaration?
			if (raw[i + 1] === "!") {
				const end = raw.indexOf(">", i);
				if (end < 0) {
					tokens.push({ kind: "text", text: raw.slice(i) });
					break;
				}
				tokens.push({ kind: "doctype", text: raw.slice(i, end + 1) });
				i = end + 1;
				continue;
			}
			// Closing tag?
			if (raw[i + 1] === "/") {
				const end = raw.indexOf(">", i);
				if (end < 0) {
					tokens.push({ kind: "text", text: raw.slice(i) });
					break;
				}
				const name = raw.slice(i + 2, end).trim();
				tokens.push({ kind: "close", name });
				i = end + 1;
				continue;
			}
			// Opening tag.
			const end = findTagEnd(raw, i);
			if (end < 0) {
				tokens.push({ kind: "text", text: raw.slice(i) });
				break;
			}
			const tagText = raw.slice(i, end + 1);
			const parsed = parseOpenTag(tagText);
			const isVoid =
				parsed.selfClosing || VOID_ELEMENTS.has(parsed.name.toLowerCase());
			tokens.push({ kind: isVoid ? "void" : "open", parsed });
			i = end + 1;
			// If we just opened a body-preserving tag (script/style/pre/etc.),
			// fast-forward past its body so its contents land in a single
			// text token without further re-tokenising.
			if (
				!isVoid &&
				PRESERVE_BODY_ELEMENTS.has(parsed.name.toLowerCase())
			) {
				const closeTag = `</${parsed.name}`;
				const closeIdx = raw
					.toLowerCase()
					.indexOf(closeTag.toLowerCase(), i);
				if (closeIdx >= 0) {
					const body = raw.slice(i, closeIdx);
					if (body.length > 0) {
						tokens.push({ kind: "text", text: body });
					}
					i = closeIdx;
				}
			}
			continue;
		}
		// Text run until next "<".
		const next = raw.indexOf("<", i);
		const end = next < 0 ? n : next;
		const text = raw.slice(i, end);
		if (text.length > 0) {
			tokens.push({ kind: "text", text });
		}
		i = end;
	}
	return tokens;
}

function findTagEnd(raw: string, start: number): number {
	// Walks through attribute values respecting both single and double
	// quoting so a quoted ">" doesn't terminate the tag prematurely.
	let i = start + 1;
	const n = raw.length;
	let inQuote: '"' | "'" | null = null;
	while (i < n) {
		const c = raw[i];
		if (inQuote) {
			if (c === inQuote) inQuote = null;
		} else {
			if (c === '"' || c === "'") inQuote = c;
			else if (c === ">") return i;
		}
		i += 1;
	}
	return -1;
}

function parseOpenTag(tagText: string): ParsedTag {
	// tagText is like '<div class="x" id="y">' or '<input type="text" />'
	let inner = tagText.slice(1, -1).trim();
	let selfClosing = false;
	if (inner.endsWith("/")) {
		selfClosing = true;
		inner = inner.slice(0, -1).trim();
	}
	const firstSpace = firstUnquotedSpace(inner);
	let name: string;
	let rest: string;
	if (firstSpace < 0) {
		name = inner;
		rest = "";
	} else {
		name = inner.slice(0, firstSpace);
		rest = inner.slice(firstSpace + 1).trim();
	}
	const attrs = parseAttributes(rest);
	return {
		name: name.toLowerCase(),
		attrs,
		selfClosing,
	};
}

function firstUnquotedSpace(s: string): number {
	let inQuote: '"' | "'" | null = null;
	for (let i = 0; i < s.length; i += 1) {
		const c = s[i];
		if (inQuote) {
			if (c === inQuote) inQuote = null;
			continue;
		}
		if (c === '"' || c === "'") {
			inQuote = c;
			continue;
		}
		if (c === " " || c === "\t" || c === "\n" || c === "\r") return i;
	}
	return -1;
}

function parseAttributes(s: string): ParsedAttribute[] {
	const attrs: ParsedAttribute[] = [];
	let i = 0;
	const n = s.length;
	while (i < n) {
		// Skip whitespace.
		while (i < n && /\s/.test(s[i])) i += 1;
		if (i >= n) break;
		// Read name.
		const nameStart = i;
		while (i < n && !/[\s=]/.test(s[i])) i += 1;
		const name = s.slice(nameStart, i).trim();
		if (!name) break;
		// Skip whitespace before potential =.
		while (i < n && /\s/.test(s[i])) i += 1;
		if (s[i] !== "=") {
			attrs.push({ name, value: "", hasValue: false });
			continue;
		}
		i += 1; // consume =
		while (i < n && /\s/.test(s[i])) i += 1;
		// Read value.
		let value = "";
		const c = s[i];
		if (c === '"' || c === "'") {
			i += 1;
			const valStart = i;
			while (i < n && s[i] !== c) i += 1;
			value = s.slice(valStart, i);
			i += 1; // consume closing quote
		} else {
			const valStart = i;
			while (i < n && !/\s/.test(s[i])) i += 1;
			value = s.slice(valStart, i);
		}
		attrs.push({ name, value, hasValue: true });
	}
	return attrs;
}

function formatOpenTag(tag: ParsedTag): string {
	const filtered = tag.attrs.filter((a) => !isStrippedAttribute(a.name));
	// ADR-001 rule 4: sort attributes alphabetically.
	filtered.sort((a, b) => a.name.localeCompare(b.name));
	const parts: string[] = [tag.name];
	for (const attr of filtered) {
		parts.push(formatAttribute(attr));
	}
	const body = parts.join(" ");
	if (tag.selfClosing) return `<${body}/>`;
	if (VOID_ELEMENTS.has(tag.name)) return `<${body}>`;
	return `<${body}>`;
}

function isStrippedAttribute(name: string): boolean {
	// ADR-001 rule 1: strip data-react-* attributes.
	return name.toLowerCase().startsWith("data-react-");
}

function formatAttribute(attr: ParsedAttribute): string {
	const lname = attr.name.toLowerCase();
	if (!attr.hasValue) return lname;
	let value = attr.value;
	if (lname === "class") {
		// ADR-001 rule 3: sort class tokens alphabetically.
		const tokens = value.split(/\s+/).filter((t) => t.length > 0);
		tokens.sort((a, b) => a.localeCompare(b));
		value = tokens.join(" ");
	} else if (lname === "style") {
		// Stable sort of style declarations: helps when React re-orders
		// inline-style emission across versions. Normalise spacing too.
		const decls = value
			.split(";")
			.map((d) => d.trim())
			.filter((d) => d.length > 0)
			.map((d) => d.replace(/\s*:\s*/, ": "));
		decls.sort((a, b) => a.localeCompare(b));
		value = decls.join("; ");
	} else {
		// ADR-001 rule 2: normalise whitespace inside attribute values.
		value = value.replace(/\s+/g, " ").trim();
	}
	return `${lname}="${escapeAttrValue(value)}"`;
}

function escapeAttrValue(value: string): string {
	return value
		.replace(/&/g, "&amp;")
		.replace(/"/g, "&quot;")
		.replace(/</g, "&lt;")
		.replace(/>/g, "&gt;");
}
