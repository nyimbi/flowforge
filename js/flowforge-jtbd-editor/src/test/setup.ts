import "@testing-library/jest-dom/vitest";

// Polyfill ResizeObserver for reactflow / measurement code paths under
// happy-dom. The same polyfill is used by flowforge-designer; mirroring
// it keeps the two test environments consistent.
class ResizeObserverPolyfill {
	observe(): void {}
	unobserve(): void {}
	disconnect(): void {}
}

if (typeof globalThis.ResizeObserver === "undefined") {
	(globalThis as unknown as { ResizeObserver: typeof ResizeObserverPolyfill }).ResizeObserver =
		ResizeObserverPolyfill;
}

if (typeof (globalThis as unknown as { DOMMatrixReadOnly?: unknown }).DOMMatrixReadOnly === "undefined") {
	(globalThis as unknown as { DOMMatrixReadOnly: unknown }).DOMMatrixReadOnly = class {
		m22 = 1;
	};
}
