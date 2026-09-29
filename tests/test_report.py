import json
import unittest

from tvbakim.demo import DemoAdb, DemoDevice
from tvbakim.report import sanitize_report


class ReportTests(unittest.TestCase):
    def test_inspection_omits_identifiers_raw_logs_and_packages(self):
        device = DemoDevice(DemoAdb(), 'demo-tv')
        data = device.inspect()
        data.update(serial='192.0.2.10:5555', packages=device.packages(), health=device.health())
        data['health']['cam_evidence_lines'] = ['SECRET RAW LOG']
        data['health']['read_errors'] = [{'error': 'SECRET IP 192.0.2.10'}]
        raw = json.dumps(sanitize_report(data, True))
        for private in ['192.0.2.10', 'SECRET', 'serial_hash', 'fingerprint', 'com.tcl.browser']:
            self.assertNotIn(private, raw)
        self.assertEqual(sanitize_report(data, True)['read_error_count'], 1)

    def test_transaction_omits_values_packages_and_errors(self):
        data = {'id': 'a' * 32, 'status': 'partial', 'kind': 'apply', 'error': 'SECRET',
                'device': {'serial_hash': 'SECRET', 'model': 'TV'},
                'actions': [{'type': 'package', 'package': 'com.private.app', 'status': 'failed', 'before': 'SECRET', 'after': 'SECRET', 'error': 'SECRET'}]}
        result = sanitize_report(data)
        self.assertEqual(result['evidence'], 'device_readings')
        raw = json.dumps(result)
        self.assertNotIn('SECRET', raw)
        self.assertNotIn('com.private.app', raw)
        self.assertEqual(result['transaction']['status'], 'partial')

    def test_missing_data_does_not_invent_metrics(self):
        result = sanitize_report({'health': {'read_errors': [{}]}})
        self.assertIsNone(result['health']['memory'])
        self.assertIsNone(result['health']['events'])
        self.assertEqual(result['read_error_count'], 1)


if __name__ == '__main__': unittest.main()
