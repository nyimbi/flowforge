/**
 * Tests for CommentThread + ReviewPanel — E-18.
 */

import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

import { CommentThread, extractMentions, type Comment } from "../CommentThread.js";
import { ReviewPanel, type ReviewDecision } from "../ReviewPanel.js";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const NOW = "2026-05-06T03:00:00.000Z";

function makeComment(overrides: Partial<Comment> = {}): Comment {
	return {
		id: "cmt-1",
		author_user_id: "alice",
		body: "This looks good.",
		mentions: [],
		parent_id: null,
		resolved: false,
		deleted: false,
		created_at: NOW,
		...overrides,
	};
}

// ---------------------------------------------------------------------------
// CommentThread — render
// ---------------------------------------------------------------------------

describe("CommentThread", () => {
	it("renders heading with jtbdId and version", () => {
		render(
			<CommentThread
				jtbdId="claim_intake"
				version="1.4.0"
				comments={[]}
				currentUserId="alice"
				onSubmit={vi.fn()}
			/>,
		);
		expect(screen.getByTestId("comment-thread-heading").textContent).toContain(
			"claim_intake",
		);
		expect(screen.getByTestId("comment-thread-heading").textContent).toContain(
			"1.4.0",
		);
	});

	it("shows empty state when no comments", () => {
		render(
			<CommentThread
				jtbdId="x"
				version="1.0.0"
				comments={[]}
				currentUserId="u"
				onSubmit={vi.fn()}
			/>,
		);
		expect(screen.getByTestId("comment-empty")).toBeDefined();
	});

	it("renders comment list when comments present", () => {
		render(
			<CommentThread
				jtbdId="x"
				version="1.0.0"
				comments={[makeComment()]}
				currentUserId="alice"
				onSubmit={vi.fn()}
			/>,
		);
		expect(screen.getByTestId("comment-list")).toBeDefined();
		expect(screen.getByTestId("comment-cmt-1")).toBeDefined();
	});

	it("shows 'You' for currentUser's own comment", () => {
		render(
			<CommentThread
				jtbdId="x"
				version="1.0.0"
				comments={[makeComment({ author_user_id: "alice" })]}
				currentUserId="alice"
				onSubmit={vi.fn()}
			/>,
		);
		expect(screen.getByTestId("comment-author-cmt-1").textContent).toBe("You");
	});

	it("shows author id for other users", () => {
		render(
			<CommentThread
				jtbdId="x"
				version="1.0.0"
				comments={[makeComment({ author_user_id: "bob" })]}
				currentUserId="alice"
				onSubmit={vi.fn()}
			/>,
		);
		expect(screen.getByTestId("comment-author-cmt-1").textContent).toBe("bob");
	});

	it("shows resolved badge when resolved", () => {
		render(
			<CommentThread
				jtbdId="x"
				version="1.0.0"
				comments={[makeComment({ resolved: true })]}
				currentUserId="alice"
				onSubmit={vi.fn()}
			/>,
		);
		expect(screen.getByTestId("comment-resolved-badge-cmt-1")).toBeDefined();
	});

	it("does not show reply/resolve buttons for resolved comment", () => {
		render(
			<CommentThread
				jtbdId="x"
				version="1.0.0"
				comments={[makeComment({ resolved: true })]}
				currentUserId="alice"
				onSubmit={vi.fn()}
				onResolve={vi.fn()}
			/>,
		);
		expect(screen.queryByTestId("reply-btn-cmt-1")).toBeNull();
		expect(screen.queryByTestId("resolve-btn-cmt-1")).toBeNull();
	});

	it("calls onSubmit when compose submitted", () => {
		const onSubmit = vi.fn();
		render(
			<CommentThread
				jtbdId="x"
				version="1.0.0"
				comments={[]}
				currentUserId="alice"
				onSubmit={onSubmit}
			/>,
		);
		fireEvent.change(screen.getByTestId("compose-input"), {
			target: { value: "Great spec!" },
		});
		fireEvent.click(screen.getByTestId("compose-submit-btn"));
		expect(onSubmit).toHaveBeenCalledOnce();
		expect(onSubmit).toHaveBeenCalledWith("Great spec!", undefined);
	});

	it("shows error if body empty and submit clicked", () => {
		render(
			<CommentThread
				jtbdId="x"
				version="1.0.0"
				comments={[]}
				currentUserId="alice"
				onSubmit={vi.fn()}
			/>,
		);
		fireEvent.click(screen.getByTestId("compose-submit-btn"));
		expect(screen.getByTestId("compose-error")).toBeDefined();
	});

	it("reply button sets replying-to context", () => {
		render(
			<CommentThread
				jtbdId="x"
				version="1.0.0"
				comments={[makeComment()]}
				currentUserId="alice"
				onSubmit={vi.fn()}
			/>,
		);
		fireEvent.click(screen.getByTestId("reply-btn-cmt-1"));
		expect(screen.getByTestId("replying-to")).toBeDefined();
	});

	it("cancel reply clears replying-to", () => {
		render(
			<CommentThread
				jtbdId="x"
				version="1.0.0"
				comments={[makeComment()]}
				currentUserId="alice"
				onSubmit={vi.fn()}
			/>,
		);
		fireEvent.click(screen.getByTestId("reply-btn-cmt-1"));
		fireEvent.click(screen.getByTestId("cancel-reply-btn"));
		expect(screen.queryByTestId("replying-to")).toBeNull();
	});

	it("onResolve called when resolve button clicked", () => {
		const onResolve = vi.fn();
		render(
			<CommentThread
				jtbdId="x"
				version="1.0.0"
				comments={[makeComment()]}
				currentUserId="alice"
				onSubmit={vi.fn()}
				onResolve={onResolve}
			/>,
		);
		fireEvent.click(screen.getByTestId("resolve-btn-cmt-1"));
		expect(onResolve).toHaveBeenCalledWith("cmt-1");
	});

	it("renders replies under parent comment", () => {
		const reply = makeComment({
			id: "cmt-2",
			author_user_id: "bob",
			body: "Thanks!",
			parent_id: "cmt-1",
		});
		render(
			<CommentThread
				jtbdId="x"
				version="1.0.0"
				comments={[makeComment(), reply]}
				currentUserId="alice"
				onSubmit={vi.fn()}
			/>,
		);
		expect(screen.getByTestId("replies-cmt-1")).toBeDefined();
		expect(screen.getByTestId("reply-body-cmt-2").textContent).toBe("Thanks!");
	});

	it("deleted comments not shown", () => {
		render(
			<CommentThread
				jtbdId="x"
				version="1.0.0"
				comments={[makeComment({ deleted: true })]}
				currentUserId="alice"
				onSubmit={vi.fn()}
			/>,
		);
		expect(screen.queryByTestId("comment-cmt-1")).toBeNull();
	});
});

// ---------------------------------------------------------------------------
// extractMentions
// ---------------------------------------------------------------------------

describe("extractMentions", () => {
	it("extracts single mention", () => {
		expect(extractMentions("Hey @alice!")).toEqual(["alice"]);
	});

	it("extracts multiple mentions", () => {
		expect(extractMentions("@alice and @bob")).toEqual(["alice", "bob"]);
	});

	it("deduplicates mentions", () => {
		expect(extractMentions("@alice @alice")).toEqual(["alice"]);
	});

	it("returns empty for no mentions", () => {
		expect(extractMentions("no mentions")).toEqual([]);
	});
});

// ---------------------------------------------------------------------------
// ReviewPanel
// ---------------------------------------------------------------------------

describe("ReviewPanel", () => {
	it("renders heading", () => {
		render(
			<ReviewPanel jtbdId="claim_intake" version="1.4.0" onSubmit={vi.fn()} />,
		);
		expect(screen.getByTestId("review-heading").textContent).toContain(
			"claim_intake",
		);
	});

	it("renders three decision radios", () => {
		render(
			<ReviewPanel jtbdId="x" version="1.0.0" onSubmit={vi.fn()} />,
		);
		expect(screen.getByTestId("decision-radio-approve")).toBeDefined();
		expect(screen.getByTestId("decision-radio-reject")).toBeDefined();
		expect(screen.getByTestId("decision-radio-request_changes")).toBeDefined();
	});

	it("shows error if submit without selecting decision", () => {
		render(
			<ReviewPanel jtbdId="x" version="1.0.0" onSubmit={vi.fn()} />,
		);
		fireEvent.click(screen.getByTestId("review-submit-btn"));
		expect(screen.getByTestId("review-error")).toBeDefined();
	});

	it("calls onSubmit with decision when submitted", () => {
		const onSubmit = vi.fn();
		render(<ReviewPanel jtbdId="x" version="1.0.0" onSubmit={onSubmit} />);
		fireEvent.click(screen.getByTestId("decision-radio-approve"));
		fireEvent.click(screen.getByTestId("review-submit-btn"));
		expect(onSubmit).toHaveBeenCalledOnce();
		expect(onSubmit).toHaveBeenCalledWith("approve", undefined);
	});

	it("passes body to onSubmit when provided", () => {
		const onSubmit = vi.fn();
		render(<ReviewPanel jtbdId="x" version="1.0.0" onSubmit={onSubmit} />);
		fireEvent.click(screen.getByTestId("decision-radio-reject"));
		fireEvent.change(screen.getByTestId("review-body-input"), {
			target: { value: "Missing audit stage." },
		});
		fireEvent.click(screen.getByTestId("review-submit-btn"));
		expect(onSubmit).toHaveBeenCalledWith("reject", "Missing audit stage.");
	});

	it("shows decision preview after selecting", () => {
		render(<ReviewPanel jtbdId="x" version="1.0.0" onSubmit={vi.fn()} />);
		fireEvent.click(screen.getByTestId("decision-radio-approve"));
		expect(screen.getByTestId("review-decision-preview")).toBeDefined();
		expect(screen.getByTestId("review-selected-decision").textContent).toBe(
			"Approve",
		);
	});

	it("resets after submit", () => {
		render(<ReviewPanel jtbdId="x" version="1.0.0" onSubmit={vi.fn()} />);
		fireEvent.click(screen.getByTestId("decision-radio-approve"));
		fireEvent.click(screen.getByTestId("review-submit-btn"));
		// Decision preview gone after reset.
		expect(screen.queryByTestId("review-decision-preview")).toBeNull();
	});

	it("disabled state disables submit button", () => {
		render(
			<ReviewPanel jtbdId="x" version="1.0.0" onSubmit={vi.fn()} disabled />,
		);
		const btn = screen.getByTestId("review-submit-btn") as HTMLButtonElement;
		expect(btn.disabled).toBe(true);
	});
});
