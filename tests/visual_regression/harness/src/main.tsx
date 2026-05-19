import * as React from "react";
import { createRoot } from "react-dom/client";

import { EXAMPLES, harnessUrl, type PageSpec } from "../../lib/page_catalog";

const modules = import.meta.glob(
	"../../../../examples/**/generated/{frontend,frontend-admin}/**/*.tsx",
);

type Component = (props: Record<string, never>) => React.ReactElement;
type Module = Record<string, unknown>;

interface RouteMatch {
	readonly exampleName: string;
	readonly page: PageSpec;
}

function routeFor(pathname: string): RouteMatch | null {
	for (const example of EXAMPLES) {
		for (const page of example.pages) {
			if (page.url === pathname) {
				throw new Error(
					`legacy visual-regression URL ${pathname} is ambiguous; use ${harnessUrl(
						example.name,
						page,
					)}`,
				);
			}
			if (harnessUrl(example.name, page) === pathname) {
				return { exampleName: example.name, page };
			}
		}
	}
	return null;
}

function componentName(entry: string): string {
	const filename = entry.split("/").at(-1) ?? "";
	return filename.replace(/\.tsx$/, "");
}

function resolveComponent(mod: Module, page: PageSpec): Component {
	if (typeof mod.default === "function") {
		return mod.default as Component;
	}
	const named = componentName(page.entry);
	if (typeof mod[named] === "function") {
		return mod[named] as Component;
	}
	const exported = Object.entries(mod).filter(
		([name, value]) => /^[A-Z]/.test(name) && typeof value === "function",
	);
	if (exported.length === 1) {
		return exported[0][1] as Component;
	}
	throw new Error(`could not resolve component export for ${page.entry}`);
}

async function mount(): Promise<void> {
	const rootNode = document.getElementById("root");
	if (rootNode == null) {
		throw new Error("missing #root");
	}
	const match = routeFor(window.location.pathname);
	if (match == null) {
		rootNode.textContent = `No visual-regression route for ${window.location.pathname}`;
		return;
	}
	document.documentElement.dataset.example = match.exampleName;
	document.documentElement.dataset.flavor = match.page.flavor;
	document.documentElement.dataset.page = match.page.id;

	const key = `../../../../${match.page.entry}`;
	const importer = modules[key];
	if (importer == null) {
		throw new Error(`visual-regression harness missing module for ${match.page.entry}`);
	}
	const mod = (await importer()) as Module;
	const Component = resolveComponent(mod, match.page);
	createRoot(rootNode).render(
		<React.StrictMode>
			<Component />
		</React.StrictMode>,
	);
}

void mount();
