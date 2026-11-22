/** Typed client for the Kotlin dispatch service (ADR-001). No secrets in VITE_*. */
const BASE: string =
  (import.meta as unknown as { env: Record<string, string> }).env.VITE_DISPATCH_URL ||
  'http://127.0.0.1:8081';

export interface TelemetryAck { h3_res8: string; h3_res7: string }
export interface OfferResult {
  status: 'OFFERED' | 'ESCALATED';
  offer_id?: string;
  mechanic_id?: string;
  eta_seconds?: number;
  ring?: number;
  hotline?: string;
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(String(data.error || data.message || `Dispatch failed (${res.status})`));
  return data as T;
}

const json = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

export const dispatchApi = {
  base: BASE,
  health: () => call<{ message: string }>('/api/dispatch/health/'),
  telemetry: (mechanic_id: string, lat: number, lon: number, skills: string[], status = 'ONLINE') =>
    call<TelemetryAck>('/api/dispatch/telemetry/', json({ mechanic_id, lat, lon, skills, status })),
  createBooking: (booking_id: string, lat: number, lon: number, required_skill: string, urgency: string) =>
    call<{ booking_id: string }>('/api/dispatch/bookings/', json({ booking_id, lat, lon, required_skill, urgency })),
  dispatch: (bookingId: string) => call<OfferResult>(`/api/dispatch/bookings/${bookingId}/dispatch/`, json({})),
  accept: (offerId: string, mechanic_id: string) =>
    call<{ status: string }>(`/api/dispatch/offers/${offerId}/accept/`, json({ mechanic_id })),
  reject: (offerId: string, mechanic_id: string) =>
    call<{ message: string }>(`/api/dispatch/offers/${offerId}/reject/`, json({ mechanic_id })),
  advance: (bookingId: string, to: string) =>
    call<{ status: string }>(`/api/dispatch/jobs/${bookingId}/status/`, json({ to })),
  subscribe: (bookingId: string, onMessage: (payload: string) => void): WebSocket => {
    const ws = new WebSocket(`${BASE.replace(/^http/, 'ws')}/api/dispatch/ws/jobs/${bookingId}`);
    ws.onmessage = (event) => onMessage(String(event.data));
    return ws;
  },
};
