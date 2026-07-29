# Release checklist

Verification date: 2026-07-29 (Asia/Shanghai)

## Release decision

- **Implementation portfolio package:** PASS. The standalone folder and source archive are suitable for creating a public GitHub portfolio repository and demonstrating implemented product/engineering decisions.
- **Product validation:** **INCOMPLETE.** The planned 3–5 user interviews and task tests have not been run, so the portfolio does not claim validated usability, trust, completion, or real-world demand.
- **Clinical or production medical release:** **FAIL / BLOCKED.** Red-flag recall is **92.00% (46/50)**, below the predeclared **98%** safety threshold. This prototype must not be described as clinically safe, medically validated, or ready for patient use.

## Secrets, privacy and file size

- The required brief scan returned three benign matches: privacy-warning text in `docs/EVALUATION.md` and `app/web/index.html`, plus a synthetic-data validator in `tests/test_eval.py`. It returned no credential or real-identity value.
- Expanded credential scan returned zero matches for private-key headers, AWS access-key shapes, long OpenAI-style keys, or non-empty key/secret/token/password assignments.
- Chinese mobile-number and PRC identity-number shape scan returned zero matches.
- `.env.example` contains only empty model-key, base-URL, and model-name entries. No `.env` file is tracked.
- No release-scope file is 1 MiB or larger. The largest file is `assets/demo-result.png` at 193,402 bytes.
- `.venv`, `.env`, `__pycache__`, `.pytest_cache`, and evaluation scratch output are ignored or excluded from the archive.

## Automated quality gate

Run from the standalone repository root using the existing project environment:

```bash
UV_CACHE_DIR=/private/tmp/xunji-uv-cache .venv/bin/uv run --no-sync pytest -q
UV_CACHE_DIR=/private/tmp/xunji-uv-cache .venv/bin/uv run --no-sync python scripts/run_eval.py \
  --input data/eval_cases.jsonl \
  --output eval-results/latest.md
```

The project-local `uv` and `--no-sync` were used because the verification host did not expose `uv` on `PATH` and network access was unavailable; this still exercises the documented `uv run` execution path against the already synchronized environment.

| Gate | Actual result | Status |
| --- | ---: | --- |
| Pytest | 120 passed, 1 dependency deprecation warning | PASS |
| Red-flag recall | **92.00% (46/50)** | **FAIL — below 98% safety threshold** |
| Action-level accuracy | 90.00% (108/120) | Recorded; no release threshold |
| Boundary-language pass rate | 90.00% (108/120) | Recorded; no release threshold |
| Average supplied turns | 1.32 | Recorded |
| Failed evaluation cases | 12 | Open concern |

The warning is the existing Starlette TestClient/httpx deprecation warning. It is not a test failure.

## Six-state UI inspection

Fresh interaction and visual inspection used the running local FastAPI app in headless Google Chrome. Every state was checked at desktop **1440×1000** and mobile **390×844** CSS pixels.

| State | Trigger / evidence | Focus | Mobile overflow | Result |
| --- | --- | --- | --- | --- |
| Start | Fresh page; start form and boundary copy visible | Keyboard Tab reached the skip link with a visible solid 3 px outline | 390/390 px document/client width | PASS |
| Follow-up | Synthetic mild-cough input produced only `followup-state` | `question-heading` | 390/390 px | PASS |
| Emergency | Synthetic chest-pain plus breathing-difficulty input produced only `emergency-state` | `emergency-heading` | 390/390 px | PASS |
| Normal result | README synthetic ordinary-care input produced only `result-state` | `result-heading` | 390/390 px | PASS |
| Insufficient | README synthetic conflicting-trend input produced only `insufficient-state` | `insufficient-heading` | 390/390 px | PASS |
| Network error | Browser aborted `POST /api/sessions`; only `error-state` was visible and entered text was retained for retry | `error-heading` | 390/390 px | PASS |

Additional interaction evidence:

- Every state retained a visible, in-viewport fixed emergency link with the literal `tel:120` target at both viewports.
- Copying the visit summary wrote the complete summary to the clipboard and displayed `摘要已复制。`.
- Clearing the completed session returned to only `start-state`, emptied the symptom field, reset status to `尚未开始`, and focused `symptom-input`.
- Visual review found no clipped state heading, broken panel, or horizontal overflow in the six desktop captures.

The UI review identified and fixed one release issue: the follow-up heading now has `tabindex="-1"` so the existing focus transition succeeds. A regression contract test covers it.

## Standalone repository boundary and README

- `find . -maxdepth 3 -type f | sort` and `git ls-files` were reviewed from the standalone repository root.
- No tracked symlink exists. Local `.venv` interpreter symlinks are ignored and excluded from the archive.
- Application code, assets, public documentation links, and runnable commands resolve entirely inside the standalone repository. No runtime or documentation command depends on the source monorepo, its `src/`, environment files, assets, internal planning files, or absolute filesystem paths.
- Runtime code has no dependency on environment variables; `.env.example` is documentation only.
- All 16 README-local image/document links resolve.
- README prominently states the 92% result, failed 98% safety gate, synthetic-data boundary, no-key demo path, limitations, and medical disclaimer.
- Added `tool.pytest.ini_options.pythonpath = ["."]` so the standalone `uv run pytest` command resolves local packages without a parent-repository path.

## Archive gate

- Target: `/private/tmp/xunji-health-triage-github.tar.gz`
- Required top-level prefix: `health-triage-agent/`
- Exclusions: `.venv`, `.env`, `__pycache__`, `.pytest_cache`, bytecode, `.DS_Store`, internal `.superpowers`, and local scratch files.
- Listing verification passed: 57 entries, all under `health-triage-agent/`, with zero forbidden entries.
- `README.md`, `RELEASE-CHECKLIST.md`, `.env.example`, and `eval-results/latest.md` are present.
- Gzip integrity passed. The final compressed archive is below 1 MiB; exact size and checksum are recorded during handoff after the final commit is archived.

## Open concerns

1. Four synthetic red-flag spelling/wording variants are missed; this is the reason the safety gate fails.
2. Eight synthetic low-acuity cases do not reach the expected result, contributing to the 12 evaluation failures.
3. The evaluation is synthetic and is not clinical validation.
4. No qualified clinical review or completed user research exists; this is why only the implementation portfolio package—not the full product-validation case—is marked ready.
5. Sessions and analytics are in-memory only; the product is not production infrastructure.
6. The emergency number is fixed to mainland China `120` and is not localized.
