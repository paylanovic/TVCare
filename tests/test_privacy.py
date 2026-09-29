import importlib.util
from pathlib import Path
import io
import unittest
import zipfile

spec=importlib.util.spec_from_file_location('privacy_check',Path(__file__).resolve().parents[1]/'scripts/privacy_check.py')
privacy=importlib.util.module_from_spec(spec)
spec.loader.exec_module(privacy)

class PrivacyTests(unittest.TestCase):
    def scan(self,data,name='file.txt'):
        findings=[]
        privacy.scan_bytes(name,data,[],findings)
        return findings
    def test_private_keys_and_tokens_detected_without_echoing_values(self):
        for value in [b'-----BEGIN '+b'PRIVATE KEY-----',b'ghp_'+b'A'*36]:
            findings=self.scan(value)
            self.assertTrue(findings)
            self.assertNotIn(value.decode(),str(findings))
    def test_real_home_and_private_network_paths_detected(self):
        private_home='/'.join(['','Users','private-user','project','main.py'])
        private_ip='.'.join(['192','168','4','12'])
        for value in [private_home,private_ip]: self.assertTrue(self.scan(value.encode()))
    def test_documentation_and_loopback_addresses_allowed(self):
        self.assertEqual(self.scan(b'192.0.2.10:5555 http://127.0.0.1:8765'),[])
    def test_archive_members_checked_recursively(self):
        memory=io.BytesIO()
        with zipfile.ZipFile(memory,'w') as z:z.writestr('credentials.key',b'private material')
        self.assertTrue(self.scan(memory.getvalue(),'nested.zip'))
    def test_private_marker_not_printed(self):
        findings=[]
        privacy.scan_bytes('file.txt',b'dummy private marker',[b'dummy private marker'],findings)
        self.assertEqual(findings,[{'file':'file.txt','category':'private_marker'}])

if __name__=='__main__': unittest.main()
