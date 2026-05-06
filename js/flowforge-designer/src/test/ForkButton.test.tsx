/**
 * Tests for ForkButton — E-2 fork operation UI component.
 *
 * Covers: render, open/close dialog, tenant validation, onFork callback,
 * disabled state, and aria attributes.
 */

import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

import { ForkButton } from "../ForkButton.js";

const UPSTREAM = "flowforge-jtbd-insurance@2.1.0";

describe("ForkButton", () => {
	it("renders the fork button", () => {
		render(<ForkButton upstream={UPSTREAM} onFork={vi.fn()} />);
		expect(screen.getByTestId("fork-btn")).toBeDefined();
		expect(screen.getByText("Fork library")).toBeDefined();
	});

	it("dialog is hidden by default", () => {
		render(<ForkButton upstream={UPSTREAM} onFork={vi.fn()} />);
		expect(screen.queryByTestId("fork-dialog")).toBeNull();
	});

	it("opens dialog when fork button is clicked", () => {
		render(<ForkButton upstream={UPSTREAM} onFork={vi.fn()} />);
		fireEvent.click(screen.getByTestId("fork-btn"));
		expect(screen.getByTestId("fork-dialog")).toBeDefined();
	});

	it("shows upstream package name in dialog", () => {
		render(<ForkButton upstream={UPSTREAM} onFork={vi.fn()} />);
		fireEvent.click(screen.getByTestId("fork-btn"));
		expect(screen.getByTestId("fork-dialog-upstream").textContent).toContain(UPSTREAM);
	});

	it("cancel button closes dialog without calling onFork", () => {
		const onFork = vi.fn();
		render(<ForkButton upstream={UPSTREAM} onFork={onFork} />);
		fireEvent.click(screen.getByTestId("fork-btn"));
		fireEvent.click(screen.getByTestId("fork-cancel-btn"));
		expect(screen.queryByTestId("fork-dialog")).toBeNull();
		expect(onFork).not.toHaveBeenCalled();
	});

	it("shows error when tenant is empty and confirm is clicked", () => {
		render(<ForkButton upstream={UPSTREAM} onFork={vi.fn()} />);
		fireEvent.click(screen.getByTestId("fork-btn"));
		fireEvent.click(screen.getByTestId("fork-confirm-btn"));
		expect(screen.getByTestId("fork-dialog-error")).toBeDefined();
	});

	it("calls onFork with upstream and tenant when confirmed", () => {
		const onFork = vi.fn();
		render(<ForkButton upstream={UPSTREAM} onFork={onFork} />);
		fireEvent.click(screen.getByTestId("fork-btn"));
		fireEvent.change(screen.getByTestId("fork-tenant-input"), {
			target: { value: "acme-corp" },
		});
		fireEvent.click(screen.getByTestId("fork-confirm-btn"));
		expect(onFork).toHaveBeenCalledOnce();
		expect(onFork).toHaveBeenCalledWith(UPSTREAM, "acme-corp");
	});

	it("closes dialog after successful confirm", () => {
		const onFork = vi.fn();
		render(<ForkButton upstream={UPSTREAM} onFork={onFork} />);
		fireEvent.click(screen.getByTestId("fork-btn"));
		fireEvent.change(screen.getByTestId("fork-tenant-input"), {
			target: { value: "tenant-X" },
		});
		fireEvent.click(screen.getByTestId("fork-confirm-btn"));
		expect(screen.queryByTestId("fork-dialog")).toBeNull();
	});

	it("trims whitespace from tenant ID", () => {
		const onFork = vi.fn();
		render(<ForkButton upstream={UPSTREAM} onFork={onFork} />);
		fireEvent.click(screen.getByTestId("fork-btn"));
		fireEvent.change(screen.getByTestId("fork-tenant-input"), {
			target: { value: "  tenant-padded  " },
		});
		fireEvent.click(screen.getByTestId("fork-confirm-btn"));
		expect(onFork).toHaveBeenCalledWith(UPSTREAM, "tenant-padded");
	});

	it("resets tenant input when dialog is reopened after cancel", () => {
		render(<ForkButton upstream={UPSTREAM} onFork={vi.fn()} />);
		fireEvent.click(screen.getByTestId("fork-btn"));
		fireEvent.change(screen.getByTestId("fork-tenant-input"), {
			target: { value: "draft-tenant" },
		});
		fireEvent.click(screen.getByTestId("fork-cancel-btn"));
		// Reopen.
		fireEvent.click(screen.getByTestId("fork-btn"));
		const input = screen.getByTestId("fork-tenant-input") as HTMLInputElement;
		expect(input.value).toBe("");
	});

	it("disabled button cannot be clicked", () => {
		render(<ForkButton upstream={UPSTREAM} onFork={vi.fn()} disabled />);
		const btn = screen.getByTestId("fork-btn") as HTMLButtonElement;
		expect(btn.disabled).toBe(true);
	});

	it("has accessible aria-label on fork button", () => {
		render(<ForkButton upstream={UPSTREAM} onFork={vi.fn()} />);
		const btn = screen.getByTestId("fork-btn");
		expect(btn.getAttribute("aria-label")).toContain(UPSTREAM);
	});

	it("dialog has role=dialog and aria-modal", () => {
		render(<ForkButton upstream={UPSTREAM} onFork={vi.fn()} />);
		fireEvent.click(screen.getByTestId("fork-btn"));
		const dialog = screen.getByTestId("fork-dialog");
		expect(dialog.getAttribute("role")).toBe("dialog");
		expect(dialog.getAttribute("aria-modal")).toBe("true");
	});
});
