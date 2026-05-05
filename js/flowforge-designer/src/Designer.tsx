import { useMemo, useState, type JSX } from "react";
import { useStore } from "zustand";

import { Canvas } from "./Canvas.js";
import { DiffViewer } from "./DiffViewer.js";
import { FormBuilder } from "./FormBuilder.js";
import { PropertyPanel } from "./PropertyPanel.js";
import { SimulationPanel } from "./SimulationPanel.js";
import { ValidationPanel } from "./ValidationPanel.js";
import {
	createDesignerStore,
	type DesignerStore,
} from "./store.js";
import type { FormSpec, WorkflowDef } from "./types.js";

export type DesignerTab = "canvas" | "form" | "validation" | "simulation" | "diff";

export interface DesignerProps {
	workflow?: WorkflowDef;
	form?: FormSpec | null;
	/** Optional second workflow used by the diff tab. */
	compareTo?: WorkflowDef;
	/** Inject an external store; useful for tests and host apps that need to
	 * subscribe to designer state changes. */
	store?: DesignerStore;
	/** Skip reactflow's measured DOM render (used by tests). */
	withReactFlow?: boolean;
	/** Initial tab. Defaults to canvas. */
	initialTab?: DesignerTab;
}

export const Designer = ({
	workflow,
	form,
	compareTo,
	store: externalStore,
	withReactFlow = true,
	initialTab = "canvas",
}: DesignerProps): JSX.Element => {
	const internalStore = useMemo(
		() =>
			externalStore ??
			createDesignerStore({ workflow, form: form ?? null }),
		// Intentionally only build once per Designer mount.
		// eslint-disable-next-line react-hooks/exhaustive-deps
		[],
	);
	const store = externalStore ?? internalStore;
	const [tab, setTab] = useState<DesignerTab>(initialTab);

	const undo = (): void => store.temporal.getState().undo();
	const redo = (): void => store.temporal.getState().redo();
	const pastSize = useStore(store.temporal, (t) => t.pastStates.length);
	const futureSize = useStore(store.temporal, (t) => t.futureStates.length);

	const currentWorkflow = store((s) => s.workflow);

	return (
		<div data-testid="ff-designer" aria-label="Flowforge designer">
			<header data-testid="designer-toolbar">
				<nav aria-label="Designer tabs">
					{(["canvas", "form", "validation", "simulation", "diff"] as DesignerTab[]).map(
						(t) => (
							<button
								key={t}
								type="button"
								data-testid={`tab-${t}`}
								data-active={tab === t}
								aria-pressed={tab === t}
								onClick={() => setTab(t)}
							>
								{t}
							</button>
						),
					)}
				</nav>
				<button
					type="button"
					data-testid="undo"
					onClick={undo}
					disabled={pastSize === 0}
				>
					Undo ({pastSize})
				</button>
				<button
					type="button"
					data-testid="redo"
					onClick={redo}
					disabled={futureSize === 0}
				>
					Redo ({futureSize})
				</button>
			</header>

			<main data-testid="designer-main">
				{tab === "canvas" ? (
					<>
						<Canvas store={store} withReactFlow={withReactFlow} />
						<PropertyPanel store={store} />
					</>
				) : null}
				{tab === "form" ? (
					<>
						<FormBuilder store={store} />
						<PropertyPanel store={store} />
					</>
				) : null}
				{tab === "validation" ? <ValidationPanel store={store} /> : null}
				{tab === "simulation" ? <SimulationPanel store={store} /> : null}
				{tab === "diff" ? (
					compareTo ? (
						<DiffViewer before={compareTo} after={currentWorkflow} />
					) : (
						<p data-testid="diff-no-compare">
							Pass a `compareTo` workflow to see version diffs.
						</p>
					)
				) : null}
			</main>
		</div>
	);
};
