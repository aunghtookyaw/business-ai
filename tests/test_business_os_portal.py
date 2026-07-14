import unittest
from unittest.mock import patch

from scripts import receive_payment_server
from tools import business_os_portal
from tools import veggies_production_portal as veggies


def empty_search(filters):
    return [], {"total_records": 0, "page": int(filters.get("page") or 1), "total_pages": 1}


class BusinessOsPortalTest(unittest.TestCase):
    def setUp(self):
        self.client = receive_payment_server.app.test_client()

    def test_home_and_sidebar_show_expected_modules_without_secrets(self):
        with patch.object(business_os_portal, "_database_health", return_value=("Connected", "good")):
            response = self.client.get("/business-os")
        html = response.get_data(as_text=True)
        self.assertEqual(200, response.status_code)
        for label in ("BigShot Business OS", "Dashboard", "Sales", "Receive Payment", "Production",
                      "Veggies Production", "Veggies Crop Master", "Customers", "Inventory",
                      "Financial", "Reports", "Settings"):
            self.assertIn(label, html)
        self.assertIn('aria-current="page">Dashboard', html)
        self.assertNotIn("POSTGRES_PASSWORD", html)
        self.assertNotIn("nc_pat_", html)

    def test_root_redirects_to_business_os(self):
        response = self.client.get("/")
        self.assertEqual(302, response.status_code)
        self.assertEqual("/business-os", response.headers["Location"])

    def test_integrated_receive_payment_and_old_route_both_work(self):
        with patch.object(receive_payment_server, "_list_vouchers", return_value=[]):
            integrated = self.client.get("/business-os/receive-payment")
            old = self.client.get("/receive-payment-basic")
        html = integrated.get_data(as_text=True)
        self.assertEqual(200, integrated.status_code)
        self.assertEqual(200, old.status_code)
        self.assertIn("BigShot Business OS", html)
        self.assertIn('aria-current="page">Receive Payment', html)
        self.assertIn('action="/business-os/receive-payment"', html)
        self.assertIn("Receive Payment Basic", old.get_data(as_text=True))

    def test_integrated_veggies_routes_and_old_routes_work(self):
        crops = []
        with patch.object(veggies, "portal_crops", return_value=crops), \
             patch.object(veggies, "search_records", side_effect=empty_search), \
             patch.object(veggies, "today_summary", return_value={"total_quantity": 0, "submission_count": 0, "crop_count": 0, "latest_entry_time": None, "unit_pending": True}), \
             patch.object(veggies, "list_crop_master", return_value=[]):
            integrated = self.client.get("/business-os/veggies-production")
            crop_master = self.client.get("/business-os/veggies-production/crops")
            old = self.client.get("/veggies-production")
            old_master = self.client.get("/veggies-production/crops")
        self.assertEqual([200, 200, 200, 200], [integrated.status_code, crop_master.status_code, old.status_code, old_master.status_code])
        self.assertIn('aria-current="page">Veggies Production', integrated.get_data(as_text=True))
        self.assertIn('aria-current="page">Veggies Crop Master', crop_master.get_data(as_text=True))

    def test_placeholder_pages_return_200(self):
        for slug in ("customers", "inventory", "financial", "reports", "settings"):
            response = self.client.get(f"/business-os/{slug}")
            self.assertEqual(200, response.status_code, slug)
            self.assertIn("Module planned for a future version.", response.get_data(as_text=True))

    def test_shared_404_and_database_unavailable_are_safe(self):
        missing = self.client.get("/business-os/not-a-page")
        self.assertEqual(404, missing.status_code)
        self.assertIn("Page not found", missing.get_data(as_text=True))

        def unavailable():
            raise RuntimeError("password=do-not-render")

        status, css_class = business_os_portal._database_health(unavailable)
        self.assertEqual(("Unavailable", "bad"), (status, css_class))
        with patch.object(business_os_portal, "_database_health", return_value=(status, css_class)):
            html = self.client.get("/business-os").get_data(as_text=True)
        self.assertIn("Unavailable", html)
        self.assertNotIn("do-not-render", html)


if __name__ == "__main__":
    unittest.main()
