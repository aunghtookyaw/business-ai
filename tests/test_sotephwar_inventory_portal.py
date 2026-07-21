import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts import receive_payment_server
from tools import sotephwar_inventory


class SotePhwarInventoryPortalTest(unittest.TestCase):
    def movement(self, movement_type="Production", **overrides):
        value = {
            "date": "2026-07-18", "type": movement_type,
            "product": "Sote Phwar 1L", "quantity": "10",
            "from_store": "", "to_store": "Factory", "note": "Test",
        }
        value.update(overrides)
        return value

    def test_production_entry_validation(self):
        result = sotephwar_inventory.validate_movement(self.movement(), check_stock=False)
        self.assertEqual("Production", result["type"])
        self.assertEqual(10, result["quantity"])
        for invalid in (
            self.movement(from_store="Factory"),
            self.movement(to_store=""),
        ):
            with self.assertRaises(sotephwar_inventory.InventoryValidationError):
                sotephwar_inventory.validate_movement(invalid, check_stock=False)

    @patch("tools.sotephwar_inventory.authoritative_stock")
    def test_transfer_validation_and_insufficient_stock(self, stock):
        stock.return_value = [{"store": "Factory", "product": "Sote Phwar 1L", "stock_qty": 9}]
        valid = self.movement("Transfer", from_store="Factory", to_store="Tatkone Store", quantity=9)
        self.assertEqual(9, sotephwar_inventory.validate_movement(valid)["available_stock"])
        with self.assertRaisesRegex(sotephwar_inventory.InventoryValidationError, "identical"):
            sotephwar_inventory.validate_movement({**valid, "to_store": "Factory"})
        with self.assertRaisesRegex(sotephwar_inventory.InventoryValidationError, "Insufficient stock"):
            sotephwar_inventory.validate_movement({**valid, "quantity": 10})

    @patch("tools.sotephwar_inventory.authoritative_stock")
    def test_sale_validation_and_insufficient_stock(self, stock):
        stock.return_value = [{"store": "Tatkone Store", "product": "Sote Phwar 1L", "stock_qty": 4}]
        valid = self.movement("Sale", from_store="Tatkone Store", to_store="", quantity=4)
        self.assertEqual(4, sotephwar_inventory.validate_movement(valid)["available_stock"])
        with self.assertRaises(sotephwar_inventory.InventoryValidationError):
            sotephwar_inventory.validate_movement({**valid, "to_store": "Factory"})
        with self.assertRaisesRegex(sotephwar_inventory.InventoryValidationError, "Insufficient stock"):
            sotephwar_inventory.validate_movement({**valid, "quantity": 5})

    def test_quantity_must_be_positive_whole_bottles(self):
        for quantity in (0, -1, "0.5", "bad"):
            with self.assertRaises(sotephwar_inventory.InventoryValidationError):
                sotephwar_inventory.validate_movement(self.movement(quantity=quantity), check_stock=False)

    @patch("tools.sotephwar_inventory.formula_engine.sotephwar_inventory_stock")
    def test_summary_reuses_formula_engine_and_builds_complete_matrix(self, stock):
        stock.return_value = {"stock": [
            {"store": "Factory", "product": "Sote Phwar 1L", "stock_qty": 10},
            {"store": "Tatkone Store", "product": "Sote Phwar 1L", "stock_qty": 5},
            {"store": "Factory", "product": "Sote Phwar 4L", "stock_qty": 2},
        ]}
        result = sotephwar_inventory.inventory_summary()
        stock.assert_called_once_with(period="all_time")
        self.assertEqual("sotephwar_inventory_stock", result["formula"])
        self.assertEqual(17, result["total_stock"])
        self.assertEqual(4, len(result["matrix"]))
        self.assertEqual(0, result["matrix"][3]["stores"]["Naung Tayar"])
        self.assertEqual("zero", result["product_totals"][3]["status"])

    @patch("tools.sotephwar_inventory.formula_engine.sotephwar_inventory_list")
    def test_history_search_and_filters_reuse_formula_engine(self, listing):
        listing.return_value = {"movements": [
            {"id": 1, "date": "2026-07-18", "type": "Transfer", "from_store": "Factory", "to_store": "Tatkone Store", "product": "Sote Phwar 1L", "quantity": 5, "note": "North route"},
            {"id": 2, "date": "2026-07-17", "type": "Transfer", "from_store": "Factory", "to_store": "Min Hla Store", "product": "Sote Phwar 1L", "quantity": 2, "note": "South route"},
        ]}
        result = sotephwar_inventory.movement_history({"search": "north", "date": "2026-07-18", "type": "Transfer", "product": "Sote Phwar 1L", "store": "Factory"})
        self.assertEqual([1], [row["id"] for row in result["movements"]])
        listing.assert_called_once_with(period="all_time", product="Sote Phwar 1L", store="Factory", movement_type="Transfer", limit=500)

    @patch("tools.sotephwar_inventory.inventory_summary", return_value={"total_stock": 10})
    @patch("tools.sotephwar_inventory.authoritative_stock", return_value=[])
    def test_atomic_insert_and_duplicate_submission_protection(self, _stock, _summary):
        values = {**self.movement(), "confirmed": True, "submission_key": "1234567890abcdef"}
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect = [None, {"id": 54}]
        saved = sotephwar_inventory.submit_movement(values, connection=connection)
        self.assertEqual(54, saved["movement_id"])
        self.assertFalse(saved["idempotent"])
        sql_text = "\n".join(str(call.args[0]) for call in cursor.execute.call_args_list)
        self.assertIn("Sotephwar_Inventory", sql_text)
        self.assertNotIn("Sotephwar_Transection", sql_text)
        self.assertNotIn("voucher", sql_text.lower())
        connection.commit.assert_called_once()

        duplicate_connection = MagicMock()
        duplicate_cursor = duplicate_connection.cursor.return_value.__enter__.return_value
        duplicate_cursor.fetchone.return_value = {"id": 54}
        duplicate = sotephwar_inventory.submit_movement(values, connection=duplicate_connection)
        self.assertTrue(duplicate["idempotent"])
        duplicate_sql = "\n".join(str(call.args[0]) for call in duplicate_cursor.execute.call_args_list)
        self.assertNotIn("INSERT INTO", duplicate_sql)

    @patch("tools.sotephwar_inventory.authoritative_stock", return_value=[])
    def test_database_failure_rolls_back(self, _stock):
        values = {**self.movement(), "confirmed": True, "submission_key": "abcdef1234567890"}
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = None
        cursor.execute.side_effect = [None, None, RuntimeError("insert failed")]
        with self.assertRaisesRegex(RuntimeError, "insert failed"):
            sotephwar_inventory.submit_movement(values, connection=connection)
        connection.rollback.assert_called_once()

    def test_page_mobile_rendering_and_protected_api(self):
        client = receive_payment_server.app.test_client()
        page = client.get("/business-os/sotephwar-inventory")
        self.assertEqual(200, page.status_code)
        html = page.get_data(as_text=True)
        self.assertIn("SotePhwar Inventory", html)
        self.assertIn("New Inventory Movement", html)
        self.assertIn("Movement history", html)
        self.assertIn('/static/sotephwar_inventory.css?v=20260718-2', html)
        self.assertIn('class="si-kpis"', html)
        css = (Path(__file__).resolve().parents[1] / "static/sotephwar_inventory.css").read_text()
        self.assertIn("@media(max-width:700px)", css)
        self.assertIn("grid-template-columns:repeat(4", css)
        self.assertIn("min-height:44px", css)
        self.assertEqual(403, client.get("/business-os/api/sotephwar-inventory/summary").status_code)

    def test_no_edit_delete_or_cross_table_behavior(self):
        root = Path(__file__).resolve().parents[1]
        portal = (root / "tools/sotephwar_inventory_portal.py").read_text()
        adapter = (root / "tools/sotephwar_inventory.py").read_text()
        self.assertNotIn('methods=["DELETE"]', portal)
        self.assertIn('business_os_sotephwar_inventory_update_draft', portal)
        self.assertNotIn("Sotephwar_Transection", adapter)
        self.assertNotIn("farm_transection", adapter)
        self.assertNotIn("business_os_voucher_draft", adapter)


if __name__ == "__main__":
    unittest.main()
