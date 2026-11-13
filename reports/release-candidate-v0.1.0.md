# Experimental v0.1.0 release candidate

**Status: READY_FOR_PUBLIC_REVIEW.** This is an experimental, fixture-verified candidate, not a production release or a claim of live-model verification.

## Public source inventory

Intended public files (none staged or committed by this preparation):

- `LICENSE` — original Apache-2.0 license, unchanged.
- `README.md` — architecture, installation and uninstallation, advisory tool, decision types, verification scope, HTTP limitations, attribution and non-affiliation.
- `pyproject.toml`, `MANIFEST.in` — Python package metadata, entry points and source distribution contents.
- `watersheep_adaptor/__init__.py`, `watersheep_adaptor/decide.py`, `watersheep_adaptor/install_tool.py`, `watersheep_adaptor/watersheep_decide.ts` — restricted HTTP adapter, Python decision interface, non-overwriting installer and OpenCode tool.
- `tests/test_adapter.py`, `tests/test_decide.py`, `tests/pre_main_isolation.py` — offline protocol tests and optional controlled OpenCode matrix.
- `.github/workflows/tests.yml` — offline test workflow for Python 3.9 and 3.13; no private services or model downloads. Workflow has not been run on GitHub.
- `.gitignore` — excludes build artifacts, obsolete local diagnostics and the superseded local smoke harness.
- `reports/release-candidate-v0.1.0.md` and its `.sha256` sidecar — sanitized verification record and report digest.

The previous checkpoint reports and superseded smoke script remain on disk but are ignored because they contain machine-specific diagnostic context. Raw logs and virtual environments are not included in the public candidate or distributions.

## Provenance and licensing

The project was independently implemented from the WaterSheep request/response contract and OpenCode custom-tool documentation. The pre-existing local adapter had unverified authorship and redistribution rights; its source was not copied. No model weights, backend implementation, private plugin, or third-party implementation code is bundled. Setuptools-generated package metadata is included in distributions. WaterSheep upstream: https://github.com/SamratDuttaOfficial/WaterSheep. Both distributions contain the repository's unchanged Apache-2.0 `LICENSE`. OpenCode and WaterSheep are independent upstream projects and do not endorse this project.

## Verification

- Confirmed the prior isolation report SHA-256 `94a7656722dfb263a3ad82939e070f0f878b68144c33d878554fc700504e721f` and branch `feature/standalone-adaptor` before changes.
- Python 3.13.9: `python -m unittest discover -s tests -v` — **9 passed**. The tests use ephemeral loopback fixtures.
- OpenCode 1.18.35: reran `tests/pre_main_isolation.py` after the harness changes with a warm `@opencode-ai/plugin@1.18.35` dependency tree, isolated configuration and 120-second stage deadlines. **A–F passed**, including the unchanged custom tool → installed Python interface → fake WaterSheep backend → advisory result returned to OpenCode. The deterministic fake model requested the tool; no live generative model or real WaterSheep inference was exercised.
- During that rerun, stage B's title-response-to-main-request gap was approximately **85.35 seconds**; later warm stages were faster. The earlier pre-main timeout's root cause remains unresolved. A clean dependency tree and package manifest were prepared from an existing warm installation; a fresh-machine cold start was not measured.
- The matrix ran against a wheel rebuilt after the harness changes. A final rebuild followed only README and distribution-manifest changes; all four runtime package files were SHA-256-identical to those installed in the matrix environment.
- Rebuilt sdist and wheel with `python -m build --no-isolation`. The final wheel installed offline in a fresh isolated virtual environment; `pip check`, CLI help and project-local tool installation passed. The final sdist installed offline in a fresh environment using system build tooling; its resulting wheel also installed into a separate clean virtual environment and passed `pip check`. System-site `pip check` in an earlier source-install attempt reported unrelated pre-existing environment dependency conflicts; the isolated wheel checks passed.
- Compared distribution content: the sdist `README.md` and wheel metadata description match the current README byte-for-byte; both packaged license files match `LICENSE` byte-for-byte. The sdist includes the portable matrix script. The final README SHA-256 is `1d058080ef0d8f3e339897b40e9640b2031ab73d308d70fbf8b38de8bda150d8`.
- Reviewed intended public files and distribution inventories for machine-specific home paths, temporary logs, virtual environments, and common credential patterns; no credential or private-path matches were found in the intended public source files. This targeted review is not a guarantee of secret absence; dedicated secret scanners were unavailable locally.
- Existing service listeners on ports 8766 and 8767 retained their original processes; no live inference was requested. No global configuration, external repository, tag, push, release or publication was changed.

## Distribution hashes

| Local artifact | SHA-256 |
|---|---|
| `dist/watersheep_opencode_adaptor-0.1.0-py3-none-any.whl` | `2c23a0a2c02153093422a2d547ddf249099a8b4286cd5a1360846c18b2615a74` |
| `dist/watersheep_opencode_adaptor-0.1.0.tar.gz` | `a2e87ca0f45c86467203d9aafae717583549b4dc98a069d0dc95b715f302c123` |

Report SHA-256 is recorded in the adjacent `.sha256` sidecar; embedding a digest inside the bytes it hashes would change it. Built distributions are ignored local artifacts and are not committed or published.

## Remaining limitations and handoff

- Live generative-provider behavior, real WaterSheep inference, other OpenCode versions, and other operating systems have not been verified. Python 3.9 is configured in CI but was not run locally.
- The optional chat-shaped HTTP endpoint rejects history, tools and generation options and is not a complete OpenAI-compatible model provider. WaterSheep decisions are advisory; agent permissions still govern subsequent actions.
- Builds succeeded with setuptools deprecation warnings for legacy license metadata and license classifier; migrate to current SPDX metadata in a future packaging change.
- Git state: `feature/standalone-adaptor`, with the listed candidate files untracked and the existing `LICENSE` tracked. Nothing was staged or committed.
- Proposed commit message: `Prepare experimental v0.1.0 release candidate`
