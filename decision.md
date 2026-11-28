# Technical Architecture & Design Decisions

This document outlines **what** technologies, patterns, and tools are used across Instant Mechanic, **what** purpose they serve, and **why** they were chosen over alternatives. It is written to give developers, evaluators, and contributors an immediate, unambiguous understanding of the system's design rationale.

---

## 1. Quick Reference: Core Decisions Matrix

| Component | Technology / Pattern | What It Is Used For | Why We Chose It (Rationale) | Alternatives Considered |
| :--- | :--- | :--- | :--- | :--- |
| **Backend Framework** | **FastAPI 0.139 + Uvicorn** | Asynchronous REST API, request validation, lifespan management | High throughput, native async I/O, Pydantic v2 data validation, lightweight memory footprint (~60 MB vs ~250 MB Django). | Django REST Framework (migrated away due to synchronous overhead and heavy boilerplate). |
| **Database & ORM** | **SQLite + SQLAlchemy 2.0 (`aiosqlite`)** | Relational persistence for sessions, chat history, uploads, diagnoses, and bookings | Zero DevOps overhead, embedded single-file storage, modern async SQLAlchemy 2.0 query syntax (`select()`). | PostgreSQL / MySQL (overkill for prototype single-node deployment). |
| **Chat & Triage Engine** | **Deterministic Rules (`triage.py`)** | Primary symptom analysis and routing for common faults (battery, brakes, overheating, etc.) | **Safety and zero latency.** Deterministic keyword matching never hallucinates, costs \$0, operates offline, and guarantees critical safety instructions. | Pure LLM triage (unreliable safety guarantees, hallucination risk, vendor lock-in, latency). |
| **Generative AI** | **Groq API (`llama-3.3-70b-versatile`)** | Structured JSON diagnosis for vague/complex car symptoms that bypass deterministic rules | Ultra-low latency cloud inference (~500ms), high reasoning capability for ambiguous driver descriptions, strict JSON mode support. | OpenAI GPT-4o (slower/more expensive), local LLM (too heavy for standard host). |
| **Computer Vision** | **Ultralytics YOLO11n (`dashboard_lights.pt`)** | Automated warning light detection on dashboard photos | Lightweight (5.2 MB nano model), 97.9% mAP50 on 10 dashboard icon classes, runs efficiently on standard CPU (<100ms). | Cloud Vision APIs (cost per request, data privacy concerns), heavy YOLO models (x/l variants require GPU). |
| **Image Preprocessing** | **Albumentations 2.2** | Image contrast enhancement (CLAHE) and blur/lighting quality checks before YOLO inference | Enhances low-contrast dashboard photos taken in bright sun or night conditions; handles varied in-car lighting. | OpenCV basic pipeline (less expressive augmentation and equalization chains). |
| **Uncertainty Quantification** | **Split Conformal Prediction + Temperature Scaling** | Calibrating NLP symptom classifier probabilities and calculating prediction sets | Distribution-free, mathematically proven 95% coverage guarantee; safely decides when to trust local ML vs. when to escalate to an LLM. | Raw softmax confidence (notoriously overconfident and uncalibrated in neural networks). |
| **Frontend Framework** | **React 19 + TypeScript + Vite 8** | Interactive single-page marketing and diagnostic web client | Instant HMR, typed contract with backend schemas, small bundle size (~262 kB JS, 29 kB CSS), high mobile responsiveness. | Next.js / SSR (unnecessary complexity for an anonymous state-driven tool without SEO dependencies). |
| **Styling** | **Tailwind CSS 4** | Mobile-first responsive styling and component layout | Rapid UI development, zero runtime CSS overhead, accessible touch targets (44px+), responsive emergency mobile sticky bar. | Component UI libraries (MUI/Chakra - heavy bundles, difficult custom styling). |
| **Client API Layer** | **Typed Fetch Client (`src/api.ts`)** | Centralized API communication, session persistence, automatic retry with backoff | Eliminates external Axios dependency, typed response contracts matching backend schemas, automatic 5xx/network retry backoff. | Axios (extra bundle size without added value over modern `fetch`). |

---

## 2. In-Depth Engineering Rationales

### 2.1 Backend: FastAPI vs. Django REST Framework
* **Context:** The original prototype was built with Django and Django REST Framework (DRF).
* **The Decision:** Migrated completely to FastAPI + async SQLAlchemy.
* **Why:**
  1. **Async Performance:** Automotive roadside diagnosis involves streaming I/O, file uploads, and external AI calls. FastAPI's native `asyncio` event loop non-blockingly handles concurrent sessions on a single worker.
  2. **Memory Footprint:** In Docker/EC2 environments, FastAPI uses ~75% less baseline memory than Django + WSGI.
  3. **Data Integrity:** Pydantic v2 schemas provide end-to-end request validation and serialization with automatic OpenAPI documentation.

### 2.2 Triage Architecture: Deterministic First, AI Second
* **Context:** A car breakdown is a **safety-critical** domain. A wrong suggestion on a failed brake system or engine fire can cause catastrophic harm.
* **The Decision:** Implement a 2-tier triage pipeline:
  - **Tier 1 (Deterministic Rules):** Pure Python regular expressions and keyword trees for 8 known breakdown patterns (Battery/No-start, Overheating, Airbag/SRS, Flat tyre, Brakes, Fuel, Key lockout, Engine noise).
  - **Tier 2 (AI Service):** Groq LLM is only called if Tier 1 finds no match, the query is car-related, and contains at least 3 descriptive words.
* **Why:**
  1. **Zero Hallucination on Safety Risks:** If a user mentions "smoke" or "brake failure", deterministic rules immediately flag it as critical and supply towing/emergency guidance without waiting for an LLM.
  2. **Zero Latency & Cost:** Standard breakdown questions receive instant (<5ms) deterministic replies at \$0 API cost.
  3. **Graceful Offline Degradation:** If Groq encounters rate limits (503), timeouts (504), or missing API keys, the system falls back to safe deterministic triage without breaking the user journey.

### 2.3 Local Computer Vision: YOLO11n Nano Model
* **Context:** Users often photograph warning lights because they don't know their names.
* **The Decision:** Deploy a fine-tuned Ultralytics **YOLO11n** model (`5.2 MB`) loaded lazily on the CPU, coupled with Albumentations CLAHE preprocessing.
* **Why:**
  1. **CPU Friendly:** YOLO11n achieves sub-100ms inference on standard CPUs without requiring expensive GPU instances.
  2. **Class-Specific Reliability Gates:** Lower-recall classes (`Check Engine`, `ESP`, `Low Engine Oil`) enforce a `0.50` confidence threshold, while high-accuracy icons use `0.40`. Unreliable detections are discarded to prevent misdiagnosis.
  3. **Strict Honesty Rule:** The API only claims an image was analyzed if real detections were produced. Media is stored safely with UUID naming but is never fabricated.

### 2.4 Uncertainty Quantification: Conformal Prediction
* **Context:** When local ML models (e.g. DistilBERT / DeBERTa) classify symptom descriptions, raw softmax probabilities often exhibit high overconfidence on ambiguous inputs.
* **The Decision:** Implement Temperature Scaling and Split Conformal Prediction (`calibration.py`).
* **Why:**
  1. **Statistical Coverage:** Generates a prediction set of possible labels guaranteed to contain the true fault with 95% confidence ($\alpha=0.05$).
  2. **Dynamic Routing:**
     - If the prediction set has **1 label** $\rightarrow$ ML is confident; use deterministic service mapping.
     - If the prediction set has **2 labels** $\rightarrow$ ML is moderately confident; present ML-assisted multi-cause assessment.
     - If the prediction set has **$>2$ labels** $\rightarrow$ High uncertainty; automatically escalate the query to the Groq LLM for deeper conversational diagnosis.

### 2.5 Security, Privacy & Sessions
* **Context:** Drivers on the roadside need instant help and will abandon tools requiring account registration. Photos carry GPS/device metadata and symptom text carries phone numbers and VINs.
* **The Decision:** Anonymous UUID sessions stored in local storage (`im-session`). **No account system, no stored PII, no encryption-at-rest** (confirmed again in section 4).
* **Why:**
  1. **Frictionless Onboarding:** Instant roadside assistance without passwords, emails, or OAuth flows.
  2. **Upload Safety:** All uploaded files are validated via magic bytes and Pillow image headers, saved with random UUID filenames, and placed outside the web server's publicly browsable paths.
  3. **Isolated History:** Session IDs isolate user diagnostics, chat history, and bookings.
  4. **Data Minimization:** The safest PII is PII never stored — masking in memory and stripping metadata remove the data before it can leak from a backup or log.

---

## 3. Maintenance & Evolution

1. **Deterministic rules remain the ultimate gatekeeper:** No new ML or AI model may bypass the safety overrides in `triage.py`.
2. **ML inference remains optional:** `ENABLE_ML_INFERENCE=False` ensures the entire application runs deterministically even without model weights installed.
3. **Additive APIs:** Any new data surfaced by vision or NLP is exposed via additive keys (`vision`, `detections`, `reliable_labels`), ensuring zero breaking changes to existing frontend clients.

---

## 4. Stateless Security Hardening ADR (2026-11-28)

Scope: input/upload hardening, EXIF stripping, in-memory PII masking, output
sanitisation, security headers, rate limiting and structured audit logging.
ML weights, training scripts, YOLO11n/DeBERTa/MAPIE inference and non-root
Docker hardening were **not** modified.

### 4.1 Data minimization beats encryption-at-rest

A user table plus AES-encrypted PII columns was rejected. It adds key
management, a decryption fan-out on every read, backup exposure and an
authorization matrix — while still retaining the data. Instead the API is
stateless: `ChatSession` is an anonymous UUID capability, there are no
`users`/`diagnostic_records` tables, and the only durable PII is the booking
phone needed to dispatch a mechanic (never sent to Groq, never logged).

**Consequence:** losing a session ID loses the history; there is no identity
and no key to rotate. This is intentional for a roadside prototype and is
documented as such in `SECURITY_ASSESSMENT.md`.

### 4.2 EXIF/GPS destroyed before inference or disk

`security/image_sanitizer.py` checks magic bytes (never client MIME), enforces
5 MB, then decodes and re-encodes through Pillow into `BytesIO` with no `exif`
or `encoderinfo`. The clean bytes are what reach YOLO11n/CLIP helpers and what
get written under `MEDIA_ROOT` with a UUID filename. A test builds a JPEG with a
real GPS IFD and proves both the sanitized bytes and the stored file have no
GPS/orientation tags.

### 4.3 PII masking at the only provider boundary

`mask_pii` / `mask_messages` live inside `services/ai_service.py`, the only
module importing the Groq SDK. Both the free-form and structured calls mask
phone/email/VIN before egress; the system prompt keeps the public emergency
number because it is not user PII. Ordering is email → VIN → phone so a
17-character VIN is not partially consumed by the phone rule. `sanitize_llm_output`
runs on replies and on every parsed diagnosis field (LLM10).

### 4.4 Headers, limits and audit events

`app/middleware/security_headers.py` owns the five required headers plus COOP/
CORP. `security/middleware.py` keeps slowapi at 10/min with `429` + `Retry-After`
and emits `RATE_LIMIT_EXCEEDED`. `security/audit_logger.py` emits exactly three
stateless events — `PROMPT_INJECTION_BLOCKED`, `INVALID_UPLOAD` and
`RATE_LIMIT_EXCEEDED` — as JSON lines containing only metadata. Every field is
redacted, so raw image bytes, keys and unmasked PII cannot be logged even if a
caller tries.

### 4.5 MAPIE HITL as an LLM07/LLM09 governance control

The conformal gate is kept out of the prompt path: wide prediction sets (>2
labels) return a human-in-the-loop "inspection" result with `ai_used: false` and
zero LLM tokens. Deterministic hazard overrides run last and cannot be bypassed
by ML or Groq. No calibration or hidden context is ever included in a prompt.

### 4.6 Path mapping (brief → repository)

The brief uses a generic `src/` + `tests/` layout. This repository keeps the
API in `backend/app/` and the React app in `src/`:

| Requested | Implemented |
|:--|:--|
| `src/security/image_sanitizer.py` | `backend/app/security/image_sanitizer.py` (pre-existing, retained) |
| `src/security/pii_masker.py` | `backend/app/security/pii_masker.py` |
| `src/security/audit_logger.py` | `backend/app/security/audit_logger.py` |
| `src/middleware/security_headers.py` | `backend/app/middleware/security_headers.py` |
| `tests/test_security_hardening.py` | `backend/app/tests/test_security_hardening.py` |

### 4.7 Verification and limits

136 passed / 1 skipped; Bandit `-ll` 0 Medium/0 High; `pip-audit` clean. No
dependency changed. Manual Burp/Postman execution and CI Trivy remain
outstanding — see `SECURITY_ASSESSMENT.md` §6–7. The in-memory limiter is per
worker and resets on restart; TLS is terminated at the edge and the app sets
HSTS without redirecting.
