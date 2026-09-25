import { useEffect, useRef, useState } from 'react';
import { CONTACT, HistoryData, api, Diagnosis } from '../api';

interface Msg { role: 'user' | 'assistant'; content: string; ai?: boolean }

const URGENCY_STYLE: Record<string, string> = {
  low: 'bg-emerald-400/15 text-emerald-300 border-emerald-400/40',
  medium: 'bg-amber-400/15 text-amber-300 border-amber-400/40',
  high: 'bg-orange-400/15 text-orange-300 border-orange-400/40',
  critical: 'bg-red-500/15 text-red-300 border-red-500/50',
};

function Urgency({ level }: { level: string }) {
  return (
    <span aria-label={`Urgency: ${level}`} className={`inline-block rounded-full border px-3 py-1 text-xs font-extrabold uppercase tracking-wide ${URGENCY_STYLE[level] || URGENCY_STYLE.medium}`}>
      {level}
    </span>
  );
}

export default function Chatbot({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [session, setSession] = useState<string | null>(null);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [vehicle, setVehicle] = useState({ vehicle_make: '', vehicle_model: '', vehicle_year: '' });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [diag, setDiag] = useState<Diagnosis | null>(null);
  const [diagLoading, setDiagLoading] = useState(false);
  const [uploadPct, setUploadPct] = useState<number | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [showBooking, setShowBooking] = useState(false);
  const [booking, setBooking] = useState({ name: '', phone: '', service_type: 'general_repair', location: '', vehicle_details: '', notes: '', scheduled_at: '' });
  const [bookingDone, setBookingDone] = useState<string>('');
  const [bookingId, setBookingId] = useState<string>('');
  const [lookupId, setLookupId] = useState('');
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open) {
      try {
        const s = localStorage.getItem('im-session');
        if (s) {
          setSession(s);
          api.history(s).then((h: HistoryData) => {
            setMsgs(h.messages.map((m) => ({ role: m.role as 'user' | 'assistant', content: m.content })));
            if (h.diagnoses[0]) setDiag(h.diagnoses[0]);
          }).catch(() => {});
        }
      } catch { /* private mode */ }
    }
  }, [open ]);

  useEffect(() => { boxRef.current?.scrollTo({ top: boxRef.current.scrollHeight, behavior: 'smooth' }); }, [msgs, loading]);

  if (!open) return null;

  async function send(text?: string) {
    const message = (text ?? input).trim();
    if (!message || loading) return;
    setError(''); setSuccess('');
    setMsgs((m) => [...m, { role: 'user', content: message }]);
    setInput('');
    setLoading(true);
    try {
      const r = await api.chat(session, message, vehicle);
      setSession(r.session_id);
      try { localStorage.setItem('im-session', r.session_id); } catch { /* noop */ }
      setMsgs((m) => [...m, { role: 'assistant', content: r.reply, ai: r.ai_used }]);
      if (r.action === 'ready') setSuccess('I have enough detail — tap “Get diagnosis” when ready.');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong. Call +91 9266961110 for urgent help.');
    } finally { setLoading(false); }
  }

  async function getDiagnosis() {
    if (!session) { setError('Chat first so I know your symptoms, then request a diagnosis.'); return; }
    setDiagLoading(true); setError(''); setSuccess('');
    try {
      const d = await api.diagnose(session);
      setDiag(d);
      setMsgs((m) => [...m, { role: 'assistant', content: `Diagnosis ready: ${d.summary}`, ai: d.ai_used }]);
      setSuccess('Diagnosis saved. Review it below, then Book Mechanic if you want help.');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Diagnosis failed. Please add more detail and retry.');
    } finally { setDiagLoading(false); }
  }

  async function onFile(f: File | undefined) {
    if (!f) return;
    if (!session) { setError('Send one chat message first so I can link your file to the session.'); return; }
    setError(''); setUploadPct(0);
    if (f.type.startsWith('image/')) {
      const url = URL.createObjectURL(f);
      setPreview(url);
    } else setPreview(null);
    try {
      const r = await api.upload(session, f, setUploadPct);
      setMsgs((m) => [...m, { role: 'user', content: `[Uploaded ${r.kind} — ${f.name}]` }, { role: 'assistant', content: r.note }]);
      setSuccess('File received and linked to your session.');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Upload failed.');
    } finally { setUploadPct(null); }
  }

  async function submitBooking(e: React.FormEvent) {
    e.preventDefault();
    if (!booking.name.trim() || booking.name.trim().length < 2) { setError('Please enter your name.'); return; }
    if (!/^[6-9]\d{9}$/.test(booking.phone.replace(/\D/g, '').slice(-10))) { setError('Enter a valid 10-digit Indian mobile number.'); return; }
    if (booking.location.trim().length < 5) { setError('Please share a pickup location (min 5 characters).'); return; }
    setLoading(true); setError('');
    try {
      const b = await api.book({ session_id: session, diagnosis_id: diag?.id, ...booking, website: '' });
      setBookingDone(`Booking confirmed — ID ${b.id}. ${b.message || ''}`);
      setBookingId(b.id);
      setSuccess('Booking created successfully.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Booking failed.');
    } finally { setLoading(false); }
  }

  async function lookup() {
    if (!lookupId.trim()) { setError('Enter a booking ID to look up.'); return; }
    setError('');
    try {
      const b = await api.booking(lookupId.trim());
      setBookingDone(`Found booking ${b.id} — ${b.service_type}, ${b.status}, ${b.location}.`);
    } catch {
      setError('Booking not found. Check the ID and try again.');
    }
  }

  return (
    <div role="dialog" aria-modal="true" aria-label="IM Buddy AI car mechanic chatbot" className="fixed inset-0 z-50 flex items-end justify-center bg-black/70 p-0 sm:items-center sm:p-4">
      <div className="flex h-[94vh] w-full max-w-2xl flex-col overflow-hidden rounded-t-2xl border border-white/10 bg-neutral-950 sm:h-[85vh] sm:rounded-2xl">
        <div className="flex items-center justify-between gap-2 border-b border-white/10 bg-black px-4 py-3">
          <div>
            <p className="font-extrabold text-white">🤖 IM Buddy — AI Car Mechanic</p>
            <p className="text-xs text-neutral-400">Preliminary help only · Emergencies: <a className="font-bold text-amber-300" href={CONTACT.phoneHref}>{CONTACT.phoneDisplay}</a></p>
          </div>
          <button onClick={onClose} aria-label="Close chatbot" className="rounded-lg border border-white/15 px-3 py-2 text-sm font-bold text-white">✕</button>
        </div>

        <div className="grid grid-cols-2 gap-1 border-b border-white/10 bg-black/60 p-2 text-center text-xs font-bold sm:grid-cols-4">
          <a href={CONTACT.phoneHref} className="rounded-lg bg-amber-400 px-2 py-2 text-black">📞 Call</a>
          <a href={CONTACT.whatsapp} target="_blank" rel="noreferrer" className="rounded-lg border border-emerald-400/50 px-2 py-2 text-emerald-300">💬 WhatsApp</a>
          <button onClick={() => setShowBooking(true)} className="rounded-lg border border-white/15 px-2 py-2 text-white">🧰 Book</button>
          <button onClick={getDiagnosis} className="rounded-lg border border-white/15 px-2 py-2 text-white">🩺 Diagnose</button>
        </div>

        <div className="border-b border-white/10 p-3">
          <p className="mb-2 text-xs font-bold text-neutral-400">Vehicle (optional but helps — no long form required)</p>
          <div className="grid grid-cols-3 gap-2">
            <input aria-label="Vehicle make" value={vehicle.vehicle_make} onChange={(e) => setVehicle({ ...vehicle, vehicle_make: e.target.value })} placeholder="Make (Maruti)" className="rounded-lg border border-white/10 bg-white/5 px-2 py-2 text-sm text-white placeholder:text-neutral-500" />
            <input aria-label="Vehicle model" value={vehicle.vehicle_model} onChange={(e) => setVehicle({ ...vehicle, vehicle_model: e.target.value })} placeholder="Model (Swift)" className="rounded-lg border border-white/10 bg-white/5 px-2 py-2 text-sm text-white placeholder:text-neutral-500" />
            <input aria-label="Vehicle year" value={vehicle.vehicle_year} onChange={(e) => setVehicle({ ...vehicle, vehicle_year: e.target.value })} placeholder="Year" inputMode="numeric" className="rounded-lg border border-white/10 bg-white/5 px-2 py-2 text-sm text-white placeholder:text-neutral-500" />
          </div>
        </div>

        <div ref={boxRef} className="flex-1 space-y-2 overflow-y-auto p-3" aria-live="polite">
          {msgs.length === 0 && (
            <div className="rounded-xl border border-white/10 bg-white/5 p-3 text-sm text-neutral-300">
              <p className="font-bold text-white">Namaste! Describe your car problem to begin.</p>
              <p className="mt-1">Try: “Swift 2019 petrol won't start, clicking sound” or “steam from bonnet, temp gauge high”.</p>
              <div className="mt-2 flex flex-wrap gap-1">
                {["Won't start — clicking", 'Flat tyre on highway', 'Steam / overheating', 'Brake grinding noise'].map((s) => (
                  <button key={s} onClick={() => send(s)} className="rounded-full border border-amber-400/40 px-2 py-1 text-xs font-bold text-amber-300">{s}</button>
                ))}
              </div>
            </div>
          )}
          {msgs.map((m, i) => (
            <div key={i} className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm leading-relaxed ${m.role === 'user' ? 'ml-auto bg-amber-400 text-black' : 'bg-white/8 border border-white/10 text-neutral-100'}`}>
              <p>{m.content}</p>
              {m.ai && <p className="mt-1 text-[10px] opacity-70">AI-assisted</p>}
            </div>
          ))}
          {loading && <p className="text-sm text-neutral-400" aria-label="Loading">IM Buddy is typing…</p>}
          {preview && <img src={preview} alt="Preview of your uploaded image" className="h-24 rounded-lg border border-white/15 object-cover" />}
          {uploadPct !== null && <p className="text-xs text-neutral-300">Uploading… {uploadPct}%</p>}

          {diag && (
            <article className="rounded-2xl border border-amber-400/30 bg-amber-400/5 p-4" aria-label="Diagnosis result">
              <div className="flex items-center justify-between gap-2">
                <h3 className="font-extrabold text-white">Diagnosis</h3>
                <Urgency level={diag.urgency} />
              </div>
              <p className="mt-2 text-sm text-neutral-200">{diag.summary}</p>
              {diag.possible_causes?.length > 0 && (
                <><p className="mt-2 text-xs font-bold text-neutral-400">POSSIBLE CAUSES</p>
                <ul className="list-disc pl-5 text-sm text-neutral-200">{diag.possible_causes.map((c) => <li key={c}>{c}</li>)}</ul></>
              )}
              {diag.next_steps?.length > 0 && (
                <><p className="mt-2 text-xs font-bold text-neutral-400">RECOMMENDED NEXT STEPS</p>
                <ol className="list-decimal pl-5 text-sm text-neutral-200">{diag.next_steps.map((s) => <li key={s}>{s}</li>)}</ol></>
              )}
              <p className="mt-2 text-sm"><span className="font-bold text-white">Service: </span><span className="text-amber-300">{diag.recommended_service.replace(/_/g, ' ')}</span></p>
              {diag.drive_guidance && <p className="mt-1 text-sm text-neutral-200"><strong>Drive guidance:</strong> {diag.drive_guidance}</p>}
              {diag.safety_warning && <p className="mt-1 rounded-lg border border-red-500/40 bg-red-500/10 p-2 text-sm text-red-200"><strong>Safety:</strong> {diag.safety_warning}</p>}
              <p className="mt-1 text-xs text-neutral-400">{diag.disclaimer || 'Preliminary remote assessment — not a confirmed inspection.'}</p>
              <div className="mt-3 flex flex-col gap-2 sm:flex-row">
                <button onClick={() => setShowBooking(true)} className="rounded-xl bg-amber-400 px-4 py-2.5 font-extrabold text-black">🧰 Book Mechanic</button>
                <a href={CONTACT.phoneHref} className="rounded-xl border border-amber-400/50 px-4 py-2.5 text-center font-bold text-amber-300">📞 Call instead</a>
              </div>
            </article>
          )}

          {showBooking && (
            <form onSubmit={submitBooking} className="rounded-2xl border border-white/10 bg-white/5 p-4" aria-label="Book mechanic form">
              <h3 className="font-extrabold text-white">Book Mechanic</h3>
              <div className="mt-2 grid gap-2">
                <input aria-label="Your name" value={booking.name} onChange={(e) => setBooking({ ...booking, name: e.target.value })} placeholder="Full name" className="rounded-lg border border-white/10 bg-black px-3 py-2 text-sm text-white" required minLength={2} />
                <input aria-label="Phone number" value={booking.phone} onChange={(e) => setBooking({ ...booking, phone: e.target.value })} placeholder="10-digit mobile" inputMode="tel" className="rounded-lg border border-white/10 bg-black px-3 py-2 text-sm text-white" required />
                <select aria-label="Service type" value={booking.service_type} onChange={(e) => setBooking({ ...booking, service_type: e.target.value })} className="rounded-lg border border-white/10 bg-black px-3 py-2 text-sm text-white">
                  <option value="battery_jumpstart">Battery jumpstart</option>
                  <option value="flat_tyre">Flat tyre</option>
                  <option value="towing">Towing</option>
                  <option value="fuel_delivery">Fuel delivery</option>
                  <option value="key_lockout">Key lockout</option>
                  <option value="general_repair">General repair</option>
                  <option value="inspection">Inspection</option>
                </select>
                <input aria-label="Pickup location" value={booking.location} onChange={(e) => setBooking({ ...booking, location: e.target.value })} placeholder="Pickup location / landmark" className="rounded-lg border border-white/10 bg-black px-3 py-2 text-sm text-white" required minLength={5} />
                <input aria-label="Vehicle details" value={booking.vehicle_details} onChange={(e) => setBooking({ ...booking, vehicle_details: e.target.value })} placeholder="Vehicle (e.g. Swift 2019 petrol)" className="rounded-lg border border-white/10 bg-black px-3 py-2 text-sm text-white" />
                <div>
                  <label htmlFor="scheduled_at" className="mb-1 block text-xs font-bold text-neutral-400">Preferred date & time (optional)</label>
                  <input id="scheduled_at" type="datetime-local" aria-label="Preferred appointment date and time" value={booking.scheduled_at} onChange={(e) => setBooking({ ...booking, scheduled_at: e.target.value })} min={new Date().toISOString().slice(0,16)} className="w-full rounded-lg border border-white/10 bg-black px-3 py-2 text-sm text-white [color-scheme:dark]" />
                </div>
                <input aria-label="Notes" value={booking.notes} onChange={(e) => setBooking({ ...booking, notes: e.target.value })} placeholder="Notes (optional)" className="rounded-lg border border-white/10 bg-black px-3 py-2 text-sm text-white" />
                <input type="text" name="website" tabIndex={-1} autoComplete="off" className="hidden" aria-hidden="true" />
              </div>
              <div className="mt-3 flex gap-2">
                <button type="submit" disabled={loading} className="rounded-xl bg-amber-400 px-4 py-2.5 font-extrabold text-black disabled:opacity-60">{loading ? 'Booking…' : 'Confirm booking'}</button>
                <button type="button" onClick={() => setShowBooking(false)} className="rounded-xl border border-white/15 px-4 py-2.5 text-white">Cancel</button>
              </div>
            </form>
          )}
          {bookingDone && <p role="status" className="rounded-xl border border-emerald-400/40 bg-emerald-400/10 p-3 text-sm text-emerald-200">{bookingDone}{bookingId && <span className="mt-1 block text-xs">Save this ID to retrieve your booking. Try lookup below.</span>}</p>}

          <div className="rounded-xl border border-white/10 bg-white/5 p-3">
            <p className="text-xs font-bold text-neutral-300">Retrieve a booking</p>
            <div className="mt-1 flex gap-2">
              <input aria-label="Booking ID" value={lookupId} onChange={(e) => setLookupId(e.target.value)} placeholder="Paste booking ID" className="flex-1 rounded-lg border border-white/10 bg-black px-2 py-2 text-sm text-white" />
              <button onClick={lookup} className="rounded-lg border border-white/15 px-3 py-2 text-sm font-bold text-white">Find</button>
            </div>
          </div>
        </div>

        {error && <p role="alert" className="border-t border-red-500/30 bg-red-500/10 px-4 py-2 text-sm text-red-200">{error}</p>}
        {success && <p role="status" className="border-t border-emerald-400/30 bg-emerald-400/10 px-4 py-2 text-sm text-emerald-200">{success}</p>}

        <div className="border-t border-white/10 bg-black p-3 pb-5">
          <div className="flex items-center gap-2">
            <label htmlFor="file" className="cursor-pointer rounded-lg border border-white/15 px-3 py-2.5 text-sm font-bold text-white" title="Upload image, audio or video">📎</label>
            <input id="file" type="file" className="hidden" accept="image/*,audio/*,video/*" onChange={(e) => onFile(e.target.files?.[0])} />
            <button onClick={getDiagnosis} disabled={diagLoading} className="rounded-lg border border-white/15 px-3 py-2.5 text-sm font-bold text-white disabled:opacity-60">{diagLoading ? '…' : '🩺'}</button>
            <input aria-label="Type your car problem" value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') send(); }} placeholder="Describe symptoms…" maxLength={2000} className="flex-1 rounded-lg border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white placeholder:text-neutral-500" />
            <button onClick={() => send()} disabled={loading} className="rounded-lg bg-amber-400 px-4 py-2.5 text-sm font-extrabold text-black disabled:opacity-60">Send</button>
          </div>
          <p className="mt-1 text-[11px] text-neutral-500">Images/audio/video attach to your session for the mechanic. Media content is stored, not auto-diagnosed by AI.</p>
        </div>
      </div>
    </div>
  );
}
