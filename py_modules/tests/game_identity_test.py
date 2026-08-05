import unittest

from py_modules.game_identity import build_game_identity_components


class GameIdentityComponentsTest(unittest.TestCase):
    def test_checksum_components_are_independent_of_input_order(self):
        game_ids = ["gamma", "alpha", "beta"]
        checksum_records = [
            ("beta", "checksum-two", "sha256"),
            ("alpha", "checksum-one", "sha256"),
            ("gamma", "checksum-two", "sha256"),
            ("beta", "checksum-one", "sha256"),
        ]

        expected = build_game_identity_components(game_ids, checksum_records, [])
        reversed_components = build_game_identity_components(
            list(reversed(game_ids)), list(reversed(checksum_records)), []
        )

        self.assertEqual(expected, reversed_components)
        component = expected["alpha"]
        self.assertEqual(component.members, ("alpha", "beta", "gamma"))
        self.assertEqual(component.aliases, ("beta", "gamma"))
        self.assertEqual(component.canonical_id, "alpha")
        self.assertEqual(component.explicit_parent_ids, ())
        self.assertEqual(component.status, "unconfirmed")

    def test_explicit_parent_wins_over_a_smaller_checksum_member(self):
        components = build_game_identity_components(
            ["alpha", "parent"],
            [
                ("alpha", "shared", "sha256"),
                ("parent", "shared", "sha256"),
            ],
            [("parent", "alpha")],
        )

        component = components["alpha"]
        self.assertEqual(component.canonical_id, "parent")
        self.assertEqual(component.aliases, ("alpha",))
        self.assertEqual(component.explicit_parent_ids, ("parent",))
        self.assertEqual(component.status, "confirmed")

    def test_transitive_mixed_checksum_and_association_edges_share_one_component(self):
        components = build_game_identity_components(
            ["alpha", "beta", "child", "parent"],
            [
                ("alpha", "left", "sha256"),
                ("beta", "left", "sha256"),
                ("beta", "right", "sha256"),
                ("child", "right", "sha256"),
            ],
            [("parent", "child")],
        )

        component = components["beta"]
        self.assertEqual(component.members, ("alpha", "beta", "child", "parent"))
        self.assertEqual(component.canonical_id, "parent")
        self.assertEqual(component.aliases, ("alpha", "beta", "child"))
        self.assertEqual(component.status, "confirmed")

    def test_explicit_associations_form_components_without_checksums(self):
        components = build_game_identity_components(
            ["child-a", "child-b", "parent"],
            [],
            [("parent", "child-b"), ("parent", "child-a")],
        )

        component = components["child-a"]
        self.assertEqual(component.members, ("child-a", "child-b", "parent"))
        self.assertEqual(component.aliases, ("child-a", "child-b"))
        self.assertEqual(component.canonical_id, "parent")

    def test_multiple_explicit_parents_report_a_conflict_with_a_deterministic_fallback(
        self,
    ):
        components = build_game_identity_components(
            ["alpha", "beta", "parent-a", "parent-b"],
            [
                ("alpha", "shared", "sha256"),
                ("beta", "shared", "sha256"),
            ],
            [("parent-b", "beta"), ("parent-a", "alpha")],
        )

        component = components["parent-a"]
        self.assertEqual(component.canonical_id, "alpha")
        self.assertEqual(component.aliases, ("beta", "parent-a", "parent-b"))
        self.assertEqual(component.explicit_parent_ids, ("parent-a", "parent-b"))
        self.assertEqual(component.status, "conflict")


if __name__ == "__main__":
    unittest.main()
