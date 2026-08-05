import {
	ButtonItem,
	ConfirmModal,
	Focusable,
	PanelSection,
	PanelSectionRow,
	showModal,
} from "@decky/ui";
import { PageWrapper } from "@src/components/PageWrapper";
import { useAssociations } from "./association/hooks/useAssociations";
import { AddAssociationButton } from "./association/components/AddAssociationButton";
import { EmptyState } from "./association/components/EmptyState";
import { AssociationListItem } from "./association/components/AssociationListItem";
import { navigateToAssociationSelection } from "./navigation";

export function AssociationListPage() {
	const { groups, loading, error, refresh, detachMember, dissolveGroup } =
		useAssociations();

	const showResultError = (message: string) => {
		showModal(
			<ConfirmModal
				strTitle="Association change was not saved"
				strDescription={message}
				bOKDisabled
			/>,
		);
	};

	const handleDetach = (childGameId: string, childGameName: string) => {
		showModal(
			<ConfirmModal
				strTitle="Detach child from game group"
				strDescription={`Detach "${childGameName}"? Its recorded playtime history will be retained; only this explicit association edge is removed.`}
				onOK={async () => {
					const result = await detachMember(childGameId);
					if (!result.success)
						showResultError(result.error?.message ?? "Failed to detach child.");
				}}
			/>,
		);
	};

	const handleDissolve = (anchorGameId: string, parentGameName: string) => {
		showModal(
			<ConfirmModal
				strTitle="Dissolve game group"
				strDescription={`Dissolve the group confirmed under "${parentGameName}"? This removes all explicit group edges and does not promote a remaining child.`}
				onOK={async () => {
					const result = await dissolveGroup(anchorGameId);
					if (!result.success)
						showResultError(
							result.error?.message ?? "Failed to dissolve group.",
						);
				}}
			/>,
		);
	};

	if (loading) {
		return (
			<PageWrapper>
				<PanelSection title="Game Associations">
					<PanelSectionRow>
						<div style={{ padding: "8px 0", color: "#8b929a" }}>Loading...</div>
					</PanelSectionRow>
				</PanelSection>
			</PageWrapper>
		);
	}

	return (
		<PageWrapper>
			<Focusable style={{ height: "calc(100% - 40px)", overflow: "scroll" }}>
				<PanelSection title="Game Associations">
					<PanelSectionRow>
						<AddAssociationButton
							onClick={() => navigateToAssociationSelection()}
						/>
					</PanelSectionRow>
					<PanelSectionRow>
						<ButtonItem layout="below" onClick={() => void refresh()}>
							Refresh status
						</ButtonItem>
					</PanelSectionRow>
					<PanelSectionRow>
						<div
							style={{
								padding: "8px 0",
								fontSize: "12px",
								color: "#8b929a",
								lineHeight: 1.4,
							}}
						>
							Each card is one confirmed logical game group. Change a parent
							through the same review-and-confirm path used when creating a
							group.
						</div>
					</PanelSectionRow>

					{error && (
						<PanelSectionRow>
							<div style={{ color: "#dc3545", fontSize: "12px" }}>
								{error.message}
							</div>
						</PanelSectionRow>
					)}

					{groups.length === 0 ? (
						<EmptyState
							title="No game associations configured"
							description="Choose a game group to confirm how its playtime is combined"
						/>
					) : (
						<div
							style={{
								display: "flex",
								flexDirection: "column",
								gap: "8px",
								marginTop: "8px",
							}}
						>
							{groups.map((group) => (
								<AssociationListItem
									key={group.anchorGameId}
									group={group}
									onChangeParent={() =>
										navigateToAssociationSelection(group.anchorGameId)
									}
									onDetachChild={handleDetach}
									onDissolve={() =>
										handleDissolve(group.anchorGameId, group.parent.title)
									}
								/>
							))}
						</div>
					)}
				</PanelSection>
			</Focusable>
		</PageWrapper>
	);
}
