/* Stream Link: Handys als zusätzliche Leitungen. Gemeinsam für „Netzwerk“ und „Live“: Abfrage der Daten, Namen, Akku mit Blitz, Zeilen mit Hoch und Runter. */
(() => {
  'use strict';
  const { h, App, poll, row, badge, fmt } = Neu;

  const refresh = poll('link', '/api/link', 4000, () => App.view === 'netz' || App.view === 'live');
  Neu.linkRefresh = refresh;

  /* Hoch und Runter je Handy aus den Zählern des Dienstes (MB); neu gerechnet, wenn neue Daten da sind */
  const samp = {}, rate = {}; let seen = null;
  function rates(hs) {
    if (App.data.link === seen) return; seen = App.data.link; const now = Date.now();
    for (const x of hs) {
      const p = samp[x.id]; samp[x.id] = { t: now, up: x.mb_up, down: x.mb_down };
      if (!p || now - p.t < 500 || x.mb_up == null) continue;
      const dt = (now - p.t) / 1000;
      rate[x.id] = { up: Math.max(0, (x.mb_up - p.up) * 8 / dt), down: Math.max(0, (x.mb_down - p.down) * 8 / dt) };
    }
  }

  /* Verbundene Handys, nach Kennung sortiert: eigener Name oder „Handy 1“, „Handy 2“ … */
  Neu.linkPhones = () => {
    const d = App.data.link, hs = d && d.enabled ? (d.helpers || []).filter(x => x.state === 'up').slice().sort((a, b) => String(a.id).localeCompare(String(b.id))) : [];
    rates(hs);
    return hs.map((x, i) => ({ ...x, label: x.name || `Handy ${i + 1}`, custom: x.name || '', rate: rate[x.id] || null }));
  };

  /* Akku in Prozent, bei „lädt“ mit kleinem Blitz davor (die App meldet es im Akku-Byte mit) */
  Neu.linkBatt = (x, cls) => {
    if (x.battery == null) return null;
    const t = h('span', { class: cls, text: `Akku ${x.battery} %` });
    if (!x.charging) return t;
    const b = Neu.ico('bolt', 'sm'); b.style.color = 'var(--ok)';
    return h('span', { class: 'cluster', style: '--gap:var(--space-1);flex-wrap:nowrap;align-items:center', title: 'lädt' }, b, t);
  };

  /* Zeilen für Listen. edit: Stift zum Umbenennen (nur wo die Zeilen Knöpfe haben dürfen); ip: Adresse dazu; speed: Hoch und Runter in Mbit/s als eigene Zeile (sonst nur Akku und gesendete MB, klein für die Live-Seite) */
  Neu.linkRows = ({ edit = false, ip = false, speed = true } = {}) => Neu.linkPhones().map(x => {
    const rt = x.rate ? `${fmt(x.rate.up)} Mbit/s hoch · ${fmt(x.rate.down)} Mbit/s runter` : '– Mbit/s hoch · – Mbit/s runter';
    const bits = [ip && x.ip ? h('span', { class: 'muted', text: x.ip }) : null, Neu.linkBatt(x, 'muted'), x.mobile === false ? h('span', { class: 'muted', text: 'Kein Mobilfunk' }) : null, h('span', { class: 'muted', text: `${fmt(x.mb_up)} MB hoch` })].filter(Boolean);
    const info = h('span', { class: 'cluster', style: '--gap:var(--space-2)' }, ...bits.flatMap((b, k) => k ? [h('span', { class: 'muted', 'aria-hidden': 'true', text: '·' }), b] : [b]));
    const title = edit ? Neu.named(x.label, Neu.iconBtn('pencil', 'Umbenennen', async () => { await Neu.rename('link:' + x.id, x.custom); refresh(); })) : x.label;
    return row({ icon: 'wifi', title, desc: speed ? h('span', null, h('span', { class: 'num', text: rt }), h('br'), info) : info, end: badge('Verbunden', 'ok') });
  });
})();
