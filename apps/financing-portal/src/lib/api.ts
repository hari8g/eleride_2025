export class HttpError extends Error {
  status: number;
  body: unknown;
  constructor(status: number, body: unknown) {
    super(`HTTP ${status}`);
    this.status = status;
    this.body = body;
  }
}

export type LessorRole = "OWNER" | "ANALYST" | "VIEWER";

export type LessorSessionOut = {
  access_token: string;
  lessor_id: string;
  lessor_name: string;
  lessor_slug: string;
  user_id: string;
  user_phone: string;
  role: LessorRole;
};

export type PartnerSummary = {
  operator_id: string;
  vehicles_leased: number;
  vehicles_valued: number;
  fleet_vehicles_active: number;
  fleet_open_tickets: number;
  fleet_low_battery: number;
  fleet_avg_battery_pct?: number | null;
  leased_vehicles_active: number;
  leased_open_tickets: number;
  leased_vehicles_in_maintenance: number;
  leased_low_battery: number;
  est_buyback_value_inr: number;
};

export type LessorDashboard = {
  vehicles_leased_total: number;
  vehicles_valued_total: number;
  active_leases: number;
  partners: PartnerSummary[];
  est_buyback_value_total_inr: number;
};

export type LeasedVehicle = {
  vehicle_id: string;
  registration_number: string;
  operator_id: string;
  status: string;
  last_lat?: number | null;
  last_lon?: number | null;
  odometer_km?: number | null;
  battery_pct?: number | null;
  lease_status: "ACTIVE" | "CLOSED";
  purchase_price_inr?: number | null;
  monthly_rent_inr?: number | null;
  start_date: string;
};

export type BuybackEstimate = {
  vehicle_id: string;
  registration_number: string;
  operator_id: string;
  estimated_value_inr: number;
  floor_inr?: number | null;
  reasons: string[];
};

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

export const api = {
  base: BASE,

  otpRequest: (payload: { phone: string; mode: "signup" | "login"; lessor_name?: string; lessor_slug?: string }) =>
    http<{ request_id: string; expires_in_seconds: number; dev_otp?: string }>("/lessor/auth/otp/request", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  otpVerify: (payload: { request_id: string; otp: string }) =>
    http<LessorSessionOut>("/lessor/auth/otp/verify", { method: "POST", body: JSON.stringify(payload) }),

  me: (token: string) =>
    http<{ lessor_id: string; lessor_name: string; lessor_slug: string; user_id: string; user_phone: string; role: LessorRole }>(
      "/lessor/me",
      { token },
    ),

  dashboard: (token: string) => http<LessorDashboard>("/lessor/dashboard", { token }),

  vehicles: (token: string) => http<{ items: LeasedVehicle[] }>("/lessor/vehicles", { token }),

  buyback: (token: string, vehicle_id: string) =>
    http<BuybackEstimate>(`/lessor/vehicles/${encodeURIComponent(vehicle_id)}/buyback`, { token }),

  seedDemo: (token: string, per_partner: number) =>
    http<{ ok: boolean; vehicles_created: number }>(`/lessor/admin/seed-demo?per_partner=${encodeURIComponent(per_partner)}`, {
      method: "POST",
      token,
    }),
};


