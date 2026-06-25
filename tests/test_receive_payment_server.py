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
                    "note": "Paid by transfer",
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
                    "note": "",
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
        self.assertIn("<th>Note</th>", html)
        self.assertIn('class="voucher-row"', html)
        self.assertIn('id="selectedVoucher"', html)
        self.assertIn('id="paymentNote"', html)
        self.assertIn('name="notes"', html)
        self.assertNotIn('id="selectedNote"', html)
        self.assertIn("function selectRow(row)", html)
        self.assertIn("Enter new receive amount only", html)
        self.assertIn("200,000", html)
        self.assertIn("Paid by transfer", html)
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

    def test_voucher_query_groups_sotephwar_for_payment_lookup_and_uses_payment_history(self):
        sql = receive_payment_server._voucher_query(
            where_sql='WHERE vg."Sector" = %(sector)s AND COALESCE(vg."Outstanding_Balance", 0) > 0'
        )

        self.assertIn('FROM "', sql)
        self.assertIn('"Sotephwar_Transection" s', sql)
        self.assertIn('GROUP BY s."Invoice_Number"::text', sql)
        self.assertIn('"Payment_Receive"', sql)
        self.assertIn('COALESCE(SUM(s."Total_Received"), 0) AS "Source_Total_Received"', sql)
        self.assertIn('COALESCE(SUM(s."Outstanding_Balance"), 0) AS "Source_Outstanding_Balance"', sql)
        self.assertIn('GREATEST(sv."Source_Total_Received", COALESCE(p."Total_Received", 0))', sql)
        self.assertIn('COALESCE(vg."Outstanding_Balance", 0) > 0', sql)
        self.assertNotIn('COALESCE(MAX(s."Total_Received"), 0)', sql)
        self.assertNotIn('COALESCE(MAX(s."Outstanding_Balance"), 0)', sql)
        self.assertNotIn('COALESCE(SUM(s."Outstanding_Balance"), 0) AS "Outstanding_Balance"', sql)

    def test_sotephwar_listing_query_returns_raw_rows(self):
        sql = receive_payment_server._sotephwar_listing_query(
            where_sql=(
                ' AND COALESCE(s."Outstanding_Balance", 0) > 0'
                ' AND COALESCE(NULLIF(TRIM(s."Customer_Name"), \'\'), \'\') ILIKE %(customer)s'
            )
        )

        self.assertIn('"Sotephwar_Transection" s', sql)
        self.assertIn('s."Item"', sql)
        self.assertIn('s."Total_Amount"', sql)
        self.assertIn('s."Total_Received"', sql)
        self.assertIn('s."Outstanding_Balance"', sql)
        self.assertIn('s."Payment_Status"', sql)
        self.assertIn('ILIKE %(customer)s', sql)
        self.assertNotIn('GROUP BY', sql)
        self.assertNotIn('STRING_AGG', sql)

    def test_create_payment_receive_inserts_history_and_returns_refreshed_voucher(self):
        calls = []
        fetch_count = {"count": 0}
        original_fetch_voucher = receive_payment_server._fetch_voucher
        original_insert = receive_payment_server._insert_payment_receive

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
                "note": "Paid by transfer",
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
                "note": "Paid by transfer",
            },
        ]

        def fake_fetch_voucher(sector, invoice_number, invoice_date="", customer=""):
            calls.append(("fetch", sector, invoice_number))
            fetch_count["count"] += 1
            return vouchers[1] if fetch_count["count"] > 1 else vouchers[0]

        def fake_insert_payment_receive(**values):
            calls.append(("insert", values))
            return {
                "id": 1,
                "sector": values["sector"],
                "voucher_number": values["voucher_number"],
                "receive_amount": values["receive_amount"],
                "invoice_amount": 3128000,
                "previous_paid": 200000,
                "outstanding_balance": 2828000,
            }

        receive_payment_server._fetch_voucher = fake_fetch_voucher
        receive_payment_server._insert_payment_receive = fake_insert_payment_receive
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

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(100000, payload["payment"]["receive_amount"])
        self.assertEqual(300000, payload["voucher"]["total_received"])
        self.assertEqual(2828000, payload["voucher"]["outstanding_balance"])
        self.assertEqual("Paid by transfer", payload["voucher"]["note"])
        self.assertEqual("insert", calls[1][0])
        inserted = calls[1][1]
        self.assertEqual("2026-06-11", inserted["invoice_date"])
        self.assertEqual("Makro", inserted["customer"])
        self.assertNotIn("invoice_amount", inserted)
        self.assertNotIn("previous_paid", inserted)
        self.assertNotIn("outstanding_balance", inserted)

    def test_api_payment_receive_rejects_negative_outstanding(self):
        original_fetch_voucher = receive_payment_server._fetch_voucher
        original_insert = receive_payment_server._insert_payment_receive

        def fake_fetch_voucher(sector, invoice_number, invoice_date="", customer=""):
            return {
                "sector": sector,
                "invoice_number": invoice_number,
                "customer": "Makro",
                "sote_type": "",
                "invoice_date": "2026-06-11",
                "voucher_total": 100000,
                "legacy_received": 0,
                "new_received": 0,
                "total_received": 100000,
                "outstanding_balance": 0,
                "note": "Closed",
            }

        def fake_insert_payment_receive(**values):
            raise ValueError("Outstanding_Balance cannot be negative.")

        receive_payment_server._fetch_voucher = fake_fetch_voucher
        receive_payment_server._insert_payment_receive = fake_insert_payment_receive
        try:
            client = receive_payment_server.app.test_client()
            response = client.post(
                "/api/payment-receive",
                json={
                    "sector": "Farm",
                    "invoice_number": "75",
                    "receive_amount": "1",
                    "payment_method": "Cash",
                },
            )
        finally:
            receive_payment_server._fetch_voucher = original_fetch_voucher
            receive_payment_server._insert_payment_receive = original_insert

        self.assertEqual(400, response.status_code)
        payload = response.get_json()
        self.assertFalse(payload["ok"])
        self.assertIn("Outstanding_Balance cannot be negative", payload["error"])


if __name__ == "__main__":
    unittest.main()
