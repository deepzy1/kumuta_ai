# Kumuta AI — Third-Party Software Policy

Kumuta AI is a proprietary commercial SaaS application.

## Approved source-code licenses
- MIT
- Apache-2.0

## Not approved for direct code reuse
- GPL, AGPL, LGPL, SSPL, and other licenses outside the approved list
- Repositories without an explicit license
- Repositories with unclear or conflicting license terms
- Code with unverified third-party licensing

## Engineering requirements
1. Verify the license of each dependency and the exact version used.
2. Check subdirectories, assets, fonts, bundled code, and transitive dependencies.
3. Preserve required copyright, attribution, LICENSE, and NOTICE information.
4. Record approved components and versions in a third-party inventory.
5. For incompatible repositories, use only general architectural concepts and create an independent implementation.
6. Never assume AI-generated rewrites of restricted source code are legally independent.
7. Run automated license and dependency scans in CI.
8. Block unknown or unapproved licenses pending review.
9. Recheck licenses when updating dependencies.
10. Obtain legal review before releasing components with unresolved licensing questions.

## Architecture principle

Prefer traditional SaaS implementations using FastAPI, SQLite, and React. Use Gemini only where AI adds clear value.

All newly developed Kumuta AI application code remains proprietary unless explicitly decided otherwise.

## Audit workflow and current baseline

Run `backend/venv/bin/python scripts/license_audit.py --check` from the project root (or `.venv/bin/python` for a new environment). This offline metadata screen includes frontend lockfile transitives and the installed Python environment. Export `--output /tmp/kumuta-license-inventory.json` for a versioned comparison. Exact source/package LICENSE and NOTICE inspection, assets and bundled code review are still required before adding a dependency; metadata alone is not approval.

The existing baseline has known conflicts, including PyMuPDF's AGPL/commercial licensing and ISC/BSD dependencies. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Phase 1B introduces no dependencies; Phase 1C adds only pdfnaut 0.13.0 under Apache-2.0, with no new transitive distributions. Its existing typing-extensions dependency remains a documented baseline exception; this is not a new exception approval. The user explicitly reaffirmed strict MIT/Apache additions and declined BSD pypdf. See the exact-version selection audit in docs/PHASE1BC_DECISIONS.md and attribution in third_party/pdfnaut. Existing Google SDK 2.29.0 is now pinned to match the tested environment; its installed code/dependency set was not changed. Existing conflicts are not approved exceptions, and the scanner is expected to return a failing gate until remediation or an explicit user-approved policy change. No CI configuration exists yet; this is currently a manual development gate.

## Phase 2A/2B addition review — 2026-10-12

Only `fsrs==6.3.2` is added: MIT, exact pure-Python wheel/source/license/assets/import audit, no extras or new transitive distribution. Its existing runtime `typing-extensions` dependency remains the recorded PSF baseline finding; no policy exception is granted. Preserve `third_party/fsrs/LICENSE` and NOTICE.md. The scanner normalizes this exact package/version's verbose license metadata only when its complete text matches the retained audited MIT notice. Other verbose/unknown metadata remains review-required. RJSF is rejected at a BSD transitive; Tiptap adds unnecessary editor infrastructure and has not received full-tree clearance; Recharts is deferred to Phase 2C. See [exact selection evidence](docs/PHASE2_DECISIONS.md). No rejected code/assets, frontend dependency, fonts, model weights, optimizer or paid infrastructure are incorporated.

Current inventory: **468 entries, 79 review findings**. Compared with the recorded Phase 1B/1C baseline, only MIT FSRS is added; the baseline findings remain. `--check` intentionally fails and commercial distribution clearance remains unresolved. Timer, scoring, progress, CRUD, FSRS reviews and time tracking make zero AI calls. No CI configuration is introduced; the documented manual audit gate remains the current workflow.
