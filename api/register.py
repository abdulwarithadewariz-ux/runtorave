import json, os, random, smtplib, ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone
from urllib.parse import urlparse

def db():
    import psycopg
    return psycopg.connect(os.environ["DATABASE_URL"])

SQL = """CREATE TABLE IF NOT EXISTS rtr_registrations (
 id SERIAL PRIMARY KEY,
 bib INTEGER UNIQUE,
 ticket_id TEXT, ticket_name TEXT,
 payment_status TEXT DEFAULT 'pending',
 fleexi_waitlist TEXT,
 submitted_at TIMESTAMPTZ,
 data JSONB,
 label TEXT,
 email TEXT
)"""

def handler(event, context):
    method = event.get("httpMethod", "GET")
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Content-Type": "application/json",
    }
    if method == "OPTIONS":
        return {"statusCode": 204, "headers": headers}
    if method != "POST":
        return {"statusCode": 405, "headers": headers, "body": json.dumps({"error": "POST only"})}
    body = json.loads(event.get("body") or "{}")
    data = body.get("data") or {}
    labels = {k: v for k, v in body.items() if k not in ("data", "ticket", "ticket_name", "submitted_at")}
    email = data.get("email") or labels.get("Email address") or ""
    first = (data.get("full_name") or labels.get("Full name (as it should appear on your race bib)") or "Runner").split()[0]
    fleexi = data.get("fleexi") or labels.get("Would you like to join the Fleexi early access waitlist?") or ""

    try:
        with db() as conn, conn.cursor() as cur:
            cur.execute(SQL)
            bib = allocate(cur)
            cur.execute(
                "INSERT INTO rtr_registrations (bib,ticket_id,ticket_name,payment_status,fleexi_waitlist,submitted_at,data,label,email) "
                "VALUES (%s,%s,%s,'pending',%s,%s,%s,%s,%s) RETURNING id",
                (bib, body.get("ticket"), body.get("ticket_name"), fleexi,
                 datetime.now(timezone.utc), json.dumps(data), json.dumps(labels, ensure_ascii=False), email))
            rid = cur.fetchone()[0]
        send_confirmation(email, first, bib)
        return {"statusCode": 200, "headers": headers,
                "body": json.dumps({"ok": True, "id": rid, "bib": bib})}
    except DuplicateBib as e:
        return {"statusCode": 409, "headers": headers, "body": json.dumps({"error": str(e)})}
    except Exception as e:
        return {"statusCode": 500, "headers": headers, "body": json.dumps({"error": "Could not save registration", "detail": str(e)[:200]})}

class DuplicateBib(Exception):
    pass

def allocate(cur):
    # random unique bib in 100-200; guard against exhaustion
    used = {r[0] for r in cur.execute("SELECT bib FROM rtr_registrations WHERE bib IS NOT NULL").fetchall()}
    free = [n for n in range(100, 201) if n not in used]
    if not free:
        raise DuplicateBib("All 101 bib numbers are taken. Registration closed.")
    return random.choice(free)

def send_confirmation(email, first, bib):
    host = os.environ.get("SMTP_HOST"); user = os.environ.get("SMTP_USER"); pwd = os.environ.get("SMTP_PASSWORD")
    if not (host and user and pwd and email):
        return
    waitlist = "https://fleexi.africa/#waitlist"
    html = f"""<div style="font-family:Arial,sans-serif;max-width:560px;margin:auto;color:#1c1430">
<h2 style="color:#ff2e93">You're officially in, {first}! 🎉</h2>
<p>Thank you for registering for <b>RUN TO RAVE 2026</b>, brought to you by <b>Men That Cook</b>.<br>
Your registration is confirmed.</p>
<table style="background:#f6f2fb;border-radius:12px;padding:14px 18px;width:100%;line-height:1.8">
<tr><td><b>Event</b></td><td>Run to Rave 2026</td></tr>
<tr><td><b>Date</b></td><td>Monday, 28 December 2026</td></tr>
<tr><td><b>Location</b></td><td>Kaduna</td></tr>
<tr><td><b>Your Bib Number</b></td><td style="font-size:1.3em;color:#ff2e93"><b>{bib}</b></td></tr>
<tr><td><b>Status</b></td><td>Registered — complete payment to fully confirm</td></tr>
</table>
<p><b>What's next?</b><br>We'll share the route, meeting point, schedule and what to bring as we get closer to the day. Keep your bib number safe!</p>
<p>Follow Men That Cook: Instagram <b>@mtc_lifestyle</b> · Facebook <b>Men That Cook</b> · TikTok <b>@men.that.cook</b></p>
<div style="background:#120b22;color:#f3eefc;border-radius:12px;padding:16px 18px;margin:14px 0">
<b style="color:#ffb02e">A ₦50,000 CASH PRIZE IS UP FOR GRABS!</b>
<p>Want to win ₦50,000 at Run to Rave? Join the Fleexi waitlist and stand a chance to take home the cash prize.</p>
<p><a href="{waitlist}" style="background:#ff2e93;color:#fff;padding:10px 18px;border-radius:999px;text-decoration:none;font-weight:bold">JOIN THE FLEEXI WAITLIST</a></p>
<p style="font-size:.85em;color:#a99fc0">Powered by Fleexi.</p>
</div>
<p>See you on 28 December!<br><b>MEN THAT COOK</b><br><span style="color:#a99fc0">Eat Well. Move Well. Live Well.<br>Run to Rave 2026 | Gym &amp; Juice by MTC</span></p>
</div>"""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "You're In! Your Run to Rave 2026 Registration Is Confirmed!"
    msg["From"] = f"Men That Cook | Run to Rave 2026 <{user}>"
    msg["To"] = email
    msg.attach(MIMEText(f"Hello {first}, your Run to Rave 2026 registration is confirmed. Bib number: {bib}. Join the Fleexi waitlist for a chance to win N50,000: {waitlist}", "plain"))
    msg.attach(MIMEText(html, "html"))
    ctx = ssl.create_default_context()
    port = int(os.environ.get("SMTP_PORT", "587"))
    with smtplib.SMTP(host, port) as s:
        s.starttls(context=ctx); s.login(user, pwd); s.send_message(msg)
