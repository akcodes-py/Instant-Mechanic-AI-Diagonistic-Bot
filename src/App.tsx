import { useState } from 'react';
import Chatbot from './components/Chatbot';
import { CookieBanner, Coverage, FinalCTA, Footer, Header, Hero, Membership, Pillars, RSAGrid, Steps, Trust, Legal, StickyBar, Page } from './components/Site';

export default function App() {
  const [page, setPage] = useState<Page>('home');
  const [chatOpen, setChatOpen] = useState(false);

  const go = (p: Page) => {
    setPage(p);
    window.scrollTo(0, 0);
  };

  if (page !== 'home') {
    return (
      <div className="min-h-screen bg-neutral-950">
        <Header go={go} onBook={() => { go('home'); setTimeout(() => setChatOpen(true), 50); }} />
        <Legal page={page} go={go} />
        <Footer go={go} />
        <CookieBanner />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-neutral-950">
      <Header go={go} onBook={() => setChatOpen(true)} />
      <main>
        <Hero onDiagnose={() => setChatOpen(true)} />
        <Pillars />
        <RSAGrid />
        <section id="diagnosis" className="mx-auto max-w-6xl scroll-mt-24 px-4 py-8" aria-labelledby="buddy-h">
          <div className="glass rounded-2xl p-6 md:p-10">
            <div className="flex flex-col gap-6 md:flex-row md:items-start">
              <div className="flex-1">
                <p className="inline-block rounded-full bg-amber-400/15 border border-amber-400/40 px-3 py-1 text-xs font-bold text-amber-300">🤖 Free to use · No signup</p>
                <h2 id="buddy-h" className="mt-2 text-xl font-extrabold text-white md:text-2xl">IM Buddy — AI Car Diagnosis</h2>
                <p className="mt-1 text-sm text-neutral-400">Describe your car problem in plain language. Our AI identifies the issue, gives drive/don't-drive guidance, and connects you to a mechanic in minutes.</p>
                <ul className="mt-4 space-y-2 text-sm text-neutral-300">
                  <li className="flex items-start gap-2"><span className="mt-0.5 text-amber-300">①</span><span><strong className="text-white">Chat</strong> — describe symptoms (sound, smell, warning light, situation)</span></li>
                  <li className="flex items-start gap-2"><span className="mt-0.5 text-amber-300">②</span><span><strong className="text-white">Diagnose</strong> — AI returns possible causes + urgency level</span></li>
                  <li className="flex items-start gap-2"><span className="mt-0.5 text-amber-300">③</span><span><strong className="text-white">Book</strong> — mechanic dispatched to your location in ≈20 min</span></li>
                </ul>
                <div className="mt-4 flex flex-wrap gap-2">
                  {['🔋 Dead battery', '🌡️ Overheating', '🛞 Flat tyre', '🔊 Brake noise', '⛽ Out of fuel', '🔑 Car lockout'].map((s) => (
                    <span key={s} className="rounded-full border border-white/15 bg-white/5 px-3 py-1 text-xs text-neutral-300">{s}</span>
                  ))}
                </div>
                <button onClick={() => setChatOpen(true)} className="mt-5 rounded-xl bg-amber-400 px-5 py-3 font-extrabold text-black hover:bg-amber-300 transition-colors">Start AI Diagnosis — Free</button>
              </div>
              <div className="hidden md:block md:w-56 shrink-0">
                <div className="rounded-2xl border border-white/10 bg-black/60 p-4 text-sm space-y-3">
                  <p className="text-xs font-bold text-neutral-400 uppercase tracking-wide">Quick example</p>
                  <div className="rounded-xl bg-amber-400 px-3 py-2 text-xs font-bold text-black ml-4">"Swift won't start, rapid clicking"</div>
                  <div className="rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs text-neutral-200">🔋 Likely dead battery or starter issue. Do your dashboard lights come on?</div>
                  <div className="rounded-xl border border-amber-400/30 bg-amber-400/5 px-3 py-2 text-xs text-neutral-200">⚡ Diagnosis: Battery system fault — <span className="font-bold text-amber-300">medium urgency</span></div>
                </div>
              </div>
            </div>
          </div>
        </section>
        <Membership />
        <Steps />
        <Trust />
        <Coverage />
        <FinalCTA onDiagnose={() => setChatOpen(true)} />
      </main>
      <Footer go={go} />
      <StickyBar />
      <CookieBanner />
      <Chatbot open={chatOpen} onClose={() => setChatOpen(false)} />
    </div>
  );
}
