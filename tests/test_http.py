"""Start the real app with disposable data and exercise its public workflow."""
from pathlib import Path
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='whole-house-customization-http-')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        cls.base = 'http://127.0.0.1:%d' % port
        env = dict(os.environ,
                   WHOLE_HOUSE_CUSTOMIZATION_DATA_DIR=str(Path(cls.tmp.name) / 'data'),
                   WHOLE_HOUSE_CUSTOMIZATION_EXPORT_DIR=str(Path(cls.tmp.name) / 'exports'),
                   WHOLE_HOUSE_CUSTOMIZATION_NO_BROWSER='1', PYTHONIOENCODING='utf-8')
        cls.log = open(Path(cls.tmp.name) / 'server.log', 'w+', encoding='utf-8')
        cls.proc = subprocess.Popen(
            [sys.executable, str(ROOT / 'app.py'), '--no-browser', '--port', str(port)],
            cwd=ROOT, env=env, stdout=cls.log, stderr=cls.log,
            creationflags=0x08000000 if os.name == 'nt' else 0)
        try:
            for _ in range(100):
                if cls.proc.poll() is not None:
                    cls.log.seek(0)
                    raise RuntimeError(cls.log.read())
                try:
                    with urllib.request.urlopen(cls.base + '/api/identity', timeout=0.5) as response:
                        if response.status == 200:
                            return
                except OSError:
                    time.sleep(0.1)
            raise RuntimeError('Application startup timed out')
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait(timeout=10)
        cls.log.close()
        cls.tmp.cleanup()

    def request_json(self, path, data=None):
        request = urllib.request.Request(
            self.base + path,
            data=json.dumps(data).encode('utf-8') if data is not None else None,
            headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.load(response)

    def test_project_name_in_identity_and_page(self):
        self.assertEqual(self.request_json('/api/identity')['application'],
                         'whole-house-customization-independent-v3')
        with urllib.request.urlopen(self.base + '/', timeout=5) as response:
            html = response.read().decode('utf-8')
        self.assertIn('<title>Whole-House Customization 报价系统</title>', html)
        self.assertIn('<strong>Whole-House Customization</strong>', html)

    def test_bootstrap_and_empty_database(self):
        self.assertTrue(self.request_json('/api/health')['ok'])
        self.assertEqual(self.request_json('/api/quotes')['quotes'], [])
        self.assertTrue(self.request_json('/api/bootstrap'))
        with urllib.request.urlopen(self.base + '/', timeout=5) as response:
            self.assertIn(b'id="depth"', response.read())

    def test_create_quote_and_download_customer_workbook(self):
        result = self.request_json('/api/quotes', {
            'customer': 'Demo Customer', 'project': 'Open Source Demo',
            'items': [{'cat': 'custom_cabinet', 'material': 'body_particle',
                       'length_mm': 1219.2, 'height_mm': 1219.2,
                       'depth_mm': 600, 'qty': 1, 'unit_price': 1}]})
        self.assertEqual(result['computed']['summary']['total'], 16)
        quote_id = result['quote']['id']
        exported = self.request_json('/api/quotes/%d/export?kind=customer&fmt=xlsx' % quote_id)
        with urllib.request.urlopen(self.base + exported['url'], timeout=15) as response:
            workbook = load_workbook(io.BytesIO(response.read()))
        self.assertTrue(workbook.worksheets[0]._images)
        self.assertFalse(any('CostProfit' in name for name in workbook.sheetnames))
        workbook.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
