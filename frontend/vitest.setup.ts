import "@testing-library/jest-dom/vitest";

// jsdom has no EventSource. Tests using PriceStreamProvider with override
// still mount the live hook (React requires unconditional hooks), so its
// `new EventSource()` would throw. Stub a no-op class.
class StubEventSource {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSED = 2;
  readyState = 0;
  onopen: ((e: Event) => void) | null = null;
  onmessage: ((e: MessageEvent) => void) | null = null;
  onerror: ((e: Event) => void) | null = null;
  constructor(_url: string) {}
  close() {
    this.readyState = StubEventSource.CLOSED;
  }
}

if (typeof globalThis.EventSource === "undefined") {
  (globalThis as unknown as { EventSource: typeof EventSource }).EventSource =
    StubEventSource as unknown as typeof EventSource;
}
