# API documentation

Base URL: `VITE_API_URL` (dev `http://127.0.0.1:8000`). Backend: FastAPI + Uvicorn. All paths end with `/`. All JSON unless noted.

## POST /api/chat/
```json
{ "session_id": "uuid-or-null", "message": "Swift won't start, clicking sound", "vehicle_make": "Maruti", "vehicle_model": "Swift", "vehicle_year": "2019" }
```
- 200: `{ session_id, reply, action: follow_up|greet|reject|ready, needs_info, ai_used, unsafe }`
- 400: empty-file/honeypot/too-long (`website` field = bot trap, `message` max 2000)
- 429: rate-limited
- Non-car queries → 200 with `action: "reject"` + polite message (no AI call).

## POST /api/upload/ (multipart)
Fields: `session_id`, `file` (images: jpg/jpeg/png/webp, max 10 MB; audio: mp3/wav/ogg/m4a/webm; video: mp4/webm/mov/mkv/3gp). With `ENABLE_ML_INFERENCE=True`, only JPG/JPEG/PNG/WebP images up to 10 MB are accepted for warning-light analysis; other media is rejected with 400.
- 201: `{ id, session_id, kind, size_bytes, analyzed, note, message, detections, reliable_labels, vision }`
- `detections` (and `vision.detections`) is a list of `{ label, confidence, box: [x1,y1,x2,y2], reliable }`, sorted by confidence. `confidence` is rounded to 3 decimals. Reliable threshold is 0.40 by default; `Check Engine`, `Electronic Stability Problem -ESP-`, and `Low Engine Oil Warning Light` require 0.50 because of weaker validation recall.
- `reliable_labels` contains only labels above those gates. Only reliable labels are added to the chat history that feeds diagnosis/LLM explanation; safety-critical labels (brakes, overheating, airbag) still resolve through deterministic rules. If no reliable detection exists, `note`/`message` asks for a clearer, closer dashboard photo or a text description instead of guessing.
- `analyzed` is `false` when ML is off, unavailable, failed, or returned no detections; `vision` is `null` when ML is off or inference failed, otherwise `{ detections, count, labels, reliable_labels, analyzed }`.
- 400: missing session, unsupported type (GIF is not accepted), content mismatch, oversize (image 10MB, audio 15MB, video 50MB), empty file.
- Media is stored for the mechanic; image dimensions are noted. Visual content is only described when a real model produced detections; audio/video are not transcribed and no observation is fabricated.

## POST /api/diagnosis/
```json
{ "session_id": "uuid" }
```
- 201 (persisted): `{ id, session, summary, possible_causes[], supporting_symptoms[], recommended_service, next_steps[], urgency: low|medium|high|critical, drive_guidance, safety_warning, inspection_recommended, ai_generated, ai_used, disclaimer, created_at }`
- 400: bad session / no messages. 422: only greetings so far. 503/504: provider rate-limit/timeout.
- Rule-based first (battery, overheating, tyre, brakes, fuel, keys, noise); optional ML classifier only when `ENABLE_ML_INFERENCE=True` and a model is configured; Groq only for nuanced/uncertain cases; unsafe symptoms force `urgency: critical` + do-not-drive guidance. `ai_used` stays `false` for rule- and ML-derived diagnoses.

## POST /api/booking/
```json
{ "session_id": "uuid?", "diagnosis_id": "uuid?", "name": "Atul Kumar", "phone": "9876543210", "service_type": "battery_jumpstart|flat_tyre|towing|fuel_delivery|key_lockout|general_repair|inspection", "location": "Sector 75 Gurugram", "vehicle_details": "Swift 2019", "scheduled_at": "", "notes": "" }
```
- 201: booking + `message`. Phone validated (10-digit Indian mobile). No AI dependency.
- 400: validation errors or diagnosis/session mismatch.

## GET /api/booking/<id>/
- 200: booking (+ embedded `diagnosis` when linked). 404: unknown/invalid id or wrong `?session_id=`.
- Example: `/api/booking/<id>/?session_id=<sid>` enforces session isolation.

## GET /api/history/<session_id>/
- 200: `{ session_id, vehicle, messages[], diagnoses[], uploads[] }`. 404: unknown session.

## GET /api/health/
- 200: `{ status: "ok", service: "instant-mechanic-backend" }`
