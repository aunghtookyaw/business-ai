import unittest

from scripts import receive_payment_server


class ReceivePaymentServerTest(unittest.TestCase):
    def test_receive_payment_basic_renders_visible_html(self):
        original_list_vouchers = receive_payment_server._list_vouchers

        def fake_list_vouchers(search="", sector="", voucher_number="", invoice_date="", customer=""):
            return [
                {
                    "sector": "Farm",
                    "invoice_number": "75",
                    "customer": "Makro",
                    "sote_type": "",
                    "invoice_date": "2026-06-11",
                    "voucher_total": 3128000,
                    "legacy_received": 200000,
                    "new_received": 0,
                    "total_received": 200000,
                    "outstanding_balance": 2928000,
                },
                {
                    "sector": "Sote Phwar",
                    "invoice_number": "SP-1",
                    "customer": "Aung Myat Thu",
                    "sote_type": "4L Bottle",
                    "invoice_date": "2026-06-11",
                    "voucher_total": 500000,
                    "legacy_received": 0,
                    "new_received": 0,
                    "total_received": 0,
                    "outstanding_balance": 500000,
                }
            ]

        receive_payment_server._list_vouchers = fake_list_vouchers
        try:
            client = receive_payment_server.app.test_client()
            response = client.get("/receive-payment-basic")
        finally:
            receive_payment_server._list_vouchers = original_list_vouchers

        self.assertEqual(200, response.status_code)
        html = response.get_data(as_text=True)
        self.assertIn("<h1>Receive Payment Basic</h1>", html)
        self.assertIn('action="/receive-payment-basic"', html)
        self.assertIn('name="voucher_number"', html)
        self.assertIn('name="invoice_date"', html)
        self.assertIn('name="customer"', html)
        self.assertIn('list="customerSuggestions"', html)
        self.assertIn("Farm||75", html)
        self.assertIn("Sote Type / Item", html)
        self.assertIn('class="voucher-row"', html)
        self.assertIn('id="selectedVoucher"', html)
        self.assertIn("function selectRow(row)", html)
        self.assertIn("Enter new receive amount only", html)
        self.assertIn("200,000", html)
        self.assertIn("Save Payment", html)

    def test_receive_payment_basic_shows_error_when_vouchers_fail_to_load(self):
        original_list_vouchers = receive_payment_server._list_vouchers

        def fake_list_vouchers(search="", sector="", voucher_number="", invoice_date="", customer=""):
            raise RuntimeError("database unavailable")

        receive_payment_server._list_vouchers = fake_list_vouchers
        try:
            client = receive_payment_server.app.test_client()
            response = client.get("/receive-payment-basic")
        finally:
            receive_payment_server._list_vouchers = original_list_vouchers

        self.assertEqual(200, response.status_code)
        html = response.get_data(as_text=True)
        self.assertIn("<h1>Receive Payment Basic</h1>", html)
        self.assertIn("Could not load vouchers: database unavailable", html)
        self.assertIn("No vouchers are available.", html)

    def test_create_payment_receive_inserts_history_and_returns_refreshed_voucher(self):
        calls = []
        original_fetch_voucher = receive_payment_server._fetch_voucher
        original_insert = receive_payment_server._insert_payment_receive
        original_update = receive_payment_server.formula_engine._update_voucher_payment_summary

        vouchers = [
            {
                "sector": "Farm",
                "invoice_number": "75",
                "customer": "Makro",
                "sote_type": "",
                "invoice_date": "2026-06-11",
                "voucher_total": 3128000,
                "legacy_received": 200000,
                "new_received": 0,
                "total_received": 200000,
                "outstanding_balance": 2928000,
            },
            {
                "sector": "Farm",
                "invoice_number": "75",
                "customer": "Makro",
                "sote_type": "",
                "invoice_date": "2026-06-11",
                "voucher_total": 3128000,
                "legacy_received": 200000,
                "new_received": 100000,
                "total_received": 300000,
                "outstanding_balance": 2828000,
            },
        ]

        def fake_fetch_voucher(sector, invoice_number):
            calls.append(("fetch", sector, invoice_number))
            return vouchers[1] if ("update", sector, invoice_number) in calls else vouchers[0]

        def fake_insert_payment_receive(**values):
            calls.append(("insert", values))
            return {
                "id": 1,
                "sector": values["sector"],
                "voucher_number": values["voucher_number"],
                "receive_amount": values["receive_amount"],
            }

        def fake_update_summary(sector, invoice_number):
            calls.append(("update", sector, invoice_number))

        receive_payment_server._fetch_voucher = fake_fetch_voucher
        receive_payment_server._insert_payment_receive = fake_insert_payment_receive
        receive_payment_server.formula_engine._update_voucher_payment_summary = fake_update_summary
        try:
            client = receive_payment_server.app.test_client()
            response = client.post(
                "/api/payment-receive",
                json={
                    "sector": "Farm",
                    "invoice_number": "75",
                    "receive_amount": "100000",
                    "payment_method": "Cash",
                    "reference_number": "R1",
                    "notes": "partial",
                },
            )
        finally:
            receive_payment_server._fetch_voucher = original_fetch_voucher
            receive_payment_server._insert_payment_receive = original_insert
            receive_payment_server.formula_engine._update_voucher_payment_summary = original_update

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(100000, payload["payment"]["receive_amount"])
        self.assertEqual(300000, payload["voucher"]["total_received"])
        self.assertEqual(2828000, payload["voucher"]["outstanding_balance"])
        self.assertEqual("insert", calls[1][0])
        self.assertEqual("update", calls[2][0])
        inserted = calls[1][1]
        self.assertEqual(3128000, inserted["invoice_amount"])
        self.assertEqual(200000, inserted["previous_paid"])
        self.assertEqual(2828000, inserted["outstanding_balance"])


if __name__ == "__main__":
    unittest.main()
