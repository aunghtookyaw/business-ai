import unittest
from datetime import date
from unittest.mock import MagicMock, patch
from uuid import UUID

import business_os_app as receive_payment_server
from tools import general_transaction


class GeneralTransactionTest(unittest.TestCase):
    def category(self, active=True):
        return {"id": 20, "category_code": "CAT-0020", "category_name": "General Expense"} if active else None

    def values(self, **updates):
        values = {
            "transaction_date": "2026-07-19", "transaction_type": "Expense", "sector": "Farm",
            "category_id": 20, "description": "Office supplies", "amount": "15000",
            "payment_method": "Cash", "comment": "Receipt retained",
        }
        values.update(updates)
        return values

    def test_income_and_expense_validation_and_exact_mapping_values(self):
        for transaction_type in ("Income", "Expense"):
            result = general_transaction.validate(self.values(transaction_type=transaction_type), self.category())
            self.assertEqual(transaction_type, result["transaction_type"])
            self.assertEqual("General Expense", result["category_name"])
            self.assertEqual(15000, result["amount"])

    def test_submitted_transaction_delete_is_atomic_and_scoped(self):
        connection=MagicMock();cursor=connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect=[{"id":7,"status":"submitted","is_deleted":False,"submitted_transaction_id":88,"attachment_path":""},{"id":7}]
        result=general_transaction.delete_submitted_transaction(7,"88","test cleanup","Business OS",connection=connection)
        self.assertTrue(result["deleted"]);connection.commit.assert_called_once()
        statements="\n".join(str(call.args[0]) for call in cursor.execute.call_args_list)
        self.assertIn("_nc_m2m_Transection_category_master",statements)
        self.assertNotIn("Payment_Receive",statements);self.assertNotIn("Inventory",statements)

    def test_category_description_amount_and_payment_validation(self):
        cases = [
            (self.values(), None, "Category is inactive or unavailable"),
            (self.values(description="   "), self.category(), "Description is required"),
            (self.values(amount="0"), self.category(), "Amount must be a positive whole-number"),
            (self.values(amount="1.50"), self.category(), "Amount must be a positive whole-number"),
            (self.values(payment_method="AYPay"), self.category(), "Payment method is required"),
        ]
        for values, category, message in cases:
            with self.assertRaises(general_transaction.GeneralTransactionValidationError) as raised:
                general_transaction.validate(values, category)
            self.assertTrue(any(message in error for error in raised.exception.errors))

    def test_exact_standard_payment_methods(self):
        self.assertEqual(("Cash", "KPay", "AYA Pay", "UAB Pay", "Other Online Pay"), general_transaction.PAYMENT_METHODS)
        for payment_method in general_transaction.PAYMENT_METHODS:
            self.assertEqual(payment_method, general_transaction.validate(self.values(payment_method=payment_method), self.category())["payment_method"])

    def test_voucher_income_collision_rejection_for_each_sector(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (1,)
        for sector, module in (("Farm", "Farm Voucher"), ("Sote Phwar", "SotePhwar Voucher")):
            with self.assertRaises(general_transaction.GeneralTransactionValidationError) as raised:
                general_transaction._reject_voucher_collision(connection, self.values(transaction_type="Income", sector=sector, amount=15000))
            self.assertIn(module, str(raised.exception))
        cursor.fetchone.return_value = None
        general_transaction._reject_voucher_collision(connection, self.values(transaction_type="Expense"))

    def test_submit_is_idempotent_and_uses_server_submission_identity(self):
        key = "f85e2e61-e385-4a94-8f6b-a9c22fdc2751"
        submitted = {**self.values(), "id": 7, "status": "submitted", "submission_key": key, "submitted_transaction_id": 99}
        connection = MagicMock()
        with patch.object(general_transaction, "get_draft", return_value=submitted):
            result = general_transaction.submit(7, key, "tester", connection=connection)
        self.assertTrue(result["idempotent"])
        self.assertEqual(99, result["transaction_id"])
        connection.commit.assert_called_once()

    def test_atomic_rollback_when_category_relationship_insert_fails(self):
        key = "f85e2e61-e385-4a94-8f6b-a9c22fdc2751"
        draft = {**self.values(), "id": 7, "status": "validated", "submission_key": key,
                 "attachment_path": "", "comment": "", "submitted_transaction_id": None}
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = {"id": 501}
        calls = {"count": 0}
        def execute(*args, **kwargs):
            calls["count"] += 1
            if calls["count"] == 3:
                raise RuntimeError("junction failed")
        cursor.execute.side_effect = execute
        with patch.object(general_transaction, "get_draft", return_value=draft), \
             patch.object(general_transaction, "_active_category", return_value=self.category()), \
             patch.object(general_transaction, "_reject_voucher_collision"):
            with self.assertRaisesRegex(RuntimeError, "junction failed"):
                general_transaction.submit(7, key, "tester", connection=connection)
        connection.rollback.assert_called_once()
        connection.commit.assert_not_called()

    def test_submit_requires_validation_but_not_preview_and_revalidates(self):
        key = "f85e2e61-e385-4a94-8f6b-a9c22fdc2751"
        draft = {**self.values(), "id": 7, "status": "draft", "submission_key": key,
                 "attachment_path": "", "submitted_transaction_id": None}
        connection = MagicMock()
        with patch.object(general_transaction, "get_draft", return_value=draft):
            with self.assertRaisesRegex(general_transaction.GeneralTransactionValidationError, "validated before submission"):
                general_transaction.submit(7, key, "tester", connection=connection)
        draft["status"] = "validated"
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect = [{"id": 501}, {**draft, "transaction_date": date(2026, 7, 19), "status": "submitted", "submitted_transaction_id": 501}]
        with patch.object(general_transaction, "get_draft", return_value=draft), \
             patch.object(general_transaction, "_active_category", return_value=self.category()), \
             patch.object(general_transaction, "_reject_voucher_collision"), \
             patch.object(general_transaction, "validate", wraps=general_transaction.validate) as validate:
            result = general_transaction.submit(7, key, "tester", connection=connection)
        self.assertEqual(501, result["transaction_id"])
        validate.assert_called_once()

    def test_expense_and_genuine_income_use_exact_atomic_mapping(self):
        key = "f85e2e61-e385-4a94-8f6b-a9c22fdc2751"
        for transaction_type in ("Expense", "Income"):
            draft = {**self.values(transaction_type=transaction_type), "id": 7, "status": "validated",
                     "submission_key": key, "attachment_path": "receipt.jpg", "submitted_transaction_id": None}
            connection = MagicMock(); cursor = connection.cursor.return_value.__enter__.return_value
            cursor.fetchone.side_effect = [{"id": 501}, {**draft, "transaction_date": date(2026, 7, 19), "status": "submitted", "submitted_transaction_id": 501}]
            with patch.object(general_transaction, "get_draft", return_value=draft), \
                 patch.object(general_transaction, "_active_category", return_value=self.category()), \
                 patch.object(general_transaction, "_reject_voucher_collision") as collision:
                general_transaction.submit(7, key, "tester", connection=connection)
            statements = [str(call.args[0]) for call in cursor.execute.call_args_list]
            self.assertEqual(1, sum('INSERT INTO' in value and '"Transection"' in value for value in statements))
            self.assertEqual(1, sum('INSERT INTO' in value and '_nc_m2m_Transection_category_master' in value for value in statements))
            transaction_call = next(call for call in cursor.execute.call_args_list if '"Transection"' in str(call.args[0]) and 'INSERT INTO' in str(call.args[0]))
            self.assertEqual(("2026-07-19", transaction_type, "General Expense", "Farm", "Office supplies", 15000, "Cash", "receipt.jpg", "Receipt retained"), transaction_call.args[1])
            collision.assert_called_once()
            connection.commit.assert_called_once()

    def test_page_uses_validate_submit_workflow_and_refreshes_history(self):
        from pathlib import Path
        page = receive_payment_server.app.test_client().get("/business-os/general-transaction").get_data(as_text=True)
        script = (Path(__file__).resolve().parents[1] / "static/general_transaction.js").read_text()
        history = (Path(__file__).resolve().parents[1] / "static/operational_history.js").read_text()
        self.assertNotIn('id="gtPreview"', page)
        self.assertNotIn('id="gtPreviewCard"', page)
        self.assertIn("d?.status!=='validated'", script)
        self.assertIn("Validation successful. Confirm & Submit is now available.", script)
        self.assertIn("if(submitting||!draft||draft.status!=='validated')return", script)
        self.assertIn("fill(null,{clearNotices:false})", script)
        self.assertIn("await recent()", script)
        self.assertNotIn("Preview failed", script)
        self.assertIn("module==='inventory'", history)

    def test_portal_returns_all_safe_human_readable_errors(self):
        client = receive_payment_server.app.test_client()
        error = general_transaction.GeneralTransactionValidationError(["Category is inactive", "Amount must be positive"])
        with patch.object(general_transaction, "set_workflow_state", side_effect=error):
            response = client.post("/business-os/api/general-transaction/drafts/7/validated")
        self.assertEqual(400, response.status_code)
        self.assertEqual(["Category is inactive", "Amount must be positive"], response.get_json()["errors"])

    def test_incomplete_draft_amount_reaches_human_readable_validation(self):
        self.assertEqual(0, general_transaction._draft_amount(""))
        self.assertEqual(0, general_transaction._draft_amount("not an amount"))
        with self.assertRaisesRegex(general_transaction.GeneralTransactionValidationError, "Amount must be a positive"):
            general_transaction.validate(self.values(amount=general_transaction._draft_amount("1.50")), self.category())

    def test_server_generates_uuid_and_page_is_lan_http_compatible(self):
        fake = {**self.values(), "id": 1, "status": "draft", "version": 1,
                "submission_key": "d52cc195-adde-4442-92c8-b4e657133252"}
        client = receive_payment_server.app.test_client()
        with patch.object(general_transaction, "create_draft", return_value=fake):
            response = client.post("/business-os/api/general-transaction/drafts", data=self.values())
        self.assertEqual(200, response.status_code)
        UUID(response.get_json()["draft"]["submission_key"])
        page = client.get("/business-os/general-transaction").get_data(as_text=True)
        self.assertNotIn("crypto.randomUUID", page)
        self.assertIn("General Transaction", page)

    def test_server_submission_uuid_is_bound_as_postgres_safe_text(self):
        connection = MagicMock(); connection.__enter__.return_value = connection
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = {
            **self.values(), "transaction_date": date(2026, 7, 19), "id": 1, "status": "draft", "version": 1,
            "submission_key": "d52cc195-adde-4442-92c8-b4e657133252",
        }
        with patch.object(general_transaction, "_connect", return_value=connection):
            general_transaction.create_draft(self.values(), "tester")
        bound_key = cursor.execute.call_args.args[1][0]
        self.assertIsInstance(bound_key, str)
        UUID(bound_key)


if __name__ == "__main__":
    unittest.main()
