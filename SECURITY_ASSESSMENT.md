# Security Assessment — Instant Mechanic

Status: **implemented and tested locally**. Not independently audited. No live
deployment was verified; the Burp Suite checklist is a prepared manual
procedure, not a recorded result.

Companion documents: `README.md` (setup), `docs/API.md` (contract),
`docs/ARCHITECTURE.md` (layers), `MODEL_CARD.md` (ML limits),
`docs/BURP_SUITE_CHECKLIST.md` (manual VAPT runbook),
`docs/instant_mechanic.postman_collection.json` (automation).

---

## 1. System scope and trust boundaries

| Component | Technology | Boundary |
|:--|:--|:--|
| React SPA | React 19 + Vite + TypeScript (`src/`) | Browser; never sees secrets |
| API | FastAPI 0.139 + Uvicorn, Pydantic v2 (`backend/app/`) | Internet, behind Nginx/CloudFront |
| Persistence | SQLite + SQLAlchemy async; session/chat/upload rows only | API process; **no PII columns** |
| LLM | Groq `llama-3.3-70b-versatile`, key server-side only | Egress to `api.groq.com` |
| Vision | Optional YOLO11n warning-light detector | API process, in-memory only |
| NLP | Optional DeBERTa-v3 classifier + MAPIE conformal gate | API process, in-memory only |
| Image pipeline | Pillow re-encode, magic bytes, 5 MB cap | Before any model or disk write |
| Packaging | Non-root Docker image, Compose, GitHub Actions | CI/CD |

Trust boundaries: browser → API (all input untrusted); API → Groq (user text is
PII-masked and injection-filtered before egress); API → model (enum-only labels,
sanitized in-memory pixels); API → disk (sanitized bytes, UUID filenames, no
metadata).

---

## 2. Threat model and data-minimization rationale

Assets worth protecting here are a driver's phone/email/VIN, their GPS/device
metadata inside photos, the Groq key, prompt integrity, and safety-critical
advice.

**Decision: do not build an account system or encrypt PII at rest.** Instead,
remove PII from the data flow:

| Approach | Result |
|:--|:--|
| Store PII, encrypt it at rest | New key-management surface, decryption fan-out, backup exposure, retention obligations — and every read path becomes an authorization bug risk |
| **Stateless + mask in memory + strip metadata** (chosen) | PII never enters a durable store; a database dump or backup yields session IDs and symptom text only; there is no key to rotate and no per-user access-control matrix |

Concretely:

1. **No user database, no JWT/RBAC surface.** `ChatSession` is an anonymous
   UUID capability; `diagnostic_records`/`users` tables do not exist here.
2. **No PII columns.** `bookings` still needs a phone to dispatch a mechanic —
   this is a documented prototype field, not an account credential; it is never
   sent to Groq and never logged.
3. **EXIF/GPS is destroyed before inference or storage.** Pillow re-encodes
   every image in `BytesIO` with no `exif`/`encoderinfo`, so the exact bytes
   handed to YOLO11n/CLIP helpers carry no location or device identity.
4. **PII is masked in memory at the provider boundary.** `ai_service` is the
   only module that imports the Groq SDK; both calls apply `mask_pii` /
   `mask_messages`, so no route can forget.
5. **TLS/HSTS headers are set at the app** (termination still happens at the
   edge) and every response carries the five hardening headers.

Accepted consequence: records are tied to a browser session ID, not an identity.
Losing the session loses the history. That is intentional for a roadside
prototype; it is not described as an authenticated system.

---

## 3. OWASP Top 10 for LLM Applications (2026) mapping

| ID | Risk in this system | Control | Status |
|:--|:--|:--|:--|
| **LLM01** — Prompt Injection | Chat text and multi-turn history can carry role overrides, delimiter smuggling or cost bait | Deterministic two-layer guard (`injection_guard.py`), per-turn sanitizer (`sanitize_thread`), bounded context (`policy_router.py`), 0-token template routes, `PROMPT_INJECTION_BLOCKED` audit with no raw text | Mitigated |
| **LLM02** — Sensitive Information Disclosure | Phone/email/VIN in symptom text; system prompt extraction | `mask_pii` → `[PHONE_REDACTED]` / `[EMAIL_REDACTED]` / `[VIN_REDACTED]` before every provider call; hidden-context redaction on output; no key in prompts or logs; uploads never served | Mitigated |
| **LLM03** — Supply Chain | Third-party LLM/ML packages | Exact pins, Bandit, `pip-audit`, Trivy in CI; no runtime model downloads | Partial — weights are unverified local artefacts |
| **LLM04** — Data/Model Poisoning | Optional NLP/vision training inputs | `ENABLE_ML_INFERENCE=False` by default; deterministic rules remain authoritative | Accepted (ML off by default) |
| **LLM05** — Improper Output Handling | Model text rendered in React | `sanitize_llm_output` strips script/style/tags, `javascript:` and `on*=` handlers; `parse_diagnosis_json` validates enums and truncates fields; React escaping is the final layer | Mitigated |
| **LLM06** — Unbounded Consumption | Token spend and request floods | `MAX_LLM_TOKENS=400`, bounded history (6 messages / 1200 chars / 600 tokens), `max_tokens` caps, 3-word minimum for Groq, slowapi `429` + `Retry-After` on `/diagnosis/`, `/chat/`, `/upload/` | Mitigated |
| **LLM07** — System Prompt Leakage / hidden context | "Reveal your rules" payloads; hidden context echoed | Injection guard blocks extraction; `scrub_hidden_context` redacts `SYSTEM:` markers; enum-only vision handoff means no raw detector strings enter a prompt | Mitigated |
| **LLM08** — Vector/Embedding weaknesses | CLIP/SigLIP helpers | Not on the request path; no user-controlled retrieval corpus | Not applicable today |
| **LLM09** — Misinformation | Overconfident diagnosis | **MAPIE-style conformal gate (HITL):** prediction set of 1–2 labels may be used; **>2 labels forces a human-in-the-loop "inspection" result with `ai_used: false` and 0 LLM tokens**; safety overrides cannot be bypassed | Partially mitigated — accuracy unmeasured |
| **LLM10** — Improper Output Handling / unsafe content | Untrusted HTML or dangerous driving advice from the model | Output sanitisation on replies and structured fields; `output_safety.py` forces stop/tow for brake, oil-pressure, overheat and airbag/ABS hazards and removes sensor-bypass advice | Mitigated |

LLM07 note on MAPIE HITL: the conformal step is a *governance* control for
LLM07-adjacent failure modes — it prevents an uncertain model from presenting
itself as authoritative and keeps hidden calibration context out of prompts.
No model weights ship, so this is exercised via deterministic fallbacks.

---

## 4. API / transport controls

| Control | Location | Behaviour |
|:--|:--|:--|
| 5 MB image cap + magic bytes | `security/image_sanitizer.py`, `services/media.py` | Only genuine JPEG/PNG/WebP headers pass; spoofed extensions → `400`/`415` |
| EXIF/GPS stripping | `image_sanitizer.sanitize_image_bytes` | Pillow re-encode keeps pixels, drops EXIF/IPTC/XMP; UUID filename on disk |
| Pre-LLM PII masking | `security/pii_masker.py`, `services/ai_service.py` | Masking at the only provider boundary; system prompt keeps the public emergency number |
| Output sanitisation | `pii_masker.sanitize_llm_output`, `security/output_safety.py` | HTML/script stripping + safety-critical override |
| Security headers | `middleware/security_headers.py` | HSTS (31536000, includeSubDomains), nosniff, DENY, CSP `default-src 'self'`, no-referrer, COOP/CORP |
| Rate limiting | `security/middleware.py` (slowapi) | 10/min default on chat/diagnosis/upload; `429` + `Retry-After` + audit |
| Structured audit log | `security/audit_logger.py` | JSON lines: `timestamp`, `event_type`, `client_ip`, `endpoint`, `status`, `detail`; PII-redacted; optional file sink |
| Prompt-injection guard | `security/injection_guard.py`, `policy_router.py` | Two deterministic layers, bounded context, template routing |
| Log scrubbing | `security/middleware.py` (`PIIScrubFilter`) | Phone/email/VIN/plate patterns replaced in all log records |

Audit events emitted: `PROMPT_INJECTION_BLOCKED`, `INVALID_UPLOAD`,
`RATE_LIMIT_EXCEEDED`. Raw image bytes, provider keys and unmasked PII are never
logged.

---

## 5. VAPT findings and remediation log

Severity uses CVSS v3.1 bands. All four findings are fixed in this change.

### F-01 — Unbounded image upload (High, CVSS 7.1)

- **Evidence:** a >5 MB PNG and a `.jpg` containing plain text were both accepted
  by the upload path before the fix.
- **Fix:** 5 MB cap plus magic-byte detection in `image_sanitizer.py`, with
  `INVALID_UPLOAD` audit events.
- **Verification:** `test_security_hardening.py` — oversized image and fake-MIME
  `.jpg` both return `400`/`415`; the audit event is emitted without echoing the
  payload.

### F-02 — EXIF/GPS leakage into inference and storage (Medium, CVSS 6.5)

- **Evidence:** an uploaded JPEG retained a GPS IFD (lat 28°35′N, lon 77°12′E)
  and orientation tag in the bytes written to `MEDIA_ROOT` and passed to vision.
- **Fix:** every image is decoded and re-encoded through Pillow in memory with
  no EXIF argument; only the clean bytes reach the model and the disk.
- **Verification:** `test_security_hardening.py` builds a JPEG with a real GPS
  IFD, asserts the fixture has it, then asserts the sanitized bytes and the
  **stored file** contain no GPS/orientation tags.

### F-03 — Prompt injection reaching the LLM (High, CVSS 7.2)

- **Evidence:** `Ignore all previous instructions…` was forwarded to the
  provider and could cause hidden-context disclosure.
- **Fix:** deterministic two-layer guard with per-turn sanitization, bounded
  context, and `PROMPT_INJECTION_BLOCKED` audit. No payload text is logged.
- **Verification:** `test_security_hardening.py` patches `groq_chat` and asserts
  it is never called for an injection message; `ai_used` is `false`.

### F-04 — Missing security headers / abuse signalling (Medium, CVSS 5.3)

- **Evidence:** responses lacked HSTS, CSP, `nosniff` and `DENY`; rate-limit and
  upload rejections produced no structured event for alerting.
- **Fix:** header middleware on every response; `429` handler with
  `Retry-After`; structured JSON audit logger.
- **Verification:** `test_security_hardening.py` asserts all five required
  headers, `429` + `Retry-After`, and the three event types.

### Accepted risks

| ID | Risk | Why accepted |
|:--|:--|:--|
| R-01 | Session-ID capability URLs | Stateless prototype; no identity by design |
| R-02 | In-memory limiter, per worker | Single-instance SQLite design; resets on restart |
| R-03 | `bookings.phone` is stored | Operationally required to dispatch a mechanic; never sent to Groq or logged |
| R-04 | No CAPTCHA / account lockout | Out of scope for a stateless prototype |
| R-05 | TLS terminated at the edge | App sets HSTS but does not redirect; avoids a loop behind plain HTTP |
| R-06 | ML accuracy unmeasured | No weights shipped; ML off by default |
| R-07 | FastAPI 422 validation errors echo the rejected `input` field | Observed during the Postman run: a rejected `<script>` payload appears verbatim in `detail[].input`. It is not a model reply and is not persisted, but it can echo PII if a user puts PII in a rejected field. Recommended follow-up: a `RequestValidationError` handler that omits `input`. |

---

## 6. Verification summary

Measured on this machine (Windows, Python 3.14.4) on 2026-11-28.

| Check | Command | Result |
|:--|:--|:--|
| Full suite | `python -m pytest -q` | **119 passed, 1 skipped** (120 collected; skip = optional YOLO weights), 85% coverage |
| Original suite | `python -m pytest -q` (excluding the new file) | **103 passed, 1 skipped**, unchanged |
| New security suite | `python -m pytest -q backend/app/tests/test_security_hardening.py` | **16 passed** |
| SAST (CI gate) | `bandit -r backend/app -ll -x backend/app/tests` | **No issues identified** — 0 Medium, 0 High, exit 0 |
| SAST (all) | `bandit -r backend/app -ll` | 0 Medium, 0 High, exit 0 |
| Dependency audit | `pip-audit -r backend/requirements.txt --no-deps --disable-pip` | **No known vulnerabilities**, exit 0; `torch`/`torchvision` CPU wheels skipped (not on PyPI) |
| Container scan | Trivy in `.github/workflows/ci.yml` | Runs in CI only; **not run locally** in this change |
| Postman / Newman | `npx newman run docs/instant_mechanic.postman_collection.json` against local Uvicorn | **Executed**: 29 requests, 14 test scripts, 32 assertions, 0 failures. Raw report: `docs/security_evidence/postman_run_report.json` |
| Burp Suite | `docs/BURP_SUITE_CHECKLIST.md` | Runbook prepared; **0 of 4 screenshots captured** — Burp Suite is not installed in this environment. No screenshots were fabricated |
| Deployment | — | **Not deployed.** No URL, uptime or live smoke result is claimed |

No dependency was added or changed in this hardening pass; no ML weight,
training script, inference path or Docker hardening was modified.

---

## 7. Outstanding manual steps

1. Run the Postman collection against a local server and attach the run report.
2. Execute the four Burp Repeater checks and save the screenshots named in
   `docs/security_evidence/README.md`.
3. Capture the CI security job log (Bandit + pip-audit + Trivy).
4. Re-run this assessment after any change to the upload, masking, prompt or
   header paths.
