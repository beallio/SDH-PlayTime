import {
	ButtonItem,
	ConfirmModal,
	Field,
	Focusable,
	PanelSection,
	PanelSectionRow,
	showModal,
} from "@decky/ui";
import { useStore } from "@nanostores/react";
import { PageWrapper } from "@src/components/PageWrapper";
import { AssociationCandidateCard } from "./association/components/AssociationCandidateCard";
import { useGamesForAssociation } from "./association/hooks/useGamesForAssociation";
import { $associationSelectionAnchor, navigateBack } from "./navigation";

function confirmationDescription(
	summary: NonNullable<
		ReturnType<typeof useGamesForAssociation>["confirmationSummary"]
	>,
) {
	return [
		summary.oldParent
			? `Current confirmed parent: ${summary.oldParent.gameName} (ID: ${summary.oldParent.gameId})`
			: "Current confirmed parent: none",
		`Proposed parent: ${summary.proposedParent.gameName} (ID: ${summary.proposedParent.gameId})`,
		`Affected members: ${summary.selectedMembers
			.map((member) => `${member.gameName} (ID: ${member.gameId})`)
			.join(", ")}`,
		...summary.reasons.map((reason) => `Review reason: ${reason}`),
		...summary.warnings.map((warning) => `Warning: ${warning}`),
	].join("\n\n");
}

export function AssociationAddPage() {
	const anchorGameId = useStore($associationSelectionAnchor);
	const {
		anchorCards,
		componentCards,
		additionCards,
		snapshot,
		loading,
		saving,
		error,
		selectedMemberIds,
		additionMessages,
		pendingCandidateIds,
		allMembersSelected,
		hasEnoughMembers,
		canConfirm,
		rankingReasons,
		confirmationSummary,
		selectAnchor,
		selectParent,
		toggleMember,
		refresh,
		confirm,
	} = useGamesForAssociation(anchorGameId);

	const showConfirmation = () => {
		if (!confirmationSummary) return;
		showModal(
			<ConfirmModal
				strTitle="Confirm game group parent"
				strDescription={confirmationDescription(confirmationSummary)}
				onOK={async () => {
					const result = await confirm();
					if (result?.success) {
						navigateBack();
						return;
					}
					if (result && !result.success) {
						showModal(
							<ConfirmModal
								strTitle="Association was not saved"
								strDescription={result.error.message}
								bOKDisabled
							/>,
						);
					}
				}}
			/>,
		);
	};

	return (
		<PageWrapper>
			<Focusable style={{ height: "calc(100% - 40px)", overflow: "scroll" }}>
				<PanelSection title="Choose Game Group Parent">
					<PanelSectionRow>
						<div
							style={{
								padding: "8px 0",
								fontSize: "12px",
								color: "#8b929a",
								lineHeight: 1.4,
							}}
						>
							Choose an entry to load its explicit identity group. Status labels
							show what is known now; they do not infer that a shortcut is
							installed.
						</div>
					</PanelSectionRow>

					{error && (
						<PanelSectionRow>
							<div
								style={{
									padding: "8px 12px",
									background: "rgba(220, 53, 69, 0.1)",
									border: "1px solid rgba(220, 53, 69, 0.3)",
									borderRadius: "4px",
									color: "#dc3545",
									fontSize: "12px",
								}}
							>
								{error}
							</div>
						</PanelSectionRow>
					)}

					<PanelSectionRow>
						<ButtonItem
							layout="below"
							onClick={() => void refresh()}
							disabled={loading || saving}
						>
							Refresh status
						</ButtonItem>
					</PanelSectionRow>

					{loading && !snapshot ? (
						<PanelSectionRow>
							<div style={{ color: "#8b929a", padding: "8px" }}>
								Loading status...
							</div>
						</PanelSectionRow>
					) : !snapshot ? (
						<PanelSectionRow>
							<div
								style={{
									display: "flex",
									flexDirection: "column",
									gap: "8px",
									width: "100%",
								}}
							>
								{anchorCards.map((card) => (
									<AssociationCandidateCard
										key={card.id}
										card={card}
										onSelectParent={() => selectAnchor(card.id)}
										primaryActionLabel="Open explicit group"
									/>
								))}
							</div>
						</PanelSectionRow>
					) : (
						<>
							<PanelSectionRow>
								<Field label="Explicit members">
									<div
										style={{
											fontSize: "11px",
											color: "#8b929a",
											padding: "4px 0",
										}}
									>
										Select every member shown by the backend component, then add
										any eligible singleton entries and choose the proposed
										parent. Existing component members are always required. A
										recommendation is convenient only; it is never saved until
										you confirm it.
									</div>
								</Field>
							</PanelSectionRow>
							<PanelSectionRow>
								<div
									style={{
										display: "flex",
										flexDirection: "column",
										gap: "8px",
										width: "100%",
									}}
								>
									{componentCards.map((card) => (
										<AssociationCandidateCard
											key={card.id}
											card={card}
											memberSelected={selectedMemberIds.includes(card.id)}
											onSelectParent={() => void selectParent(card.id)}
										/>
									))}
								</div>
							</PanelSectionRow>

							<PanelSectionRow>
								<Field label="Candidate additions">
									<div
										style={{
											fontSize: "11px",
											color: "#8b929a",
											padding: "4px 0",
										}}
									>
										Include one or more entries to create or expand this group.
										Each candidate is checked against its own explicit component
										before it can be selected.
									</div>
								</Field>
							</PanelSectionRow>
							<PanelSectionRow>
								<div
									style={{
										display: "flex",
										flexDirection: "column",
										gap: "8px",
										width: "100%",
									}}
								>
									{additionCards.map((card) => (
										<AssociationCandidateCard
											key={card.id}
											card={card}
											memberSelected={selectedMemberIds.includes(card.id)}
											onToggleMember={() => void toggleMember(card.id)}
											onSelectParent={() => void selectParent(card.id)}
											membershipMessage={additionMessages[card.id]}
											checkingEligibility={pendingCandidateIds.includes(
												card.id,
											)}
										/>
									))}
								</div>
							</PanelSectionRow>

							{rankingReasons.length > 0 && (
								<PanelSectionRow>
									<div
										style={{
											color: "#f1c46a",
											fontSize: "12px",
											lineHeight: 1.5,
										}}
									>
										{rankingReasons.map((reason) => (
											<div key={reason}>Review: {reason}</div>
										))}
									</div>
								</PanelSectionRow>
							)}

							{!allMembersSelected && (
								<PanelSectionRow>
									<div style={{ color: "#f1c46a", fontSize: "12px" }}>
										Every backend member must be included before confirmation.
									</div>
								</PanelSectionRow>
							)}

							{!hasEnoughMembers && (
								<PanelSectionRow>
									<div style={{ color: "#f1c46a", fontSize: "12px" }}>
										Include at least one eligible addition to create a group.
									</div>
								</PanelSectionRow>
							)}

							{confirmationSummary && (
								<PanelSectionRow>
									<div
										style={{
											padding: "10px",
											background: "rgba(255, 255, 255, 0.04)",
											borderRadius: "4px",
											fontSize: "12px",
											lineHeight: 1.5,
										}}
									>
										<div>
											Old parent:{" "}
											{confirmationSummary.oldParent?.gameName ?? "None"}
										</div>
										<div>
											Proposed parent:{" "}
											{confirmationSummary.proposedParent.gameName}
										</div>
										<div>
											Affected members:{" "}
											{confirmationSummary.selectedMembers
												.map((member) => member.gameName)
												.join(", ")}
										</div>
									</div>
								</PanelSectionRow>
							)}

							<PanelSectionRow>
								<ButtonItem
									layout="below"
									disabled={!canConfirm}
									onClick={showConfirmation}
								>
									{saving ? "Saving..." : "Review and confirm parent"}
								</ButtonItem>
							</PanelSectionRow>
						</>
					)}
				</PanelSection>
			</Focusable>
		</PageWrapper>
	);
}
