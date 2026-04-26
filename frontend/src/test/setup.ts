import "@testing-library/jest-dom";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}

// React Flow reads these browser APIs even in simple render tests.
if (!globalThis.ResizeObserver) {
  globalThis.ResizeObserver = ResizeObserverMock as typeof ResizeObserver;
}

if (!globalThis.DOMMatrixReadOnly) {
  globalThis.DOMMatrixReadOnly = class DOMMatrixReadOnlyMock {} as typeof DOMMatrixReadOnly;
}

afterEach(() => {
  cleanup();
});
