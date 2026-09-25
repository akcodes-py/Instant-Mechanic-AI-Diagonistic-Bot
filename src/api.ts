/** Typed API client. Base URL comes from VITE_API_URL (no secrets in frontend). */
const BASE: string =
  (import.meta as unknown as { env: Record<string, string> }).env.VITE_API_URL || 'http://127.0.0.1:8000';

export interface ChatReply {
  session_id: string;
  reply: string;
  action: string;
  needs_info?: string[];
  ai_used?: boolean;
  diagnosis_ready?: boolean;
  unsafe?: boolean;
}

export interface Diagnosis {
  id: string;
  session: string;
  summary: string;
  possible_causes: string[];
  supporting_symptoms: string[];
  recommended_service: string;
  next_steps: string[];
  urgency: 'low' | 'medium' | 'high' | 'critical';
  drive_guidance: string;
  safety_warning: string;
  inspection_recommended: boolean;
  ai_used?: boolean;
  disclaimer?: string;
  created_at: string;
}

export interface Booking {
  id: string;
  session: string | null;
  diagnosis?: unknown;
  name: string;
  phone: string;
  service_type: string;
  vehicle_details: string;
  location: string;
  scheduled_at: string;
  notes: string;
  status: string;
  created_at: string;
  message?: string;
}

export interface HistoryData {
  session_id: string;
  vehicle: { make: string; model: string; year: string; fuel: string };
  messages: { id: string; role: string; content: string; ai_used: boolean; created_at: string }[];
  diagnoses: Diagnosis[];
  uploads: { id: string; kind: string; original_name: string; created_at: string }[];
}

async function req<T>(path: string, init?: RequestInit, _attempt = 0): Promise<T> {
  const MAX_RETRIES = 2;
  const RETRY_DELAY_MS = 800;
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, init);
  } catch {
    if (_attempt < MAX_RETRIES) {
      await new Promise((r) => setTimeout(r, RETRY_DELAY_MS * Math.pow(2, _attempt)));
      return req<T>(path, init, _attempt + 1);
    }
    throw new Error('Cannot reach server. Check your connection or try calling +91 9266961110.');
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    // Retry on server errors (5xx), not client errors (4xx)
    if (res.status >= 500 && _attempt < MAX_RETRIES) {
      await new Promise((r) => setTimeout(r, RETRY_DELAY_MS * Math.pow(2, _attempt)));
      return req<T>(path, init, _attempt + 1);
    }
    const msg =
      (data as Record<string, unknown>).error ||
      (data as Record<string, unknown>).detail ||
      Object.values(data || {}).flat().join(' ') ||
      `Request failed (${res.status})`;
    throw new Error(String(msg));
  }
  return data as T;
}

export const api = {
  base: BASE,
  chat(session_id: string | null, message: string, vehicle?: Record<string, string>): Promise<ChatReply> {
    return req<ChatReply>('/api/chat/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id, message, ...(vehicle || {}) }),
    });
  },
  upload(session_id: string, file: File, onProgress?: (pct: number) => void): Promise<{ id: string; kind: string; size_bytes: number; analyzed: boolean; note: string }> {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open('POST', `${BASE}/api/upload/`);
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable && onProgress) onProgress(Math.round((e.loaded / e.total) * 100));
      };
      xhr.onload = () => {
        try {
          const data = JSON.parse(xhr.responseText || '{}');
          if (xhr.status >= 200 && xhr.status < 300) resolve(data);
          else reject(new Error(data.error || `Upload failed (${xhr.status})`));
        } catch {
          reject(new Error('Upload failed. Please try again.'));
        }
      };
      xhr.onerror = () => reject(new Error('Upload failed. Check connection and retry.'));
      const fd = new FormData();
      fd.append('session_id', session_id);
      fd.append('file', file, file.name);
      xhr.send(fd);
    });
  },
  diagnose(session_id: string): Promise<Diagnosis> {
    return req<Diagnosis>('/api/diagnosis/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id }),
    });
  },
  book(payload: Record<string, unknown>): Promise<Booking> {
    return req<Booking>('/api/booking/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  },
  booking(id: string): Promise<Booking> {
    return req<Booking>(`/api/booking/${id}/`);
  },
  history(session_id: string): Promise<HistoryData> {
    return req<HistoryData>(`/api/history/${session_id}/`);
  },
  health(): Promise<{ status: string }> {
    return req<{ status: string }>('/api/health/');
  },
};

export const CONTACT = {
  phoneDisplay: '+91 9266961110',
  phoneHref: 'tel:+919266961110',
  whatsapp: 'https://wa.me/919266961110?text=Hi%20Instant%20Mechanic%2C%20I%20need%20roadside%20help.%20My%20location%3A%20',
  email: 'gordhan@instantmechanic.online',
  address: 'Sector 75, Southern Peripheral Road, Gurugram, Haryana, India',
};
