"""A small local bridge from chat requests to WaterSheep decisions."""
import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LIMIT = 1_048_576
ALIASES = {"noul", "binary", "yes/no", "boolean", "choice", "score", "multi", "multi_choice", "multilabel", "multi-label"}


class Invalid(ValueError):
    pass


def parse_request(body, model):
    if not isinstance(body, dict):
        raise Invalid("request must be an object")
    extra = set(body) - {"model", "messages", "stream"}
    if extra:
        raise Invalid("unsupported fields: " + ", ".join(sorted(extra)))
    if body.get("model") != model:
        raise Invalid("unknown model")
    if not isinstance(body.get("stream", False), bool):
        raise Invalid("stream must be a boolean")
    messages = body.get("messages")
    if not isinstance(messages, list) or len(messages) != 1:
        raise Invalid("exactly one user message is required")
    message = messages[0]
    if not isinstance(message, dict) or set(message) != {"role", "content"} or message.get("role") != "user" or not isinstance(message.get("content"), str):
        raise Invalid("only one plain-text user message is supported")
    text = message["content"].strip()
    if not text or len(text) > 65536:
        raise Invalid("user text must contain 1 to 65536 characters")
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        obj = None
    if isinstance(obj, dict) and ("state" in obj or "questions" in obj):
        if set(obj) - {"state", "questions"} or not isinstance(obj.get("questions"), dict) or not 1 <= len(obj["questions"]) <= 32:
            raise Invalid("expected state and a nonempty questions object of at most 32 entries")
        for key, q in obj["questions"].items():
            if not key or not isinstance(q, dict) or not isinstance(q.get("type"), str) or q["type"] not in ALIASES:
                raise Invalid("invalid question or question type")
            if set(q) - {"type", "instructions", "question", "criteria", "threshold"}:
                raise Invalid("unsupported question fields")
            instruction = q.get("instructions") or q.get("question")
            if not isinstance(instruction, str) or not instruction.strip():
                raise Invalid("question instructions are required")
        return obj, "explicit-json"
    return {"state": text, "questions": {
        "response_mode": {"type": "choice", "instructions": "Which response mode is most useful for the user's request?", "criteria": {
            "direct-answer": "Answer directly", "compare-decide": "Compare or decide", "inspect-verify": "Inspect or verify", "modify-artifacts": "Change artifacts", "clarify-first": "Ask for clarification"}},
        "external_state": {"type": "noul", "instructions": "Does fulfilling the request require changing external state?"}
    }}, "plain-text"


def validate_url(url):
    p = urllib.parse.urlsplit(url)
    try:
        port = p.port
    except ValueError as exc:
        raise Invalid("invalid upstream port") from exc
    if p.scheme != "http" or p.hostname != "127.0.0.1" or not port or p.username is not None or p.password is not None or p.fragment or p.query:
        raise Invalid("upstream must be unauthenticated HTTP on 127.0.0.1 with an explicit port and no query or fragment")
    return url


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def ask(url, model, decision, timeout=60):
    request = urllib.request.Request(url, data=json.dumps(decision, ensure_ascii=False).encode(), headers={"Content-Type": "application/json"})
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(LIMIT + 1)
        if len(raw) > LIMIT:
            raise ValueError("backend response too large")
        result = json.loads(raw)
        if not isinstance(result, dict) or result.get("model") != model or not isinstance(result.get("answers"), dict):
            raise ValueError("invalid response or backend model mismatch")
        if set(result["answers"]) != set(decision["questions"]):
            raise ValueError("backend answer keys do not match questions")
        return result
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        raise RuntimeError("WaterSheep backend error: " + str(exc)) from exc


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def send_json(self, status, data):
        encoded = json.dumps(data, ensure_ascii=False, allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def error_json(self, status, message):
        self.send_json(status, {"error": {"message": message, "type": "invalid_request_error" if status < 500 else "upstream_error"}})

    def do_GET(self):
        if self.path == "/healthz":
            return self.send_json(200, {"status": "ok", "model": self.server.model})
        if self.path in ("/v1/models", "/models"):
            return self.send_json(200, {"object": "list", "data": [{"id": self.server.model, "object": "model", "owned_by": "local-watersheep"}]})
        self.error_json(404, "not found")

    def do_POST(self):
        if self.path not in ("/v1/chat/completions", "/chat/completions"):
            return self.error_json(404, "not found")
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= LIMIT:
                raise Invalid("invalid request size")
            payload = json.loads(self.rfile.read(length), parse_constant=lambda value: (_ for _ in ()).throw(Invalid("non-finite JSON number")))
            decision, mode = parse_request(payload, self.server.model)
        except (ValueError, UnicodeDecodeError) as exc:
            return self.error_json(400, str(exc))
        try:
            result = ask(self.server.upstream, self.server.model, decision)
            text = json.dumps({"notice": "Advisory classification only; no execution authority.", "request_mode": mode, "watersheep": result}, ensure_ascii=False, allow_nan=False)
        except (RuntimeError, ValueError) as exc:
            return self.error_json(502, str(exc))
        common = {"id": "chatcmpl-" + uuid.uuid4().hex, "created": int(time.time()), "model": self.server.model}
        if payload.get("stream", False):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            try:
                for delta, reason in [({"role": "assistant", "content": text}, None), ({}, "stop")]:
                    event = {**common, "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": delta, "finish_reason": reason}]}
                    self.wfile.write(("data: " + json.dumps(event, ensure_ascii=False) + "\n\n").encode())
                self.wfile.write(b"data: [DONE]\n\n")
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
            self.close_connection = True
            return
        self.send_json(200, {**common, "object": "chat.completion", "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}]})


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port, upstream, model):
        self.upstream, self.model = validate_url(upstream), model
        super().__init__(("127.0.0.1", port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8767)
    parser.add_argument("--upstream", default="http://127.0.0.1:8766/v1/decisions")
    parser.add_argument("--model", required=True, help="exact model name returned by the backend")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or not args.model.strip():
        parser.error("port must be 1-65535 and model must be nonempty")
    try:
        server = Server(args.port, args.upstream, args.model)
    except (Invalid, OSError) as exc:
        parser.error(str(exc))
    print("listening on http://127.0.0.1:%d" % args.port, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
