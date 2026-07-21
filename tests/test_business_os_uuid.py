import json
import re
import subprocess
import unittest
from pathlib import Path

from scripts import receive_payment_server


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "static/business_os_uuid.js"
UUID_V4 = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", re.I)


def run_helper(setup):
    code = f"""
const fs=require('fs'),vm=require('vm');
const sandbox={{console,Uint8Array}};
{setup}
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync({json.dumps(str(HELPER))},'utf8'),sandbox);
sandbox.BusinessOS.secureUuidV4().then(value=>process.stdout.write(JSON.stringify({{value,fetchCalls:sandbox.fetchCalls||0}}))).catch(error=>{{console.error(error);process.exit(1)}});
"""
    result = subprocess.run(["node", "-e", code], check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


class BusinessOsUuidTest(unittest.TestCase):
    def test_crypto_random_uuid_is_preferred(self):
        result = run_helper("sandbox.crypto={randomUUID:()=>\"123e4567-e89b-42d3-a456-426614174000\"};sandbox.fetch=()=>{throw new Error('fetch not expected')};")
        self.assertEqual("123e4567-e89b-42d3-a456-426614174000", result["value"])
        self.assertEqual(0, result["fetchCalls"])

    def test_lan_http_falls_back_to_get_random_values(self):
        result = run_helper("sandbox.crypto={getRandomValues:bytes=>{for(let i=0;i<bytes.length;i++)bytes[i]=i;return bytes}};sandbox.fetch=()=>{throw new Error('fetch not expected')};")
        self.assertRegex(result["value"], UUID_V4)
        self.assertEqual("4", result["value"][14])
        self.assertIn(result["value"][19].lower(), "89ab")

    def test_no_web_crypto_uses_protected_flask_token(self):
        token = "9f50bc6a-6b41-4d61-8a9d-8fd2a5f69555"
        result = run_helper(f"sandbox.crypto=undefined;sandbox.fetchCalls=0;sandbox.fetch=async(url,options)=>{{sandbox.fetchCalls++;if(url!='/business-os/api/security/idempotency-token'||options.headers['X-Business-OS-Request']!=='uuid-v1')throw new Error('bad fallback request');return{{ok:true,status:200,text:async()=>JSON.stringify({{ok:true,token:{json.dumps(token)}}})}}}};")
        self.assertEqual(token, result["value"])
        self.assertEqual(1, result["fetchCalls"])

    def test_flask_token_endpoint_is_protected_and_returns_uuid_v4(self):
        client = receive_payment_server.app.test_client()
        self.assertEqual(403, client.post("/business-os/api/security/idempotency-token").status_code)
        response = client.post("/business-os/api/security/idempotency-token", headers={"X-Business-OS-Request": "uuid-v1"})
        self.assertEqual(200, response.status_code)
        self.assertRegex(response.get_json()["token"], UUID_V4)

    def test_all_submission_pages_load_and_use_shared_helper(self):
        inventory_page = (ROOT / "tools/sotephwar_inventory_portal.py").read_text()
        farm_page = (ROOT / "tools/farm_voucher_portal.py").read_text()
        sote_page = (ROOT / "tools/sotephwar_voucher_portal.py").read_text()
        inventory_script = (ROOT / "static/sotephwar_inventory.js").read_text()
        farm_script = (ROOT / "static/farm_voucher.js").read_text()
        sote_script = (ROOT / "static/sotephwar_voucher.js").read_text()
        for page in (farm_page, sote_page):
            self.assertIn("/static/business_os_uuid.js?v=20260720-2", page)
        for script in (farm_script, sote_script):
            self.assertIn("BusinessOS.secureUuidV4()", script)
            self.assertNotIn("Math.random", script)
        self.assertNotIn("BusinessOS.secureUuidV4()", inventory_script)
        self.assertIn("submission_key:draft.submission_key", inventory_script)
        self.assertNotIn("crypto.randomUUID", inventory_script)

    def test_inventory_submission_uses_server_generated_draft_identity(self):
        script = (ROOT / "static/sotephwar_inventory.js").read_text()
        self.assertIn("if(!draft||draft.status!=='previewed')return", script)
        self.assertIn("submission_key:draft.submission_key", script)
        self.assertNotIn("Math.random", script)


if __name__ == "__main__":
    unittest.main()
