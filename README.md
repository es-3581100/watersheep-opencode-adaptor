# WaterSheep OpenCode Adaptor

**Experimental v0.1.0**: a local advisory bridge between OpenCode and a separately running [WaterSheep](https://github.com/SamratDuttaOfficial/WaterSheep) decision server. It is not production-ready.

This project is independent of both the WaterSheep and OpenCode teams. It is not affiliated with, endorsed by, or sponsored by either project or its creators.

## Architecture

An OpenCode generative model can call the project-local `watersheep_decide` custom tool. The thin tool starts the installed Python decision interface, which sends a structured request to the separate WaterSheep server and returns its advisory result to OpenCode. WaterSheep is a decision engine, not a generative assistant. An optional restricted HTTP chat-shaped adapter is also provided for minimal compatible clients.

## OpenCode custom tool

WaterSheep does not replace OpenCode's generative LLM. A normal tool-capable model can call `watersheep_decide` for independent, advisory decisions. OpenCode `1.18.35` completed a full custom-tool invocation using a deterministic model fixture and fake WaterSheep backend; see `reports/release-candidate-v0.1.0.md` in the repository. A live generative model and real WaterSheep inference remain untested. Other OpenCode versions are untested.

Install Python 3.9+ and a separately running WaterSheep backend. In an environment available on the `PATH` of the OpenCode process:

```sh
python -m pip install .
watersheep-install-tool /path/to/your/project
export WATERSHEEP_MODEL=ACTUAL_BACKEND_MODEL_NAME
export WATERSHEEP_UPSTREAM=http://127.0.0.1:8766/v1/decisions
export WATERSHEEP_TIMEOUT=60
opencode /path/to/your/project
```

The installer creates only `.opencode/tools/watersheep_decide.ts` and refuses to overwrite an existing file. Restart OpenCode after installation. `watersheep-decide` must be on OpenCode's `PATH`, including when launched from a desktop. The tool uses the official `@opencode-ai/plugin` tool API; OpenCode must be able to resolve its package. The backend model is the name returned by WaterSheep, not necessarily its repository ID. The upstream defaults to the URL above, and timeout defaults to 60 seconds (maximum 120). Loopback access is unauthenticated.

The bridge does not execute a decision. The generative agent can still use its other permitted tools, so configure OpenCode permissions appropriately and treat model outputs as untrusted advice. Do not expose the unauthenticated local services to untrusted users or networks.

Ask your OpenCode model, for example: “Use watersheep_decide to choose between `z` and `a` for this context.” Tool arguments are `state` (text), `question` (text), `type` (`binary`, `choice`, `score`, or `multi`), and `options` (ordered strings, omitted for binary). Score levels are ordered and returned probabilities use indexed levels; multi probabilities are independent per label. The result preserves backend metadata and per-question errors. It carries no authority to execute suggestions and does not invent reasoning or token usage.

Example tool arguments for an ordered choice:

```json
{"state":"An order is late","question":"Which queue should handle it?","type":"choice","options":["shipping","support"]}
```

For a yes/no decision use `type: "binary"` and omit `options`. For `score`, provide 2–10 ordered levels; for `choice` or `multi`, provide 2–255 unique ordered labels.

### Uninstall

Remove the installed `.opencode/tools/watersheep_decide.ts` from each project where you installed it, after confirming it is the file you intend to remove. Then uninstall the package from the same Python environment:

```sh
python -m pip uninstall watersheep-opencode-adaptor
```

Restart OpenCode after removing the tool. Uninstalling the adapter does not uninstall WaterSheep.

## Optional limited HTTP adapter

Requires Python 3.9+ and a separately installed WaterSheep backend. From a source checkout:

```sh
python -m pip install .
watersheep-opencode-adapter --port 18767 --upstream http://127.0.0.1:8766/v1/decisions --model ACTUAL_BACKEND_MODEL_NAME
```

The backend model name is the `model` field returned by WaterSheep, not necessarily its repository ID. The backend and adapter must be running separately. Both adapter and backend are unauthenticated; the adapter binds only to IPv4 loopback. The backend URL must be unauthenticated HTTP on `127.0.0.1` with an explicit port; redirects and proxies are disabled. Anyone with access to the local port can submit requests. `/healthz` indicates adapter liveness only.

## Protocol

`GET /v1/models` lists the configured model. `POST /v1/chat/completions` accepts only `model`, `messages`, and optional boolean `stream`. Exactly one user message with string content is accepted. All other message roles, history, tools, multimodal input, generation parameters and unknown fields are rejected with HTTP 400. Explicit JSON text containing `state` or `questions` is validated and forwarded as a WaterSheep request. Otherwise plain text is classified using two fixed decision questions. The assistant content is JSON containing the entire backend response, including per-question errors, usage, and metadata. Question and option ordering is preserved. Backend failures, invalid responses and model mismatches return HTTP 502.

`stream: true` sends a completed advisory result using chat-completion SSE framing, followed by `[DONE]`; it is not incremental inference. Chat-level usage is omitted rather than inventing generated token counts. Backend usage remains in the advisory content. This is a deliberately restricted interface, not full OpenAI compatibility.

Example (replace the model and port):

```sh
curl http://127.0.0.1:18767/v1/chat/completions -H 'Content-Type: application/json' -d '{"model":"ACTUAL_BACKEND_MODEL_NAME","messages":[{"role":"user","content":"{\"state\":\"An order is late\",\"questions\":{\"urgent\":{\"type\":\"noul\",\"instructions\":\"Is this urgent?\"}}}"}]}'
```

OpenCode normally supplies system messages, tools, history, and generation options. The limited HTTP endpoint rejects these semantics and is not a general OpenCode model provider. Use the custom-tool pathway above with a separate generative model.

## Development and provenance

Run `python -m unittest discover -s tests -v`; tests use local fixture servers and need no model download or external service. No Python runtime dependencies are required. The optional OpenCode matrix requires OpenCode 1.18.35, a built wheel, and a warm `@opencode-ai/plugin@1.18.35` dependency tree: set `OPENCODE_WARM_DEPENDENCIES` to its containing `.opencode` directory and run `python tests/pre_main_isolation.py`. Startup can be slow; the earlier pre-main timeout's cause remains unresolved.

The adapter was independently implemented from the WaterSheep request/response contract; the locally installed adapter had unverified provenance and was not copied. [SamratDuttaOfficial/WaterSheep](https://github.com/SamratDuttaOfficial/WaterSheep) is a separately distributed Apache-2.0 project. This repository is licensed under Apache-2.0; see `LICENSE`.
