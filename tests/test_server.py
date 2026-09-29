import http.client
import json
import tempfile
import threading
import unittest

from tvbakim.demo import DemoDevice
from tvbakim.engine import Engine
from tvbakim.server import App, LocalServer
from tvbakim.store import Store
from tests.test_engine import TracedAdb


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.adb = TracedAdb()
        self.engine = Engine(self.adb, Store(self.tmp.name), DemoDevice)
        self.app = App(self.engine, demo=True)
        self.server = LocalServer(self.app)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
        self.thread.start()
    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.app.jobs.close()
        self.thread.join(2)
        self.tmp.cleanup()
    def request(self, method, path, body=None, headers=None, auth=True):
        request_headers = {'Authorization': 'Bearer ' + self.app.token} if auth else {}
        if body is not None: request_headers['Content-Type'] = 'application/json'
        request_headers.update(headers or {})
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        try:
            connection.request(method, path, body=body, headers=request_headers)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally: connection.close()

    def test_loopback_only_and_static_has_no_token(self):
        self.assertEqual(self.server.server_address[0], '127.0.0.1')
        status, headers, body = self.request('GET', '/', auth=False)
        self.assertEqual(status, 200)
        self.assertNotIn(self.app.token.encode(), body)
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertIn("frame-ancestors 'none'", headers['Content-Security-Policy'])

    def test_api_requires_bearer(self):
        for path in ['/api/status', '/api/discover', '/api/history', '/api/report']:
            with self.subTest(path=path): self.assertEqual(self.request('GET', path, auth=False)[0], 401)
        self.assertEqual(self.request('POST', '/api/inspect', '{}', auth=False)[0], 401)

    def test_nonascii_authorization_is_rejected_cleanly(self):
        self.assertEqual(self.request('GET', '/api/status', headers={'Authorization': 'Bearer caf\u00e9'})[0], 401)

    def test_wrong_origin_host_and_fetch_site_rejected_even_with_token(self):
        for headers in [{'Origin': 'https://evil.example'}, {'Host': 'evil.example'}, {'Sec-Fetch-Site': 'cross-site'}]:
            with self.subTest(headers=headers):
                self.assertEqual(self.request('GET', '/api/status', headers=headers)[0], 403)
                self.assertEqual(self.request('POST', '/api/inspect', '{}', headers=headers)[0], 403)

    def test_same_origin_allowed(self):
        status, _, body = self.request('GET', '/api/status', headers={'Origin': self.server.origin})
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)['demo'])

    def test_get_never_dispatches_mutations(self):
        for path in ['/api/apply', '/api/connect', '/api/pair', '/api/plan', '/api/rollback-plan', '/api/guard/plan']:
            with self.subTest(path=path): self.assertEqual(self.request('GET', path)[0], 404)
        self.assertEqual(self.app.jobs.list(), [])
        self.assertEqual(self.adb.writes, [])

    def test_traversal_and_unknown_static_paths_not_served(self):
        for path in ['/../engine.py', '/%2e%2e/engine.py', '/tvbakim/engine.py', '//etc/passwd', '/api/report/../../foo']:
            with self.subTest(path=path): self.assertEqual(self.request('GET', path)[0], 404)

    def test_invalid_json_content_type_and_oversize_rejected(self):
        self.assertEqual(self.request('POST', '/api/inspect', '{broken')[0], 400)
        self.assertEqual(self.request('POST', '/api/inspect', '[]')[0], 400)
        self.assertEqual(self.request('POST', '/api/inspect', '{}', {'Content-Type': 'text/plain'})[0], 400)
        self.assertEqual(self.request('POST', '/api/inspect', 'x' * 32769)[0], 400)
        self.assertEqual(self.adb.writes, [])

    def test_report_removes_identifier_and_marks_demo(self):
        self.engine.inspect('demo-tv')
        status, headers, body = self.request('GET', '/api/report')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['evidence'], 'synthetic_demo')
        self.assertNotIn(b'serial_hash', body)
        self.assertNotIn(b'demo-tv', body)
        self.assertIn('attachment', headers['Content-Disposition'])

    def test_readonly_status_and_discovery_do_not_write(self):
        self.assertEqual(self.request('GET', '/api/status')[0], 200)
        self.assertEqual(self.request('GET', '/api/discover')[0], 200)
        self.assertEqual(self.request('GET', '/api/history')[0], 200)
        self.assertEqual(self.adb.writes, [])


if __name__ == '__main__': unittest.main()
