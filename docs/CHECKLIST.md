# Website quality checklist (20 Things × 2 lists) — verified

Fix list: ✅ = done & verified in this build.
1. ✅ No horizontal scrolling — `overflow-x:hidden`, responsive grids, tested at 360px.
2. ✅ Broken links — all anchors (`#services/#diagnosis/#membership/#coverage`) exist; tel/mailto/wa.me valid; legal pages in-app.
3. ✅ Mobile menu — hamburger with aria-expanded, closes on navigate.
4. ✅ Favicon — `public/favicon.svg` (custom wrench), linked in index.html.
5. ✅ Page titles — specific title in index.html; in-app legal/404 headings.
6. ✅ Meta descriptions — page-specific description + OG/Twitter tags.
7. ✅ Footer links — contact/explore/legal all functional.
8. ✅ Custom 404 — in-app `notfound` page with home + call actions.
9. ✅ Dynamic copyright year — `new Date().getFullYear()`.
10. ✅ Images optimized — removed unused Vite template PNGs; favicon/OG are tiny SVGs; chat previews bounded.
11. ✅ Broken buttons — every button wired (call/WhatsApp/diagnose/book/lookup/menu/cookie).
12. ✅ Success messages — chat/diagnosis/booking/upload show `role=status` confirmations.
13. ✅ Error messages — useful `role=alert` messages + validation text, no raw stacks.
14. ✅ No placeholder text — all copy real; inputs have labels + meaningful placeholders.
15. ✅ No unused nav — 4 anchors only, all mapped to sections.
16. ✅ Mobile overflow — max-width 100vw, images bounded, sticky bar safe-area.
17. ✅ Clickable logo — header logo → home.
18. ✅ Clickable phones — `tel:+919266961110` everywhere incl. sticky bar.
19. ✅ Clickable emails — `mailto:gordhan@instantmechanic.online`.
20. ✅ Mobile optimized — stacked layouts, 44px+ targets, sticky emergency bar.

Pre-launch:
1. ✅ Privacy page (owner-review draft). 2. ✅ Terms page (draft). Refund page also added.
3. ✅ Secrets off frontend — only `VITE_API_URL`; `GROQ_API_KEY` server-only; `.env.example` placeholders.
4. ✅ HTTPS enforced — `SECURE_SSL_REDIRECT`/HSTS when `DEBUG=False`; Vercel/AWS TLS per DEPLOYMENT.md.
5. ✅ Cookie banner — essential-only, persisted choice, no trackers.
6. ✅ Meta titles/descriptions. 7. ✅ Social preview (`og-preview.svg`). 8. ✅ Favicon.
9. ✅ `sitemap.xml` + `robots.txt` in `public/`.
10. ✅ Alt text on images (logo, previews, icons aria-hidden).
11. ✅ Images compressed (SVG, no heavy assets).
12. ✅ Perf — `npm run build` 262KB JS (79KB gzip); no third-party scripts.
13. ✅ Contrast — amber-on-black / white-on-dark; focus rings.
14. ✅ Mobile friendly. 15. ✅ 404. 16. ✅ Broken links fixed.
17. ✅ Form validation — booking + chat + upload validated client + server.
18. ✅ Spam protection — honeypot `website` field + rate limiting; no fake CAPTCHA.
19. ⏭️ Analytics — NOT added (no ID/consent basis); add privacy-conscious analytics only with config + consent. Documented, not faked.
20. ✅ Clear CTA per view — Call/WhatsApp/Diagnose/Book on every screen incl. chatbot header.
