# Third-party notices and licensing audit

## Phase 1B/1C — 2026-10-11

New runtime component: [aescarias/pdfnaut](https://github.com/aescarias/pdfnaut), **pdfnaut 0.13.0**, **Apache-2.0**, pinned in backend/requirements.txt. Unmodified installed wheel; Python PDF parsing/tokenization only. Preserve [full LICENSE](third_party/pdfnaut/LICENSE) and [component attribution and artifact hash](third_party/pdfnaut/NOTICE.md) with distribution. SHA-256 of audited wheel: `c402ffaa76ba7ead6380ed7d77c6c7cd47c98f3e506d83c2011c9f1daa3e99d1`. Inspected sources contain no bundled fonts, model weights or native binaries. Its sole runtime requirement, typing-extensions>=4.11.0, was already baseline (PSF-2.0); no new transitive distribution was installed or approved. The policy does not newly clear that baseline dependency.

Memory, text chunking/FTS services, basic OOXML ZIP/XML handling, PDF text-operator adaptation and frontend controls are original application code using existing facilities. No mem0, Docling, LlamaIndex, pdfminer, pypdf, python-docx or pdfrw source/package was incorporated. Exact versions, incompatibilities and official evidence are in [PHASE1BC_DECISIONS.md](docs/PHASE1BC_DECISIONS.md). The user declined a BSD parser exception; no license policy was broadened. Production extraction does not import PyMuPDF; the existing test fixture uses its pre-existing installation to construct sample PDFs, without incorporating new code/assets.

Before/after offline inventory: **466 → 467** entries; only addition **pdfnaut 0.13.0 / Apache-2.0**; **79 existing review findings unchanged**. `--check` continues to fail on that baseline, as expected. No frontend manifest/lockfile dependency changes. Existing Google SDK is now pinned to 2.29.0 to match tested code; installed SDK and its tree remain unchanged. No rejected candidate, OCR/model, external storage or paid infrastructure was added.

## Phase 1A backend group — 2026-10-11

**No new application packages, third-party source, assets or fonts were incorporated.** Workspace models, migration, APIs, ordering logic and frontend components are original project code using existing framework facilities. No AppFlowy code or assets were used.

## Phase 1A frontend checkpoint — 2026-10-11

The candidate [`@dnd-kit/core` 6.3.1 manifest](https://raw.githubusercontent.com/clauderic/dnd-kit/@dnd-kit/core@6.3.1/packages/core/package.json) declares MIT, but includes runtime `tslib ^2.0.0`, accessibility and utilities dependencies. The examined [`tslib` 2.8.1 manifest](https://raw.githubusercontent.com/microsoft/tslib/v2.8.1/package.json) and [license text](https://raw.githubusercontent.com/microsoft/tslib/v2.8.1/LICENSE.txt) identify 0BSD, outside this project's MIT/Apache-only allowlist. The candidate was rejected at that transitive finding; this is not a completed clearance of the remaining dnd-kit tree. No dnd-kit package was installed or copied. Drag interactions use original Pointer Events and keyboard code.

Frontend package manifests/lockfiles are unchanged. Browser tests use the existing external Playwright/Chromium QA installation; neither is added to or bundled with the application. Existing React/ReactDOM supply the new UI. The prior metadata inventory remains unchanged; its open baseline exceptions are retained below.

The existing application is **not verified as compliant** with the requested MIT/Apache-only policy. The following is a factual installed/lockfile audit, not approval of the baseline or a legal opinion. Existing dependency LICENSE/NOTICE files must remain with their distributions. The offline scanner supports reproducible inventory and catches metadata exceptions; it does not replace inspection of full license texts, bundled code and assets.

## Existing components reused by this group

- FastAPI **0.143.0** — installed metadata: MIT. [Source](https://github.com/fastapi/fastapi).
- SQLAlchemy **2.1.4** — installed metadata: MIT. [Source](https://github.com/sqlalchemy/sqlalchemy).
- Pydantic **2.14.0** — installed metadata: MIT. [Source](https://github.com/pydantic/pydantic).

These are installed versions, not new dependency pins. Python requirement ranges remain broader than a complete lock. The former Google SDK `>=1,<2` mismatch is corrected by pinning the already installed/tested **2.29.0**; this does not change its existing installed dependency tree. Do not equate tests in this environment with a verified clean installation from requirements.

## Confirmed baseline exceptions requiring remediation

- PyMuPDF **1.28.2** — installed metadata: GNU AGPL 3.0 or Artifex commercial license. It is already used for PDF/image validation and token estimation. Neither offered license is on this project's MIT/Apache-only list. No evidence of a commercial license was examined, and obtaining one would still require a policy change. Preserve current attachment behavior while selecting and validating a compliant replacement; do not extend its use into new document features. [Official licensing](https://pymupdf.io/licensing).
- HTTPX **0.28.1** and Uvicorn **0.54.0** — installed metadata: BSD-3-Clause, outside the explicit allowlist. [HTTPX source](https://github.com/encode/httpx), [Uvicorn source](https://github.com/Kludex/uvicorn).
- `lucide-react` **0.468.0**, `d3` **7.9.0**, and multiple D3/transitive packages — frontend lockfile: ISC, outside the allowlist. [Lucide source](https://github.com/lucide-icons/lucide), [D3 source](https://github.com/d3/d3).
- `highlight.js` **10.7.3** — lockfile: BSD-3-Clause. [Source](https://github.com/highlightjs/highlight.js).
- `caniuse-lite` **1.0.30001815** — lockfile: CC-BY-4.0; `highlightjs-vue` **1.0.0** — CC0-1.0; `robust-predicates` **3.0.3** — Unlicense. These and remaining exceptions are reported by the scanner.

BSD/ISC and other exceptions are findings against this user's strict policy, not assertions that these licenses categorically prohibit proprietary software. No exceptions have been silently granted. Whole-application release clearance remains unresolved.

## Existing alternative-license selections

- DOMPurify **3.4.16** — lockfile `(MPL-2.0 OR Apache-2.0)`; use the Apache-2.0 option and retain its required notices. [Source](https://github.com/cure53/DOMPurify).
- Cryptography **50.0.2** — installed metadata `Apache-2.0 OR BSD-3-Clause`; use the Apache-2.0 option, subject to bundled/transitive review. [Source](https://github.com/pyca/cryptography).
- Google Gen AI SDK **2.29.0** — installed metadata Apache-2.0; unchanged existing provider dependency. [Source](https://github.com/googleapis/python-genai).

An allowlisted top-level license does not approve every bundled or transitive component.

## Retained vendored attribution

QuickUI already includes selected helpers adapted from [answer-me-with-html](https://github.com/QingYunA/answer-me-with-html), revision `43d53147d2a1414b7843a9ed6ef5bbd9977680f1`, under MIT. Copyright (c) 2026 Answer me with HTML contributors. The full permission/warranty notice remains in [the vendored LICENSE](frontend/src/vendor/answer-me-with-html/LICENSE); [source and adaptation notes](frontend/src/vendor/answer-me-with-html/README.md) identify the included files. This group makes no changes to those files.

## Reproduce the inventory

From the project root, using the backend environment:

```bash
backend/venv/bin/python scripts/license_audit.py --output /tmp/kumuta-license-inventory.json
backend/venv/bin/python scripts/license_audit.py --check
```

For a newly created environment use `backend/.venv/bin/python`. The report includes each frontend lockfile package path/version/license/source and each installed Python distribution/version/license/PyPI source. Installed Python scope conservatively includes development and optional packages. `--check` is expected to fail on the existing baseline; do not suppress findings or label this a passing release gate. Before adding a dependency, compare inventories and manually inspect the exact package's LICENSE/NOTICE files, bundled assets and transitives.

## Phase 2A/2B — 2026-10-12

New runtime component: [open-spaced-repetition/py-fsrs](https://github.com/open-spaced-repetition/py-fsrs), **fsrs 6.3.2**, **MIT**, Copyright (c) 2022 Open Spaced Repetition. Exact wheel SHA-256: `bc55066c821164b1cff6d75b17a3ed8e86cfd45789e3d775cfcb895319ce9ba4`. Retain the full [LICENSE](third_party/fsrs/LICENSE) and [attribution/artifact notes](third_party/fsrs/NOTICE.md). Unmodified pure-Python runtime scheduler; no bundled media/fonts/native code/models were present in the inspected wheel. Python >=3.10; tested with this checkout's Python 3.12. Default scheduler only; optimizer/dev extras and their Torch/NumPy/Pandas tree are not installed/imported. Sole runtime dependency `typing-extensions` was already installed; its PSF baseline exception remains unresolved rather than newly approved.

The inventory changes from the documented **467** to **468** entries, with **79 existing review findings unchanged**. The offline scanner recognizes FSRS's exact MIT text by comparison with the retained notice; no generic classifier/text bypass or allowlist broadening is added. Existing frontend manifest/lockfile and existing runtime packages are unchanged. Whole-application licensing remains unresolved.

RJSF core/utils/validator 6.11.0: Apache-2.0 top level, rejected because utils pulls fast-uri 4.2.2 / BSD-3-Clause. Tiptap core/pm 3.31.4: MIT top level, not selected because existing Markdown/textarea suffices; its full editor tree is not cleared. Recharts 3.10.1: MIT top level, deferred without tree clearance to Phase 2C. No source from these candidates or another LMS/flashcard product is incorporated. Details, exact manifests, compatibility and maintenance-review scope are in [PHASE2_DECISIONS.md](docs/PHASE2_DECISIONS.md). New application forms, quiz scoring, progress, goals, session state, time allocation and related services are original project code using the existing stack. External Playwright/Chromium remain QA tooling, not application dependencies.


## Phase 2C — 2026-10-12

No dependencies or third-party source/assets added. Original React/SVG charts and existing components are used. Exact Recharts **3.10.1** published LICENSE is MIT and its peers support React 18, but its `victory-vendor ^37.0.2` dependency admits inspected **37.3.6**, which declares **MIT AND ISC** and includes ISC/BSD D3 code; inspected **d3-scale 4.0.2** is ISC. These are confirmed non-allowlisted licenses, so Recharts is rejected without claiming that its remaining tree has full clearance. Exact metadata URLs, source revision, artifact hashes and selection rationale are recorded in [PHASE2C_REPORT.md](docs/PHASE2C_REPORT.md). Nothing from those packages is incorporated; no new attribution obligation is created.

The awesome-llm-apps catalogue was reviewed for relevance, not copied; its memory/RAG/agents/optimization examples add unnecessary scope to provider-free analytics. Existing attribution/license selections remain unchanged. Final inventory: **468 package entries, 79 require review**, expected nonzero license gate; this is the same existing baseline and not release clearance.


## Phase 3A/3B/3C — 2026-10-12

No new runtime dependency, third-party source, assets, fonts, binaries or paid infrastructure. CSV/basic XLSX parsing uses bounded original standard-library code. Bar/line charts reuse the existing QuickUI renderer and retained MIT scale helper; area/pie/donut/report forms are original application code. Existing attribution remains unchanged.

Reviewed the awesome-llm-apps AI Data Analysis Agent README, source, requirements and repository Apache-2.0 license; no implementation or assets copied and none of its Streamlit/Agno/DuckDB/Pandas/OpenAI/NumPy stack adopted. General ingestion/schema/question/results concepts informed an independent restricted specification architecture. This does not clear its complete transitive tree. Exact inspected URLs and decisions are in PHASE3_SESSION1_REPORT.md. No new package is proposed, so no new dependency-tree license exception is needed.

Fresh offline inventory remains **468 entries, 79 review findings**; `--check` intentionally fails on the existing unresolved baseline. Application-wide commercial release remains uncleared. External installed Playwright/Chromium/Node are QA tools only and are not added to application manifests or lockfiles.
