import { ButtonItem, PanelSection, PanelSectionRow } from "@decky/ui";
import { CurrentPlayTime } from "../containers/CurrentPlayTime";
import { ReportWeekly } from "../containers/ReportWeekly";
import {
	DETAILED_REPORT_ROUTE,
	SETTINGS_ROUTE,
	REPLAY_ROUTE,
	navigateToPage,
	navigateToExternalWeb,
} from "./navigation";
import { useEffect, useMemo } from "react";
import { $lastOpenedPage } from "@src/stores/ui";
import { getDefaultReplayYear } from "@src/app/replay.constants";
import { useVersionCheck } from "@src/app/useVersionCheck";
import { BsInfoCircle } from "react-icons/bs";

const GITHUB_URL = "https://github.com/0u73r-h34v3n/SDH-PlayTime";

const useShowReplayButton = (): { show: boolean; year: number } => {
	return useMemo(() => {
		const now = new Date();
		const currentYear = now.getFullYear();
		const currentMonth = now.getMonth(); // 0-11
		const currentDay = now.getDate();

		// Show from Dec 10 to Dec 31
		if (currentMonth === 11 && currentDay >= 10) {
			return { show: true, year: currentYear };
		}

		// Show from Jan 1 to Jan 7
		if (currentMonth === 0 && currentDay <= 7) {
			return { show: true, year: currentYear - 1 };
		}

		return { show: false, year: getDefaultReplayYear() };
	}, []);
};

const CHANGELOG_URL = `${GITHUB_URL}/blob/master/CHANGELOG.md`;

export function DeckyPanelPage() {
	const { show: showReplayButton, year: replayYear } = useShowReplayButton();
	const { showChangelogButton, markVersionAsSeen } = useVersionCheck();

	useEffect(() => {
		$lastOpenedPage.set("all-time");
	}, []);

	const handleChangelogClick = async () => {
		await markVersionAsSeen();
		navigateToExternalWeb(CHANGELOG_URL);
	};

	return (
		<div>
			<CurrentPlayTime />

			<ReportWeekly isFromQAM={true} />

			<PanelSection title="Misc">
				{showReplayButton && (
					<PanelSectionRow>
						<ButtonItem
							layout="below"
							onClick={() =>
								navigateToPage(
									REPLAY_ROUTE.replace(":year", replayYear.toString()),
								)
							}
							// @ts-expect-error - ButtonItem supports style at runtime
							style={{
								background:
									"repeating-linear-gradient(45deg, rgba(196, 30, 58, 0.4), rgba(196, 30, 58, 0.4) 10px, rgba(255, 255, 255, 0.2) 10px, rgba(255, 255, 255, 0.2) 20px)",
								color: "#ffffff",
								fontWeight: "bold",
							}}
							description={`Available from Dec 10 to Jan 7`}
						>
							Your {replayYear} ❄️
						</ButtonItem>
					</PanelSectionRow>
				)}

				<PanelSectionRow>
					<ButtonItem
						layout="below"
						onClick={() => navigateToPage(DETAILED_REPORT_ROUTE)}
					>
						Detailed report
					</ButtonItem>
				</PanelSectionRow>

				<PanelSectionRow>
					<ButtonItem
						layout="below"
						onClick={() => navigateToPage(SETTINGS_ROUTE)}
					>
						Settings
					</ButtonItem>
				</PanelSectionRow>

				{showChangelogButton && (
					<PanelSectionRow>
						<ButtonItem
							layout="below"
							onClick={handleChangelogClick}
							description="You just got an update! This button will be hidden once accessed. View changelog anytime from Settings > About"
							// @ts-expect-error - ButtonItem supports style at runtime
							style={{
								display: "flex",
								alignItems: "center",
								justifyContent: "center",
							}}
						>
							<BsInfoCircle size={16} style={{ marginRight: "0.5rem" }} /> View
							Changelog
						</ButtonItem>
					</PanelSectionRow>
				)}
			</PanelSection>
		</div>
	);
}
