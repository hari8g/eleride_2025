export type OperatorSession = {
  token: string;
  operator_id: string; // stable tenant key (slug)
  operator_name: string;
  operator_slug: string;
  user_phone: string;
  role: "OWNER" | "ADMIN" | "OPS" | "MAINT" | "VIEWER";
};

const KEY = "eleride.fleet_portal.session.v1";

export function loadSession(): OperatorSession | null {
  const raw = localStorage.getItem(KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as OperatorSession;
  } catch {
    return null;
  }
}

export function saveSession(s: OperatorSession) {
  localStorage.setItem(KEY, JSON.stringify(s));
}

export function clearSession() {
  localStorage.removeItem(KEY);
}


