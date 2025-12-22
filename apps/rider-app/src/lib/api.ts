export type RiderStatus =
  | "NEW"
  | "PROFILE_COMPLETED"
  | "KYC_IN_PROGRESS"
  | "VERIFIED_PENDING_SUPPLY_MATCH";

export type DemandCard = {
  lane_id: string;
  qc_name: string;
  distance_km: number;
  shift_start: string;
  earning_range: string;
  minimum_guarantee: string;
  expected_trips_per_day?: number | null;
  expected_orders_per_day?: number | null;
  contract_type: string;
  slots_available: string;
  lat?: number | null;
  lon?: number | null;
  rank_reasons?: string[] | null;
};

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

async function http<T>(
  path: string,
  init: RequestInit & { token?: string } = {},
): Promise<T> {
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

export const api = {
  base: BASE,

  health: () => http<{ ok: boolean; service: string; env: string }>("/health"),

  otpRequest: (phone: string) =>
    http<{ request_id: string; expires_in_seconds: number; dev_otp?: string }>(
      "/auth/otp/request",
      {
        method: "POST",
        body: JSON.stringify({ phone }),
      },
    ),

  otpVerify: (request_id: string, otp: string) =>
    http<{ access_token: string; token_type: string }>("/auth/otp/verify", {
      method: "POST",
      body: JSON.stringify({ request_id, otp }),
    }),

  riderStatus: (token: string) =>
    http<{
      rider_id: string;
      phone: string;
      status: RiderStatus;
      active_commitment?: any | null;
    }>("/riders/status", { token }),

  profileUpsert: (token: string, payload: {
    name: string;
    dob: string;
    address: string;
    emergency_contact: string;
    preferred_zones: string[];
  }) => http("/riders/profile", { method: "POST", token, body: JSON.stringify(payload) }),

  kycStart: (token: string) =>
    http("/riders/kyc/start", {
      method: "POST",
      token,
      body: JSON.stringify({ doc_type: "DL" }),
    }),

  kycPass: (token: string) => http("/riders/kyc/complete-pass", { method: "POST", token }),

  demandNearby: (token: string, lat: number, lon: number, radius_km: number) =>
    http<{ policy: any; cards: DemandCard[] }>(
      `/demand/nearby?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}&radius_km=${encodeURIComponent(
        radius_km,
      )}`,
      { token },
    ),

  supplyConnect: (
    token: string,
    payload: { lane_id: string; time_window?: string | null; requirements?: string | null; rider_lat?: number | null; rider_lon?: number | null },
  ) =>
    http<{
      request_id: string;
      status: string;
      next_step: string;
      operator: {
        operator_id: string;
        name: string;
        pickup_location: string;
        required_docs: string[];
      };
    }>("/supply/requests", { method: "POST", token, body: JSON.stringify(payload) }),

  supplyStatus: (token: string, request_id?: string | null) =>
    http<{
      request_id: string;
      created_at: string;
      supply_status: string;
      operator_id?: string | null;
      operator_name?: string | null;
      pickup_location?: string | null;
      inbox_state: string;
      inbox_note?: string | null;
      inbox_updated_at?: string | null;
      stage: { code: string; label: string; detail?: string | null };
    }>(`/supply/status${request_id ? `?request_id=${encodeURIComponent(request_id)}` : ""}`, { token }),
};


