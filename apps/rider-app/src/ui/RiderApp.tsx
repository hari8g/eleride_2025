import React, { useEffect, useMemo, useState } from "react";
import { api, DemandCard, HttpError, RiderStatus } from "../lib/api";
import { clearSession, loadSession, saveSession, Session } from "../lib/session";
import logoPng from "../assets/eleride-logo.png";

type Step = "auth" | "profile" | "kyc" | "location" | "demand" | "connect" | "done" | "tracking";

type Geo = { lat: number; lon: number; radius_km: 5 | 10 };

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

function fmtHHmm(d: Date) {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function dayLabel(d: Date) {
  const now = new Date();
  const startOf = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diffDays = Math.round((startOf(d) - startOf(now)) / (24 * 3600 * 1000));
  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "Tomorrow";
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function ceilToNextHourEpochMs(now: Date) {
  const d = new Date(now);
  d.setMinutes(0, 0, 0);
  if (now.getMinutes() !== 0 || now.getSeconds() !== 0 || now.getMilliseconds() !== 0) d.setHours(d.getHours() + 1);
  return d.getTime();
}

function addHoursEpochMs(epochMs: number, hours: number) {
  return epochMs + hours * 3600 * 1000;
}

function buildTimeWindowParts(startEpochMs: number) {
  const start = new Date(startEpochMs);
  const end = new Date(addHoursEpochMs(startEpochMs, 6));
  const startDay = dayLabel(start);
  const endDay = dayLabel(end);
  const startTime = fmtHHmm(start);
  const endTime = fmtHHmm(end);
  return { startDay, startTime, endDay, endTime };
}

function buildTimeWindowLabel(startEpochMs: number) {
  const start = new Date(startEpochMs);
  const end = new Date(addHoursEpochMs(startEpochMs, 6));
  const startDay = dayLabel(start);
  const endDay = dayLabel(end);
  const startStr = `${startDay} ${fmtHHmm(start)}`;
  const endStr = `${endDay === startDay ? fmtHHmm(end) : `${endDay} ${fmtHHmm(end)}`}`;
  return `${startStr}–${endStr}`;
}

function parseMoneyMax(s: string | null | undefined): number {
  if (!s) return 0;
  const nums = String(s)
    .replace(/,/g, "")
    .match(/\d+(\.\d+)?/g);
  if (!nums || nums.length === 0) return 0;
  return Math.max(...nums.map((n) => Number(n)));
}

function scoreCard(c: DemandCard): number {
  const earn = parseMoneyMax(c.earning_range);
  const mg = parseMoneyMax(c.minimum_guarantee);
  const distPenalty = Math.min(25, Math.max(0, c.distance_km)) * 20; // 0..500
  return earn * 1.2 + mg * 1.6 - distPenalty;
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

function nextFromStatus(status: RiderStatus | null): Step {
  if (!status) return "auth";
  if (status === "NEW") return "profile";
  if (status === "PROFILE_COMPLETED") return "kyc";
  if (status === "KYC_IN_PROGRESS") return "kyc";
  return "location";
}

export function RiderApp() {
  const [health, setHealth] = useState<{ ok: boolean; service: string; env: string } | null>(null);
  const [session, setSession] = useState<Session | null>(() => loadSession());

  const parsedSessionPhone = useMemo(() => parseE164(session?.phone ?? null), [session?.phone]);

  const [status, setStatus] = useState<{
    rider_id: string;
    phone: string;
    status: RiderStatus;
  } | null>(null);

  const [step, setStep] = useState<Step>("auth");

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [locationHint, setLocationHint] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [notifState, setNotifState] = useState<"unknown" | "granted" | "denied" | "default">("unknown");

  // Auth
  const [countryCode, setCountryCode] = useState<string>(() => parsedSessionPhone?.cc ?? "+91");
  const [phoneDigits, setPhoneDigits] = useState<string>(() => parsedSessionPhone?.national ?? "9999000010");
  const phoneE164 = useMemo(() => buildE164(countryCode, phoneDigits), [countryCode, phoneDigits]);
  const [otpRequestId, setOtpRequestId] = useState<string>("");
  const [otp, setOtp] = useState<string>("");
  const [devOtp, setDevOtp] = useState<string>("");

  // Profile
  const [profile, setProfile] = useState({
    name: "New Rider",
    dob: "1999-01-01",
    address: "Pune",
    emergency_contact: "+919999111111",
    preferred_zones: ["Hadapsar", "Kharadi"],
  });

  // Location
  const [geo, setGeo] = useState<Geo>({ lat: 18.5204, lon: 73.8567, radius_km: 10 });
  const [geoReady, setGeoReady] = useState(false);

  // Demand
  const [demand, setDemand] = useState<DemandCard[] | null>(null);
  const [demandPolicy, setDemandPolicy] = useState<any | null>(null);
  const [selectedLaneId, setSelectedLaneId] = useState<string>("");

  // Connect
  const [connectResult, setConnectResult] = useState<null | {
    request_id: string;
    status: string;
    next_step: string;
    operator: { operator_id: string; name: string; pickup_location: string; required_docs: string[] };
  }>(null);
  const [trackingReqId, setTrackingReqId] = useState<string>(() => localStorage.getItem("eleride.rider.last_request_id") || "");
  const [supplyStatus, setSupplyStatus] = useState<null | Awaited<ReturnType<typeof api.supplyStatus>>>(null);
  const [trackingBusy, setTrackingBusy] = useState(false);
  const [remindTimer, setRemindTimer] = useState<number | null>(null);
  const [slotBaseMs, setSlotBaseMs] = useState<number>(() => ceilToNextHourEpochMs(new Date()));
  const [pickupStartMs, setPickupStartMs] = useState<number>(() => ceilToNextHourEpochMs(new Date()));
  const [docDL, setDocDL] = useState(true);
  const [docAadhaar, setDocAadhaar] = useState(true);
  const [connectNotes, setConnectNotes] = useState<string>("Preferred pickup within 2 hours.");

  const pickupOptions = useMemo(() => {
    // show next 18 hours, one-hour frequency; each option represents a 6h window
    return Array.from({ length: 18 }).map((_, i) => {
      const startMs = addHoursEpochMs(slotBaseMs, i);
      const p = buildTimeWindowParts(startMs);
      return {
        startMs,
        label: buildTimeWindowLabel(startMs),
        startDay: p.startDay,
        startTime: p.startTime,
        endDay: p.endDay,
        endTime: p.endTime,
      };
    });
  }, [slotBaseMs]);

  const selectedTimeWindowLabel = useMemo(() => buildTimeWindowLabel(pickupStartMs), [pickupStartMs]);

  const composedRequirements = useMemo(() => {
    const docs: string[] = [];
    if (docDL) docs.push("Driving License");
    if (docAadhaar) docs.push("Aadhaar");
    const lines: string[] = [];
    lines.push(`Docs: ${docs.length ? docs.join(", ") : "Not selected"}`);
    if (connectNotes.trim()) lines.push(`Notes: ${connectNotes.trim()}`);
    return lines.join("\n");
  }, [docDL, docAadhaar, connectNotes]);

  const featuredLaneId = useMemo(() => {
    if (!demand || demand.length === 0) return "";
    const sorted = [...demand].sort((a, b) => scoreCard(b) - scoreCard(a));
    return sorted[0]?.lane_id ?? "";
  }, [demand]);

  async function refresh() {
    if (!session?.token) return;
    const s = await api.riderStatus(session.token);
    setStatus({ rider_id: s.rider_id, phone: s.phone, status: s.status });
  }

  useEffect(() => {
    api.health()
      .then(setHealth)
      .catch(() => setHealth(null));
  }, []);

  useEffect(() => {
    // Clear toast automatically
    if (!toast) return;
    const t = window.setTimeout(() => setToast(null), 5000);
    return () => window.clearTimeout(t);
  }, [toast]);

  useEffect(() => {
    // Track notification permission (best-effort)
    try {
      const p = (window as any).Notification?.permission;
      if (p === "granted" || p === "denied" || p === "default") setNotifState(p);
    } catch {
      // ignore
    }
  }, [step]);

  useEffect(() => {
    // On successful connect, show a confirmation toast and (optionally) a browser notification.
    if (step !== "done") return;
    if (!connectResult) return;
    setToast("Connected. Pickup details are ready.");
    try {
      const N = (window as any).Notification;
      if (!N) return;
      const perm = N.permission as string;
      if (perm === "granted") {
        new N("You’re connected to the fleet operator", {
          body: `${connectResult.operator.name} • Pickup: ${connectResult.operator.pickup_location}`,
        });
      }
    } catch {
      // ignore
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, connectResult?.request_id]);

  useEffect(() => {
    setError(null);
    if (!session?.token) {
      setStatus(null);
      setStep("auth");
      return;
    }
    refresh()
      .then(() => null)
      .catch(() => null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session?.token]);

  useEffect(() => {
    // Keep auth inputs in sync when session changes (sign-in/out)
    const p = parseE164(session?.phone ?? null);
    if (p) {
      setCountryCode(p.cc);
      setPhoneDigits(p.national);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session?.phone]);

  useEffect(() => {
    if (!session?.token) return;
    if (!status) return;
    const desired = nextFromStatus(status.status);
    if (step === "demand" || step === "connect" || step === "done" || step === "tracking") return;
    setStep(desired);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status?.status, session?.token]);

  useEffect(() => {
    // persist last request id so user can resume tracking later
    if (connectResult?.request_id) {
      localStorage.setItem("eleride.rider.last_request_id", connectResult.request_id);
      setTrackingReqId(connectResult.request_id);
    }
  }, [connectResult?.request_id]);

  useEffect(() => {
    // Poll supply status while on tracking screen
    if (step !== "tracking") return;
    if (!session?.token) return;
    const reqId = trackingReqId || connectResult?.request_id || null;
    if (!reqId) return;

    let alive = true;
    let lastStage = localStorage.getItem(`eleride.rider.stage.${reqId}`) || "";

    async function tick() {
      try {
        setTrackingBusy(true);
        const s = await api.supplyStatus(session!.token, reqId);
        if (!alive) return;
        setSupplyStatus(s);
        setTrackingBusy(false);

        const stage = s.stage?.code || "";
        if (stage && stage !== lastStage) {
          lastStage = stage;
          localStorage.setItem(`eleride.rider.stage.${reqId}`, stage);
          setToast(`Update: ${s.stage.label}`);
          try {
            const N = (window as any).Notification;
            if (N && N.permission === "granted") {
              new N("Eleride: Status update", { body: s.stage.detail || s.stage.label });
            }
          } catch {
            // ignore
          }
        }
      } catch {
        if (!alive) return;
        setTrackingBusy(false);
      }
    }

    tick().catch(() => null);
    const t = window.setInterval(() => tick().catch(() => null), 8000);
    return () => {
      alive = false;
      window.clearInterval(t);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, session?.token, trackingReqId]);

  useEffect(() => {
    // When user enters connect step, refresh the time slots so they’re relevant “right now”.
    if (step !== "connect") return;
    const base = ceilToNextHourEpochMs(new Date());
    setSlotBaseMs(base);
    setPickupStartMs(base);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step]);

  const signedInBadge = useMemo(() => {
    if (!session?.token) return null;
    return `Signed in${session.phone ? `: ${session.phone}` : ""}`;
  }, [session?.token, session?.phone]);

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
    setStatus(null);
    setDemand(null);
    setDemandPolicy(null);
    setSelectedLaneId("");
    setConnectResult(null);
    setOtpRequestId("");
    setOtp("");
    setDevOtp("");
    setGeoReady(false);
    setTrackingReqId("");
    setSupplyStatus(null);
    setStep("auth");
  }

  return (
    <div className="app">
      <div className="phoneFrame">
        <div className="topbar">
          <div className="brand">
            <img className="brandLogo" src={logoPng} alt="Eleride" />
          </div>
          <div className="topbarRight">
            <div className="chip">{signedInBadge ?? (health ? `API: ${health.env}` : "Offline?")}</div>
            {session?.token ? (
              <button type="button" className="btn btnSecondary btnSmall" onClick={signOut}>
                Sign out
              </button>
            ) : null}
          </div>
        </div>

        <div className="content">
          {toast ? <div className="toast">{toast}</div> : null}
          {error ? <div className="error">{error}</div> : null}

          {step === "auth" ? (
            <>
              <div className="hero">
                <img className="heroLogo" src={logoPng} alt="Eleride" />
                <div className="title">Welcome</div>
                <p className="subtitle">Sign in with your phone number to continue.</p>
              </div>

              {session?.token ? (
                <div className="ok">
                  You’re already signed in.
                  <div className="divider" />
                  <div className="row">
                    <button className="btn btnSecondary" onClick={() => setStep(nextFromStatus(status?.status ?? null))}>
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
                            placeholder="9876543210"
                            inputMode="tel"
                            autoComplete="tel-national"
                          />
                        </div>
                      </div>
                      <div className="helper">We’ll send an OTP to {phoneE164}.</div>
                    </div>

                    <button
                      className="btn btnPrimary"
                      disabled={busy || !isNationalNumberish(phoneDigits)}
                      onClick={() =>
                        run(async () => {
                          const r = await api.otpRequest(phoneE164);
                          setOtpRequestId(r.request_id);
                          setDevOtp((r as any).dev_otp ?? "");
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
                        {devOtp ? <div className="helper">Dev OTP: {devOtp}</div> : null}
                      </div>

                      <button
                        className="btn btnPrimary"
                        disabled={busy || otp.trim().length < 4}
                        onClick={() =>
                          run(async () => {
                            const v = await api.otpVerify(otpRequestId, otp.trim());
                            const next = { token: v.access_token, phone: phoneE164 };
                            saveSession(next);
                            setSession(next);
                            setOtp("");
                            setDevOtp("");
                            setOtpRequestId("");
                            const s = await api.riderStatus(next.token);
                            setStatus({ rider_id: s.rider_id, phone: s.phone, status: s.status });
                            setStep(nextFromStatus(s.status));
                          })
                        }
                      >
                        {busy ? "Verifying…" : "Verify & Continue"}
                      </button>
                    </div>
                  ) : null}
                </div>
              )}
            </>
          ) : null}

          {step === "profile" ? (
            <>
              <div className="title">Create your profile</div>
              <p className="subtitle">This helps us match you to the right fleet operator.</p>

              <div className="card stack">
                <div className="row">
                  <div>
                    <label>Full name</label>
                    <input value={profile.name} onChange={(e) => setProfile({ ...profile, name: e.target.value })} />
                  </div>
                  <div>
                    <label>Date of birth</label>
                    <input
                      type="date"
                      value={profile.dob}
                      onChange={(e) => setProfile({ ...profile, dob: e.target.value })}
                    />
                  </div>
                </div>

                <div>
                  <label>Address</label>
                  <textarea
                    value={profile.address}
                    onChange={(e) => setProfile({ ...profile, address: e.target.value })}
                  />
                </div>

                <div className="row">
                  <div>
                    <label>Emergency contact</label>
                    <input
                      value={profile.emergency_contact}
                      onChange={(e) => setProfile({ ...profile, emergency_contact: e.target.value })}
                      inputMode="tel"
                    />
                  </div>
                  <div>
                    <label>Preferred zones</label>
                    <input
                      value={profile.preferred_zones.join(", ")}
                      onChange={(e) =>
                        setProfile({
                          ...profile,
                          preferred_zones: e.target.value
                            .split(",")
                            .map((x) => x.trim())
                            .filter(Boolean),
                        })
                      }
                      placeholder="Kharadi, Hadapsar"
                    />
                  </div>
                </div>

                <button
                  className="btn btnPrimary"
                  disabled={busy || !session?.token}
                  onClick={() =>
                    run(async () => {
                      await api.profileUpsert(session!.token, profile);
                      await refresh();
                      setStep("kyc");
                    })
                  }
                >
                  {busy ? "Saving…" : "Save & Continue"}
                </button>
              </div>

              <div className="footerActions">
                <button className="btn btnSecondary" onClick={signOut}>
                  Sign out
                </button>
              </div>
            </>
          ) : null}

          {step === "kyc" ? (
            <>
              <div className="title">Verify your identity</div>
              <p className="subtitle">For this MVP, verification is a quick mock step.</p>

              <div className="card stack">
                <div className="stack">
                  <div className="tag">Document: Driving License (DL)</div>
                  <div className="helper">
                    In production we’ll capture document images, validate authenticity, and run fraud checks.
                  </div>
                </div>

                <div className="row">
                  <button
                    className="btn btnSecondary"
                    disabled={busy || !session?.token}
                    onClick={() =>
                      run(async () => {
                        await api.kycStart(session!.token);
                        await refresh();
                      })
                    }
                  >
                    Start KYC
                  </button>
                  <button
                    className="btn btnPrimary"
                    disabled={busy || !session?.token}
                    onClick={() =>
                      run(async () => {
                        await api.kycStart(session!.token);
                        await api.kycPass(session!.token);
                        await refresh();
                        setStep("location");
                      })
                    }
                  >
                    {busy ? "Verifying…" : "Verify & Continue"}
                  </button>
                </div>
              </div>

              <div className="footerActions">
                <button className="btn btnSecondary" onClick={() => setStep("profile")}>
                  Back
                </button>
              </div>
            </>
          ) : null}

          {step === "location" ? (
            <>
              <div className="title">Your location</div>
              <p className="subtitle">We’ll show demand opportunities within 5–10 km.</p>

              <div className="stack">
                <div className="card stack">
                  {locationHint ? <div className="helper">{locationHint}</div> : null}
                  <div className="row">
                    <button
                      className="btn btnPrimary"
                      disabled={busy}
                      onClick={() =>
                        run(
                          () =>
                            new Promise<void>((resolve, reject) => {
                              if (!navigator.geolocation) return reject(new Error("Geolocation not supported."));
                              navigator.geolocation.getCurrentPosition(
                                (pos) => {
                                  setGeo((g) => ({
                                    ...g,
                                    lat: pos.coords.latitude,
                                    lon: pos.coords.longitude,
                                  }));
                                  setGeoReady(true);
                                  setLocationHint(
                                    `Location captured: ${pos.coords.latitude.toFixed(5)}, ${pos.coords.longitude.toFixed(5)}`,
                                  );
                                  resolve();
                                },
                                (err) => {
                                  // Don’t hard-fail the flow on denial; provide fallbacks.
                                  const msg =
                                    err?.code === 1
                                      ? "Location access denied. You can still continue using Pune demo or manual location."
                                      : err?.code === 2
                                        ? "Location unavailable. Try again or use Pune demo."
                                        : "Location timed out. Try again or use Pune demo.";
                                  setLocationHint(msg);
                                  // keep the user on this step without triggering global error banner
                                  resolve();
                                },
                                { enableHighAccuracy: true, timeout: 9000, maximumAge: 0 },
                              );
                            }),
                        )
                      }
                    >
                      {busy ? "Locating…" : "Allow location"}
                    </button>
                    <button
                      className="btn btnSecondary"
                      disabled={busy}
                      onClick={() => {
                        setGeo({ lat: 18.5204, lon: 73.8567, radius_km: geo.radius_km });
                        setGeoReady(true);
                        setLocationHint("Using Pune demo location.");
                      }}
                    >
                      Use Pune demo
                    </button>
                  </div>

                  <div className="row">
                    <div>
                      <label>Radius</label>
                      <select
                        value={geo.radius_km}
                        onChange={(e) => setGeo({ ...geo, radius_km: Number(e.target.value) as 5 | 10 })}
                      >
                        <option value={5}>5 km</option>
                        <option value={10}>10 km</option>
                      </select>
                    </div>
                    <div>
                      <label>Lat</label>
                      <input
                        value={geo.lat}
                        onChange={(e) => setGeo({ ...geo, lat: Number(e.target.value) })}
                        inputMode="decimal"
                      />
                    </div>
                    <div>
                      <label>Lon</label>
                      <input
                        value={geo.lon}
                        onChange={(e) => setGeo({ ...geo, lon: Number(e.target.value) })}
                        inputMode="decimal"
                      />
                    </div>
                  </div>

                  <div className="mapFrame">
                    <iframe title="map" src={buildOsmEmbed(geo.lat, geo.lon)} loading="lazy" />
                  </div>

                  <button
                    className="btn btnPrimary"
                    disabled={!geoReady || busy}
                    onClick={() => {
                      setDemand(null);
                      setSelectedLaneId("");
                      setStep("demand");
                    }}
                  >
                    Continue
                  </button>
                </div>
              </div>
            </>
          ) : null}

          {step === "demand" ? (
            <>
              <div className="title">Demand near you</div>
              <p className="subtitle">Choose a location to start onboarding with the fleet operator.</p>

              <div className="stack">
                <div className="card stack">
                  <div className="row">
                    <button
                      className="btn btnPrimary"
                      disabled={busy || !session?.token}
                      onClick={() =>
                        run(async () => {
                          const res = await api.demandNearby(session!.token, geo.lat, geo.lon, geo.radius_km);
                          setDemand(res.cards ?? []);
                        setDemandPolicy(res.policy ?? null);
                          if ((res.cards ?? []).length === 1) setSelectedLaneId(res.cards[0].lane_id);
                        })
                      }
                    >
                      {busy ? "Searching…" : "Find demand near me"}
                    </button>
                    <button className="btn btnSecondary" disabled={busy} onClick={() => setStep("location")}>
                      Edit location
                    </button>
                  </div>

                  {demandPolicy && demandPolicy.allowed === false ? (
                    <div className="card stack">
                      <div className="title" style={{ fontSize: 16 }}>
                        Demand is temporarily locked
                      </div>
                      <div className="helper">
                        You’ve been approved. We’ll hide new demand options for a short cooldown period.
                      </div>
                      {demandPolicy.unlock_at ? (
                        <div className="kvGrid" style={{ marginTop: 8 }}>
                          <div className="kvLabel">Unlocked at</div>
                          <div className="kvValue">{new Date(demandPolicy.unlock_at).toLocaleString()}</div>
                        </div>
                      ) : null}
                    </div>
                  ) : demand && demand.length === 0 ? (
                    <div className="error">No lanes returned.</div>
                  ) : null}

                  {demandPolicy?.allowed === false ? null : demand && demand.length > 0 ? (
                    <div className="list">
                      {featuredLaneId ? (
                        <div className="featuredBadge">
                          <span className="featuredBadgeDot" />
                          Most relevant (best pay + MG)
                        </div>
                      ) : null}
                      {demand.map((c) => (
                        <label
                          key={c.lane_id}
                          className={`demandItem ${featuredLaneId === c.lane_id ? "featured" : ""}`}
                        >
                          <input
                            className="demandRadio"
                            type="radio"
                            name="lane"
                            checked={selectedLaneId === c.lane_id}
                            onChange={() => setSelectedLaneId(c.lane_id)}
                            style={{ position: "absolute", opacity: 0, pointerEvents: "none" }}
                          />

                          <div className="demandMeta" style={{ flex: 1 }}>
                            <div className="demandTop">
                              <div className="demandMain">
                                <div className="demandTitle">{c.qc_name}</div>
                                <div className="metaRow">
                                  <span>{c.distance_km.toFixed(1)} km away</span>
                                  <span>• Shift starts {c.shift_start}</span>
                                </div>
                              </div>
                              <button
                                type="button"
                                className={`selectPill ${selectedLaneId === c.lane_id ? "selectPillSelected" : ""}`}
                                onClick={(e) => {
                                  e.preventDefault();
                                  setSelectedLaneId(c.lane_id);
                                }}
                              >
                                {selectedLaneId === c.lane_id ? "Selected" : "Select"}
                              </button>
                            </div>

                            <div className="bigMoney">{c.earning_range}</div>
                            <div className="mgPill">Minimum Guarantee: {c.minimum_guarantee}</div>

                            <div className="metricsGrid">
                              <div className="metric">
                                <div className="metricLabel">Trips / day (est.)</div>
                                <div className="metricValue">{c.expected_trips_per_day ?? "—"}</div>
                              </div>
                              <div className="metric">
                                <div className="metricLabel">Orders / day (est.)</div>
                                <div className="metricValue">{c.expected_orders_per_day ?? "—"}</div>
                              </div>
                              <div className="metric">
                                <div className="metricLabel">Contract</div>
                                <div className="metricValue">{c.contract_type}</div>
                              </div>
                              <div className="metric">
                                <div className="metricLabel">Slots available</div>
                                <div className="metricValue">{c.slots_available}</div>
                              </div>
                            </div>

                            {c.rank_reasons && c.rank_reasons.length ? (
                              <div className="metaRow" style={{ marginTop: 8 }}>
                                <span className="helper">Why this lane:</span>
                                <span className="helper">{c.rank_reasons.join(" • ")}</span>
                              </div>
                            ) : null}
                          </div>
                        </label>
                      ))}
                    </div>
                  ) : null}

                  <button
                    className="btn btnPrimary"
                    disabled={!selectedLaneId}
                    onClick={() => setStep("connect")}
                  >
                    Continue
                  </button>
                </div>
              </div>
            </>
          ) : null}

          {step === "connect" ? (
            <>
              <div className="title">Connect to fleet operator</div>
              <p className="subtitle">We’ll create your onboarding request and share pickup details.</p>

              <div className="card stack">
                <div className="helper">
                  Selected lane: <b>{selectedLaneId || "—"}</b>
                </div>

                <div>
                  <label>When will you be ready to pick up?</label>
                  <div className="helper">
                    Pick a start time. We’ll automatically reserve a <b>6-hour</b> window from that time (shown in 1-hour steps).
                  </div>
                  <div className="slotScroller" aria-label="Pickup time slots">
                    <div className="slotRow" role="list">
                      {pickupOptions.map((o) => (
                        <button
                          key={o.startMs}
                          type="button"
                          className={`slotChip ${pickupStartMs === o.startMs ? "slotChipActive" : ""}`}
                          onClick={() => setPickupStartMs(o.startMs)}
                          role="listitem"
                          aria-pressed={pickupStartMs === o.startMs}
                        >
                          <div className="slotChipTop">
                            <span className="slotChipDay">{o.startDay}</span>
                            <span className="slotChipTime">{o.startTime}</span>
                          </div>
                          <div className="slotChipSub">
                            6h → {o.endDay === o.startDay ? o.endTime : `${o.endDay} ${o.endTime}`}
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>
                  <div className="selectedWindowPill">
                    Selected window: <b>{selectedTimeWindowLabel}</b>
                  </div>
                </div>

                <div>
                  <label>Documents ready (tick)</label>
                  <div className="docGrid">
                    <label className={`checkCard ${docDL ? "checkCardOn" : ""}`}>
                      <input type="checkbox" checked={docDL} onChange={(e) => setDocDL(e.target.checked)} />
                      <div>
                        <div className="checkTitle">Driving License (DL)</div>
                        <div className="helper">Required for onboarding</div>
                      </div>
                    </label>
                    <label className={`checkCard ${docAadhaar ? "checkCardOn" : ""}`}>
                      <input type="checkbox" checked={docAadhaar} onChange={(e) => setDocAadhaar(e.target.checked)} />
                      <div>
                        <div className="checkTitle">Aadhaar</div>
                        <div className="helper">Identity verification</div>
                      </div>
                    </label>
                  </div>
                </div>

                <div>
                  <label>Notes (optional)</label>
                  <textarea
                    value={connectNotes}
                    onChange={(e) => setConnectNotes(e.target.value)}
                    placeholder="Any preferences (pickup distance, urgency, etc.)…"
                  />
                </div>

                <button
                  className="btn btnPrimary"
                  disabled={busy || !session?.token || !selectedLaneId}
                  onClick={() =>
                    run(async () => {
                      const res = await api.supplyConnect(session!.token, {
                        lane_id: selectedLaneId,
                        time_window: selectedTimeWindowLabel,
                        requirements: composedRequirements || null,
                        rider_lat: geo.lat,
                        rider_lon: geo.lon,
                      });
                      setConnectResult(res);
                      setStep("done");
                    })
                  }
                >
                  {busy ? "Connecting…" : "Connect me"}
                </button>

                <button className="btn btnSecondary" disabled={busy} onClick={() => setStep("demand")}>
                  Back
                </button>
              </div>
            </>
          ) : null}

          {step === "done" ? (
            <>
              <div className="title">You’re connected</div>
              <p className="subtitle">Pickup details are ready. We’ve shared your context with the operator.</p>

              {connectResult ? (
                <div className="card stack">
                  <div className="ok">
                    Connection created successfully.
                    <div className="helper">Next steps are below. Keep this screen for reference.</div>
                  </div>

                  <div className="tag">{connectResult.operator.name}</div>

                  <div className="nextSteps">
                    <div className="nextTitle">What happens next</div>
                    <div className="nextItem">
                      <span className="nextDot" /> Go to the pickup hub during your selected window
                    </div>
                    <div className="nextItem">
                      <span className="nextDot" /> Carry the documents you selected (DL/Aadhaar)
                    </div>
                    <div className="nextItem">
                      <span className="nextDot" /> Operator will complete onboarding + vehicle handover
                    </div>
                  </div>

                  <div>
                    <label>Pickup location</label>
                    <div className="helper">{connectResult.operator.pickup_location}</div>
                  </div>
                  <div>
                    <label>Your pickup window</label>
                    <div className="helper">{selectedTimeWindowLabel}</div>
                  </div>
                  <div>
                    <label>Required documents</label>
                    <div className="stack">
                      {connectResult.operator.required_docs.map((d) => (
                        <div key={d} className="tag">
                          {d}
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="divider" />

                  <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                    <div className="helper">Notifications</div>
                    <button
                      className="btn btnSecondary"
                      type="button"
                      disabled={!("Notification" in window)}
                      onClick={async () => {
                        try {
                          const N = (window as any).Notification;
                          if (!N) return setToast("Notifications not supported on this device.");
                          const p = await N.requestPermission();
                          setNotifState(p);
                          if (p === "granted") {
                            setToast("Notifications enabled.");
                            new N("Notifications enabled", { body: "We’ll alert you on new updates while the app is open." });
                          } else if (p === "denied") {
                            setToast("Notifications blocked. You can enable them from browser settings.");
                          }
                        } catch {
                          setToast("Could not enable notifications.");
                        }
                      }}
                    >
                      {notifState === "granted" ? "Enabled" : "Enable"}
                    </button>
                  </div>

                  <div className="divider" />
                  <div className="row">
                    <button
                      className="btn btnPrimary"
                      onClick={() => {
                        const reqId = connectResult.request_id;
                        if (reqId) {
                          localStorage.setItem("eleride.rider.last_request_id", reqId);
                          setTrackingReqId(reqId);
                        }
                        setToast("Tracking enabled. We’ll keep you updated.");
                        setStep("tracking");
                      }}
                    >
                      Finish & Track
                    </button>
                    <button className="btn btnSecondary" onClick={() => setStep("demand")}>
                      Back to demand
                    </button>
                  </div>
                  <button className="btn btnDanger" onClick={signOut}>
                    Sign out
                  </button>
                </div>
              ) : (
                <div className="error">Missing connect response.</div>
              )}
            </>
          ) : null}

          {step === "tracking" ? (
            <>
              <div className="title">Onboarding status</div>
              <p className="subtitle">We’ll keep checking with the operator and notify you when your status changes.</p>

              <div className="card stack">
                <div className="statusCard stack">
                  <div className="statusTopRow">
                    <div className="statusTitle">{supplyStatus?.stage?.label ?? "Checking status…"}</div>
                    <div className="statusPill">{trackingBusy ? "Live • syncing…" : "Live"}</div>
                  </div>
                  <div className="helper">{supplyStatus?.stage?.detail ?? "This usually takes a few minutes."}</div>
                  <div className="metricsGrid">
                    <div className="metric">
                      <div className="metricLabel">Operator</div>
                      <div className="metricValue">
                        {supplyStatus?.operator_name ?? connectResult?.operator.name ?? supplyStatus?.operator_id ?? "—"}
                      </div>
                    </div>
                    <div className="metric">
                      <div className="metricLabel">Pickup hub</div>
                      <div className="metricValue">{supplyStatus?.pickup_location ?? connectResult?.operator.pickup_location ?? "—"}</div>
                    </div>
                    <div className="metric">
                      <div className="metricLabel">Request ID</div>
                      <div className="metricValue">{(trackingReqId || supplyStatus?.request_id || "—").slice(0, 8)}…</div>
                    </div>
                    <div className="metric">
                      <div className="metricLabel">Last update</div>
                      <div className="metricValue">{supplyStatus?.inbox_updated_at ? new Date(supplyStatus.inbox_updated_at).toLocaleString() : "—"}</div>
                    </div>
                  </div>
                </div>

                {(() => {
                  const code = supplyStatus?.stage?.code ?? "sent";
                  const steps = [
                    { code: "sent", label: "Request sent", detail: "Your request is with the fleet operator." },
                    { code: "verification", label: "Verification", detail: "Operator is verifying documents & details." },
                    { code: "approved", label: "Approved", detail: "You’re approved. Proceed to pickup & onboarding." },
                  ] as const;

                  const isRejected = code === "rejected";
                  const activeIdx = code === "sent" ? 0 : code === "verification" ? 1 : code === "approved" ? 2 : 0;

                  return (
                    <div className="stack">
                      <div style={{ fontWeight: 1000 }}>Progress</div>
                      <div className="stepper">
                        {steps.map((s, i) => {
                          const done = i < activeIdx && !isRejected;
                          const active = i === activeIdx && !isRejected;
                          return (
                            <div key={s.code} className="stepRow">
                              <div className="stepRail">
                                <div className={`stepDot ${done ? "stepDotDone" : ""} ${active ? "stepDotActive" : ""}`} />
                                {i < steps.length - 1 ? <div className="stepLine" /> : null}
                              </div>
                              <div className="stepBody">
                                <div className="stepLabel">{s.label}</div>
                                <div className="stepDetail">{s.detail}</div>
                              </div>
                            </div>
                          );
                        })}
                        {isRejected ? (
                          <div className="stepRow">
                            <div className="stepRail">
                              <div className={`stepDot stepDotActive`} />
                            </div>
                            <div className="stepBody">
                              <div className="stepLabel">Rejected</div>
                              <div className="stepDetail">{supplyStatus?.stage?.detail ?? "The operator couldn’t accept your request."}</div>
                            </div>
                          </div>
                        ) : null}
                      </div>
                    </div>
                  );
                })()}

                <div className="divider" />
                <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                  <div className="helper">Notifications</div>
                  <button
                    className="btn btnSecondary"
                    type="button"
                    disabled={!("Notification" in window)}
                    onClick={async () => {
                      try {
                        const N = (window as any).Notification;
                        if (!N) return setToast("Notifications not supported on this device.");
                        const p = await N.requestPermission();
                        setNotifState(p);
                        if (p === "granted") setToast("Notifications enabled.");
                        else if (p === "denied") setToast("Notifications blocked. Enable them in browser settings.");
                      } catch {
                        setToast("Could not enable notifications.");
                      }
                    }}
                  >
                    {notifState === "granted" ? "Enabled" : "Enable"}
                  </button>
                </div>

                <div className="row">
                  <button
                    className="btn btnSecondary"
                    type="button"
                    disabled={remindTimer != null}
                    onClick={() => {
                      if (remindTimer) window.clearTimeout(remindTimer);
                      const t = window.setTimeout(() => {
                        setToast("Reminder: check your onboarding status.");
                        try {
                          const N = (window as any).Notification;
                          if (N && N.permission === "granted") {
                            new N("Eleride: Reminder", { body: "Check your onboarding status updates." });
                          }
                        } catch {
                          // ignore
                        }
                        setRemindTimer(null);
                      }, 10 * 60 * 1000);
                      setRemindTimer(t);
                      setToast("Okay — we’ll remind you in 10 minutes (while the app is open).");
                    }}
                  >
                    Remind me
                  </button>
                  <button className="btn btnPrimary" onClick={() => setStep("demand")}>
                    Explore demand
                  </button>
                </div>

                <button className="btn btnDanger" onClick={signOut}>
                  Sign out
                </button>
              </div>
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}


