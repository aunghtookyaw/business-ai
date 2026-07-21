import unittest
from unittest.mock import patch

from scripts import receive_payment_server
from tools import business_os_portal, customer_master


CUSTOMER = {
    "id": 7, "customer_name": "Aye Aye", "phone_number": "091234567",
    "town": "Heho", "customer_group": "Farm", "payment_terms_days": 7,
    "contact_address": "Main Road", "notes": "Call first", "active": True,
    "business_os_version": 2, "created_at": None, "updated_at": None,
    "business_os_modified_at": None,
}


class CustomerMasterValidationTest(unittest.TestCase):
    def test_phone_is_trimmed_text_and_leading_zero_is_preserved(self):
        value = customer_master._validate({
            "customer_name": "  Aye Aye ", "customer_group": "Farm",
            "phone_number": " 091234567 ", "payment_terms_days": "7",
        })
        self.assertEqual("091234567", value["phone_number"])
        self.assertEqual("Aye Aye", value["customer_name"])

    def test_customer_group_is_controlled(self):
        for group in ("Farm", "SotePhwar", "Both"):
            self.assertEqual(group, customer_master._validate({"customer_name": "A", "customer_group": group})["customer_group"])
        with self.assertRaises(customer_master.CustomerError):
            customer_master._validate({"customer_name": "A", "customer_group": "Retail"})

    def test_blank_name_is_rejected(self):
        with self.assertRaises(customer_master.CustomerError):
            customer_master._validate({"customer_name": "  ", "customer_group": "Farm"})

    def test_submission_keys_are_server_generated(self):
        first, second = customer_master.new_submission_key(), customer_master.new_submission_key()
        self.assertNotEqual(first, second)
        self.assertEqual(36, len(first))


class CustomerMasterPortalTest(unittest.TestCase):
    def setUp(self):
        self.client = receive_payment_server.app.test_client()

    def test_data_entry_navigation_hides_overviews_and_preserves_routes(self):
        with patch.object(business_os_portal, "_database_health", return_value=("Connected", "good")):
            html = self.client.get("/business-os").get_data(as_text=True)
        self.assertIn("Daily Entry", html)
        self.assertIn("Master Data", html)
        self.assertNotIn("Financial Overview", html)
        self.assertNotIn("Inventory Overview", html)
        self.assertEqual(200, self.client.get("/business-os/financial").status_code)
        self.assertEqual(200, self.client.get("/business-os/inventory").status_code)

    @patch("tools.customer_master.summary", return_value={"active_customers": 1})
    def test_summary_endpoint(self, _summary):
        response = self.client.get("/business-os/api/customers/summary")
        self.assertEqual(200, response.status_code)
        self.assertEqual(1, response.get_json()["summary"]["active_customers"])

    @patch("tools.customer_master.list_customers")
    def test_search_filters_and_paging_are_forwarded_server_side(self, listing):
        listing.return_value = {"customers": [], "page": 2, "page_size": 50, "total": 0, "pages": 1}
        response = self.client.get("/business-os/api/customers?q=Aye&phone_number=091&customer_group=Farm&active=true&page=2&page_size=50")
        self.assertEqual(200, response.status_code)
        filters, page, page_size = listing.call_args.args
        self.assertEqual("Aye", filters["q"])
        self.assertEqual("091", filters["phone_number"])
        self.assertEqual("Farm", filters["customer_group"])
        self.assertEqual("true", filters["active"])
        self.assertEqual(("2", "50"), (page, page_size))

    @patch("tools.customer_master.customer_detail")
    def test_customer_detail_returns_only_requested_linked_activity(self, detail):
        detail.return_value = {"customer": CUSTOMER, "recent_farm_vouchers": [{"id": 3}], "recent_sotephwar_vouchers": []}
        response = self.client.get("/business-os/api/customers/7")
        self.assertEqual(200, response.status_code)
        detail.assert_called_once_with(7)
        self.assertEqual(3, response.get_json()["recent_farm_vouchers"][0]["id"])

    def test_state_changes_require_request_protection(self):
        self.assertEqual(403, self.client.post("/business-os/api/customers", json={}).status_code)
        self.assertEqual(403, self.client.put("/business-os/api/customers/7", json={}).status_code)

    def test_deactivation_requires_administrator(self):
        response = self.client.post("/business-os/api/customers/7/status", headers={"X-Business-OS-Request": "customer-master-v1"}, json={"active": False})
        self.assertEqual(403, response.status_code)
        self.assertEqual("administrator_required", response.get_json()["code"])

    @patch("tools.customer_master.create_customer")
    def test_add_customer_and_server_idempotency_key(self, create):
        create.return_value = CUSTOMER
        token = self.client.post("/business-os/api/customers/submission-key", headers={"X-Business-OS-Request": "customer-master-v1"})
        self.assertEqual(200, token.status_code)
        key = token.get_json()["submission_key"]
        response = self.client.post("/business-os/api/customers", headers={"X-Business-OS-Request": "customer-master-v1"}, json={"customer_name": "Aye Aye", "customer_group": "Farm", "phone_number": "09123", "submission_key": key})
        self.assertEqual(200, response.status_code)
        self.assertEqual(key, create.call_args.args[1])

    @patch("tools.customer_master.create_customer", side_effect=customer_master.DuplicateWarning([{"id": 5, "customer_name": "Aye Aye"}]))
    def test_duplicate_warning_does_not_insert_silently(self, _create):
        response = self.client.post("/business-os/api/customers", headers={"X-Business-OS-Request": "customer-master-v1"}, json={"submission_key": "key"})
        self.assertEqual(409, response.status_code)
        self.assertEqual("possible_duplicate", response.get_json()["code"])
        self.assertEqual(5, response.get_json()["matches"][0]["id"])

    @patch("tools.customer_master.update_customer", side_effect=customer_master.ConcurrentEdit("reload"))
    def test_concurrent_edit_returns_structured_conflict(self, _update):
        response = self.client.put("/business-os/api/customers/7", headers={"X-Business-OS-Request": "customer-master-v1"}, json={"submission_key": "key", "expected_version": 1})
        self.assertEqual(409, response.status_code)
        self.assertEqual("concurrent_modification", response.get_json()["code"])

    def test_customer_page_has_group_appropriate_safe_shortcuts(self):
        script = open("static/customer_master.js", encoding="utf-8").read()
        self.assertIn("customer_group==='Farm'", script)
        self.assertIn("customer_group==='SotePhwar'", script)
        self.assertIn("customer_id=${c.id}", script)
        farm = open("static/farm_voucher.js", encoding="utf-8").read()
        sote = open("static/sotephwar_voucher.js", encoding="utf-8").read()
        self.assertIn("URLSearchParams(location.search).get('customer_id')", farm)
        self.assertIn("URLSearchParams(location.search).get('customer_id')", sote)


if __name__ == "__main__":
    unittest.main()
