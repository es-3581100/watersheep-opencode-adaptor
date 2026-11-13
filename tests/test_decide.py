import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from watersheep_adaptor.decide import decide, decision_request
from watersheep_adaptor import Invalid


class Fixture(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.received = request
        if self.server.mode == "timeout":
            time.sleep(0.2)
        q = request["questions"]["decision"]
        t = q["type"]
        data = {"binary": {"type": "noul", "noul": .72}, "choice": {"type": "choice", "choice": "z", "probabilities": {"z": .7, "a": .3}}, "score": {"type": "score", "score": .4, "probabilities": {"0": .6, "1": .4}, "legend": {"0": "z", "1": "a"}}, "multi": {"type": "multi", "choices": ["z"], "probabilities": {"z": .8, "a": .1}}}[t]
        if self.server.mode == "error":
            data = {"type": t, "error": "fixture failure"}
        if self.server.mode == "malformed":
            data = {"type": t}
        raw = json.dumps({"model": "fixture", "answers": {"decision": data}, "usage": {"input_tokens": 12}}).encode()
        try:
            self.send_response(200)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            pass


class Decisions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.backend = ThreadingHTTPServer(("127.0.0.1", 0), Fixture)
        threading.Thread(target=cls.backend.serve_forever, daemon=True).start()
        cls.url = "http://127.0.0.1:%d/v1/decisions" % cls.backend.server_port

    @classmethod
    def tearDownClass(cls):
        cls.backend.shutdown()
        cls.backend.server_close()

    def setUp(self):
        self.backend.mode = "ok"

    def test_types_and_order(self):
        for kind in ("binary", "choice", "score", "multi"):
            args = {"state": "context", "question": "decide?", "type": kind}
            if kind != "binary":
                args["options"] = ["z", "a"]
            with self.subTest(kind=kind):
                result = decide(args, self.url, "fixture")
                self.assertTrue(result["ok"], result)
                self.assertIn("no execution authority", result["notice"])
                q = self.backend.received["questions"]["decision"]
                self.assertEqual(q["instructions"], "decide?")
                if kind != "binary":
                    self.assertEqual(q["criteria"], ["z", "a"])
                    probs = result["watersheep"]["answers"]["decision"]["probabilities"]
                    self.assertEqual(list(probs), ["0", "1"] if kind == "score" else ["z", "a"])
                self.assertEqual(result["watersheep"]["usage"], {"input_tokens": 12})

    def test_bad_arguments(self):
        for args in ({}, {"state": "x", "question": "q", "type": "binary", "options": []}, {"state": "x", "question": "q", "type": "choice", "options": ["same", "same"]}, {"state": "x", "question": "q", "type": "score", "options": ["only"]}, {"state": "x", "question": "q", "type": "foo"}):
            with self.subTest(args=args), self.assertRaises(Invalid):
                decision_request(args)

    def test_backend_errors_and_timeout(self):
        args = {"state": "", "question": "q", "type": "binary"}
        for mode, code in (("error", "decision_error"), ("malformed", "backend_error"), ("timeout", "backend_error")):
            self.backend.mode = mode
            result = decide(args, self.url, "fixture", timeout=.02)
            self.assertEqual(result["error"]["code"], code)
        self.assertEqual(decide(args, "http://127.0.0.1:1/v1/decisions", "fixture", timeout=.1)["error"]["code"], "backend_error")
        self.assertEqual(decide(args, self.url, "wrong")["error"]["code"], "backend_error")

    def test_cli_and_install_no_overwrite(self):
        env = dict(os.environ, WATERSHEEP_UPSTREAM=self.url, WATERSHEEP_MODEL="fixture")
        command = [sys.executable, "-c", "from watersheep_adaptor.decide import main; main()"]
        result = subprocess.run(command, input=json.dumps({"state": "x", "question": "q", "type": "binary"}), text=True, capture_output=True, env=env, check=True)
        self.assertTrue(json.loads(result.stdout)["ok"])
        with tempfile.TemporaryDirectory() as project:
            install = [sys.executable, "-c", "from watersheep_adaptor.install_tool import main; main()", project]
            subprocess.run(install, check=True, capture_output=True)
            path = Path(project) / ".opencode/tools/watersheep_decide.ts"
            content = path.read_text()
            self.assertIn('"watersheep-decide"', content)
            self.assertNotIn("/home/", content)
            self.assertNotEqual(subprocess.run(install, capture_output=True).returncode, 0)
            self.assertEqual(path.read_text(), content)


if __name__ == "__main__":
    unittest.main()
