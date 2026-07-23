import unittest
import re
from pathlib import Path
from unittest.mock import patch

import business_os_app as receive_payment_server
from tools import voucher_engine


ROOT = Path(__file__).resolve().parents[1]
MODULES = (
    ("farm-voucher", "farm_voucher.js"),
    ("sotephwar-voucher", "sotephwar_voucher.js"),
    ("sotephwar-inventory", "sotephwar_inventory.js"),
    ("general-transaction", "general_transaction.js"),
)


class LanOperationalPreviewTest(unittest.TestCase):
    def setUp(self):
        self.client = receive_payment_server.app.test_client()

    def test_operational_pages_load_with_localhost_and_lan_host_headers(self):
        for host in ("127.0.0.1:5059", "192.168.0.103:5059"):
            for slug, _script in MODULES:
                response = self.client.get(f"/business-os/{slug}", headers={"Host": host})
                self.assertEqual(200, response.status_code, (host, slug))
                html = response.get_data(as_text=True)
                self.assertNotIn("http://127.0.0.1:5059", html)
                self.assertNotIn("http://localhost:5059", html)

    def test_all_operational_browser_calls_are_same_origin_relative(self):
        for _slug, filename in MODULES:
            script = (ROOT / "static" / filename).read_text(encoding="utf-8")
            self.assertIn("/business-os/", script)
            self.assertNotIn("http://127.0.0.1", script)
            self.assertNotIn("http://localhost", script)
            self.assertNotIn("Math.random", script)

    def test_voucher_operations_use_draft_id_when_number_differs(self):
        mismatch = {"id": 14, "voucher_number": "23"}
        self.assertEqual("/drafts/14", f"/drafts/{mismatch['id']}")
        self.assertNotEqual("/drafts/23", f"/drafts/{mismatch['id']}")
        for filename in ("farm_voucher.js", "sotephwar_voucher.js"):
            script = (ROOT / "static" / filename).read_text(encoding="utf-8")
            self.assertIn("function draftUrl(value=draft,suffix='')", script)
            self.assertIn("const id=Number(value?.id)", script)
            self.assertIn("draftUrl(saved,`/${action}`)", script)
            self.assertIn("`${api}/drafts/${draft.id}/pdf`", script)
            self.assertIn("`${api}/drafts/${draft.id}/submit`", script)
            self.assertIn("`${api}/drafts/${e.detail.id}`", script)
            for expression in re.findall(r"drafts/\$\{([^}]+)\}", script):
                self.assertNotIn("voucher", expression.lower())

        history = (ROOT / "static/operational_history.js").read_text(encoding="utf-8")
        self.assertIn('data-continue="${r.id}"', history)
        self.assertIn('data-preview="${r.id}"', history)
        self.assertIn('data-remove="${r.id}"', history)
        self.assertIn('data-detail="${r.draft_id}"', history)
        self.assertIn('/drafts/${r.draft_id}/pdf', history)

    def test_voucher_ui_uses_validate_then_submit_and_lazy_pdf_actions(self):
        for slug, prefix, filename in (
            ("farm-voucher", "fv", "farm_voucher.js"),
            ("sotephwar-voucher", "sv", "sotephwar_voucher.js"),
        ):
            html = self.client.get(f"/business-os/{slug}").get_data(as_text=True)
            script = (ROOT / "static" / filename).read_text(encoding="utf-8")
            self.assertIn("Save Draft → Validate → Submit", html)
            self.assertNotIn(f'<button id="{prefix}Preview"', html)
            self.assertNotIn(f'<button id="{prefix}Pdf"', html)
            self.assertIn("✓ Voucher submitted successfully.", script)
            for label in ("View Voucher", "Print PDF", "Download PDF"):
                self.assertIn(label, script)
            self.assertIn("!['validated','previewed'].includes(draft.status)", script)

    def test_optional_print_and_save_pdf_follow_validation_without_blocking_submit(self):
        for slug, prefix, filename, fallback_name in (
            ("farm-voucher", "fv", "farm_voucher.js", "Farm_Voucher_"),
            ("sotephwar-voucher", "sv", "sotephwar_voucher.js", "SotePhwar_Voucher_"),
        ):
            html = self.client.get(f"/business-os/{slug}").get_data(as_text=True)
            script = (ROOT / "static" / filename).read_text(encoding="utf-8")
            self.assertIn(f'id="{prefix}Print" disabled', html)
            self.assertIn(f'id="{prefix}SavePdf" disabled', html)
            self.assertIn('aria-hidden="true">🖨', html)
            self.assertIn('aria-hidden="true">⬇', html)
            self.assertIn("['validated','previewed','submitted'].includes(draft.status)", script)
            self.assertIn("!['validated','previewed'].includes(draft.status)", script)
            self.assertIn("draftUrl(draft,'/pdf')", script)
            self.assertIn(fallback_name, script)
            self.assertIn("catch(error){errors([error.message]);", script)
            self.assertNotIn("documentAction(download){pdfReady=false", script)

        history = (ROOT / "static/operational_history.js").read_text(encoding="utf-8")
        self.assertIn("r.pdf_available", history)
        self.assertIn("🖨", history)
        self.assertIn("⬇", history)
        self.assertIn("/drafts/${r.draft_id}/pdf?inline=1", history)
        self.assertIn("/drafts/${r.draft_id}/pdf", history)

    def test_validate_endpoint_confirms_submit_ready_state_without_pdf(self):
        cases = (
            (
                "/business-os/api/farm-voucher/drafts/14/validate",
                "tools.farm_voucher_repository.set_workflow_state",
            ),
            (
                "/business-os/api/sotephwar-voucher/drafts/14/validate",
                "tools.sotephwar_voucher_repository.set_workflow_state",
            ),
        )
        for endpoint, target in cases:
            result = {"draft": {"id": 14, "status": "previewed"}, "voucher": {}}
            with patch(target, return_value=result) as set_state:
                response = self.client.post(endpoint)
            self.assertEqual(200, response.status_code)
            set_state.assert_called_once_with(14, "previewed")
            self.assertNotIn("pdf_url", response.get_json())

    def test_voucher_preview_finishes_without_waiting_for_iframe_load(self):
        for filename in ("farm_voucher.js", "sotephwar_voucher.js"):
            script = (ROOT / "static" / filename).read_text(encoding="utf-8")
            self.assertIn("Preparing print preview...", script)
            self.assertIn("panel.innerHTML='';panel.appendChild(frame);pdfReady=draft.status==='previewed'", script)
            self.assertNotIn("frame.onload=()=>{panel.querySelector", script)
            self.assertIn("data-preview-retry", script)
            self.assertIn("Preview server returned an invalid PDF response", script)
            self.assertIn("Preview server returned an empty PDF", script)
            self.assertIn("signature!=='%PDF-'", script)
            self.assertIn("new Blob([buffer],{type:'application/pdf'})", script)
            self.assertIn("response.arrayBuffer()", script)
            self.assertNotIn("response.blob()", script)
            self.assertNotIn("response.clone()", script)
            self.assertIn("cache:'no-store'", script)
            self.assertIn("credentials:'same-origin'", script)
            self.assertIn("if(blob.size===0)throw new Error('Preview server returned an empty PDF')", script)
            self.assertNotIn("byteLength<5)throw new Error('Preview server returned an empty PDF')", script)
            for event in ("fetch response", "blob created", "object URL created", "iframe src assigned", "iframe load", "iframe error", "preview rejected"):
                self.assertIn(f"[BusinessOS preview] {event}", script)
            self.assertNotIn("frame.onload=()=>URL.revokeObjectURL", script)
            self.assertIn("if(!response.ok)", script) if filename == "farm_voucher.js" else self.assertIn("if(!r.ok)", script)

    def test_preview_failure_clears_spinner_and_keeps_submit_disabled(self):
        farm = (ROOT / "static/farm_voucher.js").read_text(encoding="utf-8")
        sote = (ROOT / "static/sotephwar_voucher.js").read_text(encoding="utf-8")
        for script in (farm, sote):
            self.assertIn("function previewFailure(panel,message){pdfReady=false", script)
            self.assertIn("Submit remains disabled.", script)
            self.assertIn("panel.innerHTML=", script)
            self.assertIn("return false", script)

    def test_successful_preview_enables_only_server_previewed_draft(self):
        for filename, updater in (("farm_voucher.js", "updateActions"), ("sotephwar_voucher.js", "actions")):
            script = (ROOT / "static" / filename).read_text(encoding="utf-8")
            self.assertIn("pdfReady=draft.status==='previewed'", script)
            self.assertIn(f"pdfReady=draft.status==='previewed';{updater}()", script)
            self.assertIn("!['validated','previewed'].includes(draft.status)", script)

    def test_json_error_handling_rejects_html_or_invalid_json(self):
        for _slug, filename in MODULES:
            script = (ROOT / "static" / filename).read_text(encoding="utf-8")
            self.assertIn("JSON.parse(text)", script)
            self.assertIn("invalid response", script)

    def test_inventory_and_general_use_server_generated_submission_identity(self):
        inventory = (ROOT / "static/sotephwar_inventory.js").read_text(encoding="utf-8")
        general = (ROOT / "static/general_transaction.js").read_text(encoding="utf-8")
        for script in (inventory, general):
            self.assertIn("submission_key:draft.submission_key", script)
            self.assertNotIn("crypto.randomUUID", script)
        self.assertIn("Preparing preview...", inventory)
        self.assertIn("Preview failed", inventory)
        self.assertNotIn("Preparing preview...", general)
        self.assertNotIn("Preview failed", general)

    def test_pdf_preview_route_works_with_lan_host_and_returns_no_absolute_url(self):
        draft = {
            "id": 71, "sector": "sotephwar", "status": "previewed", "voucher_number": "SP-9001",
            "voucher_date": "2026-07-18", "customer_id": 7,
            "customer_name": "Dealer", "payment_method": "Cash",
            "amount_received": "0", "note": "", "version": 3,
            "customer_snapshot": {
                "id": 7, "customer_name": "Dealer", "phone_number": "09123",
                "town": "Heho", "contact_address": "Main Road", "payment_terms_days": 30,
            },
            "lines": [{"product_code": "1l", "quantity": "1", "unit_price": "33000", "note": ""}],
        }

        def write_pdf(_voucher, path):
            path.write_bytes(b"%PDF-1.4\n%%EOF\n")

        with patch("tools.sotephwar_voucher_repository.get_draft", return_value=draft), \
             patch("tools.sotephwar_voucher_portal.write_sotephwar_voucher_pdf", side_effect=write_pdf):
            response = self.client.get(
                "/business-os/api/sotephwar-voucher/drafts/71/pdf?inline=1&version=3",
                headers={"Host": "192.168.0.103:5059"},
            )
        self.assertEqual(200, response.status_code)
        self.assertEqual("application/pdf", response.mimetype)
        self.assertTrue(response.data.startswith(b"%PDF-"))

        with patch("tools.sotephwar_voucher_repository.get_draft", return_value=draft), \
             patch("tools.sotephwar_voucher_portal.write_sotephwar_voucher_pdf", side_effect=write_pdf):
            download = self.client.get(
                "/business-os/api/sotephwar-voucher/drafts/71/pdf",
                headers={"Host": "192.168.0.103:5059"},
            )
        self.assertEqual(200, download.status_code)
        self.assertEqual("application/pdf", download.mimetype)
        self.assertIn("attachment", download.headers["Content-Disposition"])
        self.assertIn("SotePhwar_Voucher_SP-9001.pdf", download.headers["Content-Disposition"])
        self.assertTrue(response.data.startswith(b"%PDF-"))
        self.assertNotIn("Location", response.headers)

    def test_preview_api_lan_host_returns_json_not_html(self):
        result = {
            "draft": {"id": 71, "status": "previewed", "version": 3},
            "voucher": {"status": "previewed", "total_amount": "33000.00"},
        }
        with patch("tools.sotephwar_voucher_repository.set_workflow_state", return_value=result):
            response = self.client.post(
                "/business-os/api/sotephwar-voucher/drafts/71/preview",
                headers={"Host": "192.168.0.103:5059"},
            )
        self.assertEqual(200, response.status_code)
        self.assertTrue(response.is_json)
        self.assertTrue(response.get_json()["ok"])
        self.assertEqual("previewed", response.get_json()["draft"]["status"])
        self.assertEqual(
            "/business-os/api/sotephwar-voucher/drafts/71/pdf?inline=1&version=3",
            response.get_json()["pdf_url"],
        )
        self.assertNotIn("localhost", response.get_json()["pdf_url"])
        self.assertNotIn("127.0.0.1", response.get_json()["pdf_url"])
        pdf_path = response.get_json()["pdf_url"].split("?", 1)[0]
        endpoint, values = receive_payment_server.app.url_map.bind("192.168.0.101:5059").match(
            pdf_path, method="GET"
        )
        self.assertEqual("business_os_sotephwar_voucher_pdf", endpoint)
        self.assertEqual({"draft_id": 71}, values)

    def test_preview_metadata_and_pdf_are_two_explicit_requests(self):
        sote = (ROOT / "static/sotephwar_voucher.js").read_text(encoding="utf-8")
        farm = (ROOT / "static/farm_voucher.js").read_text(encoding="utf-8")
        for script in (sote, farm):
            self.assertIn("action==='preview'", script)
            self.assertIn("pdf_url", script)
            self.assertIn("PDF GET", script)
            self.assertIn("Accept':'application/pdf", script)
            self.assertNotIn("if(b.voucher)await previewPdf()", script)

    def test_preview_validation_failure_is_structured_and_logged_with_code(self):
        failure = voucher_engine.VoucherValidationError([
            "amount_received cannot exceed total_amount"
        ])
        with patch(
            "tools.sotephwar_voucher_repository.set_workflow_state",
            side_effect=failure,
        ), self.assertLogs("tools.sotephwar_voucher_portal", level="WARNING") as logs:
            response = self.client.post(
                "/business-os/api/sotephwar-voucher/drafts/14/preview",
                headers={"Host": "192.168.0.101:5059"},
            )
        self.assertEqual(400, response.status_code)
        self.assertTrue(response.is_json)
        self.assertEqual({
            "ok": False,
            "error": "amount_received cannot exceed total_amount",
            "code": "amount_received_exceeds_total",
            "errors": ["amount_received cannot exceed total_amount"],
        }, response.get_json())
        self.assertIn("code=amount_received_exceeds_total", "\n".join(logs.output))


if __name__ == "__main__":
    unittest.main()
