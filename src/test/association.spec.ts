import { beforeEach, describe, expect, mock, test } from "bun:test";
import { BACK_END_API } from "@src/constants";
import type {
	AssociationComponentConfirmationResult,
	AssociationComponentReadResult,
	ConfirmAssociationComponentDTO,
} from "@src/types/association";

const calls: unknown[][] = [];
let callHandler: (...args: unknown[]) => Promise<unknown>;

mock.module("@decky/api", () => ({
	call: async (...args: unknown[]) => {
		calls.push(args);
		return await callHandler(...args);
	},
}));

const { AssociationService } = await import("@src/app/association");

const confirmationRequest: ConfirmAssociationComponentDTO = {
	anchor_game_id: "gamma",
	proposed_parent_game_id: "beta",
	proposed_parent_game_name: "Beta",
	expected_parent_game_id: "alpha",
	expected_fingerprint: "component-fingerprint",
	selected_members: [
		{ game_id: "alpha", game_name: "Alpha" },
		{ game_id: "beta", game_name: "Beta" },
		{ game_id: "gamma", game_name: "Gamma" },
	],
};

describe("AssociationService component confirmation", () => {
	beforeEach(() => {
		calls.length = 0;
		callHandler = async () => undefined;
	});

	test("uses the exact grouped-read and confirmation DTOs", async () => {
		const readResponse: AssociationComponentReadResult = {
			success: true,
			data: {
				anchorGameId: "gamma",
				expectedParentGameId: "alpha",
				existingMembers: [
					{ gameId: "alpha", gameName: "Alpha" },
					{ gameId: "beta", gameName: "Beta" },
					{ gameId: "gamma", gameName: "Gamma" },
				],
				fingerprint: "component-fingerprint",
				status: "confirmed",
				aliases: ["beta", "gamma"],
			},
		};
		const confirmationResponse: AssociationComponentConfirmationResult = {
			success: true,
			data: {
				...readResponse.data,
				proposedParent: { gameId: "beta", gameName: "Beta" },
				selectedMembers: readResponse.data.existingMembers,
				confirmedParent: { gameId: "beta", gameName: "Beta" },
				status: "confirmed",
				aliases: ["alpha", "gamma"],
			},
		};
		callHandler = async (method: unknown) =>
			method === BACK_END_API.GET_GAME_ASSOCIATION_COMPONENT
				? readResponse
				: confirmationResponse;
		const service = new AssociationService();

		expect(await service.getAssociationComponent("gamma")).toEqual(readResponse);
		expect(await service.confirmAssociationComponent(confirmationRequest)).toEqual(
			confirmationResponse,
		);
		expect(calls).toEqual([
			[BACK_END_API.GET_GAME_ASSOCIATION_COMPONENT, "gamma"],
			[BACK_END_API.CONFIRM_GAME_ASSOCIATION_COMPONENT, confirmationRequest],
		]);
	});

	test("preserves structured conflicts and supplies a network fallback", async () => {
		const conflict: AssociationComponentConfirmationResult = {
			success: false,
			error: {
				code: "COMPONENT_CONFLICT",
				message: "Confirm every component member.",
			},
		};
		callHandler = async () => conflict;
		const service = new AssociationService();

		expect(await service.confirmAssociationComponent(confirmationRequest)).toEqual(conflict);

		callHandler = async () => {
			throw new Error("network unavailable");
		};
		expect(await service.confirmAssociationComponent(confirmationRequest)).toEqual({
			success: false,
			error: {
				code: "NETWORK_ERROR",
				message: "Failed to confirm association component. Please try again.",
			},
		});
	});

	test("passes detach and dissolve successes through", async () => {
		const detachSuccess = { success: true };
		const dissolveSuccess = { success: true };
		callHandler = async (method: unknown) =>
			method === BACK_END_API.DETACH_GAME_ASSOCIATION_MEMBER
				? detachSuccess
				: dissolveSuccess;
		const service = new AssociationService();

		expect(await service.detachAssociationMember("gamma")).toEqual(detachSuccess);
		expect(await service.dissolveAssociationComponent("alpha")).toEqual(
			dissolveSuccess,
		);
		expect(calls).toEqual([
			[BACK_END_API.DETACH_GAME_ASSOCIATION_MEMBER, "gamma"],
			[BACK_END_API.DISSOLVE_GAME_ASSOCIATION_COMPONENT, "alpha"],
		]);
	});

	test("preserves malformed and structured removal errors", async () => {
		const detachInvalid = {
			success: false as const,
			error: { code: "INVALID_REQUEST", message: "Invalid child." },
		};
		const dissolveConflict = {
			success: false as const,
			error: {
				code: "PARENT_REQUIRES_CONFIRMATION",
				message: "Confirm a replacement parent first.",
			},
		};
		callHandler = async (method: unknown) =>
			method === BACK_END_API.DETACH_GAME_ASSOCIATION_MEMBER
				? detachInvalid
				: dissolveConflict;
		const service = new AssociationService();

		expect(await service.detachAssociationMember("")).toEqual(detachInvalid);
		expect(await service.dissolveAssociationComponent("alpha")).toEqual(
			dissolveConflict,
		);
	});

	test("supplies network fallbacks for detach and dissolve", async () => {
		callHandler = async () => {
			throw new Error("network unavailable");
		};
		const service = new AssociationService();

		expect(await service.detachAssociationMember("gamma")).toEqual({
			success: false,
			error: {
				code: "NETWORK_ERROR",
				message: "Failed to detach association member. Please try again.",
			},
		});
		expect(await service.dissolveAssociationComponent("alpha")).toEqual({
			success: false,
			error: {
				code: "NETWORK_ERROR",
				message: "Failed to dissolve association component. Please try again.",
			},
		});
	});
});
