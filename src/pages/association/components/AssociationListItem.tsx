import { Focusable } from "@decky/ui";
import type { AssociationListGroup } from "../associationViewModel";
import { AssociationCandidateCard } from "./AssociationCandidateCard";

interface AssociationListItemProps {
	group: AssociationListGroup;
	onChangeParent: () => void;
	onDetachChild: (childGameId: string, childGameName: string) => void;
	onDissolve: () => void;
}

const actionStyle = {
	padding: "7px 9px",
	borderRadius: "4px",
	background: "rgba(255, 255, 255, 0.08)",
	fontSize: "11px",
	cursor: "pointer",
};

/** Renders a confirmed parent once, followed by its explicit child edges. */
export function AssociationListItem({
	group,
	onChangeParent,
	onDetachChild,
	onDissolve,
}: AssociationListItemProps) {
	return (
		<div
			style={{
				display: "flex",
				flexDirection: "column",
				gap: "8px",
				padding: "10px",
				background: "rgba(255, 255, 255, 0.025)",
				borderRadius: "6px",
			}}
		>
			<div style={{ color: "#8b929a", fontSize: "11px", fontWeight: 600 }}>
				CONFIRMED PARENT
			</div>
			<AssociationCandidateCard card={group.parent} />
			<div style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}>
				<Focusable
					onClick={onChangeParent}
					onActivate={onChangeParent}
					style={actionStyle}
				>
					Change parent
				</Focusable>
				<Focusable
					onClick={onDissolve}
					onActivate={onDissolve}
					style={{ ...actionStyle, color: "#f1c46a" }}
				>
					Dissolve group
				</Focusable>
			</div>

			<div style={{ color: "#8b929a", fontSize: "11px", fontWeight: 600 }}>
				CHILDREN ({group.children.length})
			</div>
			{group.children.map((child) => (
				<div
					key={child.id}
					style={{ display: "flex", flexDirection: "column", gap: "6px" }}
				>
					<AssociationCandidateCard card={child} />
					<Focusable
						onClick={() => onDetachChild(child.id, child.title)}
						onActivate={() => onDetachChild(child.id, child.title)}
						style={{ ...actionStyle, alignSelf: "flex-end", color: "#f1c46a" }}
					>
						Detach child (keeps history)
					</Focusable>
				</div>
			))}
		</div>
	);
}
