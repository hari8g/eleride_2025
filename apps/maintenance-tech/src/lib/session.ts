export type OperatorRole = "OWNER" | "ADMIN" | "OPS" | "MAINT" | "VIEWER";

export type Session = {
  token: string;
  operator_id: string;
  operator_name: string;
  operator_slug: string;
  user_id: string;
  user_phone: string;
  role: OperatorRole;
};

const KEY = "eleride.maintenance_tech.session.v1";

export function loadSession(): Session | null {
  const raw = localStorage.getItem(KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as Session;
  } catch {
    return null;
  }
}

export function saveSession(s: Session) {
  localStorage.setItem(KEY, JSON.stringify(s));
}

export function clearSession() {
  localStorage.removeItem(KEY);
}


