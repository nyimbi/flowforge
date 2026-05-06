/**
 * JobMapAnimation — replay controls + animated overlay over `JobMap`.
 *
 * Drives the `<JobMap>` component with `firedIds` / `activeIds` derived
 * from a step-through of a `Trace`. Provides:
 *
 *   * Play / pause / reset.
 *   * Step forward / step back.
 *   * Replay slider for direct seeks.
 *   * Live status read-out (current step + label).
 *   * Optional `onStepChange` callback for callers that want to hook
 *     a side panel into the active step.
 *
 * The component owns no business logic — every state transition runs
 * through the pure `animationReducer` in `./animation.ts`. The
 * `setInterval` tick is the only side-effect, and it cancels on
 * unmount + on every pause/play/reset transition.
 *
 * Tests rely on `withReactFlow={false}` to render the SVG fallback so
 * happy-dom can assert the highlighted node + slider state without
 * pulling in reactflow's measurement path. `vi.useFakeTimers()` is
 * what drives the play loop forward in tests.
 */

import {
	useCallback,
	useEffect,
	useMemo,
	useReducer,
	useRef,
	type ChangeEvent,
	type JSX,
} from "react";

import { JobMap, type JobMapProps } from "./JobMap.js";
import {
	animationReducer,
	initialAnimationState,
	stepLabel,
	type AnimationAction,
	type AnimationState,
} from "./animation.js";
import { buildDefaultTrace } from "./trace.js";
import type { Trace } from "./trace.js";
import type { JtbdBundle } from "./types.js";

export interface JobMapAnimationProps
	extends Omit<JobMapProps, "firedIds" | "activeIds"> {
	bundle: JtbdBundle;
	/** Override the default topological trace. Useful for replaying a
	 * captured execution log. */
	trace?: Trace;
	/** Milliseconds between play-loop ticks. Default 600ms — slow
	 * enough to follow visually, fast enough to feel responsive. */
	tickMs?: number;
	/** Called when the active step index changes. */
	onStepChange?: (state: AnimationState) => void;
	/** When true, autoplay on mount. */
	autoplay?: boolean;
}

interface ReducerState extends AnimationState {
	trace: Trace;
}

type ReducerAction = AnimationAction | { kind: "set_trace"; trace: Trace };

const wrappedReducer = (
	state: ReducerState,
	action: ReducerAction,
): ReducerState => {
	if (action.kind === "set_trace") {
		// Switching traces resets the animation — anything else gets
		// confusing fast (a partially-fired trace replayed against a
		// new step list rarely lines up).
		return { ...initialAnimationState(), trace: action.trace };
	}
	const next = animationReducer(state, action, state.trace);
	return { ...next, trace: state.trace };
};

const initialReducerState = (trace: Trace): ReducerState => ({
	...initialAnimationState(),
	trace,
});

export const JobMapAnimation = ({
	bundle,
	trace: traceOverride,
	tickMs = 600,
	onStepChange,
	autoplay = false,
	withReactFlow = true,
	className,
	onSelectJtbd,
}: JobMapAnimationProps): JSX.Element => {
	const trace = useMemo<Trace>(
		() => traceOverride ?? buildDefaultTrace(bundle),
		[bundle, traceOverride],
	);

	const [state, dispatch] = useReducer(
		wrappedReducer,
		trace,
		initialReducerState,
	);

	// Re-seed the reducer when the trace identity changes.
	useEffect(() => {
		dispatch({ kind: "set_trace", trace });
	}, [trace]);

	// Notify the parent when the active step changes.
	const lastNotifiedRef = useRef<number>(state.currentIndex);
	useEffect(() => {
		if (onStepChange && lastNotifiedRef.current !== state.currentIndex) {
			lastNotifiedRef.current = state.currentIndex;
			onStepChange(state);
		}
	}, [state, onStepChange]);

	// Play-loop timer.
	useEffect(() => {
		if (!state.playing) {
			return undefined;
		}
		const handle = setInterval(() => {
			dispatch({ kind: "step_forward" });
		}, tickMs);
		return () => {
			clearInterval(handle);
		};
	}, [state.playing, tickMs]);

	// Trigger autoplay once on mount when requested.
	const autoplayedRef = useRef(false);
	useEffect(() => {
		if (autoplay && !autoplayedRef.current && trace.steps.length > 0) {
			autoplayedRef.current = true;
			dispatch({ kind: "play" });
		}
	}, [autoplay, trace]);

	const handlePlayPause = useCallback((): void => {
		dispatch({ kind: state.playing ? "pause" : "play" });
	}, [state.playing]);

	const handleReset = useCallback((): void => {
		dispatch({ kind: "reset" });
	}, []);

	const handleStepForward = useCallback((): void => {
		dispatch({ kind: "step_forward" });
	}, []);

	const handleStepBack = useCallback((): void => {
		dispatch({ kind: "step_back" });
	}, []);

	const handleSeek = useCallback((event: ChangeEvent<HTMLInputElement>): void => {
		const value = Number.parseInt(event.target.value, 10);
		if (!Number.isNaN(value)) {
			dispatch({ kind: "seek", index: value });
		}
	}, []);

	const totalSteps = trace.steps.length;
	const atEnd = state.currentIndex >= totalSteps - 1;
	const atStart = state.currentIndex <= -1;
	const currentStep = state.currentIndex >= 0
		? trace.steps[state.currentIndex]
		: undefined;

	return (
		<div
			data-testid="ff-jobmap-animation"
			className={className}
			style={{ display: "flex", flexDirection: "column", gap: 8 }}
		>
			<div
				data-testid="ff-jobmap-animation-controls"
				role="toolbar"
				aria-label="JobMap animation controls"
				style={{ display: "flex", gap: 8, alignItems: "center" }}
			>
				<button
					type="button"
					data-testid="ff-jobmap-animation-play"
					onClick={handlePlayPause}
					disabled={totalSteps === 0}
					aria-pressed={state.playing}
				>
					{state.playing ? "Pause" : "Play"}
				</button>
				<button
					type="button"
					data-testid="ff-jobmap-animation-step-back"
					onClick={handleStepBack}
					disabled={atStart}
					aria-label="Step back"
				>
					‹ Back
				</button>
				<button
					type="button"
					data-testid="ff-jobmap-animation-step-forward"
					onClick={handleStepForward}
					disabled={atEnd}
					aria-label="Step forward"
				>
					Forward ›
				</button>
				<button
					type="button"
					data-testid="ff-jobmap-animation-reset"
					onClick={handleReset}
					disabled={atStart}
					aria-label="Reset animation"
				>
					Reset
				</button>
				<label
					style={{ display: "flex", gap: 6, alignItems: "center", flex: 1 }}
				>
					<span style={{ fontSize: 12, color: "#475569" }}>Step</span>
					<input
						type="range"
						data-testid="ff-jobmap-animation-slider"
						aria-label="Animation step slider"
						min={-1}
						max={Math.max(totalSteps - 1, 0)}
						step={1}
						value={state.currentIndex}
						onChange={handleSeek}
						disabled={totalSteps === 0}
						style={{ flex: 1 }}
					/>
					<span
						data-testid="ff-jobmap-animation-step-label"
						style={{ fontSize: 12, color: "#0f172a", minWidth: 80 }}
					>
						{state.currentIndex < 0
							? "—"
							: `${state.currentIndex + 1}/${totalSteps}`}
					</span>
				</label>
			</div>
			<div
				data-testid="ff-jobmap-animation-status"
				style={{ fontSize: 12, color: "#0f172a" }}
			>
				{currentStep ? `Active: ${stepLabel(currentStep)}` : "Idle"}
			</div>
			<JobMap
				bundle={bundle}
				withReactFlow={withReactFlow}
				onSelectJtbd={onSelectJtbd}
				firedIds={state.firedIds}
				activeIds={state.activeIds}
			/>
		</div>
	);
};
