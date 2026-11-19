import { Pool } from 'pg';
import nodemailer from 'nodemailer';
import crypto from 'crypto';

const pool = new Pool({ connectionString: process.env.DATABASE_URL, ssl: { rejectUnauthorized: false } });
const SQL = `CREATE TABLE IF NOT EXISTS rtr_registrations (
 id SERIAL PRIMARY KEY,
 bib INTEGER UNIQUE,
 ticket_id TEXT, ticket_name TEXT,
 payment_status TEXT DEFAULT 'pending',
 fleexi_waitlist TEXT,
 submitted_at TIMESTAMPTZ,
 data JSONB,
 label TEXT,
 email TEXT)`;

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  if (req.method === 'OPTIONS') return res.status(204).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'POST only' });
  const b = req.body || {};
  const data = b.data || {};
  const labels = Object.fromEntries(Object.entries(b).filter(([k]) => !['data','ticket','ticket_name','submitted_at'].includes(k)));
  const email = data.email || labels['Email address'] || '';
  const name = data.full_name || labels['Full name (as it should appear on your race bib)'] || 'Runner';
  const first = name.split(' ')[0];
  const fleexi = data.fleexi || labels['Would you like to join the Fleexi early access waitlist?'] || '';
  const client = await pool.connect();
  try {
    await client.query(SQL);
    await client.query('BEGIN');
    await client.query('LOCK TABLE rtr_registrations IN ACCESS EXCLUSIVE MODE');
    const used = (await client.query('SELECT bib FROM rtr_registrations WHERE bib IS NOT NULL')).rows.map(r => r.bib);
    const free = [];
    for (let n = 100; n <= 200; n++) if (!used.includes(n)) free.push(n);
    if (!free.length) return res.status(409).json({ error: 'All 101 bib numbers are taken. Registration closed.' });
    const bib = free[crypto.randomInt(free.length)];
    const r = await client.query(
      'INSERT INTO rtr_registrations (bib,ticket_id,ticket_name,payment_status,fleexi_waitlist,submitted_at,data,label,email) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING id',
      [bib, b.ticket || null, b.ticket_name || null, 'pending', fleexi, new Date(), JSON.stringify(data), JSON.stringify(labels), email]);
    await client.query('COMMIT');
    try { await sendEmail(email, first, bib); } catch (e) { console.error('email failed', e.message); }
    return res.status(200).json({ ok: true, id: r.rows[0].id, bib });
  } catch (e) {
    console.error(e);
    return res.status(500).json({ error: 'Could not save registration', detail: String(e.message).slice(0, 200) });
  } finally {
    client.release();
  }
}

async function sendEmail(email, first, bib) {
  const { SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD } = process.env;
  if (!(SMTP_HOST && SMTP_USER && SMTP_PASSWORD && email)) return;
  const waitlist = 'https://fleexi.africa/#waitlist';
  const html = `<div style="font-family:Arial,sans-serif;max-width:560px;margin:auto;color:#1c1430">
<h2 style="color:#ff2e93">You're officially in, ${first}! 🎉</h2>
<p>Thank you for registering for <b>RUN TO RAVE 2026</b>, brought to you by <b>Men That Cook</b>.<br>Your registration is confirmed.</p>
<table style="background:#f6f2fb;border-radius:12px;padding:14px 18px;width:100%;line-height:1.8">
<tr><td><b>Event</b></td><td>Run to Rave 2026</td></tr>
<tr><td><b>Date</b></td><td>Monday, 28 December 2026</td></tr>
<tr><td><b>Location</b></td><td>Kaduna</td></tr>
<tr><td><b>Your Bib Number</b></td><td style="font-size:1.3em;color:#ff2e93"><b>${bib}</b></td></tr>
<tr><td><b>Status</b></td><td>Registered — complete payment to fully confirm</td></tr>
</table>
<p><b>What's next?</b><br>We'll share the route, meeting point, schedule and what to bring as we get closer to the day. Keep your bib number safe!</p>
<p>Follow Men That Cook: Instagram <b>@mtc_lifestyle</b> · Facebook <b>Men That Cook</b> · TikTok <b>@men.that.cook</b></p>
<div style="background:#120b22;color:#f3eefc;border-radius:12px;padding:16px 18px;margin:14px 0">
<b style="color:#ffb02e">A ₦50,000 CASH PRIZE IS UP FOR GRABS!</b>
<p>Want to win ₦50,000 at Run to Rave? Join the Fleexi waitlist and stand a chance to take home the cash prize.</p>
<p><a href="${waitlist}" style="background:#ff2e93;color:#fff;padding:10px 18px;border-radius:999px;text-decoration:none;font-weight:bold">JOIN THE FLEEXI WAITLIST</a></p>
<p style="font-size:.85em;color:#a99fc0">Powered by Fleexi.</p>
</div>
<p>See you on 28 December!<br><b>MEN THAT COOK</b><br><span style="color:#a99fc0">Eat Well. Move Well. Live Well.<br>Run to Rave 2026 | Gym &amp; Juice by MTC</span></p></div>`;
  const transport = nodemailer.createTransport({ host: SMTP_HOST, port: +(SMTP_PORT || 587), secure: false, auth: { user: SMTP_USER, pass: SMTP_PASSWORD } });
  await transport.sendMail({
    from: `"Men That Cook | Run to Rave 2026" <${SMTP_USER}>`,
    to: email,
    subject: "You're In! Your Run to Rave 2026 Registration Is Confirmed!",
    text: `Hello ${first}, your Run to Rave 2026 registration is confirmed. Bib number: ${bib}. Join the Fleexi waitlist for a chance to win N50,000: ${waitlist}`,
    html
  });
}
