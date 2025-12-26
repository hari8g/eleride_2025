"""PDF generation for payslips."""
import io
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


def render_pdf(payslip: dict) -> bytes:
    """Render payslip as PDF."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    ident = payslip.get("identity", {})
    ops = payslip.get("ops", {})
    pay = payslip.get("pay", {})

    # Colors
    brand_blue = colors.Color(37 / 255, 99 / 255, 235 / 255)
    brand_green = colors.Color(5 / 255, 150 / 255, 105 / 255)
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

    # Derived values
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

    # Layout helpers
    margin_x = 18 * mm
    y_top = height - 18 * mm
    page_w = width - 2 * margin_x

    def rr(x, y, w, h, r=6 * mm, fill=1, stroke=1):
        c.roundRect(x, y, w, h, r, stroke=stroke, fill=fill)

    # Hero section
    hero_h = 34 * mm
    hero_y = y_top - hero_h
    c.setFillColor(colors.Color(37 / 255, 99 / 255, 235 / 255, alpha=0.06))
    c.setStrokeColor(border)
    rr(margin_x, hero_y, page_w, hero_h, r=6 * mm, fill=1, stroke=1)

    c.setFillColor(colors.Color(17 / 255, 24 / 255, 39 / 255, alpha=0.92))
    c.setFont("Helvetica-Bold", 12)
    c.drawString(margin_x + 5 * mm, hero_y + hero_h - 11.5 * mm, "Payslip")
    c.setFillColor(gray)
    c.setFont("Helvetica", 8.5)
    c.drawString(margin_x + 5 * mm, hero_y + hero_h - 16.8 * mm, "System generated • INR (₹)")

    rider_name = str(ident.get("cee_name") or "—")
    rider_id = str(ident.get("cee_id") or "—")
    city = str(ident.get("city") or "—")

    c.setFillColor(colors.Color(17 / 255, 24 / 255, 39 / 255, alpha=0.92))
    c.setFont("Helvetica-Bold", 13)
    c.drawString(margin_x + 5 * mm, hero_y + hero_h - 23.5 * mm, rider_name)
    c.setFillColor(gray)
    c.setFont("Helvetica", 9)
    c.drawString(margin_x + 5 * mm, hero_y + hero_h - 29 * mm, f"Period: {period}  •  Rider ID: {rider_id}  •  City: {city}")

    # Simple summary
    y = hero_y - 6 * mm
    c.setFont("Helvetica-Bold", 14)
    c.setFillColor(brand_green)
    c.drawString(margin_x + 5 * mm, y, f"Net Payout: {money(net)}")
    c.setFont("Helvetica", 10)
    c.setFillColor(gray)
    c.drawString(margin_x + 5 * mm, y - 8 * mm, f"Gross: {money(gross)}  •  Fees: {money(fees)}  •  Orders: {delivered}")

    # Footer
    footer_y = 12 * mm
    c.setFillColor(soft_bg)
    rr(margin_x, footer_y + 8 * mm, page_w, 14 * mm, r=6 * mm, fill=1, stroke=0)
    c.setFont("Helvetica-Bold", 9.5)
    c.setFillColor(brand_blue)
    c.drawString(margin_x + 5 * mm, footer_y + 17.5 * mm, "Thank you for riding with eleRide.")
    c.setFont("Helvetica", 8)
    c.setFillColor(gray)
    c.drawString(margin_x + 5 * mm, footer_y + 13 * mm, f"Rider ID {rider_id} • Period {period}")

    c.showPage()
    c.save()
    return buf.getvalue()
