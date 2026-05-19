const descriptor = Object.getOwnPropertyDescriptor(globalThis, "localStorage");

if (descriptor?.configurable && typeof descriptor.get === "function") {
  // MSW's cookie store probes localStorage during import. In Node 22, that
  // getter emits an ExperimentalWarning unless --localstorage-file is set.
  delete (globalThis as { localStorage?: unknown }).localStorage;
}
