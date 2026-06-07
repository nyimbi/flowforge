import { type JSX } from "react";

export interface JtbdSummaryItem {
	id: string;
	title: string;
	actor: { role: string };
	domain: string;
}

export interface JobMapProps {
	jtbds: JtbdSummaryItem[];
	onSelect?: (id: string) => void;
}

const LANE_COLORS: string[] = [
	"#e0e7ff",
	"#fce7f3",
	"#d1fae5",
	"#fef3c7",
	"#dbeafe",
	"#f3e8ff",
	"#ffedd5",
	"#f0fdf4",
];

const LANE_HEADER_COLORS: string[] = [
	"#4f46e5",
	"#db2777",
	"#059669",
	"#d97706",
	"#2563eb",
	"#7c3aed",
	"#ea580c",
	"#16a34a",
];

export const JobMap = ({ jtbds, onSelect }: JobMapProps): JSX.Element => {
	// Group JTBDs by actor.role, preserving insertion order of first appearance.
	const roleOrder: string[] = [];
	const byRole = new Map<string, JtbdSummaryItem[]>();

	for (const jtbd of jtbds) {
		const role = jtbd.actor.role;
		if (!byRole.has(role)) {
			roleOrder.push(role);
			byRole.set(role, []);
		}
		byRole.get(role)!.push(jtbd);
	}

	return (
		<div
			data-testid="ff-job-map"
			role="region"
			aria-label="Job map"
			style={{
				display: "flex",
				flexDirection: "row",
				gap: 12,
				overflowX: "auto",
				padding: 16,
				background: "var(--ff-jobmap-bg, #f8fafc)",
				borderRadius: 8,
				minHeight: 200,
			}}
		>
			{roleOrder.map((role, laneIdx) => {
				const items = byRole.get(role)!;
				const bgColor = LANE_COLORS[laneIdx % LANE_COLORS.length];
				const headerColor = LANE_HEADER_COLORS[laneIdx % LANE_HEADER_COLORS.length];

				return (
					<div
						key={role}
						data-testid={`ff-job-map-lane-${role}`}
						aria-label={`Actor lane: ${role}`}
						style={{
							display: "flex",
							flexDirection: "column",
							gap: 8,
							minWidth: 200,
							flex: "0 0 200px",
							background: bgColor,
							borderRadius: 8,
							padding: 8,
						}}
					>
						{/* Lane header */}
						<div
							style={{
								background: headerColor,
								color: "#ffffff",
								borderRadius: 6,
								padding: "6px 10px",
								fontWeight: 600,
								fontSize: 13,
								letterSpacing: "0.02em",
							}}
						>
							{role}
						</div>

						{/* JTBD cards */}
						{items.map((jtbd) => (
							<button
								key={jtbd.id}
								data-testid={`ff-job-map-card-${jtbd.id}`}
								aria-label={`JTBD: ${jtbd.title}`}
								onClick={() => onSelect?.(jtbd.id)}
								style={{
									display: "block",
									width: "100%",
									textAlign: "left",
									background: "var(--ff-jobmap-card-bg, #ffffff)",
									border: `1px solid ${headerColor}`,
									borderRadius: 6,
									padding: "8px 10px",
									cursor: onSelect ? "pointer" : "default",
									fontSize: 12,
									color: "var(--ff-jobmap-card-fg, #172033)",
									boxShadow: "0 1px 2px rgba(0,0,0,0.06)",
									transition: "box-shadow 0.15s",
								}}
							>
								<div style={{ fontWeight: 600, marginBottom: 2 }}>{jtbd.title}</div>
								<div
									style={{
										fontSize: 11,
										color: "var(--ff-jobmap-card-domain, #6b7280)",
									}}
								>
									{jtbd.domain}
								</div>
							</button>
						))}
					</div>
				);
			})}
		</div>
	);
};
