# API documentation

Base URL: `VITE_API_URL` (dev `http://127.0.0.1:8000`). All JSON unless noted.

## POST /api/chat/
```json
{ "session_id": "uuid-or-null", "message": "Swift won't start, clicking sound", "vehicle_make": "Maruti", "vehicle_model": "Swift", "vehicle_year": "2019" }
```
- 200: `{ session_id, reply, action: follow_up|greet|reject|ready, needs_info, ai_used, unsafe }`
- 400: empty-file/honeypot/too-long (`website` field = bot trap, `message` max 2000)
- 429: rate-limited
- Non-car queries → 200 with `action: "reject"` + polite message (no AI call).

## POST /api/upload/ (multipart)
Fields: `session_id`, `file` (jpg/jpeg/png/webp/gif, mp3/wav/ogg/m4a/webm, mp4/webm/mov/mkv/3gp).
- 201: `{ id, session_id, kind, size_bytes, analyzed: false, note }`
- 400: missing session, unsupported type, content mismatch, oversize (image 10MB, audio 15MB, video 50MB), empty file.
- Media is stored for the mechanic; image dimensions noted but visual content is NOT auto-diagnosed (never fabricated).

## POST /api/diagnosis/
```json
{ "session_id": "uuid" }
```
- 201 (persisted): `{ id, session, summary, possible_causes[], supporting_symptoms[], recommended_service, next_steps[], urgency: low|medium|high|critical, drive_guidance, safety_warning, inspection_recommended, ai_used, disclaimer, created_at }`
- 400: bad session / no messages. 422: only greetings so far. 503/504: provider rate-limit/timeout.
- Rule-based first (battery, overheating, tyre, brakes, fuel, keys, noise); Groq only for nuanced cases; unsafe symptoms force `urgency: critical` + do-not-drive guidance.

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
