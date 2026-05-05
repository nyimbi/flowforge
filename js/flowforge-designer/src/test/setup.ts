import "@testing-library/jest-dom/vitest";

// Polyfill ResizeObserver for reactflow / measurement code paths under happy-dom.
class ResizeObserverPolyfill {
	observe(): void {}
	unobserve(): void {}
	disconnect(): void {}
}

if (typeof globalThis.ResizeObserver === "undefined") {
	(globalThis as unknown as { ResizeObserver: typeof ResizeObserverPolyfill }).ResizeObserver =
		ResizeObserverPolyfill;
}

// happy-dom does not implement DOMMatrix / getBBox; reactflow internals only touch them
// when nodes are mounted to a real flow; our unit tests assert headless store behavior
// and lightweight rendering so the polyfills below are sufficient.
if (typeof (globalThis as unknown as { DOMMatrixReadOnly?: unknown }).DOMMatrixReadOnly === "undefined") {
	(globalThis as unknown as { DOMMatrixReadOnly: unknown }).DOMMatrixReadOnly = class {
		m22 = 1;
	};
}
