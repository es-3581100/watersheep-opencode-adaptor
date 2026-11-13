"""Bounded JSON-in/JSON-out advisory decision interface for OpenCode."""
import json
import math
import os
import sys

from . import Invalid, ask, validate_url

NOTICE = "Advisory decision only; no execution authority or model reasoning."
MAX_INPUT = 65536


def decision_request(args):
    if not isinstance(args, dict) or set(args) - {"state", "question", "type", "options"}:
        raise Invalid("expected state, question, type and optional options")
    state, question, kind = args.get("state"), args.get("question"), args.get("type")
    if not isinstance(state, str) or not isinstance(question, str) or not question.strip():
        raise Invalid("state must be text and question must be nonempty text")
    if len(state) > 32768 or len(question) > 4096:
        raise Invalid("state or question is too long")
    if kind not in ("binary", "choice", "score", "multi"):
        raise Invalid("type must be binary, choice, score or multi")
    options = args.get("options")
    if kind == "binary":
        if options is not None:
            raise Invalid("binary does not accept options")
    else:
        maximum = 10 if kind == "score" else 255
        if not isinstance(options, list) or not 2 <= len(options) <= maximum:
            raise Invalid("options must contain 2 to %s entries" % maximum)
        if any(not isinstance(x, str) or not x.strip() or len(x) > 1024 for x in options):
            raise Invalid("each option must be nonempty text of at most 1024 characters")
        if len(set(options)) != len(options):
            raise Invalid("options must be unique")
    question_data = {"type": kind, "instructions": question}
    if options is not None:
        question_data["criteria"] = options
    return {"state": state, "questions": {"decision": question_data}}


def decide(args, upstream, model, timeout=60):
    try:
        request = decision_request(args)
        validate_url(upstream)
        if not isinstance(model, str) or not model.strip():
            raise Invalid("WATERSHEEP_MODEL must match the backend model name")
        if not 0 < timeout <= 120:
            raise Invalid("timeout must be greater than zero and at most 120 seconds")
        result = ask(upstream, model, request, timeout=timeout)
        answer = result["answers"]["decision"]
        if not isinstance(answer, dict):
            raise RuntimeError("invalid backend answer")
        if "error" in answer:
            return {"ok": False, "notice": NOTICE, "error": {"code": "decision_error", "message": str(answer["error"])}, "watersheep": result}
        expected = {"binary": ("noul", "noul"), "choice": ("choice", "choice"), "score": ("score", "score"), "multi": ("multi", "choices")}[args["type"]]
        if answer.get("type") != expected[0] or expected[1] not in answer:
            raise RuntimeError("invalid backend decision type or missing result")
        value = answer[expected[1]]
        number = lambda x: isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)
        if args["type"] in ("binary", "score") and not number(value):
            raise RuntimeError("invalid backend numeric result")
        if args["type"] == "binary" and not 0 <= value <= 1:
            raise RuntimeError("invalid backend binary probability")
        if args["type"] == "choice" and value not in args["options"]:
            raise RuntimeError("invalid backend choice")
        if args["type"] == "multi" and (not isinstance(value, list) or any(x not in args["options"] for x in value)):
            raise RuntimeError("invalid backend multi choices")
        if args["type"] != "binary":
            probabilities = answer.get("probabilities")
            expected_keys = [str(i) for i in range(len(args["options"]))] if args["type"] == "score" else args["options"]
            if not isinstance(probabilities, dict) or list(probabilities) != expected_keys or any(not number(p) or not 0 <= p <= 1 for p in probabilities.values()):
                raise RuntimeError("invalid backend probabilities or option order")
        json.dumps(result, allow_nan=False)
        return {"ok": True, "notice": NOTICE, "watersheep": result}
    except Invalid as exc:
        return {"ok": False, "notice": NOTICE, "error": {"code": "invalid_request", "message": str(exc)}}
    except (RuntimeError, ValueError) as exc:
        return {"ok": False, "notice": NOTICE, "error": {"code": "backend_error", "message": str(exc)}}


def main():
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT + 1)
        if len(raw) > MAX_INPUT:
            raise Invalid("input too large")
        args = json.loads(raw)
        timeout = float(os.environ.get("WATERSHEEP_TIMEOUT", "60"))
        result = decide(args, os.environ.get("WATERSHEEP_UPSTREAM", "http://127.0.0.1:8766/v1/decisions"), os.environ.get("WATERSHEEP_MODEL", ""), timeout)
    except (ValueError, UnicodeDecodeError) as exc:
        result = {"ok": False, "notice": NOTICE, "error": {"code": "invalid_request", "message": str(exc)}}
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return 0
