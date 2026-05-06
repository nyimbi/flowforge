/**
 * CommentThread — E-18 comments UI component.
 *
 * Renders a JTBD comment thread: the list of existing comments, a compose
 * box with @mention support, and resolve/reply controls.
 *
 * The component is intentionally headless: it holds no network state.
 * The host app wires ``onSubmit``, ``onResolve``, and ``onReply`` to the
 * ``/jtbd/{id}/comments`` API endpoints.
 *
 * Required RBAC permission for commenting: ``jtbd.comment``.
 *
 * @example
 * ```tsx
 * <CommentThread
 *   jtbdId="claim_intake"
 *   version="1.4.0"
 *   comments={comments}
 *   currentUserId="alice"
 *   onSubmit={(body, parentId) => api.postComment(body, parentId)}
 *   onResolve={(commentId) => api.resolveComment(commentId)}
 * />
 * ```
 */

import { useState, type JSX } from "react";

/** A single comment as returned by the API. */
export interface Comment {
	id: string;
	author_user_id: string;
	body: string;
	mentions: string[];
	parent_id: string | null;
	resolved: boolean;
	deleted: boolean;
	created_at: string;
}

export interface CommentThreadProps {
	jtbdId: string;
	version: string;
	comments: Comment[];
	/** The logged-in user's id — used to label "You" and control resolve. */
	currentUserId: string;
	/** Called when a new comment (or reply) is submitted. */
	onSubmit: (body: string, parentId?: string) => void;
	/** Called when a comment thread is marked resolved. */
	onResolve?: (commentId: string) => void;
	/** Disable all inputs (e.g., while a request is in-flight). */
	disabled?: boolean;
}

/** Extract ``@mention`` tokens from a body string. */
function extractMentions(body: string): string[] {
	const seen = new Set<string>();
	const out: string[] = [];
	for (const m of body.matchAll(/@([\w.-]+)/g)) {
		if (!seen.has(m[1])) {
			seen.add(m[1]);
			out.push(m[1]);
		}
	}
	return out;
}

export const CommentThread = ({
	jtbdId,
	version,
	comments,
	currentUserId,
	onSubmit,
	onResolve,
	disabled = false,
}: CommentThreadProps): JSX.Element => {
	const [body, setBody] = useState("");
	const [replyTo, setReplyTo] = useState<string | null>(null);
	const [error, setError] = useState<string | null>(null);

	// Root comments only; replies are filtered inline.
	const roots = comments.filter((c) => c.parent_id === null && !c.deleted);

	const getReplies = (parentId: string): Comment[] =>
		comments.filter((c) => c.parent_id === parentId && !c.deleted);

	const handleSubmit = (): void => {
		const trimmed = body.trim();
		if (!trimmed) {
			setError("Comment body cannot be empty.");
			return;
		}
		onSubmit(trimmed, replyTo ?? undefined);
		setBody("");
		setReplyTo(null);
		setError(null);
	};

	return (
		<div data-testid="comment-thread" aria-label={`Comments for ${jtbdId}@${version}`}>
			<h3 data-testid="comment-thread-heading">
				Comments — {jtbdId}@{version}
			</h3>

			{roots.length === 0 ? (
				<p data-testid="comment-empty">No comments yet.</p>
			) : (
				<ul data-testid="comment-list" aria-label="Comment list">
					{roots.map((comment) => (
						<li key={comment.id} data-testid={`comment-${comment.id}`}>
							<article>
								<header>
									<strong data-testid={`comment-author-${comment.id}`}>
										{comment.author_user_id === currentUserId
											? "You"
											: comment.author_user_id}
									</strong>{" "}
									<time dateTime={comment.created_at}>
										{new Date(comment.created_at).toLocaleString()}
									</time>
									{comment.resolved ? (
										<span
											data-testid={`comment-resolved-badge-${comment.id}`}
											aria-label="Resolved"
										>
											{" "}
											✓ Resolved
										</span>
									) : null}
								</header>

								<p data-testid={`comment-body-${comment.id}`}>{comment.body}</p>

								{comment.mentions.length > 0 ? (
									<p data-testid={`comment-mentions-${comment.id}`}>
										Mentions:{" "}
										{comment.mentions.map((m) => `@${m}`).join(", ")}
									</p>
								) : null}

								<footer>
									{!comment.resolved ? (
										<button
											type="button"
											data-testid={`reply-btn-${comment.id}`}
											disabled={disabled}
											onClick={() => {
												setReplyTo(comment.id);
												setBody("");
											}}
										>
											Reply
										</button>
									) : null}
									{!comment.resolved && onResolve ? (
										<button
											type="button"
											data-testid={`resolve-btn-${comment.id}`}
											disabled={disabled}
											onClick={() => onResolve(comment.id)}
										>
											Mark resolved
										</button>
									) : null}
								</footer>

								{/* Replies */}
								{getReplies(comment.id).length > 0 ? (
									<ul
										data-testid={`replies-${comment.id}`}
										aria-label={`Replies to ${comment.id}`}
									>
										{getReplies(comment.id).map((reply) => (
											<li
												key={reply.id}
												data-testid={`reply-${reply.id}`}
											>
												<strong>
													{reply.author_user_id === currentUserId
														? "You"
														: reply.author_user_id}
												</strong>
												:{" "}
												<span data-testid={`reply-body-${reply.id}`}>
													{reply.body}
												</span>
											</li>
										))}
									</ul>
								) : null}
							</article>
						</li>
					))}
				</ul>
			)}

			{/* Compose box */}
			<div data-testid="compose-box">
				{replyTo ? (
					<p data-testid="replying-to">
						Replying to comment {replyTo}{" "}
						<button
							type="button"
							data-testid="cancel-reply-btn"
							onClick={() => setReplyTo(null)}
						>
							Cancel
						</button>
					</p>
				) : null}

				<label htmlFor="comment-compose-input">Add a comment</label>
				<textarea
					id="comment-compose-input"
					data-testid="compose-input"
					value={body}
					disabled={disabled}
					placeholder="Type your comment… use @user to mention someone."
					onChange={(e) => {
						setBody(e.target.value);
						setError(null);
					}}
				/>

				{error ? (
					<p role="alert" data-testid="compose-error">
						{error}
					</p>
				) : null}

				<button
					type="button"
					data-testid="compose-submit-btn"
					disabled={disabled}
					onClick={handleSubmit}
				>
					{replyTo ? "Submit reply" : "Submit comment"}
				</button>
			</div>
		</div>
	);
};

export { extractMentions };
