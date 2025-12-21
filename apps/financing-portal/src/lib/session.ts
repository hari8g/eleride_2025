export type LessorSession = {
  token: string;
  lessor_id: string;
  lessor_name: string;
  lessor_slug: string;
  user_phone: string;
  role: "OWNER" | "ANALYST" | "VIEWER";
};

const KEY = "eleride.leasing_portal.session.v1";

export function loadSession(): LessorSession | null {
  const raw = localStorage.getItem(KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as LessorSession;
  } catch {
    return null;
  }
}

export function saveSession(s: LessorSession) {
  localStorage.setItem(KEY, JSON.stringify(s));
}

export function clearSession() {
  localStorage.removeItem(KEY);
}


