import { Pool } from 'pg';
const pool = new Pool({ connectionString: process.env.DATABASE_URL, ssl: { rejectUnauthorized: false } });

export default async function handler(req, res) {
  const qs = new URL(req.url, 'http://x').searchParams;
  const key = qs.get('key') || '';
  const adminKey = process.env.ADMIN_KEY || '';
  if (!adminKey || key.length !== adminKey.length || !cryptoSafeEq(key, adminKey)) {
    return res.status(401).send('Unauthorized. Add ?key=YOUR_ADMIN_KEY');
  }
  const { rows } = await pool.query('SELECT id, bib, ticket_name, payment_status, fleexi_waitlist, submitted_at, label, email FROM rtr_registrations ORDER BY id DESC');
  if (qs.get('format') === 'csv') {
    const esc = v => `"${String(v ?? '').replace(/"/g, '""')}"`;
    const lines = [['id','bib','ticket','payment_status','fleexi_waitlist','submitted_at','answers','email'].join(',')];
    for (const r of rows) lines.push([r.id, r.bib ?? '', r.ticket_name, r.payment_status, r.fleexi_waitlist, r.submitted_at?.toISOString() || '', esc(r.label), r.email].join(','));
    res.setHeader('Content-Type', 'text/csv');
    res.setHeader('Content-Disposition', 'attachment; filename=run-to-rave-registrations.csv');
    return res.status(200).send(lines.join('\n'));
  }
  const data = rows.map(r => ({ ...r, submitted_at: r.submitted_at?.toISOString() || null }));
  const paid = data.filter(d => d.payment_status === 'paid').length;
  const fleexi = data.filter(d => (d.fleexi_waitlist || '').toLowerCase().includes('sign me up')).length;
  return res.status(200).json({ total: data.length, paid, fleexi_waitlist: fleexi, registrations: data });
}

function cryptoSafeEq(a, b) {
  if (a.length !== b.length) return false;
  let r = 0;
  for (let i = 0; i < a.length; i++) r |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return r === 0;
}
