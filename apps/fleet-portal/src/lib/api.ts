export class HttpError extends Error {
  status: number;
  body: unknown;
  constructor(status: number, body: unknown) {
    super(`HTTP ${status}`);
    this.status = status;
    this.body = body;
  }
}

export type OperatorRole = "OWNER" | "ADMIN" | "OPS" | "MAINT" | "VIEWER";

export type OperatorSessionOut = {
  access_token: string;
  operator_id: string;
  operator_name: string;
  operator_slug: string;
  user_id: string;
  user_phone: string;
  role: OperatorRole;
};

export type InboxItem = {
  supply_request_id: string;
  lane_id: string;
  created_at: string;
  inbox_updated_at?: string | null;
  pickup_location?: string | null;
  state: "NEW" | "CONTACTED" | "ONBOARDED" | "REJECTED";
  note?: string | null;
  rider: {
    rider_id: string;
    phone: string;
    name?: string | null;
    preferred_zones?: string[] | null;
    status: string;
  };
};

export type InboxDetail = {
  supply_request_id: string;
  lane_id: string;
  created_at: string;
  inbox_updated_at?: string | null;
  pickup_location?: string | null;
  time_window?: string | null;
  requirements?: string | null;
  state: InboxItem["state"];
  note?: string | null;
  rider: {
    rider_id: string;
    phone: string;
    name?: string | null;
    dob?: string | null;
    address?: string | null;
    emergency_contact?: string | null;
    preferred_zones?: string[] | null;
    status: string;
  };
};

export type Vehicle = {
  id: string;
  registration_number: string;
  status: "ACTIVE" | "IN_MAINTENANCE" | "INACTIVE";
  model?: string | null;
  meta?: string | null;
  last_lat?: number | null;
  last_lon?: number | null;
  last_telemetry_at?: string | null;
  odometer_km?: number | null;
  battery_pct?: number | null;
};

export type Maintenance = {
  id: string;
  vehicle_id: string;
  status: "OPEN" | "CLOSED";
  category: string;
  description: string;
  cost_inr?: number | null;
  created_at: string;
  updated_at?: string | null;
  completed_at?: string | null;
  expected_ready_at?: string | null;
  expected_takt_hours?: number | null;
  assigned_to_user_id?: string | null;
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

  operatorOtpRequest: (payload: { phone: string; mode: "signup" | "login"; operator_name?: string; operator_slug?: string }) =>
    http<{ request_id: string; expires_in_seconds: number }>("/operator/auth/otp/request", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  operatorOtpVerify: (payload: { request_id: string; otp: string }) =>
    http<OperatorSessionOut>("/operator/auth/otp/verify", { method: "POST", body: JSON.stringify(payload) }),

  operatorMe: (token: string) =>
    http<{ operator_id: string; operator_name: string; operator_slug: string; user_id: string; user_phone: string; role: OperatorRole }>(
      "/operator/me",
      { token },
    ),

  dashboardSummary: (token: string) =>
    http<{
      vehicles_total: number;
      vehicles_active: number;
      vehicles_in_maintenance: number;
      vehicles_inactive: number;
      low_battery_count: number;
      avg_battery_pct?: number | null;
      open_maintenance_count: number;
      open_maintenance_ticket_count: number;
      open_maintenance_assigned_ticket_count: number;
      open_maintenance_unassigned_ticket_count: number;
      open_maintenance_overdue_count: number;
      inbox_new: number;
      inbox_contacted: number;
      inbox_onboarded: number;
      inbox_rejected: number;
      arenas: { name: string; vehicles_total: number; vehicles_active: number; vehicles_in_maintenance: number; avg_battery_pct?: number | null }[];
    }>("/operator/dashboard/summary", { token }),

  seedDemo: (token: string, vehicles: number) =>
    http<{ ok: boolean; vehicles_created: number }>(`/operator/admin/seed-demo?vehicles=${encodeURIComponent(vehicles)}`, {
      method: "POST",
      token,
    }),

  inboxList: (token: string) => http<{ items: InboxItem[] }>("/operator/inbox/requests", { token }),

  inboxDetail: (token: string, supply_request_id: string) =>
    http<InboxDetail>(`/operator/inbox/requests/${encodeURIComponent(supply_request_id)}`, { token }),

  inboxSetState: (token: string, supply_request_id: string, payload: { state: InboxItem["state"]; note?: string | null }) =>
    http<{ ok: boolean; state: string }>(`/operator/inbox/requests/${encodeURIComponent(supply_request_id)}/state`, {
      method: "POST",
      token,
      body: JSON.stringify(payload),
    }),

  vehiclesList: (token: string) => http<{ items: Vehicle[] }>("/operator/vehicles", { token }),

  vehicleCreate: (token: string, payload: { registration_number: string; model?: string; meta?: string }) =>
    http<Vehicle>("/operator/vehicles", { method: "POST", token, body: JSON.stringify(payload) }),

  deviceBind: (token: string, vehicle_id: string, payload: { device_id: string; provider?: string }) =>
    http<{ ok: boolean; device_id: string }>(`/operator/vehicles/${encodeURIComponent(vehicle_id)}/devices`, {
      method: "POST",
      token,
      body: JSON.stringify(payload),
    }),

  telemetryIngest: (token: string, vehicle_id: string, payload: { device_id?: string; lat?: number; lon?: number; speed_kph?: number; odometer_km?: number; battery_pct?: number }) =>
    http<{ ok: boolean }>(`/operator/vehicles/${encodeURIComponent(vehicle_id)}/telemetry`, {
      method: "POST",
      token,
      body: JSON.stringify(payload),
    }),

  maintenanceList: (token: string, vehicle_id: string) =>
    http<{ items: Maintenance[] }>(`/operator/vehicles/${encodeURIComponent(vehicle_id)}/maintenance`, { token }),

  maintenanceCreate: (
    token: string,
    vehicle_id: string,
    payload: { category: string; description: string; cost_inr?: number | null; expected_takt_hours?: number | null },
  ) =>
    http<Maintenance>(`/operator/vehicles/${encodeURIComponent(vehicle_id)}/maintenance`, {
      method: "POST",
      token,
      body: JSON.stringify(payload),
    }),

  maintenanceClose: (token: string, vehicle_id: string, record_id: string) =>
    http<Maintenance>(`/operator/vehicles/${encodeURIComponent(vehicle_id)}/maintenance/${encodeURIComponent(record_id)}/close`, {
      method: "POST",
      token,
    }),

  openMaintenanceFeed: (token: string) =>
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
      }>;
    }>("/operator/maintenance/open", { token }),
};


