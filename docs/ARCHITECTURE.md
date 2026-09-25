# Architecture

```
Browser (React+Vite+TS+Tailwind, Vercel)
  │  fetch (VITE_API_URL only, no secrets)
  ▼
Django + DRF (AWS, SQLite at SQLITE_PATH, media at MEDIA_ROOT)
  ├─ chatbot/views.py      — thin HTTP layer (validation, status codes, persistence)
  ├─ chatbot/serializers.py— Booking/Diagnosis/Message validation
  ├─ chatbot/models.py     — ChatSession → ChatMessage / MediaUpload / Diagnosis → Booking
  ├─ chatbot/services/
  │   ├─ triage.py         — deterministic: relevance gate, follow-ups, 7 symptom rules, safety override
  │   ├─ ai_service.py     — ONLY Groq calls (chat + structured diagnosis), error mapping, JSON validation
  │   └─ media.py          — extension + magic-byte checks, size limits, safe filenames
  └─ config/settings.py    — env-driven, HTTPS/HSTS in prod, CORS allowlist
```

## Database
- `ChatSession` (UUID, vehicle_* fields, timestamps)
- `ChatMessage` (session FK, role user/assistant/system, content, ai_used, index on session+created_at)
- `MediaUpload` (session FK, file outside executable paths, original_name, mime, size, kind, analyzed=false + honest note)
- `Diagnosis` (session FK, summary, JSON lists, recommended_service, urgency, drive/safety text, inspection_recommended, ai_generated, index on session+-created_at)
- `Booking` (session FK nullable SET_NULL, diagnosis FK nullable SET_NULL, name/phone/service/location..., status pending default, indexes on created_at/phone)
- Anonymous UUID sessions (no auth per assignment scope); session isolation enforced on booking/diagnosis/history reads.

## AI minimization
1. Reject/greet/follow-up deterministically (zero AI) for empty, greeting, irrelevant, and rule-matched inputs.
2. Groq chat used only for vague-but-car-related multi-word inputs with history (single follow-up question).
3. Diagnosis: rule match → no AI; else Groq structured JSON (validated, normalized) → else safe generic fallback. Booking never needs AI.
