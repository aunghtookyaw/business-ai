import unittest
from unittest.mock import patch
from html.parser import HTMLParser

import business_os_app as receive_payment_server
from tools import business_os_portal
from tools import farm_voucher_repository
from tools import veggies_production_portal as veggies


class AssetUrlParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, _tag, attrs):
        values = dict(attrs)
        for name in ("href", "src"):
            value = values.get(name, "")
            if value.startswith(("/static/", "/business-os/assets/")):
                self.urls.append(value)


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
        for label in ("BigShot Business OS", "Dashboard", "Daily Entry", "Farm Voucher", "Receive Payment", "General Transaction",
                      "Veggies Production", "Master Data", "Veggies Crop Master", "Customers"):
            self.assertIn(label, html)
        self.assertIn('aria-current="page">Dashboard', html)
        self.assertNotIn("POSTGRES_PASSWORD", html)
        self.assertNotIn("nc_pat_", html)
        self.assertIn('href="/business-os/farm-voucher"', html)

    def test_dashboard_static_assets_are_mounted_and_served(self):
        response = self.client.get("/business-os")
        parser = AssetUrlParser()
        parser.feed(response.get_data(as_text=True))

        self.assertEqual(
            ["/static/business_os.css", "/business-os/assets/logo", "/static/business_os.js"],
            parser.urls,
        )
        expected_types = {
            "/static/business_os.css": "text/css",
            "/static/business_os.js": "text/javascript",
            "/business-os/assets/logo": "image/jpeg",
        }
        for url, content_type in expected_types.items():
            with self.subTest(url=url):
                asset = self.client.get(url)
                self.assertEqual(200, asset.status_code)
                self.assertEqual(content_type, asset.mimetype)
                self.assertTrue(asset.data)

    def test_integrated_farm_voucher_route_card_and_sidebar(self):
        with patch.object(farm_voucher_repository, "list_customers", return_value=[]), \
             patch.object(farm_voucher_repository, "list_crops", return_value=[{"id": 1, "crop_name": "Beetroot"}]), \
             patch.object(farm_voucher_repository, "list_drafts", return_value=[]):
            home = self.client.get("/business-os")
            integrated = self.client.get("/business-os/farm-voucher")
            legacy = self.client.get("/farm-voucher")
            customers = self.client.get("/business-os/api/farm-voucher/customers")
            drafts = self.client.get("/business-os/api/farm-voucher/drafts")
            crops = self.client.get("/business-os/api/farm-voucher/crops")
        self.assertEqual([200, 200, 200, 200, 200, 200], [home.status_code, integrated.status_code, legacy.status_code, customers.status_code, drafts.status_code, crops.status_code])
        html = integrated.get_data(as_text=True)
        self.assertIn("BigShot Business OS", html)
        self.assertIn('aria-current="page">Farm Voucher', html)
        self.assertIn('/static/farm_voucher.css', html)
        self.assertIn('/static/farm_voucher.js', html)
        self.assertIn('Invoice Date', html)
        self.assertIn('Add Date Section', html)
        self.assertEqual("Beetroot", crops.get_json()["crops"][0]["crop_name"])
        self.assertIn('href="/business-os/farm-voucher"', home.get_data(as_text=True))

    def test_root_redirects_to_business_os(self):
        response = self.client.get("/")
        self.assertEqual(302, response.status_code)
        self.assertEqual("/business-os", response.headers["Location"])

    def test_receive_payment_is_available_only_inside_business_os(self):
        with patch.object(receive_payment_server, "_list_vouchers", return_value=[]):
            integrated = self.client.get("/business-os/receive-payment")
            old = self.client.get("/receive-payment-basic")
        html = integrated.get_data(as_text=True)
        self.assertEqual(200, integrated.status_code)
        self.assertEqual(404, old.status_code)
        self.assertIn("BigShot Business OS", html)
        self.assertIn('aria-current="page">Receive Payment', html)
        self.assertIn('action="/business-os/receive-payment"', html)

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
        for slug in ("inventory", "financial", "reports", "settings"):
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
