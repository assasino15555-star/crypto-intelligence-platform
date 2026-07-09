import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import WalletForm from "@/components/WalletForm";

function withProviders(node: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("WalletForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("rejects non-EVM addresses", async () => {
    const onSubmit = vi.fn();
    render(withProviders(<WalletForm onSubmit={onSubmit} loading={false} error={null} />));
    const input = screen.getByPlaceholderText("0x…");
    fireEvent.change(input, { target: { value: "not-an-address" } });
    fireEvent.click(screen.getByRole("button", { name: /add wallet/i }));
    await waitFor(() => expect(screen.getByText(/40-hex-char EVM/i)).toBeInTheDocument());
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("accepts valid EVM address", async () => {
    const onSubmit = vi.fn();
    render(withProviders(<WalletForm onSubmit={onSubmit} loading={false} error={null} />));
    fireEvent.change(screen.getByPlaceholderText("0x…"), {
      target: { value: "0x" + "ab".repeat(20) },
    });
    fireEvent.click(screen.getByRole("button", { name: /add wallet/i }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit.mock.calls[0][0]).toMatchObject({
      chain: "ethereum",
      address: "0x" + "ab".repeat(20),
    });
  });

  it("renders backend error", () => {
    render(
      withProviders(<WalletForm onSubmit={() => {}} loading={false} error={new Error("conflict")} />)
    );
    expect(screen.getByText("conflict")).toBeInTheDocument();
  });
});
