import { useEffect, useState } from 'react';
import { CONTACT } from '../api';

export type Page = 'home' | 'privacy' | 'terms' | 'refund' | 'notfound';

export function Header({ go, onBook }: { go: (p: Page) => void; onBook: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <header className="sticky top-0 z-40 border-b border-white/10 bg-black/85 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-2 px-4 py-3">
        <button onClick={() => go('home')} aria-label="Instant Mechanic home" className="flex items-center gap-2 text-left">
          <img src="/favicon.svg" alt="Instant Mechanic logo — wrench and wheel" className="h-8 w-8" />
          <span className="leading-tight">
            <span className="block text-base font-extrabold tracking-tight text-white">Instant Mechanic</span>
            <span className="block text-[11px] font-medium text-amber-300">India's Car Care Platform</span>
          </span>
        </button>
        <nav aria-label="Primary" className="hidden items-center gap-5 text-sm font-medium text-neutral-200 md:flex">
          <a href="#services" className="hover:text-amber-300">Car Services</a>
          <a href="#diagnosis" className="hover:text-amber-300">AI Diagnosis</a>
          <a href="#membership" className="hover:text-amber-300">Membership</a>
          <a href="#coverage" className="hover:text-amber-300">Coverage</a>
        </nav>
        <div className="hidden items-center gap-2 md:flex">
          <a href={CONTACT.phoneHref} className="rounded-lg border border-amber-400/40 px-3 py-2 text-sm font-bold text-amber-300 hover:bg-amber-400/10">📞 {CONTACT.phoneDisplay}</a>
          <a href={CONTACT.whatsapp} target="_blank" rel="noreferrer" className="rounded-lg border border-emerald-400/40 px-3 py-2 text-sm font-bold text-emerald-300 hover:bg-emerald-400/10">💬 WhatsApp</a>
          <button onClick={onBook} className="rounded-lg bg-amber-400 px-4 py-2 text-sm font-extrabold text-black hover:bg-amber-300">Book Now</button>
        </div>
        <button className="rounded-lg border border-white/15 px-3 py-2 text-sm font-bold text-white md:hidden" onClick={() => setOpen(!open)} aria-expanded={open} aria-label="Open menu">
          {open ? '✕ Close' : '☰ Menu'}
        </button>
      </div>
      {open && (
        <nav aria-label="Mobile" className="border-t border-white/10 bg-black px-4 py-3 md:hidden">
          <div className="grid gap-2 text-sm font-medium">
            <a href="#services" onClick={() => setOpen(false)} className="rounded-lg px-2 py-2 hover:bg-white/5">Car Services</a>
            <a href="#diagnosis" onClick={() => setOpen(false)} className="rounded-lg px-2 py-2 hover:bg-white/5">AI Diagnosis</a>
            <a href="#membership" onClick={() => setOpen(false)} className="rounded-lg px-2 py-2 hover:bg-white/5">Membership</a>
            <a href="#coverage" onClick={() => setOpen(false)} className="rounded-lg px-2 py-2 hover:bg-white/5">Coverage</a>
            <div className="mt-1 grid grid-cols-2 gap-2">
              <a href={CONTACT.phoneHref} className="rounded-lg bg-amber-400 px-3 py-2 text-center text-sm font-extrabold text-black">📞 Call Now</a>
              <a href={CONTACT.whatsapp} target="_blank" rel="noreferrer" className="rounded-lg border border-emerald-400/50 px-3 py-2 text-center text-sm font-bold text-emerald-300">💬 WhatsApp</a>
            </div>
            <button onClick={() => { setOpen(false); onBook(); }} className="rounded-lg border border-white/15 px-3 py-2 text-sm font-bold">🤖 Try AI Diagnosis — Free</button>
          </div>
        </nav>
      )}
    </header>
  );
}

export function StickyBar() {
  return (
    <div className="fixed inset-x-0 bottom-0 z-40 border-t border-white/10 bg-black/90 backdrop-blur md:hidden">
      <div className="grid grid-cols-3 gap-1 p-2 text-center text-xs font-bold">
        <a href={CONTACT.phoneHref} className="rounded-lg bg-amber-400 px-2 py-2.5 text-black">📞 Call Now</a>
        <a href={CONTACT.whatsapp} target="_blank" rel="noreferrer" className="rounded-lg border border-emerald-400/50 px-2 py-2.5 text-emerald-300">💬 WhatsApp</a>
        <a href="#diagnosis" className="rounded-lg border border-white/15 px-2 py-2.5 text-white">🤖 AI Help</a>
      </div>
    </div>
  );
}

export function Hero({ onDiagnose }: { onDiagnose: () => void }) {
  return (
    <section className="mx-auto max-w-6xl px-4 pb-10 pt-10 md:pt-16">
      <p className="mb-3 inline-flex items-center gap-2 rounded-full border border-emerald-400/40 bg-emerald-400/10 px-3 py-1 text-xs font-bold text-emerald-300">
        <span aria-hidden="true">●</span> Live Now · Delhi NCR · 24×7
      </p>
      <h1 className="max-w-3xl text-3xl font-extrabold leading-tight tracking-tight text-white md:text-5xl">
        गाड़ी खराब, मेकैनिक तैयार — <span className="text-amber-300">Car broken, mechanic ready.</span>
      </h1>
      <p className="mt-3 max-w-2xl text-base text-neutral-300 md:text-lg">
        Your car deserves expert care, not a gamble. 20-minute roadside assistance, AI-led diagnosis you approve, and transparent bills. Pay only after you're satisfied.
      </p>
      <div className="mt-5 flex flex-col gap-2 sm:flex-row">
        <button onClick={onDiagnose} className="rounded-xl bg-amber-400 px-5 py-3 text-base font-extrabold text-black hover:bg-amber-300">🤖 Try AI Diagnosis — Free</button>
        <a href={CONTACT.phoneHref} className="rounded-xl border border-amber-400/50 px-5 py-3 text-center text-base font-extrabold text-amber-300 hover:bg-amber-400/10">📞 Call {CONTACT.phoneDisplay}</a>
      </div>
      <dl className="mt-8 grid grid-cols-2 gap-2 md:grid-cols-4">
        {[['30,000+', 'Cars serviced*'], ['4.9★', 'Google rating*'], ['20 min', 'Response SLA*'], ['24×7', 'Always on']].map(([v, l]) => (
          <div key={l} className="glass rounded-xl p-4 text-center">
            <dt className="order-2 mt-1 block text-xs text-neutral-400">{l}</dt>
            <dd className="text-2xl font-extrabold tabular-nums text-white">{v}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-2 text-[11px] text-neutral-500">*Figures as claimed by the business; independently unverified. We show them as business claims, not verified facts.</p>
    </section>
  );
}

export function Pillars() {
  const items = [
    { n: '01', t: 'The Core: 20-min mechanic anywhere', d: 'On-board parts and instant dispatch across Delhi NCR corridors. One tap — call or WhatsApp your live location.' },
    { n: '02', t: 'The Guarantee: 24×7 availability', d: '365 days, including nights and highways. Stranded at midnight on NH-48? We stay on the line till help arrives.' },
    { n: '03', t: 'The Standard: trusted garage, transparent bills', d: 'KYC-verified mechanics, AI diagnosis-led estimates, and bill approval before you pay. No roadside scams.' },
  ];
  return (
    <section className="mx-auto max-w-6xl px-4 py-8" aria-labelledby="pillars-h">
      <h2 id="pillars-h" className="text-xl font-extrabold text-white md:text-2xl">Operating system for car ownership</h2>
      <div className="mt-4 grid gap-3 md:grid-cols-3">
        {items.map((i) => (
          <article key={i.n} className="glass rounded-2xl p-5">
            <p className="text-xs font-bold text-amber-300">{i.n}</p>
            <h3 className="mt-1 font-bold text-white">{i.t}</h3>
            <p className="mt-2 text-sm text-neutral-300">{i.d}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

export function RSAGrid() {
  const services = [
    { icon: '⚡', t: 'Battery Jumpstart', d: 'Dead battery? On-spot jumpstart and battery health check.' },
    { icon: '🛞', t: 'Flat Tyre', d: 'Puncture and stepney change at your location — stay clear of traffic.' },
    { icon: '🚛', t: 'Towing', d: 'Safe flatbed towing for breakdowns, overheating and accidents.' },
    { icon: '⛽', t: 'Fuel Delivery', d: 'Out of fuel? We deliver petrol/diesel to your safe parking spot.' },
    { icon: '🔑', t: 'Key Lockout', d: 'Locked out or lost keys? Non-destructive entry assistance.' },
  ];
  return (
    <section id="services" className="mx-auto max-w-6xl scroll-mt-24 px-4 py-8" aria-labelledby="rsa-h">
      <h2 id="rsa-h" className="text-xl font-extrabold text-white md:text-2xl">On-demand roadside assistance</h2>
      <p className="mt-1 text-sm text-neutral-400">Tap to call — no long forms when you're stranded.</p>
      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {services.map((s) => (
          <article key={s.t} className="glass rounded-2xl p-4">
            <p className="text-2xl" aria-hidden="true">{s.icon}</p>
            <h3 className="mt-2 font-bold text-white">{s.t}</h3>
            <p className="mt-1 text-sm text-neutral-300">{s.d}</p>
          </article>
        ))}
      </div>
      <a href={CONTACT.phoneHref} className="mt-4 inline-block rounded-xl bg-amber-400 px-5 py-3 font-extrabold text-black hover:bg-amber-300">Call for Help Now — {CONTACT.phoneDisplay}</a>
    </section>
  );
}

export function Membership() {
  return (
    <section id="membership" className="mx-auto max-w-6xl scroll-mt-24 px-4 py-8" aria-labelledby="mem-h">
      <div className="glass rounded-2xl p-6 md:p-8">
        <p className="inline-block rounded-full bg-amber-400 px-3 py-1 text-xs font-extrabold text-black">✦ Best Value</p>
        <h2 id="mem-h" className="mt-2 text-xl font-extrabold text-white md:text-2xl">Annual Car Care Membership — ₹1,599/year</h2>
        <p className="mt-1 text-sm text-neutral-300">That's just ~₹125/month. Priority help, free inspection, and repair discounts.</p>
        <ul className="mt-4 grid gap-2 text-sm text-neutral-200 md:grid-cols-2">
          {['Unlimited emergency call-outs (service charges apply per visit)', 'Priority queue jump in peak hours', '1 free 40-point inspection', '20% garage repair discount', 'Digital service logbook'].map((x) => (
            <li key={x} className="flex gap-2"><span aria-hidden="true" className="text-emerald-300">✓</span><span>{x}</span></li>
          ))}
        </ul>
        <div className="mt-4 flex flex-col gap-2 sm:flex-row">
          <a href={CONTACT.whatsapp} target="_blank" rel="noreferrer" className="rounded-xl bg-amber-400 px-5 py-3 text-center font-extrabold text-black hover:bg-amber-300">Become a Member on WhatsApp</a>
          <a href={CONTACT.phoneHref} className="rounded-xl border border-white/15 px-5 py-3 text-center font-bold text-white">Ask about Membership</a>
        </div>
      </div>
    </section>
  );
}

export function Steps() {
  const steps = [
    ['📱', 'Call or WhatsApp', CONTACT.phoneDisplay],
    ['📍', 'Share live location', 'Anywhere in Delhi NCR'],
    ['🏎️', 'Verified mechanic dispatched', 'Live tracking on WhatsApp'],
    ['✅', 'On-spot fix & pay after satisfied', 'UPI · Card · Cash'],
  ];
  return (
    <section className="mx-auto max-w-6xl px-4 py-8" aria-labelledby="steps-h">
      <h2 id="steps-h" className="text-xl font-extrabold text-white md:text-2xl">How it works — 4 steps</h2>
      <ol className="mt-4 grid gap-3 md:grid-cols-4">
        {steps.map(([icon, t, d], i) => (
          <li key={t} className="glass rounded-2xl p-4">
            <p aria-hidden="true" className="text-2xl">{icon}</p>
            <p className="mt-1 text-xs font-bold text-amber-300">Step 0{i + 1}</p>
            <h3 className="font-bold text-white">{t}</h3>
            <p className="text-sm text-neutral-300">{d}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}

export function Trust() {
  const quotes = [
    ['Gurugram', 'Night towing on NH-48 was quick and the bill matched the estimate.'],
    ['Noida', 'Battery died near Vatika Business Park — jumpstart in about 20 minutes.'],
    ['Faridabad', 'Flat tyre fixed on the spot. Mechanic shared ID on WhatsApp first.'],
    ['Delhi', 'As a solo driver at night, KYC verification and live tracking helped me feel safe.'],
    ['Ghaziabad', 'Post-accident towing with zero bill shock. Approved everything on phone.'],
    ['DLF Phase 2', 'Annual member — one inspection plus a discount already covered the fee.'],
  ];
  return (
    <section className="mx-auto max-w-6xl px-4 py-8" aria-labelledby="trust-h">
      <h2 id="trust-h" className="text-xl font-extrabold text-white md:text-2xl">Trust &amp; verification</h2>
      <p className="mt-1 text-sm text-neutral-400">KYC-verified technicians · OTP handover · Pay after satisfied · Reviews shown as customer accounts, not independently verified.</p>
      <div className="mt-4 grid gap-3 md:grid-cols-3">
        {quotes.map(([place, q]) => (
          <figure key={place} className="glass rounded-2xl p-4">
            <blockquote className="text-sm text-neutral-200">“{q}”</blockquote>
            <figcaption className="mt-2 text-xs font-bold text-amber-300">— {place}</figcaption>
          </figure>
        ))}
      </div>
    </section>
  );
}

export function Coverage() {
  const areas = ['Gurugram', 'Delhi', 'Noida', 'Faridabad', 'Ghaziabad', 'Greater Noida', 'Manesar', 'Dwarka', 'Rohini', 'NH-48 / NH-8', 'DND Corridor', 'Indirapuram'];
  return (
    <section id="coverage" className="mx-auto max-w-6xl scroll-mt-24 px-4 py-8" aria-labelledby="cov-h">
      <h2 id="cov-h" className="text-xl font-extrabold text-white md:text-2xl">Service coverage</h2>
      <p className="mt-1 text-sm text-neutral-400">Active across Delhi NCR. Expanding to more Indian cities — city list below is current coverage, not a launch promise.</p>
      <ul className="mt-3 flex flex-wrap gap-2">
        {areas.map((a) => (
          <li key={a} className="rounded-full border border-white/15 bg-white/5 px-3 py-1.5 text-sm text-neutral-200">{a}</li>
        ))}
      </ul>
    </section>
  );
}

export function FinalCTA({ onDiagnose }: { onDiagnose: () => void }) {
  return (
    <section className="mx-auto max-w-6xl px-4 py-10" aria-labelledby="cta-h">
      <div className="rounded-2xl border border-amber-400/30 bg-gradient-to-br from-amber-400/15 to-transparent p-6 text-center md:p-10">
        <h2 id="cta-h" className="text-2xl font-extrabold text-white">Stranded right now? Get help in one tap.</h2>
        <p className="mx-auto mt-2 max-w-xl text-sm text-neutral-300">AI recommends, mechanic executes, you approve. Emergency actions stay visible even inside the chatbot.</p>
        <div className="mt-5 flex flex-col justify-center gap-2 sm:flex-row">
          <a href={CONTACT.phoneHref} className="rounded-xl bg-amber-400 px-6 py-3 font-extrabold text-black hover:bg-amber-300">📞 Call Now</a>
          <a href={CONTACT.whatsapp} target="_blank" rel="noreferrer" className="rounded-xl border border-emerald-400/50 px-6 py-3 font-bold text-emerald-300">💬 WhatsApp Us</a>
          <button onClick={onDiagnose} className="rounded-xl border border-white/20 px-6 py-3 font-bold text-white">🤖 AI Diagnosis</button>
        </div>
      </div>
    </section>
  );
}

export function Footer({ go }: { go: (p: Page) => void }) {
  const year = new Date().getFullYear();
  return (
    <footer className="border-t border-white/10 bg-black pb-24 pt-8 md:pb-8">
      <div className="mx-auto grid max-w-6xl gap-6 px-4 md:grid-cols-4">
        <div>
          <p className="font-extrabold text-white">Instant Mechanic</p>
          <p className="mt-1 text-sm text-neutral-400">India's Car Care Platform</p>
          <p className="mt-2 text-sm text-neutral-400">{CONTACT.address}</p>
        </div>
        <div>
          <p className="text-sm font-bold text-white">Contact</p>
          <ul className="mt-2 space-y-1 text-sm">
            <li><a className="text-amber-300 hover:underline" href={CONTACT.phoneHref}>{CONTACT.phoneDisplay}</a></li>
            <li><a className="text-emerald-300 hover:underline" href={CONTACT.whatsapp} target="_blank" rel="noreferrer">WhatsApp us</a></li>
            <li><a className="text-neutral-300 hover:underline" href={`mailto:${CONTACT.email}`}>{CONTACT.email}</a></li>
          </ul>
        </div>
        <div>
          <p className="text-sm font-bold text-white">Explore</p>
          <ul className="mt-2 space-y-1 text-sm text-neutral-300">
            <li><a href="#services" className="hover:underline">Roadside assistance</a></li>
            <li><a href="#diagnosis" className="hover:underline">AI diagnosis</a></li>
            <li><a href="#membership" className="hover:underline">Membership</a></li>
            <li><a href="#coverage" className="hover:underline">Coverage</a></li>
          </ul>
        </div>
        <div>
          <p className="text-sm font-bold text-white">Legal</p>
          <ul className="mt-2 space-y-1 text-sm text-neutral-300">
            <li><button className="hover:underline" onClick={() => go('privacy')}>Privacy Policy</button></li>
            <li><button className="hover:underline" onClick={() => go('terms')}>Terms &amp; Conditions</button></li>
            <li><button className="hover:underline" onClick={() => go('refund')}>Cancellation &amp; Refund</button></li>
          </ul>
        </div>
      </div>
      <p className="mx-auto mt-6 max-w-6xl px-4 text-xs text-neutral-500">© {year} Instant Mechanic. All rights reserved. Business-claimed metrics are shown as claims pending verification.</p>
    </footer>
  );
}

export function Legal({ page, go }: { page: Page; go: (p: Page) => void }) {
  useEffect(() => { window.scrollTo(0, 0); }, [page]);
  const wrap = (title: string, body: React.ReactNode) => (
    <main className="mx-auto max-w-3xl px-4 py-10">
      <button onClick={() => go('home')} className="mb-4 rounded-lg border border-white/15 px-3 py-2 text-sm font-bold">← Back to home</button>
      <h1 className="text-2xl font-extrabold text-white">{title}</h1>
      <div className="prose-sm mt-4 space-y-3 text-sm leading-relaxed text-neutral-300">{body}</div>
      <p className="mt-6 rounded-xl border border-amber-400/30 bg-amber-400/10 p-3 text-xs text-amber-200">Legal draft for owner review — not a substitute for counsel. Contact {CONTACT.email} for corrections.</p>
    </main>
  );
  if (page === 'privacy') return wrap('Privacy Policy', <>
    <p>We collect only what roadside help needs: your phone number, location you share, vehicle details, chat messages and uploaded media for diagnosis.</p>
    <p>We do not sell personal data. Media is used for service delivery and stored securely. No advertising trackers are loaded by default.</p>
    <p>Contact <a className="text-amber-300" href={`mailto:${CONTACT.email}`}>{CONTACT.email}</a> to request access or deletion.</p>
  </>);
  if (page === 'terms') return wrap('Terms & Conditions', <>
    <p>AI diagnosis is a preliminary remote assessment, not a confirmed mechanical inspection. Always follow safety guidance and approve work before it begins.</p>
    <p>Roadside services are billed on-spot after your approval. Pay only after satisfied via UPI, card or cash.</p>
    <p>Liability is limited to the service amount paid. Unsafe situations (fire, fuel leak, brake failure) require stopping safely and calling {CONTACT.phoneDisplay}.</p>
  </>);
  if (page === 'refund') return wrap('Cancellation & Refund', <>
    <p>Cancel free before a mechanic is dispatched. After dispatch, visit charges may apply and will be told upfront.</p>
    <p>Unsatisfactory work: tell us within 24 hours at <a className="text-amber-300" href={`mailto:${CONTACT.email}`}>{CONTACT.email}</a> with your booking ID for re-check or refund review.</p>
  </>);
  return (
    <main className="mx-auto max-w-xl px-4 py-20 text-center">
      <h1 className="text-4xl font-extrabold text-white">404</h1>
      <p className="mt-2 text-neutral-300">That page isn't here. Get roadside help or go home.</p>
      <div className="mt-4 flex justify-center gap-2">
        <button onClick={() => go('home')} className="rounded-xl bg-amber-400 px-5 py-3 font-extrabold text-black">Go home</button>
        <a href={CONTACT.phoneHref} className="rounded-xl border border-amber-400/50 px-5 py-3 font-bold text-amber-300">📞 Call now</a>
      </div>
    </main>
  );
}

export function CookieBanner() {
  const [show, setShow] = useState(false);
  useEffect(() => {
    try {
      if (!localStorage.getItem('im-cookie')) setShow(true);
    } catch { setShow(true); }
  }, []);
  if (!show) return null;
  return (
    <div role="dialog" aria-label="Cookie consent" className="fixed inset-x-3 bottom-16 z-50 mx-auto max-w-2xl rounded-2xl border border-white/15 bg-neutral-900 p-4 shadow-2xl md:bottom-6">
      <p className="text-sm text-neutral-200"><strong className="text-white">Cookies:</strong> we use only essential storage (chat session + your consent choice). No advertising trackers.</p>
      <div className="mt-3 flex gap-2">
        <button onClick={() => { try { localStorage.setItem('im-cookie', 'ok'); } catch { /* noop */ } setShow(false); }} className="rounded-lg bg-amber-400 px-4 py-2 text-sm font-extrabold text-black">Accept essential</button>
        <button onClick={() => { try { localStorage.setItem('im-cookie', 'no'); } catch { /* noop */ } setShow(false); }} className="rounded-lg border border-white/15 px-4 py-2 text-sm font-bold text-white">Decline</button>
      </div>
    </div>
  );
}
