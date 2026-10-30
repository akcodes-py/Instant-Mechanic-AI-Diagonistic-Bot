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
* **Context:** Drivers on the roadside need instant help and will abandon tools requiring account registration.
* **The Decision:** Anonymous UUID sessions stored in local storage (`im-session`).
* **Why:**
  1. **Frictionless Onboarding:** Instant roadside assistance without passwords, emails, or OAuth flows.
  2. **Upload Safety:** All uploaded files are validated via magic bytes and Pillow image headers, saved with random UUID filenames, and placed outside the web server's publicly browsable paths.
  3. **Isolated History:** Session IDs isolate user diagnostics, chat history, and bookings.

---

## 3. Maintenance & Evolution

1. **Deterministic rules remain the ultimate gatekeeper:** No new ML or AI model may bypass the safety overrides in `triage.py`.
2. **ML inference remains optional:** `ENABLE_ML_INFERENCE=False` ensures the entire application runs deterministically even without model weights installed.
3. **Additive APIs:** Any new data surfaced by vision or NLP is exposed via additive keys (`vision`, `detections`, `reliable_labels`), ensuring zero breaking changes to existing frontend clients.

