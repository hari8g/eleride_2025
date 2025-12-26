from __future__ import annotations

import argparse
import io
import json
import os
import urllib.parse
from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler
from pathlib import Path
from socketserver import TCPServer

import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve the frontend portal locally (dashboard + scenarios + payslips APIs).")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host to bind (use 0.0.0.0 inside Docker)")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (use 0 to auto-pick a free port)")
    parser.add_argument("--dir", type=str, default="frontend", help="Directory to serve")
    parser.add_argument("--data-dir", type=str, default="Data", help="Directory containing weekly .xlsx payout files")
    args = parser.parse_args()

    project_root = Path.cwd().resolve()
    serve_dir = (project_root / args.dir).expanduser().resolve() if not Path(args.dir).is_absolute() else Path(args.dir).expanduser().resolve()
    if not serve_dir.exists():
        raise FileNotFoundError(f"Directory not found: {serve_dir}")

    data_dir = (project_root / args.data_dir).expanduser().resolve() if not Path(args.data_dir).is_absolute() else Path(args.data_dir).expanduser().resolve()

    @dataclass
    class CacheEntry:
        mtime: float
        df: pd.DataFrame

    excel_cache: dict[str, CacheEntry] = {}

    def list_xlsx_files() -> list[str]:
        if not data_dir.exists():
            return []
        files = sorted([p.name for p in data_dir.glob("*.xlsx") if not p.name.startswith("~$")])
        return files

    def load_excel(filename: str) -> pd.DataFrame:
        # allow only file basenames inside data_dir
        safe = Path(filename).name
        path = data_dir / safe
        if not path.exists():
            raise FileNotFoundError(f"File not found: {safe}")

        mtime = path.stat().st_mtime
        ce = excel_cache.get(safe)
        if ce and ce.mtime == mtime:
            return ce.df

        df = pd.read_excel(path, sheet_name=0, engine="openpyxl")
        df.columns = [str(c).strip() for c in df.columns]
        excel_cache[safe] = CacheEntry(mtime=mtime, df=df)
        return df

    def normalize_id(x: object) -> str:
        """Normalize ids like 756045.0 -> '756045'."""
        if x is None:
            return ""
        try:
            if isinstance(x, float) and pd.isna(x):
                return ""
        except Exception:
            pass
        s = str(x).strip()
        if s.endswith(".0"):
            s2 = s[:-2]
            if s2.isdigit():
                return s2
        # if it's a float string like '756045.0'
        try:
            fv = float(s)
            if fv.is_integer():
                return str(int(fv))
        except Exception:
            pass
        return s

    def pick_cols(df: pd.DataFrame, cols: list[str]) -> list[str]:
        existing = [c for c in cols if c in df.columns]
        return existing

    def infer_week_label(df: pd.DataFrame) -> str:
        for c in ["week_id", "week", "month", "year"]:
            if c in df.columns:
                pass
        if all(c in df.columns for c in ["year", "month", "week"]):
            y = int(df["year"].dropna().iloc[0]) if not df["year"].dropna().empty else None
            m = int(df["month"].dropna().iloc[0]) if not df["month"].dropna().empty else None
            w = int(df["week"].dropna().iloc[0]) if not df["week"].dropna().empty else None
            if y and m and w:
                return f"{y}-{m:02d}-W{w}"
        return ""

    def build_payslip_row(df: pd.DataFrame, cee_id: str) -> dict:
        if "cee_id" not in df.columns:
            raise ValueError("Sheet missing cee_id column")
        target = normalize_id(cee_id)
        sub = df[df["cee_id"].map(normalize_id) == target].copy()
        if sub.empty:
            raise FileNotFoundError(f"Rider cee_id not found in sheet: {cee_id}")

        # If multiple rows (e.g. multiple stores), aggregate numeric and keep representative text fields.
        numeric_cols = [c for c in sub.columns if pd.api.types.is_numeric_dtype(sub[c])]
        text_cols = [c for c in sub.columns if c not in numeric_cols]

        agg = {}
        for c in numeric_cols:
            agg[c] = float(pd.to_numeric(sub[c], errors="coerce").fillna(0).sum())
        for c in text_cols:
            # take first non-null
            s = sub[c].dropna()
            agg[c] = s.iloc[0] if not s.empty else None

        # Normalize key sections
        key = {
            "cee_id": normalize_id(agg.get("cee_id")),
            "cee_name": agg.get("cee_name"),
            "pan": agg.get("pan"),
            "city": agg.get("city"),
            "store": agg.get("store"),
            "delivery_mode": agg.get("delivery_mode"),
            "lmd_provider": agg.get("lmd_provider"),
            "rate_card_id": agg.get("rate_card_id"),
            "settlement_frequency": agg.get("settlement_frequency"),
            "period": infer_week_label(df),
        }

        ops = {
            "delivered_orders": agg.get("delivered_orders", 0.0),
            "cancelled_orders": agg.get("cancelled_orders", 0.0),
            "weekday_orders": agg.get("weekday_orders", 0.0),
            "weekend_orders": agg.get("weekend_orders", 0.0),
            "attendance": agg.get("attendance", 0.0),
            "distance": agg.get("distance", 0.0),
        }

        pay = {
            "base_pay": agg.get("base_pay", 0.0),
            "incentive_total": agg.get("incentive_total", 0.0),
            "arrears_amount": agg.get("arrears_amount", 0.0),
            "deductions_amount": agg.get("deductions_amount", 0.0),
            "management_fee": agg.get("management_fee", 0.0),
            "gst": agg.get("gst", 0.0),
            "final_with_gst": agg.get("final_with_gst", 0.0),
            "final_with_gst_minus_settlement": agg.get("final_with_gst_minus_settlement", 0.0),
        }

        # Useful derived totals
        gross = float(pay["base_pay"] + pay["incentive_total"] + pay.get("arrears_amount", 0.0))
        net = float(pay.get("final_with_gst_minus_settlement", pay.get("final_with_gst", 0.0)))
        pay["gross_earnings_est"] = gross
        pay["net_payout"] = net

        return {"identity": key, "ops": ops, "pay": pay}

    def render_pdf(payslip: dict) -> bytes:
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        width, height = A4
        ident = payslip.get("identity", {})
        ops = payslip.get("ops", {})
        pay = payslip.get("pay", {})

        # Colors (match frontend feel)
        brand_blue = colors.Color(37 / 255, 99 / 255, 235 / 255)
        brand_green = colors.Color(5 / 255, 150 / 255, 105 / 255)
        brand_orange = colors.Color(217 / 255, 119 / 255, 6 / 255)
        brand_red = colors.Color(220 / 255, 38 / 255, 38 / 255)
        soft_bg = colors.Color(37 / 255, 99 / 255, 235 / 255, alpha=0.06)
        gray = colors.Color(107 / 255, 114 / 255, 128 / 255)
        border = colors.Color(17 / 255, 24 / 255, 39 / 255, alpha=0.12)

        def money(x: object) -> str:
            try:
                v = float(x or 0)
                return f"₹{v:,.0f}"
            except Exception:
                return "—"

        def pct(x: float, d: int = 1) -> str:
            try:
                return f"{(float(x) * 100):.{d}f}%"
            except Exception:
                return "—"

        # Derived ops + pay
        delivered = int(ops.get("delivered_orders", 0) or 0)
        cancelled = int(ops.get("cancelled_orders", 0) or 0)
        weekday = int(ops.get("weekday_orders", 0) or 0)
        weekend = int(ops.get("weekend_orders", 0) or 0)
        attendance = float(ops.get("attendance", 0) or 0)
        distance = float(ops.get("distance", 0) or 0)
        total_orders = max(0, delivered + cancelled)
        cancel_rate = (cancelled / total_orders) if total_orders else 0.0
        weekend_share = (weekend / (weekday + weekend)) if (weekday + weekend) else 0.0

        base = float(pay.get("base_pay", 0) or 0)
        inc = float(pay.get("incentive_total", 0) or 0)
        arrears = float(pay.get("arrears_amount", 0) or 0)
        gross = float(pay.get("gross_earnings_est", base + inc + arrears) or 0)
        ded = float(pay.get("deductions_amount", 0) or 0)
        mgmt = float(pay.get("management_fee", 0) or 0)
        gst = float(pay.get("gst", 0) or 0)
        fees = float(ded + mgmt + gst)
        net = float(pay.get("net_payout", pay.get("final_with_gst_minus_settlement", 0)) or 0)

        period = ident.get("period", "") or ""

        # --- helpers for layout ---
        margin_x = 18 * mm
        y_top = height - 18 * mm
        page_w = width - 2 * margin_x

        def rr(x, y, w, h, r=6 * mm, fill=1, stroke=1):
            c.roundRect(x, y, w, h, r, stroke=stroke, fill=fill)

        def draw_chip(x, y, text, kind=""):
            # kind: good/warn/bad/neutral
            pad_x = 3.2 * mm
            pad_y = 2.0 * mm
            c.setFont("Helvetica-Bold", 8.5)
            tw = c.stringWidth(text, "Helvetica-Bold", 8.5)
            w = tw + 2 * pad_x
            h = 6.8 * mm
            if kind == "good":
                bg = colors.Color(5 / 255, 150 / 255, 105 / 255, alpha=0.10)
                bd = colors.Color(5 / 255, 150 / 255, 105 / 255, alpha=0.25)
            elif kind == "warn":
                bg = colors.Color(217 / 255, 119 / 255, 6 / 255, alpha=0.10)
                bd = colors.Color(217 / 255, 119 / 255, 6 / 255, alpha=0.25)
            elif kind == "bad":
                bg = colors.Color(220 / 255, 38 / 255, 38 / 255, alpha=0.08)
                bd = colors.Color(220 / 255, 38 / 255, 38 / 255, alpha=0.22)
            else:
                bg = colors.Color(17 / 255, 24 / 255, 39 / 255, alpha=0.04)
                bd = border
            c.setFillColor(bg)
            c.setStrokeColor(bd)
            rr(x, y, w, h, r=999, fill=1, stroke=1)
            c.setFillColor(colors.Color(17 / 255, 24 / 255, 39 / 255, alpha=0.92))
            c.drawString(x + pad_x, y + pad_y, text)
            return w

        def draw_kpi(x, y, w, label, value, accent=None):
            h = 18 * mm
            c.setFillColor(colors.white)
            c.setStrokeColor(border)
            rr(x, y, w, h, r=5 * mm, fill=1, stroke=1)
            c.setFillColor(gray)
            c.setFont("Helvetica-Bold", 8.5)
            c.drawString(x + 4.2 * mm, y + h - 6.2 * mm, label)
            c.setFont("Helvetica-Bold", 14)
            if accent is not None:
                c.setFillColor(accent)
            else:
                c.setFillColor(colors.Color(17 / 255, 24 / 255, 39 / 255, alpha=0.92))
            c.drawString(x + 4.2 * mm, y + 5.4 * mm, value)
            c.setFillColor(colors.black)
            return h

        # --- HERO (logo + title + badges) ---
        hero_h = 34 * mm
        hero_y = y_top - hero_h
        c.setFillColor(colors.Color(37 / 255, 99 / 255, 235 / 255, alpha=0.06))
        c.setStrokeColor(border)
        rr(margin_x, hero_y, page_w, hero_h, r=6 * mm, fill=1, stroke=1)

        # logo
        logo_candidates = [
            serve_dir / "assets" / "eleride_logo.jpeg",
            serve_dir / "assets" / "eleride_logo.jpg",
            serve_dir / "assets" / "eleride_logo.png",
        ]
        logo_path = next((p for p in logo_candidates if p.exists()), None)
        if logo_path:
            try:
                img = ImageReader(str(logo_path))
                c.drawImage(img, margin_x + 5 * mm, hero_y + hero_h - 16 * mm, width=14 * mm, height=14 * mm, mask="auto")
            except Exception:
                pass

        c.setFillColor(colors.Color(17 / 255, 24 / 255, 39 / 255, alpha=0.92))
        c.setFont("Helvetica-Bold", 12)
        c.drawString(margin_x + 21 * mm, hero_y + hero_h - 11.5 * mm, "Payslip")
        c.setFillColor(gray)
        c.setFont("Helvetica", 8.5)
        c.drawString(margin_x + 21 * mm, hero_y + hero_h - 16.8 * mm, "System generated • INR (₹)")

        rider_name = str(ident.get("cee_name") or "—")
        rider_id = str(ident.get("cee_id") or "—")
        city = str(ident.get("city") or "—")
        mode = str(ident.get("delivery_mode") or "—")
        store = str(ident.get("store") or "—")
        provider = str(ident.get("lmd_provider") or "—")

        c.setFillColor(colors.Color(17 / 255, 24 / 255, 39 / 255, alpha=0.92))
        c.setFont("Helvetica-Bold", 13)
        c.drawString(margin_x + 5 * mm, hero_y + hero_h - 23.5 * mm, rider_name)
        c.setFillColor(gray)
        c.setFont("Helvetica", 9)
        c.drawString(margin_x + 5 * mm, hero_y + hero_h - 29 * mm, f"Period: {period}  •  Rider ID: {rider_id}  •  City: {city}")
        c.setFont("Helvetica", 8.5)
        c.drawString(margin_x + 5 * mm, hero_y + hero_h - 33.3 * mm, f"Mode: {mode}  •  Store: {store}  •  Provider: {provider}")

        # badges row (same logic as frontend)
        badges: list[tuple[str, str]] = []
        if delivered >= 200:
            badges.append(("good", "Top Performer  200+ deliveries"))
        elif delivered >= 120:
            badges.append(("good", "Strong Week  120+ deliveries"))
        else:
            badges.append(("neutral", f"Deliveries  {delivered}"))

        if attendance >= 6:
            badges.append(("good", f"Consistency  {int(attendance)} days worked"))
        elif attendance >= 4:
            badges.append(("warn", f"Regular  {int(attendance)} days worked"))
        else:
            badges.append(("warn", f"Low days  {int(attendance)}"))

        if weekend_share >= 0.35:
            badges.append(("good", f"Weekend Warrior  {pct(weekend_share)}"))
        else:
            badges.append(("neutral", f"Weekend share  {pct(weekend_share)}"))

        if cancel_rate <= 0.02:
            badges.append(("good", f"Clean Ops  cancel {pct(cancel_rate)}"))
        elif cancel_rate <= 0.06:
            badges.append(("warn", f"Watchlist  cancel {pct(cancel_rate)}"))
        else:
            badges.append(("bad", f"High cancels  cancel {pct(cancel_rate)}"))

        bx = margin_x + 5 * mm
        by = hero_y + 4.4 * mm
        for kind, text in badges:
            bw = draw_chip(bx, by, text, kind=("good" if kind == "good" else "warn" if kind == "warn" else "bad" if kind == "bad" else ""))
            bx += bw + 2.4 * mm
            if bx > margin_x + page_w - 40 * mm:
                break

        # --- KPI tiles ---
        y = hero_y - 6 * mm
        kpi_gap = 3.5 * mm
        kpi_w = (page_w - 3 * kpi_gap) / 4.0
        kpi_h = 18 * mm
        y_kpi1 = y - kpi_h

        draw_kpi(margin_x + 0 * (kpi_w + kpi_gap), y_kpi1, kpi_w, "Net payout (₹)", money(net), accent=brand_green)
        draw_kpi(margin_x + 1 * (kpi_w + kpi_gap), y_kpi1, kpi_w, "Gross earnings (₹)", money(gross))
        draw_kpi(margin_x + 2 * (kpi_w + kpi_gap), y_kpi1, kpi_w, "Deductions+fees+GST (₹)", money(fees), accent=brand_red)
        draw_kpi(margin_x + 3 * (kpi_w + kpi_gap), y_kpi1, kpi_w, "Delivered orders", f"{delivered}")

        y_kpi2 = y_kpi1 - 4.2 * mm - kpi_h
        draw_kpi(margin_x + 0 * (kpi_w + kpi_gap), y_kpi2, kpi_w, "Attendance (days)", f"{int(attendance)}")
        draw_kpi(margin_x + 1 * (kpi_w + kpi_gap), y_kpi2, kpi_w, "Weekend share", pct(weekend_share))
        draw_kpi(margin_x + 2 * (kpi_w + kpi_gap), y_kpi2, kpi_w, "Cancel rate", pct(cancel_rate))
        draw_kpi(margin_x + 3 * (kpi_w + kpi_gap), y_kpi2, kpi_w, "Distance (km)", f"{distance:.2f}")

        # --- Payout section: bar + table ---
        y_sec_top = y_kpi2 - 8 * mm
        sec_h = 70 * mm
        sec_y = y_sec_top - sec_h
        c.setFillColor(colors.white)
        c.setStrokeColor(border)
        rr(margin_x, sec_y, page_w, sec_h, r=6 * mm, fill=1, stroke=1)

        c.setFillColor(colors.Color(17 / 255, 24 / 255, 39 / 255, alpha=0.92))
        c.setFont("Helvetica-Bold", 11)
        c.drawString(margin_x + 5 * mm, y_sec_top - 8 * mm, "Payout breakdown")
        c.setFillColor(gray)
        c.setFont("Helvetica", 8.5)
        c.drawString(margin_x + 5 * mm, y_sec_top - 13 * mm, "Visual split of earnings vs fees (INR ₹).")

        # bar
        bar_x = margin_x + 5 * mm
        bar_y = y_sec_top - 22 * mm
        bar_w = page_w - 10 * mm
        bar_h = 7 * mm
        c.setFillColor(colors.Color(17 / 255, 24 / 255, 39 / 255, alpha=0.06))
        c.setStrokeColor(border)
        rr(bar_x, bar_y, bar_w, bar_h, r=999, fill=1, stroke=1)

        total_bar = max(1.0, base + inc + arrears + max(0.0, fees))
        w_base = bar_w * (base / total_bar)
        w_inc = bar_w * (inc / total_bar)
        w_arr = bar_w * (arrears / total_bar)
        w_fees = bar_w * (max(0.0, fees) / total_bar)

        cur = bar_x
        c.setStrokeColor(colors.transparent)
        if w_base > 0:
            c.setFillColor(colors.Color(37 / 255, 99 / 255, 235 / 255, alpha=0.65))
            c.rect(cur, bar_y, w_base, bar_h, stroke=0, fill=1)
            cur += w_base
        if w_inc > 0:
            c.setFillColor(colors.Color(5 / 255, 150 / 255, 105 / 255, alpha=0.65))
            c.rect(cur, bar_y, w_inc, bar_h, stroke=0, fill=1)
            cur += w_inc
        if w_arr > 0:
            c.setFillColor(colors.Color(217 / 255, 119 / 255, 6 / 255, alpha=0.65))
            c.rect(cur, bar_y, w_arr, bar_h, stroke=0, fill=1)
            cur += w_arr
        if w_fees > 0:
            c.setFillColor(colors.Color(220 / 255, 38 / 255, 38 / 255, alpha=0.45))
            c.rect(cur, bar_y, w_fees, bar_h, stroke=0, fill=1)

        # legend
        leg_y = bar_y - 8.5 * mm
        c.setFont("Helvetica-Bold", 8.5)
        c.setFillColor(gray)
        legend_items = [
            ("Base", colors.Color(37 / 255, 99 / 255, 235 / 255, alpha=0.65)),
            ("Incentives", colors.Color(5 / 255, 150 / 255, 105 / 255, alpha=0.65)),
            ("Arrears", colors.Color(217 / 255, 119 / 255, 6 / 255, alpha=0.65)),
            ("Fees/GST", colors.Color(220 / 255, 38 / 255, 38 / 255, alpha=0.45)),
        ]
        lx = bar_x
        for name, col in legend_items:
            c.setFillColor(col)
            rr(lx, leg_y, 4 * mm, 4 * mm, r=1.5 * mm, fill=1, stroke=0)
            c.setFillColor(gray)
            c.drawString(lx + 5.6 * mm, leg_y + 0.3 * mm, name)
            lx += 26 * mm

        # payout table rows
        table_x = bar_x
        table_y_top = leg_y - 8 * mm
        c.setStrokeColor(border)
        c.setFillColor(colors.Color(17 / 255, 24 / 255, 39 / 255, alpha=0.04))
        rr(table_x, table_y_top - 7 * mm, bar_w, 7 * mm, r=3 * mm, fill=1, stroke=1)
        c.setFillColor(gray)
        c.setFont("Helvetica-Bold", 8.5)
        c.drawString(table_x + 3 * mm, table_y_top - 4.9 * mm, "Component")
        c.drawRightString(table_x + bar_w - 3 * mm, table_y_top - 4.9 * mm, "Amount (₹)")

        rows = [
            ("Base pay", money(base)),
            ("Incentives", money(inc)),
            ("Arrears", money(arrears)),
            ("Gross earnings (est.)", money(gross)),
            ("Deductions", money(ded)),
            ("Management fee", money(mgmt)),
            ("GST", money(gst)),
            ("Net payout", money(net)),
        ]
        c.setFont("Helvetica", 9)
        yrow = table_y_top - 12 * mm
        line_h = 6.2 * mm
        for i, (k, v) in enumerate(rows):
            if yrow < sec_y + 8 * mm:
                break
            if k == "Net payout":
                c.setFont("Helvetica-Bold", 10)
                c.setFillColor(brand_blue)
            elif k == "Gross earnings (est.)":
                c.setFont("Helvetica-Bold", 9.5)
                c.setFillColor(colors.Color(17 / 255, 24 / 255, 39 / 255, alpha=0.92))
            else:
                c.setFont("Helvetica", 9)
                c.setFillColor(colors.Color(17 / 255, 24 / 255, 39 / 255, alpha=0.92))

            c.drawString(table_x + 3 * mm, yrow, k)
            c.drawRightString(table_x + bar_w - 3 * mm, yrow, v)
            c.setStrokeColor(colors.Color(17 / 255, 24 / 255, 39 / 255, alpha=0.08))
            c.line(table_x + 3 * mm, yrow - 2.2 * mm, table_x + bar_w - 3 * mm, yrow - 2.2 * mm)
            yrow -= line_h

        # Footer thank you (matches web)
        footer_y = 12 * mm
        c.setFillColor(soft_bg)
        rr(margin_x, footer_y + 8 * mm, page_w, 14 * mm, r=6 * mm, fill=1, stroke=0)
        c.setFont("Helvetica-Bold", 9.5)
        c.setFillColor(brand_blue)
        c.drawString(margin_x + 5 * mm, footer_y + 17.5 * mm, "Thank you for riding with eleRide.")
        c.setFont("Helvetica", 8)
        c.setFillColor(gray)
        c.drawString(margin_x + 5 * mm, footer_y + 13 * mm, f"This payslip is system generated. Rider ID {rider_id} • Period {period}")
        c.setFillColor(colors.black)

        c.showPage()
        c.save()
        return buf.getvalue()

    class PortalHandler(SimpleHTTPRequestHandler):
        # serve files relative to frontend dir
        def do_GET(self):  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            qs = urllib.parse.parse_qs(parsed.query)

            if path == "/api/data-files":
                files = list_xlsx_files()
                payload = {"data_dir": str(data_dir), "files": files}
                body = json.dumps(payload).encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if path == "/api/riders":
                file = (qs.get("file") or [""])[0]
                df = load_excel(file)
                if "cee_id" not in df.columns:
                    raise ValueError("Sheet missing cee_id")
                cols = pick_cols(df, ["cee_id", "cee_name", "pan", "city", "store"])
                riders = df[cols].copy()
                riders["cee_id"] = riders["cee_id"].map(normalize_id)
                riders = riders.drop_duplicates(subset=["cee_id"]).sort_values("cee_id")
                payload = {"file": Path(file).name, "count": int(riders.shape[0]), "riders": riders.where(pd.notnull(riders), None).to_dict(orient="records")}
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if path == "/api/payslip":
                file = (qs.get("file") or [""])[0]
                cee_id = (qs.get("cee_id") or [""])[0]
                df = load_excel(file)
                payslip = build_payslip_row(df, cee_id)
                body = json.dumps(payslip, ensure_ascii=False).encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if path == "/api/payslip.pdf":
                file = (qs.get("file") or [""])[0]
                cee_id = (qs.get("cee_id") or [""])[0]
                df = load_excel(file)
                payslip = build_payslip_row(df, cee_id)
                pdf = render_pdf(payslip)
                fn = f"payslip_{Path(file).stem}_{cee_id}.pdf".replace(" ", "_")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Disposition", f'attachment; filename="{fn}"')
                self.send_header("Content-Length", str(len(pdf)))
                self.end_headers()
                self.wfile.write(pdf)
                return

            return super().do_GET()

        def log_message(self, format, *args):  # noqa: A002
            # quieter logs
            return super().log_message(format, *args)

    os.chdir(serve_dir)
    class ReusableTCPServer(TCPServer):
        allow_reuse_address = True

    handler = PortalHandler

    # If the port is busy, try a few subsequent ports. If port=0, let OS pick.
    host = str(args.host)
    port = int(args.port)
    last_err: OSError | None = None
    for attempt in range(0, 20):
        try_port = 0 if port == 0 else port + attempt
        try:
            with ReusableTCPServer((host, try_port), handler) as httpd:
                actual_port = httpd.server_address[1]
                print(f"Serving {serve_dir} at http://{host}:{actual_port}", flush=True)
                print("Open the URL in your browser. Ctrl+C to stop.", flush=True)
                httpd.serve_forever()
                return 0
        except OSError as e:
            last_err = e
            continue

    raise OSError(f"Could not bind to port {port} (or next 19 ports). Last error: {last_err}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())


