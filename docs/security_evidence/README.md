# Security evidence

Drop the four Burp Suite screenshots here after the manual pass described in
`docs/BURP_SUITE_CHECKLIST.md`:

| File | Probe |
|:--|:--|
| `01-prompt-injection.png` | Role override → 200, `ai_used: false`, `PROMPT_INJECTION_BLOCKED` |
| `02-pii-masking.png` | Phone/email/VIN masked in memory before Groq |
| `03-malicious-upload.png` | Spoofed JPEG rejected, >5 MB rejected |
| `04-rate-limit-429.png` | Burst → 429 + `Retry-After` |

`fake.jpg` is intentionally **not** an image: it is plain text with a `.jpg`
extension, used to prove magic-byte validation (expected `400`/`415`).

`oversized.png` is generated locally for the size probe and is gitignored.

Do not commit real customer data, provider keys, or screenshots containing them.
