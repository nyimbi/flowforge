import {
	useCallback,
	useEffect,
	useMemo,
	useState,
	type CSSProperties,
	type ChangeEvent,
	type JSX,
} from "react";

import { JobMap } from "./JobMap.js";
import { layoutJobMap, type JobMapLayout } from "./layout.js";
import type {
	DataSensitivity,
	JtbdBundle,
	JtbdDependency,
	JtbdDependencyStrength,
	JtbdDependencyType,
	JtbdSpec,
} from "./types.js";

export const STANDARD_DOMAINS = [
	"general",
	"insurance",
	"banking",
	"healthcare",
	"education",
	"commerce",
	"logistics",
	"government",
	"legal",
	"manufacturing",
] as const;

export const AUTHORING_DATA_SENSITIVITY = [
	"public",
	"internal",
	"confidential",
	"restricted",
	"highly-restricted",
] as const satisfies readonly DataSensitivity[];

const DEPENDENCY_TYPES = [
	"triggers",
	"blocks",
	"informs",
	"shares-actor",
] as const satisfies readonly JtbdDependencyType[];

const DEPENDENCY_STRENGTHS = [
	"strong",
	"weak",
	"optional",
] as const satisfies readonly JtbdDependencyStrength[];

export type ValidationSeverity = "error" | "warning" | "info";

export interface ValidationIssue {
	id: string;
	title: string;
	severity: ValidationSeverity;
	jtbdId?: string;
}

export interface JtbdEditorProps {
	bundle: JtbdBundle;
	onChange?: (bundle: JtbdBundle) => void;
	withReactFlow?: boolean;
	className?: string;
}

type LayoutState =
	| { status: "loading" }
	| { status: "ready"; layout: JobMapLayout }
	| { status: "error"; message: string };

interface ParsedDependencyId {
	source: string;
	target: string;
}

const SEMVER_RE =
	/^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$/;

const isSemver = (value: string): boolean => SEMVER_RE.test(value.trim());

const parseList = (value: string): string[] =>
	value
		.split(",")
		.map((item) => item.trim())
		.filter(Boolean);

const currentActors = (spec: JtbdSpec): string[] => {
	if (spec.actors && spec.actors.length > 0) {
		return spec.actors;
	}
	return spec.actor.role ? [spec.actor.role] : [];
};

const parseDependencyId = (dependencyId: string): ParsedDependencyId | null => {
	const separator = dependencyId.indexOf("->");
	if (separator <= 0 || separator >= dependencyId.length - 2) {
		return null;
	}
	return {
		source: dependencyId.slice(0, separator),
		target: dependencyId.slice(separator + 2),
	};
};

const messageFromError = (error: unknown): string =>
	error instanceof Error ? error.message : String(error);

const uniqueId = (bundle: JtbdBundle, base: string): string => {
	const existing = new Set(bundle.jtbds.map((spec) => spec.id));
	if (!existing.has(base)) {
		return base;
	}
	let index = 2;
	while (existing.has(`${base}_${index}`)) {
		index += 1;
	}
	return `${base}_${index}`;
};

const downloadName = (bundle: JtbdBundle): string => {
	const base = bundle.project.name || bundle.project.package || "jtbd-bundle";
	return `${base.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "jtbd-bundle"}.json`;
};

export const serializeJtbdBundle = (bundle: JtbdBundle): string =>
	JSON.stringify(bundle, null, 2);

export const validateJtbdBundle = (bundle: JtbdBundle): ValidationIssue[] => {
	const issues: ValidationIssue[] = [];
	const seen = new Map<string, number>();
	for (const spec of bundle.jtbds) {
		seen.set(spec.id, (seen.get(spec.id) ?? 0) + 1);
	}
	const ids = new Set(bundle.jtbds.map((spec) => spec.id));

	for (const spec of bundle.jtbds) {
		const label = spec.title || spec.id || "Untitled job";
		if (!spec.id.trim()) {
			issues.push({
				id: `${label}:missing-id`,
				title: `${label} is missing an id`,
				severity: "error",
				jtbdId: spec.id,
			});
		}
		if ((seen.get(spec.id) ?? 0) > 1) {
			issues.push({
				id: `${spec.id}:duplicate-id`,
				title: `${label} has a duplicate id`,
				severity: "error",
				jtbdId: spec.id,
			});
		}
		if (!spec.title?.trim()) {
			issues.push({
				id: `${spec.id}:missing-title`,
				title: `${label} is missing a title`,
				severity: "warning",
				jtbdId: spec.id,
			});
		}
		if (spec.version?.trim() && !isSemver(spec.version)) {
			issues.push({
				id: `${spec.id}:invalid-version`,
				title: `${label} has an invalid semver version`,
				severity: "error",
				jtbdId: spec.id,
			});
		}
		if (!spec.version?.trim()) {
			issues.push({
				id: `${spec.id}:missing-version`,
				title: `${label} has no version`,
				severity: "info",
				jtbdId: spec.id,
			});
		}
		if (currentActors(spec).length === 0) {
			issues.push({
				id: `${spec.id}:missing-actor`,
				title: `${label} has no actors`,
				severity: "error",
				jtbdId: spec.id,
			});
		}
		for (const requiredId of spec.requires ?? []) {
			if (!ids.has(requiredId)) {
				issues.push({
					id: `${spec.id}:missing-dependency:${requiredId}`,
					title: `${label} depends on missing job ${requiredId}`,
					severity: "error",
					jtbdId: spec.id,
				});
			}
			if (requiredId === spec.id) {
				issues.push({
					id: `${spec.id}:self-dependency`,
					title: `${label} depends on itself`,
					severity: "error",
					jtbdId: spec.id,
				});
			}
		}
		if (!spec.description?.trim()) {
			issues.push({
				id: `${spec.id}:missing-description`,
				title: `${label} has no description`,
				severity: "info",
				jtbdId: spec.id,
			});
		}
	}

	return issues;
};

export const JtbdEditor = ({
	bundle,
	onChange,
	withReactFlow = true,
	className,
}: JtbdEditorProps): JSX.Element => {
	const [draftBundle, setDraftBundle] = useState<JtbdBundle>(bundle);
	const [selectedJtbdId, setSelectedJtbdId] = useState<string | null>(null);
	const [selectedDependencyId, setSelectedDependencyId] = useState<string | null>(null);
	const [metadataCollapsed, setMetadataCollapsed] = useState(false);
	const [validationCollapsed, setValidationCollapsed] = useState(false);
	const [validationIssues, setValidationIssues] = useState<ValidationIssue[]>(() =>
		validateJtbdBundle(bundle),
	);
	const [layoutAttempt, setLayoutAttempt] = useState(0);
	const [layoutState, setLayoutState] = useState<LayoutState>({ status: "loading" });
	const [focusJtbdId, setFocusJtbdId] = useState<string | null>(null);
	const [focusRequest, setFocusRequest] = useState(0);

	useEffect(() => {
		setDraftBundle(bundle);
		setSelectedJtbdId(null);
		setSelectedDependencyId(null);
	}, [bundle]);

	useEffect(() => {
		setValidationIssues(validateJtbdBundle(draftBundle));
	}, [draftBundle]);

	useEffect(() => {
		let cancelled = false;
		setLayoutState({ status: "loading" });
		const timeout = window.setTimeout(() => {
			try {
				const layout = layoutJobMap(draftBundle);
				if (!cancelled) {
					setLayoutState({ status: "ready", layout });
				}
			} catch (error) {
				if (!cancelled) {
					setLayoutState({ status: "error", message: messageFromError(error) });
				}
			}
		}, 0);
		return () => {
			cancelled = true;
			window.clearTimeout(timeout);
		};
	}, [draftBundle, layoutAttempt]);

	const selectedSpec = useMemo(
		() => draftBundle.jtbds.find((spec) => spec.id === selectedJtbdId) ?? null,
		[draftBundle.jtbds, selectedJtbdId],
	);

	const parsedDependency = selectedDependencyId
		? parseDependencyId(selectedDependencyId)
		: null;
	const selectedDependencyTarget = parsedDependency
		? draftBundle.jtbds.find((spec) => spec.id === parsedDependency.target) ?? null
		: null;
	const selectedDependency =
		parsedDependency && selectedDependencyTarget
			? selectedDependencyTarget.dependencies?.find(
					(dependency) => dependency.source === parsedDependency.source,
				) ?? {
					source: parsedDependency.source,
					type: "triggers" as const,
					strength: "strong" as const,
					description: "",
				}
			: null;

	const commitBundle = useCallback(
		(nextBundle: JtbdBundle): void => {
			setDraftBundle(nextBundle);
			onChange?.(nextBundle);
		},
		[onChange],
	);

	const updateSelectedSpec = useCallback(
		(updater: (spec: JtbdSpec) => JtbdSpec): void => {
			if (!selectedJtbdId) {
				return;
			}
			commitBundle({
				...draftBundle,
				jtbds: draftBundle.jtbds.map((spec) =>
					spec.id === selectedJtbdId ? updater(spec) : spec,
				),
			});
		},
		[commitBundle, draftBundle, selectedJtbdId],
	);

	const updateSelectedDependency = useCallback(
		(patch: Partial<Omit<JtbdDependency, "source">>): void => {
			if (!parsedDependency) {
				return;
			}
			commitBundle({
				...draftBundle,
				jtbds: draftBundle.jtbds.map((spec) => {
					if (spec.id !== parsedDependency.target) {
						return spec;
					}
					const dependencies = spec.dependencies ?? [];
					const current = dependencies.find(
						(dependency) => dependency.source === parsedDependency.source,
					) ?? { source: parsedDependency.source };
					const nextDependency = { ...current, ...patch };
					const nextDependencies = [
						...dependencies.filter(
							(dependency) => dependency.source !== parsedDependency.source,
						),
						nextDependency,
					];
					const requires = new Set(spec.requires ?? []);
					requires.add(parsedDependency.source);
					return {
						...spec,
						requires: Array.from(requires),
						dependencies: nextDependencies,
					};
				}),
			});
		},
		[commitBundle, draftBundle, parsedDependency],
	);

	const handleAddJob = (): void => {
		const id = uniqueId(draftBundle, `job_${draftBundle.jtbds.length + 1}`);
		const actor =
			draftBundle.shared?.roles?.[0] ?? draftBundle.jtbds[0]?.actor.role ?? "author";
		const nextJob: JtbdSpec = {
			id,
			title: "New job",
			version: "0.1.0",
			actors: [actor],
			domain: draftBundle.project.domain,
			description: "",
			actor: { role: actor },
			situation: "",
			motivation: "",
			outcome: "",
			success_criteria: [],
			data_sensitivity: ["internal"],
		};
		commitBundle({
			...draftBundle,
			jtbds: [...draftBundle.jtbds, nextJob],
		});
		setSelectedJtbdId(id);
		setSelectedDependencyId(null);
		setMetadataCollapsed(false);
	};

	const handleExportJson = (): void => {
		const blob = new Blob([serializeJtbdBundle(draftBundle)], {
			type: "application/json",
		});
		const url = URL.createObjectURL(blob);
		const anchor = document.createElement("a");
		anchor.href = url;
		anchor.download = downloadName(draftBundle);
		document.body.append(anchor);
		anchor.click();
		anchor.remove();
		URL.revokeObjectURL(url);
	};

	const focusIssue = (issue: ValidationIssue): void => {
		if (!issue.jtbdId) {
			return;
		}
		setFocusJtbdId(issue.jtbdId);
		setFocusRequest((value) => value + 1);
		setSelectedJtbdId(issue.jtbdId);
		setSelectedDependencyId(null);
		setMetadataCollapsed(false);
	};

	const revalidate = (): void => {
		setValidationIssues(validateJtbdBundle(draftBundle));
	};

	const domainOptions = selectedSpec
		? optionList(STANDARD_DOMAINS, selectedSpec.domain ?? draftBundle.project.domain)
		: [...STANDARD_DOMAINS];
	const sensitivity = selectedSpec?.data_sensitivity?.[0] ?? "internal";
	const sensitivityOptions = optionList(AUTHORING_DATA_SENSITIVITY, sensitivity);
	const canvasReady = layoutState.status === "ready";
	const showEmptyState = canvasReady && layoutState.layout.nodes.length === 0;

	return (
		<div className={className} data-testid="ff-jtbd-editor" style={styles.shell}>
			<div style={styles.toolbar} aria-label="JTBD editor toolbar">
				<button type="button" onClick={handleAddJob} style={styles.primaryButton}>
					+ Add Job
				</button>
				<button type="button" onClick={handleExportJson} style={styles.button}>
					Export JSON
				</button>
			</div>

			<div style={styles.workspace}>
				<div style={styles.canvasFrame}>
					{layoutState.status === "error" ? (
						<div role="alert" style={styles.errorBanner}>
							<span>{layoutState.message}</span>
							<button
								type="button"
								onClick={() => setLayoutAttempt((value) => value + 1)}
								style={styles.button}
							>
								Retry
							</button>
						</div>
					) : showEmptyState ? (
						<div style={styles.emptyState}>
							<p style={styles.emptyTitle}>No jobs defined yet</p>
							<button type="button" onClick={handleAddJob} style={styles.primaryButton}>
								+ Add Job
							</button>
						</div>
					) : canvasReady ? (
						<JobMap
							bundle={draftBundle}
							withReactFlow={withReactFlow}
							onSelectJtbd={(jtbdId) => {
								setSelectedJtbdId(jtbdId);
								setSelectedDependencyId(null);
								setMetadataCollapsed(false);
							}}
							onSelectDependency={(dependencyId) => {
								setSelectedDependencyId(dependencyId);
								setSelectedJtbdId(null);
							}}
							selectedJtbdId={selectedJtbdId}
							selectedDependencyId={selectedDependencyId}
							focusJtbdId={focusJtbdId}
							focusRequest={focusRequest}
							className="ff-jtbd-editor__map"
						/>
					) : null}
					{layoutState.status === "loading" ? <LoadingOverlay /> : null}
				</div>

				{selectedSpec ? (
					metadataCollapsed ? (
						<button
							type="button"
							onClick={() => setMetadataCollapsed(false)}
							style={styles.sideRail}
						>
							Job
						</button>
					) : (
						<aside aria-label="JTBD metadata editor" style={styles.sidePanel}>
							<div style={styles.panelHeader}>
								<strong>Job metadata</strong>
								<button
									type="button"
									onClick={() => setMetadataCollapsed(true)}
									style={styles.iconButton}
									aria-label="Collapse metadata panel"
								>
									‹
								</button>
							</div>
							<LabeledTextInput
								label="Title"
								value={selectedSpec.title ?? ""}
								onChange={(value) =>
									updateSelectedSpec((spec) => ({ ...spec, title: value }))
								}
							/>
							<LabeledTextInput
								label="Version"
								value={selectedSpec.version ?? ""}
								invalid={Boolean(selectedSpec.version && !isSemver(selectedSpec.version))}
								helpText={
									selectedSpec.version && !isSemver(selectedSpec.version)
										? "Use semver, for example 1.0.0"
										: undefined
								}
								onChange={(value) =>
									updateSelectedSpec((spec) => ({ ...spec, version: value }))
								}
							/>
							<LabeledTextInput
								label="Actors"
								value={currentActors(selectedSpec).join(", ")}
								onChange={(value) =>
									updateSelectedSpec((spec) => {
										const actors = parseList(value);
										return {
											...spec,
											actors,
											actor: {
												...spec.actor,
												role: actors[0] ?? "",
											},
										};
									})
								}
							/>
							<label style={styles.field}>
								<span style={styles.label}>Domain</span>
								<select
									value={selectedSpec.domain ?? draftBundle.project.domain}
									onChange={(event: ChangeEvent<HTMLSelectElement>) =>
										updateSelectedSpec((spec) => ({
											...spec,
											domain: event.target.value,
										}))
									}
									style={styles.input}
								>
									{domainOptions.map((domain) => (
										<option key={domain} value={domain}>
											{domain}
										</option>
									))}
								</select>
							</label>
							<label style={styles.field}>
								<span style={styles.label}>DataSensitivity</span>
								<select
									value={sensitivity}
									onChange={(event: ChangeEvent<HTMLSelectElement>) =>
										updateSelectedSpec((spec) => ({
											...spec,
											data_sensitivity: [event.target.value as DataSensitivity],
										}))
									}
									style={styles.input}
								>
									{sensitivityOptions.map((value) => (
										<option key={value} value={value}>
											{value}
										</option>
									))}
								</select>
							</label>
							<label style={styles.field}>
								<span style={styles.label}>Description</span>
								<textarea
									value={selectedSpec.description ?? ""}
									onChange={(event: ChangeEvent<HTMLTextAreaElement>) =>
										updateSelectedSpec((spec) => ({
											...spec,
											description: event.target.value,
										}))
									}
									rows={5}
									style={styles.textarea}
								/>
							</label>
						</aside>
					)
				) : null}
			</div>

			{parsedDependency && selectedDependency ? (
				<section aria-label="Dependency editor" style={styles.dependencyPanel}>
					<div style={styles.panelHeader}>
						<strong>
							{parsedDependency.source} → {parsedDependency.target}
						</strong>
						<button
							type="button"
							onClick={() => setSelectedDependencyId(null)}
							style={styles.iconButton}
							aria-label="Close dependency editor"
						>
							×
						</button>
					</div>
					<label style={styles.field}>
						<span style={styles.label}>Dependency type</span>
						<select
							value={selectedDependency.type ?? "triggers"}
							onChange={(event: ChangeEvent<HTMLSelectElement>) =>
								updateSelectedDependency({
									type: event.target.value as JtbdDependencyType,
								})
							}
							style={styles.input}
						>
							{DEPENDENCY_TYPES.map((value) => (
								<option key={value} value={value}>
									{value}
								</option>
							))}
						</select>
					</label>
					<label style={styles.field}>
						<span style={styles.label}>Strength</span>
						<select
							value={selectedDependency.strength ?? "strong"}
							onChange={(event: ChangeEvent<HTMLSelectElement>) =>
								updateSelectedDependency({
									strength: event.target.value as JtbdDependencyStrength,
								})
							}
							style={styles.input}
						>
							{DEPENDENCY_STRENGTHS.map((value) => (
								<option key={value} value={value}>
									{value}
								</option>
							))}
						</select>
					</label>
					<LabeledTextInput
						label="Description"
						value={selectedDependency.description ?? ""}
						onChange={(value) => updateSelectedDependency({ description: value })}
					/>
				</section>
			) : null}

			<section style={styles.validationPanel} aria-label="Validation panel">
				<div style={styles.validationHeader}>
					<button
						type="button"
						onClick={() => setValidationCollapsed((value) => !value)}
						style={styles.iconButton}
						aria-label="Toggle validation panel"
					>
						{validationCollapsed ? "▴" : "▾"}
					</button>
					<strong>Validation</strong>
					<button type="button" onClick={revalidate} style={styles.button}>
						Re-validate
					</button>
				</div>
				{validationCollapsed ? null : validationIssues.length === 0 ? (
					<div style={styles.validBanner}>✓ No validation issues</div>
				) : (
					<ul style={styles.issueList}>
						{validationIssues.map((issue) => (
							<li key={issue.id}>
								<button
									type="button"
									onClick={() => focusIssue(issue)}
									style={{
										...styles.issueButton,
										borderLeftColor: severityColor(issue.severity),
									}}
								>
									<span style={styles.severity}>{issue.severity}</span>
									<span>{issue.title}</span>
								</button>
							</li>
						))}
					</ul>
				)}
			</section>
		</div>
	);
};

const LoadingOverlay = (): JSX.Element => (
	<>
		<style>
			{"@keyframes ff-jtbd-spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }"}
		</style>
		<div aria-live="polite" style={styles.loadingOverlay}>
			<div aria-label="Loading layout" style={styles.spinner} />
		</div>
	</>
);

interface LabeledTextInputProps {
	label: string;
	value: string;
	onChange: (value: string) => void;
	invalid?: boolean;
	helpText?: string;
}

const LabeledTextInput = ({
	label,
	value,
	onChange,
	invalid = false,
	helpText,
}: LabeledTextInputProps): JSX.Element => (
	<label style={styles.field}>
		<span style={styles.label}>{label}</span>
		<input
			type="text"
			value={value}
			aria-invalid={invalid ? "true" : "false"}
			onChange={(event: ChangeEvent<HTMLInputElement>) => onChange(event.target.value)}
			style={{
				...styles.input,
				borderColor: invalid ? "#dc2626" : "#94a3b8",
			}}
		/>
		{helpText ? <span style={styles.helpText}>{helpText}</span> : null}
	</label>
);

const optionList = <T extends string>(
	standardOptions: readonly T[],
	current: string,
): string[] => {
	if (!current || standardOptions.includes(current as T)) {
		return [...standardOptions];
	}
	return [current, ...standardOptions];
};

const severityColor = (severity: ValidationSeverity): string => {
	switch (severity) {
		case "error":
			return "#dc2626";
		case "warning":
			return "#d97706";
		case "info":
			return "#2563eb";
	}
};

const styles = {
	shell: {
		position: "relative",
		display: "flex",
		flexDirection: "column",
		width: "100%",
		height: "100%",
		minHeight: 560,
		background: "#f8fafc",
		color: "#0f172a",
		border: "1px solid #cbd5e1",
		fontFamily:
			"Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, sans-serif",
	} satisfies CSSProperties,
	toolbar: {
		display: "flex",
		alignItems: "center",
		gap: 8,
		padding: "10px 12px",
		borderBottom: "1px solid #cbd5e1",
		background: "#ffffff",
	} satisfies CSSProperties,
	workspace: {
		display: "flex",
		flex: 1,
		minHeight: 0,
	} satisfies CSSProperties,
	canvasFrame: {
		position: "relative",
		flex: 1,
		minWidth: 0,
		minHeight: 360,
		overflow: "auto",
		background: "#eef2f7",
	} satisfies CSSProperties,
	sidePanel: {
		width: 320,
		flex: "0 0 320px",
		borderLeft: "1px solid #cbd5e1",
		background: "#ffffff",
		padding: 16,
		overflow: "auto",
		boxSizing: "border-box",
	} satisfies CSSProperties,
	sideRail: {
		width: 44,
		flex: "0 0 44px",
		border: 0,
		borderLeft: "1px solid #cbd5e1",
		background: "#ffffff",
		color: "#334155",
		cursor: "pointer",
		writingMode: "vertical-rl",
		textOrientation: "mixed",
	} satisfies CSSProperties,
	panelHeader: {
		display: "flex",
		alignItems: "center",
		justifyContent: "space-between",
		gap: 8,
		marginBottom: 14,
	} satisfies CSSProperties,
	field: {
		display: "flex",
		flexDirection: "column",
		gap: 6,
		marginBottom: 12,
	} satisfies CSSProperties,
	label: {
		fontSize: 12,
		fontWeight: 700,
		color: "#334155",
	} satisfies CSSProperties,
	input: {
		width: "100%",
		border: "1px solid #94a3b8",
		borderRadius: 6,
		padding: "8px 10px",
		fontSize: 13,
		color: "#0f172a",
		background: "#ffffff",
		boxSizing: "border-box",
	} satisfies CSSProperties,
	textarea: {
		width: "100%",
		border: "1px solid #94a3b8",
		borderRadius: 6,
		padding: "8px 10px",
		fontSize: 13,
		color: "#0f172a",
		background: "#ffffff",
		resize: "vertical",
		boxSizing: "border-box",
	} satisfies CSSProperties,
	helpText: {
		fontSize: 12,
		color: "#dc2626",
	} satisfies CSSProperties,
	button: {
		border: "1px solid #94a3b8",
		borderRadius: 6,
		background: "#ffffff",
		color: "#0f172a",
		padding: "7px 10px",
		fontSize: 13,
		cursor: "pointer",
	} satisfies CSSProperties,
	primaryButton: {
		border: "1px solid #1d4ed8",
		borderRadius: 6,
		background: "#1d4ed8",
		color: "#ffffff",
		padding: "7px 10px",
		fontSize: 13,
		cursor: "pointer",
	} satisfies CSSProperties,
	iconButton: {
		border: "1px solid #cbd5e1",
		borderRadius: 6,
		background: "#ffffff",
		color: "#334155",
		width: 30,
		height: 30,
		cursor: "pointer",
	} satisfies CSSProperties,
	loadingOverlay: {
		position: "absolute",
		inset: 0,
		display: "grid",
		placeItems: "center",
		background: "rgba(248, 250, 252, 0.72)",
		zIndex: 2,
	} satisfies CSSProperties,
	spinner: {
		width: 36,
		height: 36,
		borderRadius: "50%",
		border: "4px solid #bfdbfe",
		borderTopColor: "#1d4ed8",
		animation: "ff-jtbd-spin 900ms linear infinite",
	} satisfies CSSProperties,
	errorBanner: {
		position: "absolute",
		top: 16,
		left: 16,
		right: 16,
		display: "flex",
		alignItems: "center",
		justifyContent: "space-between",
		gap: 12,
		padding: 12,
		border: "1px solid #dc2626",
		borderRadius: 8,
		background: "#fef2f2",
		color: "#991b1b",
		zIndex: 3,
	} satisfies CSSProperties,
	emptyState: {
		position: "absolute",
		inset: 0,
		display: "flex",
		flexDirection: "column",
		alignItems: "center",
		justifyContent: "center",
		gap: 12,
		color: "#334155",
	} satisfies CSSProperties,
	emptyTitle: {
		margin: 0,
		fontSize: 16,
		fontWeight: 700,
	} satisfies CSSProperties,
	dependencyPanel: {
		position: "absolute",
		right: 16,
		bottom: 132,
		width: 320,
		padding: 14,
		border: "1px solid #cbd5e1",
		borderRadius: 8,
		background: "#ffffff",
		boxShadow: "0 12px 32px rgba(15, 23, 42, 0.18)",
		zIndex: 4,
		boxSizing: "border-box",
	} satisfies CSSProperties,
	validationPanel: {
		borderTop: "1px solid #cbd5e1",
		background: "#ffffff",
		padding: 10,
	} satisfies CSSProperties,
	validationHeader: {
		display: "flex",
		alignItems: "center",
		gap: 8,
	} satisfies CSSProperties,
	validBanner: {
		marginTop: 10,
		padding: "10px 12px",
		borderRadius: 6,
		background: "#dcfce7",
		color: "#166534",
		fontWeight: 700,
	} satisfies CSSProperties,
	issueList: {
		display: "grid",
		gap: 6,
		margin: "10px 0 0",
		padding: 0,
		listStyle: "none",
		maxHeight: 140,
		overflow: "auto",
	} satisfies CSSProperties,
	issueButton: {
		display: "flex",
		alignItems: "center",
		gap: 8,
		width: "100%",
		border: "1px solid #e2e8f0",
		borderLeftWidth: 4,
		borderRadius: 6,
		background: "#ffffff",
		color: "#0f172a",
		padding: "8px 10px",
		textAlign: "left",
		cursor: "pointer",
	} satisfies CSSProperties,
	severity: {
		width: 56,
		textTransform: "uppercase",
		fontSize: 11,
		fontWeight: 800,
		color: "#334155",
	} satisfies CSSProperties,
} as const;
