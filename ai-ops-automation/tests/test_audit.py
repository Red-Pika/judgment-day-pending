import json
import os
import tempfile
import unittest
from opsguard.audit import AuditLog, AuditTamperError, verify_file


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "a.jsonl")

    def read(self):
        with open(self.path) as f:
            return f.read()

    def write(self, text, mode="w"):
        with open(self.path, mode) as f:
            f.write(text)

    def test_chain_valid(self):
        log = AuditLog(self.path)
        for i in range(5):
            log.append("e", n=i)
        self.assertEqual(verify_file(self.path), (True, None))

    def test_edit_detected(self):
        log = AuditLog(self.path)
        for i in range(5):
            log.append("e", n=i)
        lines = self.read().splitlines()
        e = json.loads(lines[2])
        e["data"]["n"] = 999
        lines[2] = json.dumps(e)
        self.write("\n".join(lines) + "\n")
        self.assertEqual(verify_file(self.path), (False, 3))

    def test_deleted_line_detected(self):
        log = AuditLog(self.path)
        for i in range(4):
            log.append("e", n=i)
        lines = self.read().splitlines()
        del lines[1]
        self.write("\n".join(lines) + "\n")
        self.assertFalse(verify_file(self.path)[0])

    def test_reopen_continues_chain(self):
        AuditLog(self.path).append("a")
        AuditLog(self.path).append("b")
        self.assertEqual(verify_file(self.path), (True, None))
        self.assertEqual(len(self.read().splitlines()), 2)

    def test_refuses_to_open_tampered_log(self):
        AuditLog(self.path).append("a")
        self.write('{"seq":2,"bogus":true}\n', "a")
        with self.assertRaises(AuditTamperError):
            AuditLog(self.path)


if __name__ == "__main__":
    unittest.main()
