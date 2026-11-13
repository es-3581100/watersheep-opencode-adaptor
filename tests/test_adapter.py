import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from watersheep_adaptor import Server, Invalid, validate_url


class Backend(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        self.server.request_body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        result = {"model": self.server.model, "answers": {k: {"type": v["type"], "error": "fixture error"} for k, v in self.server.request_body["questions"].items()}, "usage": {"input_tokens": 4}, "extra": "retained"}
        data = json.dumps(result).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class Integration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.backend = ThreadingHTTPServer(("127.0.0.1", 0), Backend)
        cls.backend.model = "fixture"
        cls.adapter = Server(0, "http://127.0.0.1:%d/v1/decisions" % cls.backend.server_port, "fixture")
        for server in (cls.backend, cls.adapter):
            threading.Thread(target=server.serve_forever, daemon=True).start()
        cls.url = "http://127.0.0.1:%d" % cls.adapter.server_port

    @classmethod
    def tearDownClass(cls):
        for server in (cls.adapter, cls.backend):
            server.shutdown()
            server.server_close()

    def post(self, body):
        req = urllib.request.Request(self.url + "/v1/chat/completions", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    def test_explicit_order_metadata_and_errors(self):
        value = {"state": "x", "questions": {t: {"type": t, "instructions": "q", "criteria": {"z": "last", "a": "first"}} for t in ("binary", "choice", "score", "multi")}}
        status, body = self.post({"model": "fixture", "messages": [{"role": "user", "content": json.dumps(value)}]})
        self.assertEqual(status, 200)
        response = json.loads(body)
        self.assertNotIn("usage", response)
        result = json.loads(response["choices"][0]["message"]["content"])["watersheep"]
        self.assertEqual(result["answers"]["multi"]["error"], "fixture error")
        self.assertEqual(result["extra"], "retained")
        self.assertEqual(list(self.backend.request_body["questions"]["choice"]["criteria"]), ["z", "a"])

    def test_plain_text_and_stream(self):
        status, body = self.post({"model": "fixture", "messages": [{"role": "user", "content": "inspect this"}], "stream": True})
        self.assertEqual(status, 200)
        self.assertTrue(body.endswith("data: [DONE]\n\n"))
        event = json.loads(body.split("\n\n")[0][6:])
        self.assertEqual(json.loads(event["choices"][0]["delta"]["content"])["request_mode"], "plain-text")

    def test_reject_unsupported(self):
        base = {"model": "fixture", "messages": [{"role": "user", "content": "hi"}]}
        for extra in ({"tools": []}, {"stream": "true"}, {"temperature": 1}, {"model": "wrong"}, {"messages": [{"role": "system", "content": "x"}]}):
            with self.subTest(extra=extra):
                self.assertEqual(self.post({**base, **extra})[0], 400)
        invalid = {"questions": {"q": {"type": [], "instructions": "q"}}}
        self.assertEqual(self.post({**base, "messages": [{"role": "user", "content": json.dumps(invalid)}]})[0], 400)

    def test_model_mismatch(self):
        self.backend.model = "different"
        try:
            self.assertEqual(self.post({"model": "fixture", "messages": [{"role": "user", "content": "hi"}]})[0], 502)
        finally:
            self.backend.model = "fixture"

    def test_url_boundary(self):
        for url in ("http://localhost:1/x", "http://user@127.0.0.1:1/x", "http://127.0.0.1:1/x?q=1", "https://127.0.0.1:1/x"):
            with self.assertRaises(Invalid):
                validate_url(url)


if __name__ == "__main__":
    unittest.main()
