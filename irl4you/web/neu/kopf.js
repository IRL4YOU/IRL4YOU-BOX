/* Kopfzeile: Verbindungsqualität (Upload der letzten 30 Sekunden) und Kamera-Punkte, wie in der bisherigen Oberfläche. */
(() => {
  'use strict';
  const { h, $, App, fmt } = Neu;
  const box = $('#hb-meters'), sig = $('#hb-sig'), dots = $('#hb-dots'), line = $('#hb-line'), val = $('#hb-sigv'), smax = $('#hb-smax'), smid = $('#hb-smid'), smin = $('#hb-smin');
  const WIN = 30000, pts = []; let okAt = 0, lastM = null, dotsSig = '';
  const views = [];       // weitere Anzeigen derselben Kurve (zum Beispiel „Upload“ auf der Live-Seite): gleiche Daten, Skala, Kurve und Farbe wie oben

  /* Kurve mit Skala wie in der Kopfzeile, zum Einbauen an anderer Stelle (nur Skala und Kurve; der Wert steht dort in der eigenen Zeile) */
  Neu.sigMeter = () => {
    const NS = 'http://www.w3.org/2000/svg', mk = n => document.createElementNS(NS, n);
    const svg = mk('svg'); svg.setAttribute('viewBox', '0 0 60 28'); svg.setAttribute('preserveAspectRatio', 'none'); svg.setAttribute('aria-hidden', 'true');
    const g = mk('path'); g.setAttribute('class', 'sg'); g.setAttribute('d', 'M0 1H60M0 14H60M0 27H60'); const pl = mk('polyline'); pl.setAttribute('points', ''); svg.append(g, pl);
    const scale = [h('i'), h('i'), h('i')]; scale[2].textContent = '0';
    const el = h('span', { class: 'hsig', role: 'img' }, h('span', { class: 'hsig__scale', 'aria-hidden': 'true' }, scale), svg);
    if (sig.dataset.tone) el.dataset.tone = sig.dataset.tone;
    views.push({ el, scale, line: pl }); if (pts.length) draw();
    return el;
  };

  /* Upload der gewählten Leitungen (Mbit/s); bei Nutzdaten der kleinere Wert, wie in der bisherigen Oberfläche */
  function upTotal(m) {
    const upl = ((App.data.srtla || {}).settings || {}).uplinks || []; let nets = Object.entries(m.net || {});
    const sel = nets.filter(([n]) => upl.includes(n)); if (sel.length) nets = sel;
    return nets.reduce((a, [, r]) => a + (+r.tx_mbit || 0), 0);
  }
  function upShown(m) { const wire = upTotal(m), pay = m.payload_mbit == null ? null : +m.payload_mbit; return pay == null || isNaN(pay) ? wire : Math.min(pay, wire); }
  /* 0 (nichts geht durch) bis 4 (gut); null = es wird nicht gesendet */
  function level(m) {
    const s = m.details && m.details.send; if (!s) return null;
    const ups = Object.values(m.uplinks || {}).filter(Boolean), on = ups.filter(u => u.state === 'an').length;
    if (ups.length && !on) return 0;
    let q = 4; if (ups.length && on < ups.length) q -= 1;
    const want = (s.bitrate_kbps || 0) / 1000;
    if (want > 0) { const r = upTotal(m) / want, backlog = s.snd_buf_ms != null && s.snd_buf_ms > 300; if (r < .1) q -= 2; else if (backlog && r < .5) q -= 2; else if (backlog && r < .8) q -= 1; }
    if (s.rtt_ms != null) { if (s.rtt_ms > 1000) q -= 2; else if (s.rtt_ms > 400) q -= 1; }
    if (s.snd_buf_ms != null) { if (s.snd_buf_ms > 3000) q -= 2; else if (s.snd_buf_ms > 1500) q -= 1; }
    return Math.max(0, Math.min(4, q));
  }
  const nice = v => { for (const c of [5, 10, 15, 20, 30, 50, 100]) if (v * 1.05 <= c) return c; return Math.ceil(v / 10) * 10; };
  function draw() {
    if (!pts.length) return;
    const now = Date.now(), cut = now - WIN; while (pts.length > 1 && pts[1].t <= cut) pts.shift();
    const p = pts.map(x => ({ t: Math.max(cut, x.t), v: x.v })), top = nice(Math.max(...p.map(x => x.v)));
    const plot = p.length === 1 ? [{ t: Math.max(cut, now - 2000), v: p[0].v }, p[0]] : p;
    val.textContent = fmt(p[p.length - 1].v, 1);
    const sc = [fmt(top, top % 1 ? 1 : 0), fmt(top / 2, 1), '0'];      // Skala wie in der bisherigen Oberfläche (Mbit/s)
    const pl = plot.map(x => (Math.min(60, (x.t - cut) / WIN * 60)).toFixed(1) + ',' + (27 - Math.max(0, Math.min(top, x.v)) / top * 26).toFixed(1)).join(' ');
    [{ scale: [smax, smid, smin], line }, ...views].forEach(v => { v.scale.forEach((e, i) => { if (e.textContent !== sc[i]) e.textContent = sc[i]; }); v.line.setAttribute('points', pl); });
  }

  const camTone = c => c.state === 'live' ? (c.pic === 'wartet' || c.pic === 'aus' ? 'warn' : 'ok') : (c.state === 'unknown' ? '' : 'danger');
  const T = s => (window.PB_I18N && window.PB_I18N.tr ? window.PB_I18N.tr(s) : s);
  const camTitle = c => (c.name || c.key || 'Kamera') + ': ' + T(c.state !== 'live' ? (c.state === 'unknown' ? 'Status unbekannt' : 'Kein Signal')
    : c.pic === 'an' ? 'Sendet und ist im Bild' : c.pic === 'wartet' ? `Sendet, kommt in ${c.pic_wait} s ins Bild` : c.pic === 'aus' ? 'Sendet, ist noch nicht im Bild' : 'Sendet');
  const quiet = c => c.parked ? 2 : (c.state === 'live' || c.state === 'unknown' ? 0 : 1);
  function drawDots(m) {
    const l = (m.cameras || []).filter(c => !c.parked).sort((a, b) => quiet(a) - quiet(b)).slice(0, 4);
    const sg = JSON.stringify(l.map(c => [camTone(c), camTitle(c)]));      // nur neu bauen, wenn sich ein Punkt ändert
    if (sg === dotsSig) return; dotsSig = sg;
    dots.replaceChildren(...l.map(c => h('span', { class: 'hdot', data: camTone(c) ? { tone: camTone(c) } : {}, title: camTitle(c) })));
    dots.setAttribute('aria-label', l.map(camTitle).join('; '));
  }
  function paint() {
    const m = lastM; if (!m) return; const s = App.data.send;
    const q = level(m), active = !!(s && s.active);
    sig.hidden = !active;
    const tone = q == null ? '' : q >= 3 ? 'ok' : q === 2 ? 'warn' : 'danger';
    [sig, ...views.map(v => v.el)].forEach(e => { if (tone) e.dataset.tone = tone; else delete e.dataset.tone; });
    const tip = q == null ? 'Verbindung: keine Messung (es wird nicht gesendet)' : q >= 3 ? 'Verbindung: gut' : q === 2 ? 'Verbindung: mäßig' : 'Verbindung: schlecht';
    sig.title = tip; sig.setAttribute('aria-label', tip);
    box.hidden = sig.hidden && !dots.children.length;
  }
  App.on('metrics', m => {
    okAt = Date.now(); lastM = m;
    const q = level(m); pts.push({ t: Date.now(), v: q == null ? 0 : Math.max(0, upShown(m)) });
    drawDots(m); draw(); paint();
  });
  App.on('send', paint);

  /* Hinweis „Update verfügbar“ in der Kopfzeile, auf jeder Seite: eigene seltene Abfrage (alle 5 Minuten); auf der Seite System kommen die Daten der Update-Karte dazu */
  const upd = $('#hb-upd');
  if (upd) {
    const show = d => {
      if (!d) return; upd.hidden = !d.newer;
      if (d.newer) { const t = 'Neue Version ' + (d.latest_version ? 'v' + d.latest_version + ' ' : '') + 'verfügbar (jetzt v' + d.current + '). ' + (d.sending ? 'Einspielen geht nicht während der Übertragung.' : 'Zum Software-Update.'); upd.title = t; upd.setAttribute('aria-label', t); }
    };
    upd.addEventListener('click', () => Neu.goto('system', 'sy-update'));
    Neu.poll('hdrupd', '/api/swupdate', 300000);
    App.on('hdrupd', show); App.on('swupdate', show);
  }
  setInterval(() => {
    if (document.hidden || !lastM) return;
    const stale = okAt > 0 && Date.now() - okAt > 8000; sig.classList.toggle('stale', stale);
    if (stale) { val.textContent = '–'; sig.title = 'Verbindung: keine Messwerte von der Box'; } else draw();
  }, 500);
})();
