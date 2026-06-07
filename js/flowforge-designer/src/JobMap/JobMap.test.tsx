/**
 * Tests for JobMap — v0.4.0 E2 swimlane component.
 *
 * Covers: renders cards, groups by actor.role, onSelect called on click.
 */

import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

import { JobMap } from "../JobMap/JobMap.js";

const JTBDS = [
	{ id: "jtbd-1", title: "Submit claim", actor: { role: "Claimant" }, domain: "insurance" },
	{ id: "jtbd-2", title: "Approve claim", actor: { role: "Adjuster" }, domain: "insurance" },
	{ id: "jtbd-3", title: "File appeal", actor: { role: "Claimant" }, domain: "insurance" },
	{ id: "jtbd-4", title: "Audit claim", actor: { role: "Auditor" }, domain: "compliance" },
];

describe("JobMap", () => {
	it("renders the job map container", () => {
		render(<JobMap jtbds={JTBDS} />);
		expect(screen.getByTestId("ff-job-map")).toBeDefined();
	});

	it("renders a card for each JTBD", () => {
		render(<JobMap jtbds={JTBDS} />);
		for (const jtbd of JTBDS) {
			expect(screen.getByTestId(`ff-job-map-card-${jtbd.id}`)).toBeDefined();
		}
	});

	it("renders card titles", () => {
		render(<JobMap jtbds={JTBDS} />);
		expect(screen.getByText("Submit claim")).toBeDefined();
		expect(screen.getByText("Approve claim")).toBeDefined();
		expect(screen.getByText("Audit claim")).toBeDefined();
	});

	it("creates one lane per unique actor.role", () => {
		render(<JobMap jtbds={JTBDS} />);
		expect(screen.getByTestId("ff-job-map-lane-Claimant")).toBeDefined();
		expect(screen.getByTestId("ff-job-map-lane-Adjuster")).toBeDefined();
		expect(screen.getByTestId("ff-job-map-lane-Auditor")).toBeDefined();
	});

	it("groups cards into the correct swimlane", () => {
		render(<JobMap jtbds={JTBDS} />);
		const claimantLane = screen.getByTestId("ff-job-map-lane-Claimant");
		// Both Claimant JTBDs appear inside the Claimant lane.
		expect(claimantLane.querySelector('[data-testid="ff-job-map-card-jtbd-1"]')).not.toBeNull();
		expect(claimantLane.querySelector('[data-testid="ff-job-map-card-jtbd-3"]')).not.toBeNull();
		// Adjuster's card is NOT in the Claimant lane.
		expect(claimantLane.querySelector('[data-testid="ff-job-map-card-jtbd-2"]')).toBeNull();
	});

	it("calls onSelect with the JTBD id when a card is clicked", () => {
		const onSelect = vi.fn();
		render(<JobMap jtbds={JTBDS} onSelect={onSelect} />);
		fireEvent.click(screen.getByTestId("ff-job-map-card-jtbd-2"));
		expect(onSelect).toHaveBeenCalledOnce();
		expect(onSelect).toHaveBeenCalledWith("jtbd-2");
	});

	it("calls onSelect for the correct id regardless of lane", () => {
		const onSelect = vi.fn();
		render(<JobMap jtbds={JTBDS} onSelect={onSelect} />);
		fireEvent.click(screen.getByTestId("ff-job-map-card-jtbd-4"));
		expect(onSelect).toHaveBeenCalledWith("jtbd-4");
	});

	it("does not throw when onSelect is not provided", () => {
		render(<JobMap jtbds={JTBDS} />);
		// Click should not throw.
		fireEvent.click(screen.getByTestId("ff-job-map-card-jtbd-1"));
	});

	it("renders empty state without crashing when jtbds is empty", () => {
		render(<JobMap jtbds={[]} />);
		expect(screen.getByTestId("ff-job-map")).toBeDefined();
	});

	it("renders domain text inside each card", () => {
		render(<JobMap jtbds={JTBDS} />);
		const card = screen.getByTestId("ff-job-map-card-jtbd-4");
		expect(card.textContent).toContain("compliance");
	});

	it("lane header contains the role name", () => {
		render(<JobMap jtbds={JTBDS} />);
		const lane = screen.getByTestId("ff-job-map-lane-Adjuster");
		expect(lane.textContent).toContain("Adjuster");
	});
});
