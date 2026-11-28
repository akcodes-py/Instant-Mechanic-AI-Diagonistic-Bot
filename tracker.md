# Security Hardening Tracker

Task: Real-World AI & API Security Hardening + OWASP 2026 Documentation.
Baseline before any change: `103 passed, 1 skipped` (104 collected).
Final: **`136 passed, 1 skipped`** (137 collected), 85% coverage.

| Phase | Scope | Status |
|:--|:--|:--|
| 0 | Inspect repo, confirm baseline, reconcile with the previous scope | **done** |
| 1 | Upload/EXIF hardening, PII masker, headers, rate limits, audit events | **done** |
| 2 | `test_security_hardening.py` (16 new tests) | **done** |
| 3 | Postman, Burp checklist, `SECURITY_ASSESSMENT.md`, README | **done** (artifacts prepared, execution outstanding) |
| 4 | pytest, Bandit, pip-audit | **done** |

## Phase log

### Phase 0 — reconciliation
- Inspected `backend/app/` first: `image_sanitizer.py`, `media.py`, `ai_service.py`,
  `injection_guard.py`, `policy_router.py`, `output_safety.py`, `middleware.py`,
  `tests/test_api_hardening.py`, `requirements.txt`.
- **Removed the account/encryption layer added in the earlier task**, because
  this brief explicitly forbids an unnecessary user database and artificial
  encryption-at-rest: deleted `backend/app/db/`, `security/encryption.py`,
  `security/auth.py`, `routes/auth.py`, `routes/records.py` and their four test
  files; reverted the related edits in `config.py`, `database.py`, `main.py`,
  `schemas.py`, `conftest.py`, `requirements.txt`, `.env.example`, `AGENTS.md`,
  `README.md`, `docs/API.md` and `decision.md`.
- Baseline re-measured after the revert: `103 passed, 1 skipped`.

### Phase 1 — stateless controls
- Kept the existing 5 MB cap + magic-byte detection in `security/image_sanitizer.py`
  and `services/media.py`; verified Pillow re-encode drops EXIF/GPS/IPTC/XMP
  before inference and before disk writes.
- Kept/verified `security/pii_masker.py`; masking is applied inside
  `services/ai_service.py` (both Groq calls) and output sanitisation on replies
  and parsed diagnosis fields.
- `middleware/security_headers.py` provides all five required headers (+ COOP/CORP).
- `security/middleware.py` — slowapi 429 with `Retry-After` and
  `RATE_LIMIT_EXCEEDED` audit.
- `security/audit_logger.py` — simplified to exactly the three stateless events,
  JSON metadata only, with PII/secret redaction and an optional file sink.
- `chat.py` / `upload.py` — `PROMPT_INJECTION_BLOCKED` / `INVALID_UPLOAD` hooks.

### Phase 2 — tests
- Added `backend/app/tests/test_security_hardening.py` — 16 tests covering:
  oversized (>5 MB) and fake-MIME uploads; EXIF/GPS removal from both sanitized
  bytes and the stored file; PII masked before a mocked Groq client; HTML/script
  stripping; all five headers; prompt-injection audit; 429 + audit; audit shape.

### Phase 3 — VAPT artifacts
- `docs/instant_mechanic.postman_collection.json` — valid v2.1, 5 folders,
  14 requests: normal diagnosis, prompt injection, PII masking, malicious/
  oversized uploads, rate-limit bursts.
- `docs/BURP_SUITE_CHECKLIST.md` — short proxy guide + 4 named screenshots.
- `SECURITY_ASSESSMENT.md` — threat model + data-minimization rationale, OWASP
  LLM Top 10 (2026) mapping (LLM01/02/06/07/10), 4 VAPT findings, verification
  summary, accepted risks.
- `README.md` — compact stateless Security Controls table linking
  `SECURITY_ASSESSMENT.md` and `MODEL_CARD.md`; `.gitignore` for the generated
  oversized probe file; `docs/API.md` and `.env.example` aligned.

### Phase 4 — verification
| Command | Result |
|:--|:--|
| `python -m pytest -q` | **136 passed, 1 skipped**, 85% coverage |
| `python -m bandit -r backend/app -ll -x backend/app/tests` | **No issues identified** — 0 Medium, 0 High, exit 0 |
| `python -m pip_audit -r backend/requirements.txt --no-deps --disable-pip` | **No known vulnerabilities**, exit 0 |

## Path mapping (requested -> actual)

| Requested | Implemented |
|:--|:--|
| `src/security/image_sanitizer.py` | `backend/app/security/image_sanitizer.py` (already present) |
| `src/security/pii_masker.py` | `backend/app/security/pii_masker.py` |
| `src/security/audit_logger.py` | `backend/app/security/audit_logger.py` |
| `src/middleware/security_headers.py` | `backend/app/middleware/security_headers.py` |
| `tests/test_security_hardening.py` | `backend/app/tests/test_security_hardening.py` |

## Notes

- `/diagnose` maps to the existing `POST /api/diagnosis/`; it already carries a
  slowapi limit.
- No dependency was added or changed; no ML weights, training scripts,
  inference logic or non-root Docker hardening were touched.
- **Outstanding:** the Postman collection and Burp checklist were prepared but
  **not executed**; 0 of 4 screenshots exist. Trivy runs in CI only. No live
  deployment is claimed.
