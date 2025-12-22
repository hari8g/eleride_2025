export class HttpError extends Error {
  status: number;
  body: unknown;
  constructor(status: number, body: unknown) {
    super(`HTTP ${status}`);
    this.status = status;
    this.body = body;
  }
}

const BASE = (import.meta as any).env?.VITE_API_BASE_URL || "http://localhost:18080";

async function http<T>(path: string, init: RequestInit & { token?: string } = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (!headers.has("content-type") && init.body) headers.set("content-type", "application/json");
  if (init.token) headers.set("authorization", `Bearer ${init.token}`);

  const res = await fetch(`${BASE}${path}`, { ...init, headers });
  const text = await res.text();
  let json: any = null;
  if (text) {
    try {
      json = JSON.parse(text);
    } catch {
      json = { raw: text };
    }
  }
  if (!res.ok) throw new HttpError(res.status, json);
  return json as T;
}

export type DemandCard = {
  lane_id: string;
  qc_name: string;
  distance_km: number;
  shift_start: string;
  earning_range: string;
  minimum_guarantee: string;
  contract_type: string;
  slots_available: string;
  lat?: number | null;
  lon?: number | null;
  rank_reasons?: string[] | null;
};

export type Availability = {
  lane: { lane_id: string; lat: number; lon: number; source: string };
  generated_at: string;
  operators: Array<{
    operator_id: string;
    operator_name?: string | null;
    active_vehicles: number;
    available_vehicles: number;
    inbox_new: number;
    inbox_contacted: number;
    open_maintenance_vehicles: number;
    top_vehicles: Array<{
      vehicle_id: string;
      registration_number: string;
      operator_id: string;
      status: string;
      last_telemetry_at?: string | null;
      battery_pct?: number | null;
      distance_km?: number | null;
      score: number;
      reasons: string[];
    }>;
  }>;
};

export type Recommendation = {
  lane: { lane_id: string; lat: number; lon: number; source: string };
  generated_at: string;
  recommended?: any | null;
  alternatives: any[];
};

export type AuditRow = {
  request_id: string;
  created_at: string;
  rider_id: string;
  lane_id: string;
  supply_status: string;
  operator_id?: string | null;
  pickup_location?: string | null;
  matched_vehicle_id?: string | null;
  matched_score?: number | null;
  matched_reasons?: string[] | null;
};

export const api = {
  base: BASE,

  health: () => http<{ ok: boolean; service: string; env: string }>("/health"),

  otpRequest: (phone: string) =>
    http<{ request_id: string; expires_in_seconds: number; dev_otp?: string }>("/auth/otp/request", {
      method: "POST",
      body: JSON.stringify({ phone }),
    }),

  otpVerify: (request_id: string, otp: string) =>
    http<{ access_token: string; token_type: string }>("/auth/otp/verify", {
      method: "POST",
      body: JSON.stringify({ request_id, otp }),
    }),

  demandNearby: (token: string, lat: number, lon: number, radius_km: number) =>
    http<{ policy: any; cards: DemandCard[] }>(
      `/demand/nearby?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}&radius_km=${encodeURIComponent(radius_km)}`,
      { token },
    ),

  availability: (token: string, lane_id: string, rider_lat: number, rider_lon: number, max_km: number) =>
    http<Availability>(
      `/matchmaking/availability?lane_id=${encodeURIComponent(lane_id)}&rider_lat=${encodeURIComponent(rider_lat)}&rider_lon=${encodeURIComponent(
        rider_lon,
      )}&max_km=${encodeURIComponent(max_km)}`,
      { token },
    ),

  recommend: (
    token: string,
    payload: {
      lane_id: string;
      rider_lat: number;
      rider_lon: number;
      max_km: number;
      min_battery_pct: number;
      max_telemetry_age_min: number;
      limit: number;
    },
  ) =>
    http<Recommendation>("/matchmaking/recommend", {
      method: "POST",
      token,
      body: JSON.stringify(payload),
    }),

  auditRecent: (token: string, limit = 50) =>
    http<{ items: AuditRow[] }>(`/matchmaking/audit/recent?limit=${encodeURIComponent(limit)}`, { token }),
};


