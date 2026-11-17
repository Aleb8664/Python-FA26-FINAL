import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from inventory_data import (
    InventoryDataError,
    add_item,
    add_user,
    authenticate,
    change_user_role,
    is_overdue,
    issue_item,
    load_state,
    remove_item,
    renew_checkout,
    return_item,
    setup_owner,
    update_item,
)


class InventoryDataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.state_path = self.root / "Inventory.json"
        self.menu_path = self.root / "menu.txt"
        self.menu_path.write_text(
            "Tools: Drill\nOffice Supplies: Paper\n", encoding="utf-8"
        )
        self.state = load_state(self.state_path, self.menu_path)
        self.state["users"].clear()
        self.state["items"].clear()
        self.state["transactions"].clear()
        setup_owner(self.state, "owner-password")
        add_user(self.state, "2", "Sam", "employee-password", "employee")
        self.stock_item = add_item(
            self.state,
            name="Paper",
            category="Office Supplies",
            item_type="stock",
            quantity=10,
            low_stock_threshold=2,
            max_checkout_days=7,
            max_renewals=2,
            authorized_user_ids=[],
        )
        self.reusable_item = add_item(
            self.state,
            name="Drill",
            category="Tools",
            item_type="reusable",
            quantity=2,
            low_stock_threshold=1,
            max_checkout_days=7,
            max_renewals=1,
            authorized_user_ids=["1"],
        )
        self.now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def test_owner_authentication_and_protected_access(self) -> None:
        self.assertEqual(authenticate(self.state, "1", "owner-password")["role"], "owner")
        self.assertIsNone(authenticate(self.state, "1", "wrong-password"))
        with self.assertRaises(InventoryDataError):
            change_user_role(self.state, "1", "employee")

    def test_stock_issue_decreases_quantity_and_requires_reason(self) -> None:
        transaction = issue_item(
            self.state,
            employee_id="2",
            item_id=self.stock_item["id"],
            quantity=3,
            reason="Office use",
            now=self.now,
        )
        self.assertEqual(self.stock_item["quantity"], 7)
        self.assertEqual(transaction["kind"], "stock_issue")
        self.assertEqual(transaction["quantity_outstanding"], 0)
        with self.assertRaisesRegex(InventoryDataError, "reason"):
            issue_item(
                self.state,
                employee_id="2",
                item_id=self.stock_item["id"],
                quantity=1,
                reason=" ",
                now=self.now,
            )

    def test_item_authorization_blocks_unapproved_employee(self) -> None:
        with self.assertRaisesRegex(InventoryDataError, "not authorized"):
            issue_item(
                self.state,
                employee_id="2",
                item_id=self.reusable_item["id"],
                quantity=1,
                reason="Repair",
                now=self.now,
            )

    def test_checkout_return_and_renewal_update_stock_and_due_date(self) -> None:
        transaction = issue_item(
            self.state,
            employee_id="1",
            item_id=self.reusable_item["id"],
            quantity=2,
            reason="Equipment maintenance",
            now=self.now,
        )
        self.assertEqual(self.reusable_item["quantity"], 0)
        self.assertEqual(
            datetime.fromisoformat(transaction["due_at"]),
            self.now + timedelta(days=7),
        )

        renew_checkout(
            self.state,
            transaction_id=transaction["id"],
            employee_id="1",
            now=self.now + timedelta(days=1),
        )
        self.assertEqual(transaction["renewals"], 1)
        self.assertEqual(
            datetime.fromisoformat(transaction["due_at"]),
            self.now + timedelta(days=14),
        )
        with self.assertRaisesRegex(InventoryDataError, "maximum"):
            renew_checkout(
                self.state,
                transaction_id=transaction["id"],
                employee_id="1",
                now=self.now + timedelta(days=2),
            )

        return_item(
            self.state,
            transaction_id=transaction["id"],
            employee_id="1",
            quantity=1,
            now=self.now + timedelta(days=2),
        )
        self.assertEqual(self.reusable_item["quantity"], 1)
        self.assertEqual(transaction["quantity_outstanding"], 1)
        return_item(
            self.state,
            transaction_id=transaction["id"],
            employee_id="1",
            quantity=1,
            now=self.now + timedelta(days=3),
        )
        self.assertEqual(self.reusable_item["quantity"], 2)
        self.assertIsNotNone(transaction["returned_at"])

    def test_overdue_detection_and_item_removal_rules(self) -> None:
        transaction = issue_item(
            self.state,
            employee_id="1",
            item_id=self.reusable_item["id"],
            quantity=1,
            reason="Project",
            now=self.now,
        )
        self.assertTrue(
            is_overdue(transaction, now=self.now + timedelta(days=8))
        )
        with self.assertRaisesRegex(InventoryDataError, "Return all"):
            remove_item(self.state, self.reusable_item["id"], permanent=True)
        remove_item(self.state, self.reusable_item["id"], permanent=False)
        self.assertFalse(self.reusable_item["active"])

    def test_legacy_inventory_is_migrated(self) -> None:
        self.state_path.write_text(
            '[{"Item":"Old item","Category":"Old category"}]', encoding="utf-8"
        )
        migrated = load_state(self.state_path, self.menu_path)
        self.assertEqual(migrated["items"][0]["name"], "Old item")
        self.assertEqual(migrated["items"][0]["type"], "stock")
        self.assertEqual(migrated["users"], [])
        self.assertEqual(migrated["transactions"], [])

    def test_seed_inventory_has_mixed_item_types_and_stable_random_quantities(
        self,
    ) -> None:
        seeded_state = load_state(self.state_path, self.menu_path)
        seeded_quantities = [item["quantity"] for item in seeded_state["items"]]
        self.assertEqual(len(seeded_state["items"]), 2)
        self.assertEqual(
            {item["type"] for item in seeded_state["items"]},
            {"stock", "reusable"},
        )
        self.assertTrue(all(2 <= quantity <= 30 for quantity in seeded_quantities))
        self.assertEqual(
            load_state(self.state_path, self.menu_path)["items"],
            seeded_state["items"],
        )

    def test_item_type_cannot_change_while_equipment_is_checked_out(self) -> None:
        issue_item(
            self.state,
            employee_id="1",
            item_id=self.reusable_item["id"],
            quantity=1,
            reason="Project",
            now=self.now,
        )
        with self.assertRaisesRegex(InventoryDataError, "Return all"):
            update_item(
                self.state,
                self.reusable_item["id"],
                name=self.reusable_item["name"],
                category=self.reusable_item["category"],
                item_type="stock",
                quantity=self.reusable_item["quantity"],
                low_stock_threshold=1,
                max_checkout_days=7,
                max_renewals=1,
                authorized_user_ids=["1"],
            )


if __name__ == "__main__":
    unittest.main()
