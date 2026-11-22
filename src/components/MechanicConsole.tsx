import { useEffect, useRef, useState } from 'react';
import { cellToBoundary, latLngToCell } from 'h3-js';
import { dispatchApi, type OfferResult } from '../dispatchApi';
import { cascade, center, zoneFor } from '../spatial';
import { CONTACT } from '../api';

/** One synthetic demo zone in Delhi NCR: Sector 75, Gurugram. No real PII. */
const CENTER: [number, number] = [28.4595, 77.0266];
const SKILLS = ['battery_jumpstart', 'tyre_puncture', 'engine_overheat', 'towing'];
const OFFSETS: Array<[number, number]> = [
  [0.0007, 0.0009], [-0.0008, 0.0006], [0.0014, -0.0007],
  [-0.0016, -0.0011], [0.0003, 0.0018], [-0.0012, 0.0015],
];

interface SimMechanic {
  id: string;
  lat: number;
  lon: number;
  skills: string[];
  online: boolean;
  cell: string;
}

function makeMechanics(): SimMechanic[] {
  return OFFSETS.map(([dLat, dLon], index) => {
    const lat = CENTER[0] + dLat;
    const lon = CENTER[1] + dLon;
    return {
      id: crypto.randomUUID(),
      lat,
      lon,
      skills: [SKILLS[index % SKILLS.length]],
      online: true,
      cell: latLngToCell(lat, lon, 8),
    };
  });
}

const PX = 14000;
const project = (lat: number, lon: number): [number, number] => [
  300 + (lon - CENTER[1]) * PX,
  240 - (lat - CENTER[0]) * PX,
];

export default function MechanicConsole({ goHome }: { goHome: () => void }) {
  const [mechanics, setMechanics] = useState<SimMechanic[]>(makeMechanics);
  const [bookingId] = useState(() => crypto.randomUUID());
  const [skill, setSkill] = useState(SKILLS[0]);
  const [urgency, setUrgency] = useState('high');
  const [offer, setOffer] = useState<OfferResult | null>(null);
  const [status, setStatus] = useState('IDLE');
  const [feed, setFeed] = useState<string[]>([]);
  const [error, setError] = useState('');
  const [connected, setConnected] = useState(false);
  const mechanicsRef = useRef(mechanics);
  useEffect(() => { mechanicsRef.current = mechanics; }, [mechanics]);

  const log = (message: string) => setFeed((prev) => [message, ...prev].slice(0, 12));

  useEffect(() => {
    const ping = () => {
      mechanicsRef.current.filter((m) => m.online).forEach((m) => {
        void dispatchApi.telemetry(m.id, m.lat, m.lon, m.skills).catch(() => undefined);
      });
    };
    ping();
    const timer = window.setInterval(ping, 5000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const socket = dispatchApi.subscribe(bookingId, (payload) => log(`WS ${payload.slice(0, 110)}…`));
    socket.onopen = () => setConnected(true);
    socket.onclose = () => setConnected(false);
    return () => socket.close();
  }, [bookingId]);

  const runDispatch = async () => {
    setError('');
    try {
      await dispatchApi.createBooking(bookingId, CENTER[0], CENTER[1], skill, urgency);
      const result = await dispatchApi.dispatch(bookingId);
      setOffer(result);
      setStatus(result.status);
      log(result.status === 'OFFERED' ? `Offer sent to ${result.mechanic_id} (ring ${result.ring}, ETA ${result.eta_seconds}s)` : 'No mechanic accepted — hotline escalation');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Dispatch failed');
    }
  };

  const accept = async () => {
    if (!offer?.offer_id) return;
    try {
      await dispatchApi.accept(offer.offer_id, String(offer.mechanic_id));
      setStatus('ASSIGNED');
      log('Offer accepted — mechanic assigned');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Accept failed');
    }
  };

  const decline = async () => {
    if (!offer?.offer_id) return;
    try {
      await dispatchApi.reject(offer.offer_id, String(offer.mechanic_id));
      setOffer(null);
      setStatus('SEARCHING');
      log('Offer declined — cascade will continue');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Decline failed');
    }
  };

  const advance = async (to: string) => {
    try {
      const result = await dispatchApi.advance(bookingId, to);
      setStatus(result.status);
      log(`Job status → ${result.status}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Status update failed');
    }
  };

  const origin = latLngToCell(CENTER[0], CENTER[1], 8);
  const hexes = cascade(origin, 3);
  const [zoneLat, zoneLon] = center(zoneFor(origin));

  return (
    <div className="min-h-screen bg-neutral-950 px-4 py-6 text-white">
      <div className="mx-auto max-w-6xl space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-extrabold">Mechanic Dispatch Simulator</h1>
            <p className="text-sm text-neutral-400">
              H3 Res-8 supply · Res-7 zone <span className="font-mono text-amber-300">{zoneFor(origin)}</span> ·
              centre {zoneLat.toFixed(4)}, {zoneLon.toFixed(4)}
            </p>
          </div>
          <button onClick={goHome} className="rounded-lg border border-white/15 px-3 py-2 text-sm font-bold">← Back to site</button>
        </div>

        <div className="grid gap-5 md:grid-cols-2">
          <section className="glass rounded-2xl p-4" aria-label="H3 supply map">
            <h2 className="mb-2 text-sm font-bold uppercase tracking-wide text-neutral-400">Live H3 hex supply</h2>
            <svg viewBox="0 0 600 480" className="w-full rounded-xl border border-white/10 bg-black/60" role="img" aria-label="H3 hexagonal rings around the breakdown">
              {hexes.map(([ring, cells]) => cells.map((cell) => {
                const points = cellToBoundary(cell).map(([lat, lon]) => project(lat, lon).join(',')).join(' ');
                return <polygon key={cell} points={points} fill={ring === 1 ? '#f59e0b22' : ring === 2 ? '#38bdf811' : '#ffffff08'} stroke={ring === 1 ? '#f59e0b' : '#ffffff30'} strokeWidth="1" />;
              }))}
              {mechanics.map((m) => {
                const [x, y] = project(m.lat, m.lon);
                return <circle key={m.id} cx={x} cy={y} r="6" fill={m.online ? '#34d399' : '#6b7280'} stroke="#000" strokeWidth="2"><title>{m.skills[0]}</title></circle>;
              })}
            </svg>
            <div className="mt-3 flex flex-wrap gap-2">
              {mechanics.map((m, index) => (
                <button key={m.id} onClick={() => setMechanics((prev) => prev.map((item, i) => i === index ? { ...item, online: !item.online } : item))}
                  className={`rounded-lg border px-2 py-1 text-xs font-bold ${m.online ? 'border-emerald-400/50 bg-emerald-400/10 text-emerald-300' : 'border-white/15 text-neutral-400'}`}>
                  M{index + 1} · {m.skills[0]}
                </button>
              ))}
            </div>
          </section>

          <section className="glass rounded-2xl p-4" aria-label="Dispatch controls">
            <h2 className="mb-3 text-sm font-bold uppercase tracking-wide text-neutral-400">Breakdown &amp; offer cascade</h2>
            <div className="grid gap-3 text-sm">
              <label className="grid gap-1">Required skill
                <select value={skill} onChange={(e) => setSkill(e.target.value)} className="rounded-lg border border-white/15 bg-neutral-900 px-3 py-2">
                  {SKILLS.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </label>
              <label className="grid gap-1">Urgency
                <select value={urgency} onChange={(e) => setUrgency(e.target.value)} className="rounded-lg border border-white/15 bg-neutral-900 px-3 py-2">
                  {['low', 'medium', 'high', 'critical'].map((u) => <option key={u} value={u}>{u}</option>)}
                </select>
              </label>
              <p className="font-mono text-xs break-all text-neutral-500">booking {bookingId}</p>
              <button onClick={runDispatch} className="rounded-xl bg-amber-400 px-4 py-3 font-extrabold text-black hover:bg-amber-300">Find nearest mechanic</button>
              {offer?.status === 'OFFERED' && (
                <div className="grid gap-2 rounded-xl border border-amber-400/40 bg-amber-400/5 p-3" role="status">
                  <p>Offer <span className="font-mono">{offer.offer_id}</span></p>
                  <p className="text-xs text-neutral-400">ETA {offer.eta_seconds}s · ring {offer.ring}</p>
                  <div className="flex gap-2">
                    <button onClick={accept} className="rounded-lg bg-emerald-500 px-4 py-2 font-bold text-black">Accept</button>
                    <button onClick={decline} className="rounded-lg border border-white/20 px-4 py-2 font-bold">Decline</button>
                  </div>
                </div>
              )}
              {offer?.status === 'ESCALATED' && (
                <div className="rounded-xl border border-red-500/50 bg-red-500/10 p-3" role="alert">
                  No mechanic accepted within the cascade window. Call <a className="font-bold underline" href={CONTACT.phoneHref}>{CONTACT.phoneDisplay}</a>.
                </div>
              )}
              <div className="flex flex-wrap gap-2">
                {['EN_ROUTE', 'ARRIVED', 'IN_REPAIR', 'COMPLETED'].map((next) => (
                  <button key={next} onClick={() => advance(next)} disabled={status !== 'ASSIGNED' && status !== 'EN_ROUTE' && status !== 'ARRIVED' && status !== 'IN_REPAIR'}
                    className="rounded-lg border border-white/15 px-3 py-2 text-xs font-bold disabled:opacity-40">{next}</button>
                ))}
              </div>
              <p className="text-sm">Status: <strong className="text-amber-300">{status}</strong> · WS {connected ? 'connected' : 'offline'}</p>
              {error && <p className="text-sm text-red-400" role="alert">{error}</p>}
              <ol className="mt-2 space-y-1 text-xs text-neutral-400" aria-live="polite">
                {feed.map((line, index) => <li key={`${index}-${line.slice(0, 12)}`}>• {line}</li>)}
              </ol>
            </div>
          </section>
        </div>
        <p className="text-xs text-neutral-500">
          Simulator only: synthetic mechanic locations, no real bookings, no fabricated analysis or ETAs. Telemetry pings every 5 s; a 60 s TTL removes stale supply.
        </p>
      </div>
    </div>
  );
}
