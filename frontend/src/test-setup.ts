import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// RTL does not auto-detect Vitest's afterEach — register cleanup explicitly.
afterEach(() => {
  cleanup();
});

/**
 * jsdom does not implement EventSource. Provide a no-op stub so that
 * usePriceStream (always mounted by PriceStreamProvider) does not throw.
 * Tests that use PriceStreamProvider pass an `override` prop so the stub
 * data is never actually used.
 */
class MockEventSource {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSED = 2;
  readyState = MockEventSource.CONNECTING;
  onopen: (() => void) | null = null;
  onmessage: ((e: MessageEvent) => void) | null = null;
  onerror: ((e: Event) => void) | null = null;
  constructor(public url: string) {}
  close() {
    this.readyState = MockEventSource.CLOSED;
  }
  addEventListener() {}
  removeEventListener() {}
  dispatchEvent() {
    return false;
  }
}

Object.defineProperty(globalThis, "EventSource", {
  value: MockEventSource,
  writable: true,
});
