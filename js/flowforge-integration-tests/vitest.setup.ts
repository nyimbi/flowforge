import "@testing-library/jest-dom";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

if (typeof document === "undefined") {
	// MSW's cookie store probes localStorage during import. In Node 22, that
	// getter emits an ExperimentalWarning unless --localstorage-file is set.
	const descriptor = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
	if (descriptor?.configurable && typeof descriptor.get === "function") {
		delete (globalThis as { localStorage?: unknown }).localStorage;
	}
}

afterEach(() => {
	cleanup();
});
