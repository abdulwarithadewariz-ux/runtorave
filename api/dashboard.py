import csv, io, json, os, secrets

def handler(event, context):
    qs = event.get("queryStringParameters") or {}
    key = qs.get("key", "")
    admin_key = os.environ.get("ADMIN_KEY", "")
    if not admin_key or not secrets.compare_digest(key, admin_key):
        return {"statusCode": 401, "headers": {"Content-Type": "text/plain"}, "body": "Unauthorized. Add ?key=YOUR_ADMIN_KEY"}
    want_csv = qs.get("format") == "csv"
    import psycopg
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn, conn.cursor() as cur:
        cur.execute("SELECT id, bib, ticket_name, payment_status, fleexi_waitlist, submitted_at, label, email FROM rtr_registrations ORDER BY id DESC")
        rows = cur.fetchall()
    cols = ["id", "bib", "ticket", "payment_status", "fleexi_waitlist", "submitted_at", "answers", "email"]
    if want_csv:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(cols)
        for r in rows:
            w.writerow([json.dumps(c, ensure_ascii=False) if isinstance(c, dict) else c for c in r])
        return {"statusCode": 200, "headers": {"Content-Type": "text/csv", "Content-Disposition": "attachment; filename=run-to-rave-registrations.csv"}, "body": buf.getvalue()}
    data = [dict(zip(cols, r)) for r in rows]
    data = [{**d, "submitted_at": d["submitted_at"].isoformat() if d["submitted_at"] else None} for d in data]
    paid = sum(1 for d in data if d["payment_status"] == "paid")
    fleexi = sum(1 for d in data if "sign me up" in (d["fleexi_waitlist"] or "").lower())
    return {"statusCode": 200, "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"total": len(data), "paid": paid, "fleexi_waitlist": fleexi, "registrations": data}, ensure_ascii=False, default=str)}
