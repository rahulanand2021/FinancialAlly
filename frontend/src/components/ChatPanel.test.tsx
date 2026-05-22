import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { PriceStreamProvider } from "@/hooks/PriceStreamContext";
import { PortfolioProvider } from "@/hooks/PortfolioContext";
import ChatPanel from "./ChatPanel";

function renderChat() {
  return render(
    <PriceStreamProvider override={{ prices: {}, history: {}, status: "connected" }}>
      <PortfolioProvider>
        <ChatPanel />
      </PortfolioProvider>
    </PriceStreamProvider>,
  );
}

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.endsWith("/api/portfolio")) {
        return new Response(
          JSON.stringify({ cash_balance: 10000, total_value: 10000, positions: [] }),
          { status: 200 },
        );
      }
      if (url.endsWith("/api/chat") && init?.method === "POST") {
        const payload = JSON.parse(init?.body as string);
        // Mirror the backend contract: request uses { message }, response
        // returns { message, actions: [...] }.
        expect(payload).toHaveProperty("message");
        return new Response(
          JSON.stringify({
            message: "Bought 5 AAPL for you.",
            actions: [
              {
                type: "trade",
                status: "ok",
                ticker: "AAPL",
                side: "buy",
                quantity: 5,
                price: 192.34,
              },
            ],
          }),
          { status: 200 },
        );
      }
      return new Response("{}", { status: 200 });
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ChatPanel", () => {
  it("renders empty-state copy initially", async () => {
    renderChat();
    expect(await screen.findByText(/Ask FinAlly/i)).toBeInTheDocument();
  });

  it("posts a message and renders the assistant reply with action chips", async () => {
    renderChat();
    const input = await screen.findByPlaceholderText("Ask FinAlly...");
    fireEvent.change(input, { target: { value: "buy me some AAPL" } });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => {
      expect(screen.getByText("buy me some AAPL")).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.getByText("Bought 5 AAPL for you.")).toBeInTheDocument();
    });
    expect(screen.getByText("Bought 5 AAPL")).toBeInTheDocument();
  });
});
