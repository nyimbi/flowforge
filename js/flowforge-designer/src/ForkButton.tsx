/**
 * ForkButton — E-2 fork operation UI component.
 *
 * Renders a "Fork library" button that opens an inline dialog prompting for a
 * tenant ID.  When the author confirms, the ``onFork`` callback fires with the
 * upstream package string and the supplied tenant ID.
 *
 * The component is intentionally headless-friendly: it holds no network state
 * and makes no fetch calls — the host app is responsible for wiring ``onFork``
 * to the ``flowforge jtbd fork`` API endpoint or CLI.
 *
 * Required RBAC permission on the server side: ``jtbd.fork``.
 *
 * @example
 * ```tsx
 * <ForkButton
 *   upstream="flowforge-jtbd-insurance@2.1.0"
 *   onFork={(upstream, tenant) => api.fork(upstream, tenant)}
 * />
 * ```
 */

import { useState, type JSX } from "react";

export interface ForkButtonProps {
	/** Upstream package reference, e.g. ``"flowforge-jtbd-insurance@2.1.0"``. */
	upstream: string;
	/** Disable the button (e.g. while a fork request is in-flight). */
	disabled?: boolean;
	/**
	 * Called when the author confirms the fork.
	 * @param upstream - The upstream package string as passed in props.
	 * @param tenant   - The tenant ID entered in the dialog.
	 */
	onFork: (upstream: string, tenant: string) => void;
}

/**
 * Fork button with an inline confirmation dialog.
 *
 * Renders as a single ``<button data-testid="fork-btn">`` when closed, and
 * adds a ``<div data-testid="fork-dialog">`` when open.
 */
export const ForkButton = ({
	upstream,
	disabled = false,
	onFork,
}: ForkButtonProps): JSX.Element => {
	const [open, setOpen] = useState(false);
	const [tenant, setTenant] = useState("");
	const [error, setError] = useState<string | null>(null);

	const handleOpen = (): void => {
		setOpen(true);
		setTenant("");
		setError(null);
	};

	const handleCancel = (): void => {
		setOpen(false);
		setTenant("");
		setError(null);
	};

	const handleConfirm = (): void => {
		const trimmed = tenant.trim();
		if (!trimmed) {
			setError("Tenant ID is required.");
			return;
		}
		onFork(upstream, trimmed);
		setOpen(false);
		setTenant("");
		setError(null);
	};

	return (
		<>
			<button
				type="button"
				data-testid="fork-btn"
				disabled={disabled}
				aria-label={`Fork ${upstream}`}
				onClick={handleOpen}
			>
				Fork library
			</button>

			{open ? (
				<div
					role="dialog"
					aria-modal="true"
					aria-label="Fork JTBD library"
					data-testid="fork-dialog"
				>
					<p data-testid="fork-dialog-upstream">
						<strong>Upstream:</strong> {upstream}
					</p>

					<label htmlFor="fork-tenant-input">Tenant ID</label>
					<input
						id="fork-tenant-input"
						data-testid="fork-tenant-input"
						type="text"
						value={tenant}
						placeholder="e.g. acme-corp"
						onChange={(e) => {
							setTenant(e.target.value);
							setError(null);
						}}
					/>

					{error ? (
						<p role="alert" data-testid="fork-dialog-error">
							{error}
						</p>
					) : null}

					<button
						type="button"
						data-testid="fork-confirm-btn"
						onClick={handleConfirm}
					>
						Confirm fork
					</button>
					<button
						type="button"
						data-testid="fork-cancel-btn"
						onClick={handleCancel}
					>
						Cancel
					</button>
				</div>
			) : null}
		</>
	);
};
