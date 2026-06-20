import unittest

from scripts import receive_payment_server


class ReceivePaymentServerTest(unittest.TestCase):
    def test_create_payment_receive_inserts_history_and_returns_refreshed_voucher(self):
        calls = []
        original_fetch_voucher = receive_payment_server._fetch_voucher
        original_total_received = receive_payment_server._payment_total_received
        original_insert = receive_payment_server._insert_payment_receive
        original_update = receive_payment_server.formula_engine._update_voucher_payment_summary

        vouchers = [
            {
                "sector": "Farm",
                "invoice_number": "75",
                "customer": "Makro",
                "invoice_date": "2026-06-11",
                "voucher_total": 3128000,
                "total_received": 0,
                "outstanding_balance": 3128000,
            },
            {
                "sector": "Farm",
                "invoice_number": "75",
                "customer": "Makro",
                "invoice_date": "2026-06-11",
                "voucher_total": 3128000,
                "total_received": 100000,
                "outstanding_balance": 3028000,
            },
        ]

        def fake_fetch_voucher(sector, invoice_number):
            calls.append(("fetch", sector, invoice_number))
            return vouchers[1] if ("update", sector, invoice_number) in calls else vouchers[0]

        def fake_total_received(sector, invoice_number):
            calls.append(("total", sector, invoice_number))
            return 0

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
        receive_payment_server._payment_total_received = fake_total_received
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
            receive_payment_server._payment_total_received = original_total_received
            receive_payment_server._insert_payment_receive = original_insert
            receive_payment_server.formula_engine._update_voucher_payment_summary = original_update

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(100000, payload["payment"]["receive_amount"])
        self.assertEqual(100000, payload["voucher"]["total_received"])
        self.assertEqual(3028000, payload["voucher"]["outstanding_balance"])
        self.assertEqual("insert", calls[2][0])
        self.assertEqual("update", calls[3][0])
        inserted = calls[2][1]
        self.assertEqual(3128000, inserted["invoice_amount"])
        self.assertEqual(0, inserted["previous_paid"])
        self.assertEqual(3028000, inserted["outstanding_balance"])


if __name__ == "__main__":
    unittest.main()
