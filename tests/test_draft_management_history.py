import unittest
from unittest.mock import MagicMock, patch

import business_os_app as receive_payment_server
from tools import draft_management, farm_voucher_repository, sotephwar_voucher_repository


class DraftManagementHistoryTest(unittest.TestCase):
    def connection(self, row, updated={"id": 7}):
        connection=MagicMock();cursor=connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect=[row,updated]
        return connection,cursor

    def test_soft_removal_is_audited_and_never_deletes(self):
        connection,cursor=self.connection({"id":7,"status":"previewed","is_deleted":False,"submitted_transaction_id":None})
        result=draft_management.remove_draft("drafts",7,"Operator","Duplicate draft",connection=connection)
        self.assertFalse(result["idempotent"]);self.assertEqual("previewed",result["previous_status"])
        sql_text=" ".join(str(call.args[0]) for call in cursor.execute.call_args_list).upper()
        self.assertIn("UPDATE",sql_text);self.assertNotIn("DELETE FROM",sql_text)
        connection.commit.assert_called_once()

    def test_same_removal_is_idempotent(self):
        connection,_=self.connection({"id":7,"status":"draft","is_deleted":True})
        result=draft_management.remove_draft("drafts",7,"Operator",connection=connection)
        self.assertTrue(result["idempotent"]);connection.commit.assert_called_once()

    def test_submitted_or_production_linked_draft_cannot_be_removed(self):
        protected=[{"status":"submitted"},{"status":"previewed","submitted_transaction_id":91},
                   {"status":"previewed","submitted_transaction_ids":[1,2]},
                   {"status":"previewed","submitted_movement_id":4},{"status":"previewed","submitted_pdf_path":"final.pdf"},
                   {"status":"previewed","submitted_json":{"id":3}}]
        for values in protected:
            connection,_=self.connection({"id":7,"is_deleted":False,**values})
            with self.assertRaisesRegex(ValueError,"cannot be removed"):
                draft_management.remove_draft("drafts",7,"Operator",connection=connection)
            connection.rollback.assert_called_once()

    def test_concurrent_change_rolls_back(self):
        connection,_=self.connection({"id":7,"status":"draft","is_deleted":False},None)
        with self.assertRaisesRegex(RuntimeError,"concurrently"):
            draft_management.remove_draft("drafts",7,"Operator",connection=connection)
        connection.rollback.assert_called_once()

    def test_page_sizes_are_server_controlled(self):
        self.assertEqual((2,50,50),draft_management.paging(2,50))
        with self.assertRaises(ValueError):draft_management.paging(1,500)

    def test_sote_history_returns_one_voucher_for_multiple_transaction_ids(self):
        row={"draft_id":3,"voucher_number":"SP-1","voucher_date":__import__('datetime').date(2026,7,19),"customer_name":"Dealer",
             "submitted_at":__import__('datetime').datetime(2026,7,19,1,0),"submitted_transaction_ids":[11,12],
             "submitted_voucher":{"lines":[{"item":"1L","quantity":2},{"item":"4L","quantity":1}],"total_amount":"100","amount_received":"40","outstanding_balance":"60","payment_status":"Partial"},
             "submitted_pdf_path":"x","submitted_pdf_checksum":"y","total_count":1}
        connection=MagicMock();connection.__enter__.return_value=connection;cursor=connection.cursor.return_value.__enter__.return_value;cursor.fetchall.return_value=[row]
        with patch.object(sotephwar_voucher_repository,"_connect",return_value=connection):
            result=sotephwar_voucher_repository.recent_submissions({},1,20)
        self.assertEqual(1,len(result["records"]));self.assertEqual([11,12],result["records"][0]["record_ids"]);self.assertEqual(3,result["records"][0]["total_quantity"])

    def test_sote_history_accepts_decimal_formatted_quantities(self):
        row={"draft_id":3,"voucher_number":"SP-1","voucher_date":__import__('datetime').date(2026,7,19),"customer_name":"Dealer",
             "submitted_at":__import__('datetime').datetime(2026,7,19,1,0),"submitted_transaction_ids":[11],
             "submitted_voucher":{"lines":[{"item":"1L","quantity":"1000.00"}],"free_lines":[{"item":"100ml","quantity":"2.00"}]},
             "submitted_pdf_path":None,"submitted_pdf_checksum":None,"total_count":1}
        connection=MagicMock();connection.__enter__.return_value=connection;cursor=connection.cursor.return_value.__enter__.return_value;cursor.fetchall.return_value=[row]
        with patch.object(sotephwar_voucher_repository,"_connect",return_value=connection):
            result=sotephwar_voucher_repository.recent_submissions({},1,20)
        self.assertEqual(1000,result["items"][0]["paid_quantity"])
        self.assertEqual(2,result["items"][0]["free_quantity"])

    def test_farm_history_uses_current_payment_state_and_keeps_original_audit_values(self):
        row={"draft_id":8,"voucher_number":"FV-8","voucher_date":__import__('datetime').date(2026,7,1),"customer_name":"Customer",
             "submitted_at":__import__('datetime').datetime(2026,7,1,1,0),"submitted_pdf_path":"original.pdf","submitted_pdf_checksum":"checksum",
             "submitted_voucher":{"gross_amount":"2000000","discount_amount":"120000","cashback_amount":"0","net_amount":"1880000","amount_received":"880000","outstanding_balance":"1000000"},
             "record_id":91,"total_amount":1880000,"total_received":880000,"outstanding_balance":1000000,"payment_status":"Partial","total_count":1}
        connection=MagicMock();connection.__enter__.return_value=connection;cursor=connection.cursor.return_value.__enter__.return_value;cursor.fetchall.return_value=[row]
        current={"invoice_amount":1880000,"current_received":1880000,"current_outstanding":0,"current_payment_status":"Paid","latest_payment_date":"2026-07-20"}
        with patch.object(farm_voucher_repository,"_connect",return_value=connection), patch.object(farm_voucher_repository,"current_voucher_payment_state",return_value=current):
            result=farm_voucher_repository.recent_submissions({},1,20)
        item=result["records"][0]
        self.assertEqual("1880000",item["net_amount"]);self.assertEqual("880000",item["original_received"])
        self.assertEqual("1000000",item["original_outstanding"]);self.assertEqual("1880000",item["total_received"])
        self.assertEqual("0",item["outstanding_balance"]);self.assertEqual("Paid",item["payment_status"])
        self.assertEqual("2026-07-20",item["latest_payment_date"])

    def test_farm_summary_uses_all_today_vouchers_not_visible_history_page(self):
        today = __import__('datetime').date(2026,7,22)
        rows = [
            {"voucher_number":"700","voucher_date":today,"customer_name":"A","total_amount":1000},
            {"voucher_number":"701","voucher_date":today,"customer_name":"B","total_amount":1284000},
            {"voucher_number":"702","voucher_date":today,"customer_name":"C","total_amount":1880000},
        ]
        connection=MagicMock();connection.__enter__.return_value=connection
        cursor=connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value={"open_drafts":0};cursor.fetchall.return_value=rows
        states=[{"current_outstanding":1000},{"current_outstanding":500},{"current_outstanding":0}]
        with patch.object(farm_voucher_repository,"_connect",return_value=connection), \
             patch.object(farm_voucher_repository,"current_voucher_payment_state",side_effect=states) as current:
            summary=farm_voucher_repository.operational_summary()
        self.assertEqual({"open_drafts":0,"outstanding_today":1500,"submitted_today":3,"total_today":3165000},summary)
        self.assertEqual(3,current.call_count)

    def test_farm_summary_all_paid_is_zero_and_endpoint_is_not_cached(self):
        today = __import__('datetime').date(2026,7,22)
        rows=[{"voucher_number":"701","voucher_date":today,"customer_name":"B","total_amount":1284000},
              {"voucher_number":"702","voucher_date":today,"customer_name":"C","total_amount":1880000}]
        connection=MagicMock();connection.__enter__.return_value=connection
        cursor=connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value={"open_drafts":0};cursor.fetchall.return_value=rows
        with patch.object(farm_voucher_repository,"_connect",return_value=connection), \
             patch.object(farm_voucher_repository,"current_voucher_payment_state",side_effect=[{"current_outstanding":0},{"current_outstanding":0}]):
            summary=farm_voucher_repository.operational_summary()
        self.assertEqual(0,summary["outstanding_today"]);self.assertEqual(2,summary["submitted_today"]);self.assertEqual(3164000,summary["total_today"])
        client=receive_payment_server.app.test_client()
        with patch.object(farm_voucher_repository,"operational_summary",side_effect=[summary,{**summary,"outstanding_today":99}]) as operational:
            first=client.get("/business-os/api/farm-voucher/summary");second=client.get("/business-os/api/farm-voucher/summary")
        self.assertEqual("no-store",first.headers["Cache-Control"]);self.assertEqual(0,first.get_json()["summary"]["outstanding_today"])
        self.assertEqual(99,second.get_json()["summary"]["outstanding_today"]);self.assertEqual(2,operational.call_count)

    def test_sote_history_endpoint_normalizes_empty_filters_and_defaults(self):
        client=receive_payment_server.app.test_client()
        empty={"items":[],"records":[],"total":0,"page":1,"page_size":20,"pages":1}
        with patch.object(sotephwar_voucher_repository,"recent_submissions",return_value=empty) as recent:
            response=client.get("/business-os/api/sotephwar-voucher/history?page=&page_size=&status=&customer=&voucher=&start_date=&end_date=")
        self.assertEqual(200,response.status_code)
        body=response.get_json()
        self.assertEqual([],body["items"]);self.assertEqual(0,body["total"]);self.assertEqual(1,body["page"]);self.assertEqual(20,body["page_size"])
        recent.assert_called_once_with({"customer":"","voucher_number":"","date_from":None,"date_to":None,"payment_status":""},"1","20")

    def test_sote_history_no_records_has_stable_empty_shape(self):
        connection=MagicMock();connection.__enter__.return_value=connection
        connection.cursor.return_value.__enter__.return_value.fetchall.return_value=[]
        with patch.object(sotephwar_voucher_repository,"_connect",return_value=connection):
            result=sotephwar_voucher_repository.recent_submissions({},None,None)
        self.assertEqual([],result["items"]);self.assertEqual(0,result["total"])
        self.assertEqual(1,result["page"]);self.assertEqual(20,result["page_size"])

    def test_sote_history_logs_exact_validation_error_and_query_parameter(self):
        client=receive_payment_server.app.test_client()
        with patch.object(sotephwar_voucher_repository,"recent_submissions",side_effect=ValueError("page_size must be 20, 50, or 100")):
            with self.assertLogs("tools.sotephwar_voucher_portal",level="WARNING") as logged:
                response=client.get("/business-os/api/sotephwar-voucher/history?page_size=17")
        self.assertEqual(400,response.status_code)
        messages="\n".join(logged.output)
        self.assertIn("page_size must be 20, 50, or 100",messages)
        self.assertIn("'page_size': '17'",messages)

    def test_history_frontend_replaces_loading_state_on_error(self):
        script=(__import__('pathlib').Path(__file__).resolve().parents[1]/"static/operational_history.js").read_text()
        self.assertIn("Could not load recent insertions. Please try again.",script)
        self.assertIn("History unavailable",script)

    def test_all_pages_render_shared_sections_and_lan_safe_script(self):
        client=receive_payment_server.app.test_client()
        expected={"/business-os/farm-voucher":"Saved Drafts","/business-os/sotephwar-voucher":"Saved Drafts",
                  "/business-os/sotephwar-inventory":"Saved Movement Drafts","/business-os/general-transaction":"Saved Transaction Drafts"}
        for url,label in expected.items():
            html=client.get(url).get_data(as_text=True)
            self.assertIn(label,html);self.assertIn("operational_history.js",html);self.assertNotIn("Math.random",html);self.assertNotIn("crypto.randomUUID",html)

    def test_remove_endpoint_requires_protection_header(self):
        client=receive_payment_server.app.test_client()
        response=client.post("/business-os/api/farm-voucher/drafts/7/remove",json={})
        self.assertEqual(403,response.status_code)
        with patch.object(farm_voucher_repository,"remove_draft",return_value={"removed":True,"idempotent":False}):
            response=client.post("/business-os/api/farm-voucher/drafts/7/remove",json={},headers={"X-Business-OS-Request":"draft-management-v1"})
        self.assertEqual(200,response.status_code)


if __name__ == "__main__":unittest.main()
