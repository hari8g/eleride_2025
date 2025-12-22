export type OperatorRole = "OWNER" | "ADMIN" | "OPS" | "MAINT" | "VIEWER";

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

  otpRequest: (payload: { phone: string; mode: "login" | "signup"; operator_slug?: string; operator_name?: string }) =>
    http<{ request_id: string; expires_in_seconds: number }>("/operator/auth/otp/request", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  otpVerify: (payload: { request_id: string; otp: string }) =>
    http<{
      access_token: string;
      operator_id: string;
      operator_name: string;
      operator_slug: string;
      user_id: string;
      user_phone: string;
      role: OperatorRole;
    }>("/operator/auth/otp/verify", { method: "POST", body: JSON.stringify(payload) }),

  me: (token: string) =>
    http<{ operator_id: string; operator_name: string; operator_slug: string; user_id: string; user_phone: string; role: OperatorRole }>(
      "/operator/me",
      { token },
    ),

  openMaintenance: (token: string) =>
    http<{
      total_open: number;
      items: Array<{
        record_id: string;
        vehicle_id: string;
        registration_number: string;
        vehicle_status: string;
        model?: string | null;
        category: string;
        description: string;
        status: string;
        created_at: string;
        updated_at?: string | null;
        expected_ready_at?: string | null;
        expected_takt_hours?: number | null;
        assigned_to_user_id?: string | null;
        last_lat?: number | null;
        last_lon?: number | null;
        last_telemetry_at?: string | null;
        odometer_km?: number | null;
        battery_pct?: number | null;
      }>;
    }>("/operator/maintenance/open", { token }),

  updateTakt: (token: string, vehicle_id: string, record_id: string, expected_takt_hours: number) =>
    http<{
      id: string;
      vehicle_id: string;
      status: string;
      category: string;
      description: string;
      created_at: string;
      updated_at?: string | null;
      completed_at?: string | null;
      expected_ready_at?: string | null;
      expected_takt_hours?: number | null;
      assigned_to_user_id?: string | null;
    }>(`/operator/vehicles/${encodeURIComponent(vehicle_id)}/maintenance/${encodeURIComponent(record_id)}/takt`, {
      method: "POST",
      token,
      body: JSON.stringify({ expected_takt_hours }),
    }),

  assignTicket: (token: string, vehicle_id: string, record_id: string, assigned: boolean) =>
    http<{
      id: string;
      vehicle_id: string;
      status: string;
      category: string;
      description: string;
      created_at: string;
      updated_at?: string | null;
      completed_at?: string | null;
      expected_ready_at?: string | null;
      expected_takt_hours?: number | null;
      assigned_to_user_id?: string | null;
    }>(`/operator/vehicles/${encodeURIComponent(vehicle_id)}/maintenance/${encodeURIComponent(record_id)}/assign`, {
      method: "POST",
      token,
      body: JSON.stringify({ assigned }),
    }),

  closeTicket: (token: string, vehicle_id: string, record_id: string) =>
    http<{
      id: string;
      vehicle_id: string;
      status: string;
      category: string;
      description: string;
      created_at: string;
      updated_at?: string | null;
      completed_at?: string | null;
      expected_ready_at?: string | null;
      expected_takt_hours?: number | null;
      assigned_to_user_id?: string | null;
    }>(`/operator/vehicles/${encodeURIComponent(vehicle_id)}/maintenance/${encodeURIComponent(record_id)}/close`, {
      method: "POST",
      token,
    }),
};


