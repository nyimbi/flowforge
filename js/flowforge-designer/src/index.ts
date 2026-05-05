export { Canvas } from "./Canvas.js";
export type { CanvasProps } from "./Canvas.js";
export { Designer } from "./Designer.js";
export type { DesignerProps, DesignerTab } from "./Designer.js";
export { DiffViewer } from "./DiffViewer.js";
export type { DiffViewerProps } from "./DiffViewer.js";
export { FormBuilder } from "./FormBuilder.js";
export type { FormBuilderProps } from "./FormBuilder.js";
export { PropertyPanel } from "./PropertyPanel.js";
export type { PropertyPanelProps } from "./PropertyPanel.js";
export { SimulationPanel } from "./SimulationPanel.js";
export type { SimulationPanelProps } from "./SimulationPanel.js";
export { ValidationPanel } from "./ValidationPanel.js";
export type { ValidationPanelProps } from "./ValidationPanel.js";

export {
	createDesignerStore,
	emptyWorkflow,
	type CreateStoreOptions,
	type DesignerState,
	type DesignerStore,
	type SelectionKind,
} from "./store.js";

export { sampleForm, sampleWorkflow } from "./fixtures.js";
export { simulate, type SimulationInput } from "./simulation.js";
export { validateWorkflow } from "./validation.js";
export { diffWorkflows } from "./diff.js";

export type {
	ChecklistItem,
	ConditionalRule,
	DelegationPolicy,
	DiffChangeKind,
	DiffEntry,
	EscalationPolicy,
	FieldDef,
	FieldKind,
	FieldOption,
	FormSpec,
	GateCondition,
	SimulationResult,
	SimulationStep,
	ValidationIssue,
	WorkflowDef,
	WorkflowState,
	WorkflowStateKind,
	WorkflowTransition,
} from "./types.js";
