"""Controlled OpenCode isolation matrix; writes only disposable project and synthetic evidence."""
import datetime
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = Path(os.environ.get("WATERSHEEP_DIAGNOSTICS_DIR", str(Path(tempfile.gettempdir()) / "watersheep-opencode-diagnostics")))
OPENCODE = os.environ.get("OPENCODE_BIN") or shutil.which("opencode")
WARM = Path(os.environ["OPENCODE_WARM_DEPENDENCIES"]) if os.environ.get("OPENCODE_WARM_DEPENDENCIES") else None
TIMEOUT = 120
ECHO = 'import { tool } from "@opencode-ai/plugin"\nexport default tool({description:"Deterministic diagnostic echo",args:{text:tool.schema.string()},async execute(args){return "ECHO:"+args.text}})\n'


def main():
    if not OPENCODE:
        raise RuntimeError("opencode executable not found; set OPENCODE_BIN")
    if WARM is None or not (WARM / "node_modules/@opencode-ai/plugin/package.json").exists():
        raise RuntimeError("warm npm dependency fixture missing: %s" % WARM)
    BASE.mkdir(parents=True, exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix="pre-main-", dir=BASE))
    scratch = Path(tempfile.mkdtemp(prefix="water-matrix-"))
    project, home, venv = scratch / "project", scratch / "home", scratch / "venv"
    project.mkdir(); home.mkdir()
    opendir = project / ".opencode"; opendir.mkdir()
    shutil.copytree(WARM / "node_modules", opendir / "node_modules", symlinks=True)
    for name in ("package.json", "package-lock.json"):
        if (WARM / name).exists(): shutil.copy2(WARM / name, opendir / name)
    tools = opendir / "tools"; tools.mkdir(exist_ok=True)
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True, timeout=30)
    subprocess.run([str(venv / "bin/pip"), "install", "--no-index", str(ROOT / "dist/watersheep_opencode_adaptor-0.1.0-py3-none-any.whl")], check=True, capture_output=True, timeout=30)
    real = (ROOT / "watersheep_adaptor/watersheep_decide.ts").read_text()
    installed = subprocess.run([str(venv / "bin/watersheep-install-tool"), str(project)], check=True, capture_output=True, text=True, timeout=10)
    assert (tools / "watersheep_decide.ts").read_text() == real
    (tools / "watersheep_decide.ts").unlink()
    static = real[:real.index("  async execute(args) {")] + '  async execute(args) { return JSON.stringify({ok:true,notice:"Advisory only; no execution authority.",args}) },\n})\n'
    lock = threading.Lock(); events = []; active = {"stage": "setup", "start": time.monotonic()}

    def event(name, **data):
        item = {"stage": active["stage"], "event": name, "monotonic": time.monotonic(), "elapsed": round(time.monotonic() - active["start"], 6), "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), **data}
        with lock:
            events.append(item)
            with (out / "events.jsonl").open("a") as handle: handle.write(json.dumps(item) + "\n")
        print(json.dumps({key: value for key, value in item.items() if key not in ("request", "tool_results")}), flush=True)

    class Backend(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_POST(self):
            req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            event("backend_request", path=self.path, request=req)
            result = {"model": "fixture", "answers": {"decision": {"type": "choice", "choice": "z", "probabilities": {"z": .8, "a": .2}}}, "usage": {"input_tokens": 7}}
            body = json.dumps(result).encode(); self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); self.wfile.flush()
            event("backend_response", status=200)

    class Model(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_POST(self):
            req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            messages = req.get("messages", []); tool_results = [m for m in messages if m.get("role") == "tool"]
            names = [t.get("function", {}).get("name") for t in req.get("tools", [])]
            title = any("title generator" in str(m.get("content", "")) for m in messages if m.get("role") == "system")
            kind = "title" if title else "followup" if tool_results else "main"
            event("model_" + kind + "_request", path=self.path, tools=names, tool_results=tool_results, request=req)
            target = "diagnostic_echo" if active["stage"] == "B" else "watersheep_decide"
            if kind == "main" and active["stage"] != "A" and target in names:
                args = {"text": "fixture"} if active["stage"] in ("B", "C") else {"state": "fixture context", "question": "Choose?", "type": "choice", "options": ["z", "a"]}
                delta = {"tool_calls": [{"index": 0, "id": "call_fixture", "type": "function", "function": {"name": target, "arguments": json.dumps(args)}}]}; reason = "tool_calls"
            else: delta, reason = {"content": "Fixture completed."}, "stop"
            common = {"id": "fixture", "object": "chat.completion.chunk", "created": 1, "model": "fixture"}
            chunks = [{**common, "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]}, {**common, "choices": [{"index": 0, "delta": delta, "finish_reason": None}]}, {**common, "choices": [{"index": 0, "delta": {}, "finish_reason": reason}]}]
            data = ("".join("data: " + json.dumps(c) + "\n\n" for c in chunks) + "data: [DONE]\n\n").encode()
            self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data); self.wfile.flush()
            event("model_" + kind + "_response_completed", status=200, finish_reason=reason)

    backend = ThreadingHTTPServer(("127.0.0.1", 0), Backend)
    model = ThreadingHTTPServer(("127.0.0.1", 0), Model)
    for server in (backend, model): threading.Thread(target=server.serve_forever, daemon=True).start()
    event("fixtures_ready", model_port=model.server_port, backend_port=backend.server_port, installer=installed.stdout.strip())
    config = {"snapshot": False, "provider": {"fixture": {"npm": "@ai-sdk/openai-compatible", "name": "Fixture", "options": {"baseURL": "http://127.0.0.1:%d/v1" % model.server_port, "apiKey": "fixture"}, "models": {"fixture": {"name": "Fixture", "tool_call": True}}}}, "enabled_providers": ["fixture"], "permission": {"*": "deny", "diagnostic_echo": "allow", "watersheep_decide": "allow"}}
    env = {"HOME": str(home), "PWD": str(project), "PATH": str(venv / "bin") + os.pathsep + os.environ["PATH"], "LANG": "C.UTF-8", "XDG_CONFIG_HOME": str(home / "config"), "XDG_DATA_HOME": str(home / "data"), "XDG_CACHE_HOME": str(home / "cache"), "XDG_STATE_HOME": str(home / "state"), "OPENCODE_DISABLE_DEFAULT_PLUGINS": "1", "OPENCODE_DISABLE_EXTERNAL_SKILLS": "1", "OPENCODE_CONFIG_CONTENT": json.dumps(config), "WATERSHEEP_MODEL": "fixture", "WATERSHEEP_UPSTREAM": "http://127.0.0.1:%d/v1/decisions" % backend.server_port, "WATERSHEEP_TIMEOUT": "2"}
    (out / "config.json").write_text(json.dumps(config, indent=2))
    command = [OPENCODE, "run", "--pure", "--dir", str(project), "--print-logs", "--log-level", "DEBUG", "--format", "json", "--model", "fixture/fixture", "Use the available advisory tool if available."]
    (out / "command.json").write_text(json.dumps(command))
    passed_all = True
    try:
        for stage in "ABCDEF":
            for name in ("diagnostic_echo.ts", "watersheep_decide.ts"):
                path = tools / name
                if path.exists(): path.unlink()
            if stage == "B": (tools / "diagnostic_echo.ts").write_text(ECHO)
            if stage == "C": (tools / "watersheep_decide.ts").write_text(ECHO)
            if stage in "DE": (tools / "watersheep_decide.ts").write_text(static)
            if stage == "F": (tools / "watersheep_decide.ts").write_text(real)
            active.update(stage=stage, start=time.monotonic()); event("stage_start", timeout=TIMEOUT)
            with (out / (stage + ".stdout.log")).open("wb") as stdout, (out / (stage + ".stderr.log")).open("wb") as stderr:
                process = subprocess.Popen(command, cwd=project, env=env, stdout=stdout, stderr=stderr, start_new_session=True)
                event("process_started", pid=process.pid)
                observed = set(); ps = ""
                try:
                    while process.poll() is None and time.monotonic() - active["start"] < TIMEOUT:
                        try:
                            ps = subprocess.run(["ps", "-eo", "pid,ppid,pgid,comm"], capture_output=True, text=True, timeout=3).stdout
                            for line in ps.splitlines()[1:]:
                                bits = line.split(None, 3)
                                if len(bits) == 4 and bits[2] == str(process.pid) and bits[0] not in observed:
                                    observed.add(bits[0]); event("process_observed", pid=int(bits[0]), ppid=int(bits[1]), comm=bits[3])
                        except subprocess.TimeoutExpired:
                            event("process_observation_timeout")
                        time.sleep(.5)
                    if process.poll() is None:
                        own = [line for line in ps.splitlines()[1:] if len(line.split(None, 3)) == 4 and line.split(None, 3)[2] == str(process.pid)]
                        event("timeout", processes=own)
                        passed_all = False
                        break
                    event("process_exit", returncode=process.returncode)
                finally:
                    if process.poll() is None:
                        os.killpg(process.pid, signal.SIGTERM)
                        try: process.wait(timeout=3)
                        except subprocess.TimeoutExpired: os.killpg(process.pid, signal.SIGKILL); process.wait()
                        event("process_terminated", returncode=process.returncode)
            relevant = [e for e in events if e["stage"] == stage]
            follow = [e for e in relevant if e["event"] == "model_followup_request"]
            okay = process.returncode == 0 and any(e["event"] == "model_main_request" for e in relevant)
            if stage != "A": okay = okay and bool(follow)
            if stage in "BC" and follow: okay = okay and "ECHO:fixture" in str(follow[-1]["tool_results"])
            if stage in "DE" and follow: okay = okay and "Advisory only" in str(follow[-1]["tool_results"])
            if stage == "F" and follow:
                okay = okay and any(e["event"] == "backend_request" for e in relevant)
                text = str(follow[-1]["tool_results"]); okay = okay and '0.8' in text and 'execution authority' in text
            event("stage_result", passed=bool(okay))
            if not okay:
                passed_all = False
                break
    finally:
        for server in (model, backend): server.shutdown(); server.server_close()
        print("EVIDENCE", out, flush=True)
    return 0 if passed_all else 1


if __name__ == "__main__": sys.exit(main())
