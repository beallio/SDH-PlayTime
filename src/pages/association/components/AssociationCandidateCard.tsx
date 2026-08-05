import { Focusable } from "@decky/ui";
import type { AssociationCandidateCard as AssociationCandidateCardModel } from "../associationViewModel";

type AssociationCandidateCardProps = {
	card: AssociationCandidateCardModel;
	memberSelected?: boolean;
	onToggleMember?: () => void;
	onSelectParent?: () => void;
	primaryActionLabel?: string;
	membershipMessage?: string;
	checkingEligibility?: boolean;
};

function StatusPill({ children }: { children: string }) {
	return (
		<span
			style={{
				display: "inline-flex",
				alignItems: "center",
				padding: "3px 7px",
				background: "rgba(103, 193, 245, 0.12)",
				border: "1px solid rgba(103, 193, 245, 0.25)",
				borderRadius: "12px",
				color: "#b8dff5",
				fontSize: "11px",
				fontWeight: 500,
			}}
		>
			{children}
		</span>
	);
}

/** Shared card for selector and grouped-list flows; availability is always evidence, not an install claim. */
export function AssociationCandidateCard({
	card,
	memberSelected,
	onToggleMember,
	onSelectParent,
	primaryActionLabel,
	membershipMessage,
	checkingEligibility,
}: AssociationCandidateCardProps) {
	return (
		<Focusable
			style={{
				display: "flex",
				flexDirection: "column",
				gap: "8px",
				padding: "12px",
				background: card.isSelectedParent
					? "rgba(103, 193, 245, 0.12)"
					: "rgba(255, 255, 255, 0.05)",
				border: card.isSelectedParent
					? "1px solid rgba(103, 193, 245, 0.55)"
					: "1px solid transparent",
				borderRadius: "6px",
			}}
		>
			<div style={{ minWidth: 0 }}>
				<div
					style={{
						fontSize: "14px",
						fontWeight: 600,
						color: "#dcdedf",
						overflowWrap: "anywhere",
					}}
				>
					{card.title}
				</div>
				<div style={{ color: "#8b929a", fontSize: "11px", marginTop: "2px" }}>
					ID: {card.id} · {card.sourceLabel} · {card.trackedTimeLabel}
				</div>
			</div>

			<div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
				<StatusPill>{card.inventoryLabel}</StatusPill>
				<StatusPill>{card.availabilityLabel}</StatusPill>
				{card.recommendationLabel && (
					<StatusPill>{card.recommendationLabel}</StatusPill>
				)}
				{checkingEligibility && <StatusPill>Checking eligibility</StatusPill>}
			</div>

			{card.manualParentWarning && card.isSelectedParent && (
				<div
					style={{
						padding: "8px",
						background: "rgba(232, 167, 51, 0.14)",
						border: "1px solid rgba(232, 167, 51, 0.45)",
						borderRadius: "4px",
						color: "#f1c46a",
						fontSize: "11px",
					}}
				>
					{card.manualParentWarning}
				</div>
			)}

			{membershipMessage && (
				<div
					style={{
						padding: "8px",
						background: "rgba(232, 167, 51, 0.14)",
						border: "1px solid rgba(232, 167, 51, 0.45)",
						borderRadius: "4px",
						color: "#f1c46a",
						fontSize: "11px",
					}}
				>
					{membershipMessage}
				</div>
			)}

			{(onToggleMember || onSelectParent) && (
				<div style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}>
					{onToggleMember && (
						<Focusable
							onClick={onToggleMember}
							onActivate={onToggleMember}
							style={{
								padding: "6px 8px",
								borderRadius: "4px",
								background: "rgba(255, 255, 255, 0.08)",
								fontSize: "11px",
								cursor: "pointer",
							}}
						>
							{memberSelected ? "Included member" : "Include member"}
						</Focusable>
					)}
					{onSelectParent && (
						<Focusable
							onClick={onSelectParent}
							onActivate={onSelectParent}
							style={{
								padding: "6px 8px",
								borderRadius: "4px",
								background: card.isSelectedParent
									? "rgba(103, 193, 245, 0.25)"
									: "rgba(255, 255, 255, 0.08)",
								fontSize: "11px",
								cursor: "pointer",
							}}
						>
							{primaryActionLabel ??
								(card.isSelectedParent
									? "Proposed parent"
									: "Choose as parent")}
						</Focusable>
					)}
				</div>
			)}
		</Focusable>
	);
}
