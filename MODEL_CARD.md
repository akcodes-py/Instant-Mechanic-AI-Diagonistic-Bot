# Model Card — Instant Mechanic hardened diagnostics

Scope: local, deterministic security layer around the existing FastAPI + Groq
diagnostic service. **No model was retrained and no checkpoint was modified.**
All figures below were measured on this workspace on 2026-11-24; none are
copied from the ShopAssist benchmark.

## Models and what is actually verified here

| Component | Status in this workspace | Safety boundary |
|---|---|---|
| YOLO11n dashboard-light detector | Owner-reported mAP50 **0.979**; weights are **not present** in this repo, so accuracy was **not independently re-measured**. | Detections are normalized to strict enums + numeric confidence before any prompt. Unmapped labels and filenames are dropped. No reliable detection → HITL follow-up, never a fabricated diagnosis. |
| DeBERTa-v3 symptom classifier | Local model path is optional; no weights are committed. | Rules run first; ML never decides relevance or safety. |
| MAPIE-style conformal calibration | Implemented via split conformal prediction (`backend/app/services/calibration.py`): temperature scaling, finite-sample q_hat, alpha. | Prediction set of size 1–2 may be used; **size > 2 blocks the LLM diagnosis** and emits structured follow-up questions. Sufficiency check is non-circular (it reads set size, not the classifier's proposed label). |
| CLIP/SigLIP retrieval | Optional; no embeddings or index are committed. | Only enum IDs and confidences cross into prompts. |
| Groq LLM | Server-side key, deterministic fallbacks intact. | Two-layer injection guard + multi-turn thread sanitizer run before every call; output guard runs after. |

## Measured benchmark (local, no provider calls)

Reproduce with:

```bash
python -m pytest -q
python backend/scripts/eval_vision_robustness.py --out reports/vision_robustness.json
python backend/scripts/eval_security_benchmark.py --pytest-count 103 \
  --vision-report reports/vision_robustness.json --out reports/security_benchmark.json
```

| Metric | Measured result | Notes |
|---|---|---|
| Synthetic multi-turn chats | 25 | Hand-written in `eval_security_benchmark.py`. |
| Token estimate, before guard | 11,559 | Full raw history forwarded; every chat assumed an LLM answer. |
| Token estimate, after guard | 10,161 | Bounded history + only LLM-routed chats. |
| Estimated token reduction | **12.09%** | chars/4 estimate, not a provider tokenizer count. |
| Routes used | 2 deterministic template, 23 bounded LLM | No HITL routes in this particular chat set. |
| Prompt-injection block rate, before | 0% | No guard in baseline. |
| Prompt-injection block rate, after | **100%** (20/20 attacks) | Includes role overrides, extraction, encoded payloads, sensor-bypass requests. |
| English benign false-positive rate | **0%** (0/20) | Paired symptom queries. |
| Hinglish benign false-positive rate | **0%** (0/20) | Paired symptom queries. |
| English ↔ Hinglish FP gap | **0.00 pp** | Gate: < 5 pp. |
| Passing pytest cases | **103 passed, 1 skipped** | Skip is the optional YOLO-weights integration test (no weights present). |
| Bandit SAST | Clean at `-ll` | `bandit -r backend/app -ll -x backend/app/tests`. |
| pip-audit (pinned direct deps) | No known vulnerabilities | `torch`/`torchvision` `+cpu` wheels are skipped by PyPI's audit index and are checked separately by Trivy (torch 2.10.0+cpu fixes CVE-2026-24747); Pillow 13.0.0 and transformers 5.14.1 are the fixed pins. |
| Trivy container scan | **0 fixable CRITICAL/HIGH** locally | Rebuilt image `instant-mechanic-backend:security`; `--ignore-unfixed` gate shows 0 findings in both Debian 13.8 OS and Python packages. Unfixable distro CVEs remain in the log but do not block. CI uses the same `CRITICAL,HIGH` + `ignore-unfixed` gate. |
| Container import smoke | Passed | `docker run --rm instant-mechanic-backend:security python -c "import app.main"` → `import-ok`. |

## Vision robustness

`backend/scripts/eval_vision_robustness.py` applies deterministic Gaussian noise,
motion blur, low-light darkening and black-square occlusion to a validation
subset and runs the **same** YOLO loader as the API. It reports mean confidence,
reliable-detection count and safe-HITL rate per perturbation.

**Current run:** `{"status": "skipped", "reason": "no YOLO checkpoint supplied or found"}`.
There are no accuracy/robustness numbers to publish because no weights or
validation images are present. Supply `--weights` and `--images` to generate
the table; the script never invents results.

## Safety boundaries / known limits

- Prototype has no auth; a session ID is the only capability. Booking lookup without `session_id` remains public by design — do not describe it as secure.
- Rate limits are in-memory and per worker (slowapi 10/min by default), keyed on client address plus optional session header. They reset on restart.
- Uploaded images are re-encoded in memory; the **sanitized** bytes are stored (EXIF/GPS removed), never the original photo bytes. The 5 MB vision cap is enforced before storage. Media is not served by the API.
- Hidden-context markers are redacted and unsafe drive/sensor-bypass advice is removed, but this is a deterministic filter, not a guarantee against novel phrasings.
- A full Trivy run (without `--ignore-unfixed`) still reports unfixable Debian distro/kernel CVEs; the CI gate reports them but does not fail on them. Fixable HIGH/CRITICAL findings do fail.
- No live deployment is verified. No URL, uptime, or smoke result is claimed here.
- Business figures (30,000+ cars, 4.9★, 20-min SLA) remain unverified marketing claims.
