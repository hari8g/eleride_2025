import React, { useEffect, useMemo, useRef, useState } from "react";
import logoPng from "../assets/eleride-logo.png";
import { api, HttpError } from "../lib/api";
import { clearSession, loadSession, saveSession, Session } from "../lib/session";

type Step = "auth" | "tickets" | "ticket";

function parseE164(phone: string | null | undefined): { cc: string; national: string } | null {
  if (!phone) return null;
  const m = phone.trim().match(/^\+(\d{1,3})(\d{6,14})$/);
  if (!m) return null;
  return { cc: `+${m[1]}`, national: m[2] };
}

function isNationalNumberish(n: string) {
  const cleaned = n.replace(/[^\d]/g, "");
  return cleaned.length >= 6 && cleaned.length <= 14;
}

function buildE164(cc: string, national: string) {
  const n = national.replace(/[^\d]/g, "");
  const c = cc.trim();
  if (!c.startsWith("+")) return `+${c}${n}`;
  return `${c}${n}`;
}

function safeMsg(e: unknown): string {
  if (e instanceof HttpError) {
    const body = e.body as any;
    const detail = body?.detail;
    if (typeof detail === "string") return detail;
    if (detail?.message && typeof detail.message === "string") return detail.message;
    return `Request failed (${e.status}).`;
  }
  return (e as any)?.message ? String((e as any).message) : String(e);
}

function buildOsmEmbed(lat: number, lon: number) {
  const delta = 0.02;
  const left = lon - delta;
  const right = lon + delta;
  const top = lat + delta;
  const bottom = lat - delta;
  const marker = `${encodeURIComponent(lat)},${encodeURIComponent(lon)}`;
  return `https://www.openstreetmap.org/export/embed.html?bbox=${left}%2C${bottom}%2C${right}%2C${top}&layer=mapnik&marker=${marker}`;
}

function fmtDt(s: string | null | undefined) {
  if (!s) return "—";
  try {
    return new Date(s).toLocaleString();
  } catch {
    return s;
  }
}

function minutesUntil(ts: string | null | undefined): number | null {
  if (!ts) return null;
  const t = new Date(ts).getTime();
  if (!Number.isFinite(t)) return null;
  return Math.round((t - Date.now()) / 60000);
}

type Ticket = Awaited<ReturnType<typeof api.openMaintenance>>["items"][number];

export function MaintTechApp() {
  const [health, setHealth] = useState<{ ok: boolean; service: string; env: string } | null>(null);
  const [session, setSession] = useState<Session | null>(() => loadSession());
  const [step, setStep] = useState<Step>("auth");

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [banner, setBanner] = useState<string | null>(null);

  // auth inputs
  const parsedSessionPhone = useMemo(() => parseE164(session?.user_phone ?? null), [session?.user_phone]);
  const [countryCode, setCountryCode] = useState<string>(() => parsedSessionPhone?.cc ?? "+91");
  const [phoneDigits, setPhoneDigits] = useState<string>(() => parsedSessionPhone?.national ?? "9999000900");
  const phoneE164 = useMemo(() => buildE164(countryCode, phoneDigits), [countryCode, phoneDigits]);

  const [operatorSlug, setOperatorSlug] = useState<string>(() => session?.operator_slug ?? "eleride-fleet");
  const [otpRequestId, setOtpRequestId] = useState<string>("");
  const [otp, setOtp] = useState<string>("");

  // tickets
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [openTotal, setOpenTotal] = useState<number>(0);
  const [selectedId, setSelectedId] = useState<string>("");
  const selected = useMemo(() => tickets.find((t) => t.record_id === selectedId) ?? null, [tickets, selectedId]);

  const knownIdsRef = useRef<Set<string>>(new Set());
  const pollRef = useRef<number | null>(null);

  async function run(fn: () => Promise<void>) {
    setError(null);
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      setError(safeMsg(e));
    } finally {
      setBusy(false);
    }
  }

  function signOut() {
    clearSession();
    setSession(null);
    setTickets([]);
    setSelectedId("");
    setOtpRequestId("");
    setOtp("");
    setDevOtp("");
    setStep("auth");
  }

  async function refreshTickets({ notify }: { notify: boolean }) {
    if (!session?.token) return;
    const res = await api.openMaintenance(session.token);
    const items = res.items ?? [];
    setOpenTotal(res.total_open ?? items.length);
    setTickets(items);

    const newIds: string[] = [];
    for (const it of items) {
      if (!knownIdsRef.current.has(it.record_id)) newIds.push(it.record_id);
    }
    if (items.length > 0) {
      knownIdsRef.current = new Set(items.map((x) => x.record_id));
    } else {
      knownIdsRef.current = new Set();
    }

    if (notify && newIds.length > 0) {
      setBanner(`New maintenance tickets: ${newIds.length}`);
      try {
        if (Notification?.permission === "granted") {
          const first = items.find((x) => x.record_id === newIds[0]);
          const title = "New maintenance ticket";
          const body = first ? `${first.registration_number} • ${first.category}` : `${newIds.length} new tickets`;
          new Notification(title, { body });
        }
      } catch {
        // ignore
      }
    }
  }

  useEffect(() => {
    api.health()
      .then(setHealth)
      .catch(() => setHealth(null));
  }, []);

  useEffect(() => {
    // keep auth phone fields in sync with session
    const p = parseE164(session?.user_phone ?? null);
    if (p) {
      setCountryCode(p.cc);
      setPhoneDigits(p.national);
    }
  }, [session?.user_phone]);

  useEffect(() => {
    if (!session?.token) {
      setStep("auth");
      return;
    }
    setStep("tickets");
    refreshTickets({ notify: false }).catch(() => null);

    if (pollRef.current) window.clearInterval(pollRef.current);
    pollRef.current = window.setInterval(() => {
      refreshTickets({ notify: true }).catch(() => null);
    }, 9000);
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
      pollRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session?.token]);

  const badge = useMemo(() => {
    if (!session?.token) return health ? `API: ${health.env}` : "Offline?";
    return `${session.role} • ${openTotal} open`;
  }, [health, session?.token, session?.role, openTotal]);

  const actionDisabled = !session?.token || busy;

  return (
    <div className="app">
      <div className="phoneFrame">
        <div className="topbar">
          <div className="brand">
            <img className="brandLogo" src={logoPng} alt="Eleride" />
            <div>Maintenance</div>
          </div>
          <div className="chip">{badge}</div>
        </div>

        <div className="content">
          {error ? <div className="error">{error}</div> : null}
          {banner ? (
            <div className="ok">
              {banner}
              <div className="divider" />
              <button className="btn btnSecondary" onClick={() => setBanner(null)}>
                Dismiss
              </button>
            </div>
          ) : null}

          {step === "auth" ? (
            <>
              <div className="hero">
                <img className="heroLogo" src={logoPng} alt="Eleride" />
                <div className="title">Technician login</div>
                <p className="subtitle">Sign in to view open maintenance tickets and update ETA.</p>
              </div>

              {session?.token ? (
                <div className="ok">
                  You’re already signed in.
                  <div className="divider" />
                  <div className="row">
                    <button className="btn btnPrimary" onClick={() => setStep("tickets")}>
                      Continue
                    </button>
                    <button className="btn btnDanger" onClick={signOut}>
                      Sign out
                    </button>
                  </div>
                </div>
              ) : (
                <div className="stack">
                  <div className="card stack">
                    <div>
                      <label>Operator</label>
                      <input value={operatorSlug} onChange={(e) => setOperatorSlug(e.target.value)} placeholder="eleride-fleet" />
                      <div className="helper">Choose tenant (e.g. eleride-fleet).</div>
                    </div>

                    <div>
                      <label>Phone</label>
                      <div className="row">
                        <div style={{ width: 110 }}>
                          <label>Country</label>
                          <select value={countryCode} onChange={(e) => setCountryCode(e.target.value)}>
                            <option value="+91">+91 (IN)</option>
                            <option value="+1">+1 (US)</option>
                            <option value="+44">+44 (UK)</option>
                          </select>
                        </div>
                        <div style={{ flex: 1, minWidth: 200 }}>
                          <label>Number</label>
                          <input
                            value={phoneDigits}
                            onChange={(e) => setPhoneDigits(e.target.value)}
                            placeholder="9999000900"
                            inputMode="tel"
                            autoComplete="tel-national"
                          />
                        </div>
                      </div>
                      <div className="helper">We’ll send an OTP to {phoneE164}.</div>
                    </div>

                    <button
                      className="btn btnPrimary"
                      disabled={busy || !isNationalNumberish(phoneDigits) || !operatorSlug.trim()}
                      onClick={() =>
                        run(async () => {
                          const r = await api.otpRequest({ phone: phoneE164, mode: "login", operator_slug: operatorSlug.trim() });
                          setOtpRequestId(r.request_id);
                        })
                      }
                    >
                      {busy ? "Sending…" : "Send OTP"}
                    </button>
                  </div>

                  {otpRequestId ? (
                    <div className="card stack">
                      <div>
                        <label>OTP</label>
                        <input
                          value={otp}
                          onChange={(e) => setOtp(e.target.value)}
                          placeholder="6-digit OTP"
                          inputMode="numeric"
                          autoComplete="one-time-code"
                        />
                      </div>

                      <button
                        className="btn btnPrimary"
                        disabled={busy || otp.trim().length < 4}
                        onClick={() =>
                          run(async () => {
                            const s = await api.otpVerify({ request_id: otpRequestId, otp: otp.trim() });
                            const next: Session = {
                              token: s.access_token,
                              operator_id: s.operator_id,
                              operator_name: s.operator_name,
                              operator_slug: s.operator_slug,
                              user_id: s.user_id,
                              user_phone: s.user_phone,
                              role: s.role,
                            };
                            saveSession(next);
                            setSession(next);
                            setOtpRequestId("");
                            setOtp("");
                            setDevOtp("");
                            setStep("tickets");
                            await refreshTickets({ notify: false });
                          })
                        }
                      >
                        {busy ? "Verifying…" : "Verify & Enter"}
                      </button>
                    </div>
                  ) : null}
                </div>
              )}
            </>
          ) : null}

          {step === "tickets" ? (
            <>
              <div className="row" style={{ justifyContent: "space-between", alignItems: "baseline" }}>
                <div>
                  <div className="title">Open tickets</div>
                  <p className="subtitle">New tickets auto-refresh every ~9 seconds.</p>
                </div>
                <div className="row">
                  <button
                    className="btn btnSecondary"
                    disabled={busy || !session?.token}
                    onClick={() => run(async () => refreshTickets({ notify: false }))}
                  >
                    Refresh
                  </button>
                  <button
                    className="btn btnSecondary"
                    disabled={!("Notification" in window)}
                    onClick={async () => {
                      try {
                        const p = await Notification.requestPermission();
                        if (p === "granted") setBanner("Notifications enabled.");
                        else setBanner("Notifications blocked.");
                      } catch {
                        setBanner("Notifications not supported.");
                      }
                    }}
                  >
                    Enable alerts
                  </button>
                </div>
              </div>

              {session?.role !== "MAINT" ? (
                <div className="helper">
                  Note: your role is <b>{session?.role}</b>. In production, technicians should have <b>MAINT</b> role.
                </div>
              ) : null}

              <div className="card stack">
                <div className="row" style={{ justifyContent: "space-between" }}>
                  <div className="pill">{openTotal} open</div>
                  <div className="pill">{session?.operator_name}</div>
                </div>

                {tickets.length === 0 ? <div className="helper">No open tickets right now.</div> : null}

                <div className="list">
                  {tickets.map((t) => {
                    const etaMin = minutesUntil(t.expected_ready_at ?? null);
                    const etaLabel =
                      etaMin == null ? "ETA —" : etaMin <= 0 ? "ETA due" : etaMin < 60 ? `ETA ${etaMin}m` : `ETA ${Math.round(etaMin / 60)}h`;
                    const assigned =
                      t.assigned_to_user_id == null
                        ? "Unassigned"
                        : t.assigned_to_user_id === session?.user_id
                          ? "Mine"
                          : "Assigned";
                    return (
                      <button
                        key={t.record_id}
                        type="button"
                        className={`ticketItem ${selectedId === t.record_id ? "ticketItemActive" : ""}`}
                        onClick={() => {
                          setSelectedId(t.record_id);
                          setStep("ticket");
                        }}
                      >
                        <div className="ticketTop">
                          <div style={{ fontWeight: 900 }}>{t.registration_number}</div>
                          <div className="row">
                            <div className="pill">{assigned}</div>
                            <div className="pill">{etaLabel}</div>
                          </div>
                        </div>
                        <div className="helper">
                          {t.category} • {t.description}
                        </div>
                        <div className="metaRow" style={{ marginTop: 8 }}>
                          <span>{fmtDt(t.created_at)}</span>
                          <span>• Updated {fmtDt((t as any).updated_at ?? null)}</span>
                          <span>• Batt {t.battery_pct != null ? `${Math.round(t.battery_pct)}%` : "—"}</span>
                        </div>
                      </button>
                    );
                  })}
                </div>

                <div className="footerActions">
                  <button className="btn btnDanger" onClick={signOut}>
                    Sign out
                  </button>
                </div>
              </div>
            </>
          ) : null}

          {step === "ticket" ? (
            <>
              {!selected ? (
                <div className="card stack">
                  <div className="helper">Ticket not found (maybe it was closed). Go back and refresh.</div>
                  <button className="btn btnPrimary" onClick={() => setStep("tickets")}>
                    Back
                  </button>
                </div>
              ) : (
                <>
                  <div className="row" style={{ justifyContent: "space-between" }}>
                    <div>
                      <div className="title">{selected.registration_number}</div>
                      <div className="helper">{selected.model ?? "—"}</div>
                    </div>
                    <button className="btn btnSecondary" onClick={() => setStep("tickets")} disabled={busy}>
                      Back
                    </button>
                  </div>

                  <div className="card stack">
                    <div className="row" style={{ justifyContent: "space-between" }}>
                      <div className="tag">Status: {selected.status}</div>
                      <div className="tag">Vehicle: {selected.vehicle_status}</div>
                    </div>

                    <div className="grid2">
                      <div>
                        <label>Category</label>
                        <div className="helper">{selected.category}</div>
                      </div>
                      <div>
                        <label>Created</label>
                        <div className="helper">{fmtDt(selected.created_at)}</div>
                      </div>
                    </div>

                    <div>
                      <label>Description</label>
                      <div className="helper">{selected.description}</div>
                    </div>

                    <div className="grid2">
                      <div>
                        <label>Current ETA active</label>
                        <div className="helper">{fmtDt(selected.expected_ready_at ?? null)}</div>
                      </div>
                      <div>
                        <label>Expected takt (hours)</label>
                        <div className="helper">{selected.expected_takt_hours != null ? `${selected.expected_takt_hours}` : "—"}</div>
                      </div>
                    </div>

                    <div className="grid2">
                      <div>
                        <label>Assigned</label>
                        <div className="helper">
                          {selected.assigned_to_user_id == null
                            ? "Unassigned"
                            : selected.assigned_to_user_id === session?.user_id
                              ? "Assigned to you"
                              : "Assigned"}
                        </div>
                      </div>
                      <div>
                        <label>Updated</label>
                        <div className="helper">{fmtDt((selected as any).updated_at ?? null)}</div>
                      </div>
                    </div>

                    <div className="grid2">
                      <div>
                        <label>Battery</label>
                        <div className="helper">{selected.battery_pct != null ? `${Math.round(selected.battery_pct)}%` : "—"}</div>
                      </div>
                      <div>
                        <label>Odometer</label>
                        <div className="helper">{selected.odometer_km != null ? `${selected.odometer_km.toFixed(0)} km` : "—"}</div>
                      </div>
                    </div>

                    {selected.last_lat != null && selected.last_lon != null ? (
                      <div className="mapFrame">
                        <iframe title="map" src={buildOsmEmbed(selected.last_lat, selected.last_lon)} loading="lazy" />
                      </div>
                    ) : (
                      <div className="helper">No location telemetry yet for this vehicle.</div>
                    )}

                    <div className="divider" />

                    <div className="grid2">
                      <div>
                        <label>Update takt time (hours)</label>
                        <input
                          type="number"
                          min={1}
                          max={24 * 30}
                          step={1}
                          value={String(Math.round(selected.expected_takt_hours ?? 24))}
                          onChange={(e) => {
                            const v = Number(e.target.value);
                            if (!Number.isFinite(v)) return;
                            setTickets((prev) =>
                              prev.map((x) => (x.record_id === selected.record_id ? { ...x, expected_takt_hours: v } : x)),
                            );
                          }}
                        />
                        <div className="helper">This updates ETA active in the backend immediately.</div>
                      </div>
                      <div>
                        <label>Last telemetry</label>
                        <div className="helper">{fmtDt(selected.last_telemetry_at ?? null)}</div>
                      </div>
                    </div>

                    <div className="row">
                      <button
                        className="btn btnSecondary"
                        disabled={actionDisabled}
                        onClick={() =>
                          run(async () => {
                            const mine = selected.assigned_to_user_id === session?.user_id;
                            await api.assignTicket(session!.token, selected.vehicle_id, selected.record_id, !mine);
                            await refreshTickets({ notify: false });
                            setBanner(!mine ? "Ticket claimed." : "Ticket unassigned.");
                          })
                        }
                      >
                        {selected.assigned_to_user_id === session?.user_id ? "Unassign" : "Claim"}
                      </button>

                      <button
                        className="btn btnPrimary"
                        disabled={actionDisabled}
                        onClick={() =>
                          run(async () => {
                            const hrs = Math.round(Number(selected.expected_takt_hours ?? 24));
                            const r = await api.updateTakt(session!.token, selected.vehicle_id, selected.record_id, hrs);
                            // refresh list from backend for canonical ETA
                            await refreshTickets({ notify: false });
                            setBanner(`Updated takt to ${r.expected_takt_hours ?? hrs}h.`);
                          })
                        }
                      >
                        Save ETA
                      </button>

                      <button
                        className="btn btnDanger"
                        disabled={actionDisabled}
                        onClick={() =>
                          run(async () => {
                            await api.closeTicket(session!.token, selected.vehicle_id, selected.record_id);
                            await refreshTickets({ notify: false });
                            setBanner("Ticket closed. Vehicle may return ACTIVE if no other OPEN tickets remain.");
                            setStep("tickets");
                          })
                        }
                      >
                        Close ticket
                      </button>
                    </div>
                  </div>
                </>
              )}
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}


