/* Ansicht „Netzwerk“: Leitungen (wählen, testen), Server und Bitrate, Stream Link (zweites Handy), Fernzugriff. WLAN, Bluetooth und feste Adresse bleiben in der bisherigen Oberfläche. */
(() => {
  'use strict';
  const { h, ico, fmt, api, App, poll, ask, sheet, closeSheet, toast, run, badge, btn, alertBox, card, row, list, sw, field, input, select, seg, range, disclosure, pageHead, view } = Neu;

  view('netz', sec => {
    const leitungen = h('div', { class: 'stack' }), server = h('div', { class: 'stack' });
    const CAN_TEST = true;
    const allBtn = btn('Alle Leitungen testen', { ico: 'activity', onclick: () => startTest({ all: true }) });
    allBtn.setAttribute('data-shape', 'pill');
    sec.append(pageHead('Netzwerk', null, CAN_TEST ? [allBtn] : []));
    const T = Neu.slots.netz = Neu.tabbed(sec, 'Netzwerk');
    const linkHost = h('div'), linkLines = h('div'); let linkSig = '';
    const LINK_APP = 'https://github.com/IRL4YOU/IRL4YOU-Cam/releases/latest', LINK_INFO = 'https://github.com/IRL4YOU/IRL4YOU-Cam';
    const linkLinks = () => h('p', { class: 'cluster', style: 'font-size:var(--text-sm)' }, h('a', { href: LINK_APP, target: '_blank', rel: 'noopener', text: 'App herunterladen' }), h('a', { href: LINK_INFO, target: '_blank', rel: 'noopener', text: 'Beschreibung der App' }));
    const linkLogo = px => h('img', { src: '/logo-link.svg', alt: '', width: px, height: px, style: 'border-radius:22%' });
    T.add('n1', 'Leitungen', leitungen); T.add('n2', 'Server und Bitrate', server); T.add('n-link', 'Stream Link', h('div', { class: 'stack' }, linkHost));
    const subP = h('p', { id: 'net-sub' }); sec.querySelector('.page-head > div').append(subP);

    /* ================= Stream Link (zweites Handy, App „IRL4YOU Stream Link“) ================= */
    const linkRefresh = poll('link', '/api/link', 4000, () => App.view === 'netz');
    const linkPost = async body => { try { App.set('link', await api('POST', '/api/link', body)); } catch (x) { toast(x.message); linkRefresh(); } };
    const LINK_ERR = { password: 'Das Passwort stimmt nicht mit dem in der App überein.', no_mobile: 'Das zweite Handy hat gerade kein Mobilfunknetz.', target: 'Das zweite Handy erreicht den Server nicht.', busy: 'Das zweite Handy ist belegt.', other: 'Das zweite Handy hat die Anmeldung abgelehnt.' };
    function renderLink() {
      const d = App.data.link; if (!d) return;
      const sg = JSON.stringify(d); if (sg === linkSig && linkHost.firstChild) return;
      if (linkHost.contains(document.activeElement) && document.activeElement.tagName === 'INPUT' && document.activeElement.type === 'text') return;
      linkSig = sg;
      const kids = [linkLinks(), sw({ checked: !!d.enabled, label: 'Zweites Handy als zusätzlichen Sendeweg nutzen', s: 'Stream Link', k: 'stream link cam link zweites handy mobilfunk sendeweg', onchange: on => linkPost({ enabled: on }) })];
      if (d.enabled && !d.service) kids.push(alertBox({ tone: 'warn', text: 'Der Stream-Link-Dienst läuft nicht. Spiele das Software-Update ein oder starte die Box neu.' }));
      if (d.enabled && d.service && !d.target) kids.push(alertBox({ tone: 'warn', text: 'Wähle zuerst einen SRTLA-Server.' }));
      if (d.enabled) {
        const ifs = (d.interfaces || []).map(o => [o.iface, o.label]);
        kids.push(field({ label: 'Passwort (wie in der App)', control: input({ value: d.password || '', maxLength: 64, autocomplete: 'off', onchange: e => linkPost({ password: e.target.value }) }) }),
          field({ label: 'Netzwerkkarte, an der das zweite Handy hängt', control: select([['', 'Alle'], ...ifs], d.iface || '', v => linkPost({ iface: v })) }));
        const hs = d.helpers || [];
        if (!hs.length) kids.push(d.searching ? badge('Suche nach dem zweiten Handy …', null, true) : null);
        for (const x of hs) {
          if (x.state === 'up') kids.push(h('div', { class: 'cluster' }, badge('Verbunden', 'ok'), x.battery != null ? h('span', { class: 'num', text: `Akku ${x.battery} %` }) : null, x.mobile === false ? badge('Kein Mobilfunk', 'warn') : null, h('span', { class: 'num', text: `${fmt(x.mb_up)} MB hoch` })));
          else if (x.state === 'error') kids.push(alertBox({ tone: 'warn', text: LINK_ERR[x.error] || LINK_ERR.other }));
          else kids.push(badge('Verbinde …', null, true));
        }
      }
      kids.push(disclosure('Wie funktioniert das?', h('div', { class: 'stack', style: '--gap:var(--space-2)' },
        h('p', { class: 'muted', style: 'font-size:var(--text-sm)' }, 'Ein zweites Handy mit der App „IRL4YOU Stream Link“ schickt einen Teil der Daten über sein eigenes Mobilfunknetz. Es muss im selben Netz wie die Box hängen, zum Beispiel am Router. Gib in der App dasselbe Passwort ein und lass sie laufen, die Box findet das Handy selbst.'),
        h('p', { class: 'muted', style: 'font-size:var(--text-sm)' }, 'Die App „IRL4YOU Stream Link“ erweitert das Netz der Box über ein zweites Handy und ist für diese Box gemacht.'),
        )));
      linkHost.replaceChildren(card({ title: 'Stream Link', logo: linkLogo(40), body: kids.filter(Boolean) }));
    }

    /* Zweite Handys als Zeilen unter „Leitungen“: Hochladen und Herunterladen je Handy, aus den Zählern des Link-Dienstes (alle paar Sekunden abgefragt) */
    const lSamp = {}, lRate = {}; let lObj = null;
    function linkRates(hs) {
      if (App.data.link === lObj) return; lObj = App.data.link; const now = Date.now();
      for (const x of hs) {
        const p = lSamp[x.id]; lSamp[x.id] = { t: now, up: x.mb_up, down: x.mb_down };
        if (!p || now - p.t < 500 || x.mb_up == null) continue;
        const dt = (now - p.t) / 1000;
        lRate[x.id] = { up: Math.max(0, (x.mb_up - p.up) * 8 / dt), down: Math.max(0, (x.mb_down - p.down) * 8 / dt) };
      }
    }
    function renderLinkLines() {
      const d = App.data.link, hs = d && d.enabled ? (d.helpers || []).filter(x => x.state === 'up') : [];
      if (!hs.length) { linkLines.replaceChildren(); return; }
      linkRates(hs);
      const rows = hs.map((x, i) => {
        const r = lRate[x.id], rate = r ? `${fmt(r.up)} Mbit/s hoch · ${fmt(r.down)} Mbit/s runter` : '– Mbit/s hoch · – Mbit/s runter';
        const bits = [x.ip ? h('span', { class: 'muted', text: x.ip }) : null, x.battery != null ? h('span', { class: 'muted', text: `Akku ${x.battery} %` }) : null, x.mobile === false ? h('span', { class: 'muted', text: 'Kein Mobilfunk' }) : null, h('span', { class: 'muted', text: `${fmt(x.mb_up)} MB hoch` })].filter(Boolean);
        const info = h('span', { class: 'cluster', style: '--gap:var(--space-2)' }, ...bits.flatMap((b, k) => k ? [h('span', { class: 'muted', 'aria-hidden': 'true', text: '·' }), b] : [b]));
        return row({ icon: 'wifi', title: hs.length > 1 ? `Zweites Handy ${i + 1}` : 'Zweites Handy', desc: h('span', null, h('span', { class: 'num', text: rate }), h('br'), info),
          end: badge('Verbunden', 'ok') });
      });
      linkLines.replaceChildren(card({ title: 'Stream Link', logo: linkLogo(32), foot: [linkLinks()], sub: 'Werden als zusätzliche Leitung genutzt, solange sie verbunden sind. Einstellungen im Reiter „Stream Link“.', body: list(rows), flush: true }));
    }

    /* ================= Leitungen ================= */
    const rateEls = {}, resEls = {};
    let rowsSig = '';
    const ut = () => App.data.uplinktest || { tests: {}, busy: false };
    async function startTest(body) {
      if (App.data.send && App.data.send.active && !await ask({ title: 'Während der Sendung testen?', text: 'Der Test belegt die Leitung für einige Sekunden, das Bild kann kurz schlechter werden.', ok: 'Trotzdem testen' })) return;
      try { App.set('uplinktest', await api('POST', '/api/uplinktest', body)); pollTest(); } catch (e) { toast(e.message); }
    }
    let testTimer = 0;
    function pollTest() { clearTimeout(testTimer); testTimer = setTimeout(async () => { try { App.set('uplinktest', await api('GET', '/api/uplinktest')); } catch (e) { return; } if (ut().busy) pollTest(); }, 1500); }
    const fig = (label, v, unit) => h('div', { class: 'stat' }, h('span', { class: 'stat__label', text: label }), h('span', { class: 'stat__value', style: 'font-size:var(--text-lg)' }, v, h('span', { class: 'stat__unit', text: unit })));
    function testText(t) {
      if (!t) return null;
      if (t.state === 'wartet') return badge('Wartet …');
      if (t.state === 'läuft') return badge('Test läuft: ' + (t.step || 'Start'), null, true);
      if (t.state === 'fehler') return alertBox({ tone: 'danger', text: (t.text || 'Test fehlgeschlagen') + (t.hint ? ' ' + t.hint : '') });
      if (t.state === 'fertig') {
        const f = [];
        if (t.down_mbit != null) f.push(fig('Herunterladen', fmt(t.down_mbit), 'Mbit/s'));
        if (t.up_mbit != null) f.push(fig('Hochladen', fmt(t.up_mbit), 'Mbit/s'));
        if (t.rtt_ms != null) f.push(fig('Antwortzeit', String(t.rtt_ms), 'ms'));
        return h('div', { class: 'stack', style: '--gap:var(--space-1)' }, h('div', { class: 'cluster', style: '--gap:var(--space-6)' }, ...f), t.during_send ? h('span', { class: 'muted', style: 'font-size:var(--text-xs)', text: 'Während der Sendung gemessen' }) : null);
      }
      return null;
    }
    function paintTests() { const t = ut().tests || {}; for (const [k, el] of Object.entries(resEls)) el.replaceChildren(...[testText(t[k])].filter(Boolean)); allBtn.disabled = !!ut().busy; document.querySelectorAll('[data-testbtn]').forEach(b => { b.disabled = !!ut().busy; }); }

    async function setUplinks(iface, on, el) {
      const sr = App.data.srtla, ups = new Set(sr.settings.uplinks); on ? ups.add(iface) : ups.delete(iface);
      await run(el, async () => { await api('POST', '/api/srtla/settings', { ...sr.settings, uplinks: [...ups] }); App.set('srtla', await api('GET', '/api/srtla')); toast('Sendewege gespeichert. Das gilt innerhalb weniger Sekunden.'); });
      if (el && !ups.has(iface) === on) el.checked = !on;
    }
    function renderLeitungen() {
      const sr = App.data.srtla; if (!sr) return;
      const sel = new Set(sr.settings.uplinks), hot = new Set(sr.hotspot_ifaces || []), ifs = sr.interfaces || [];
      const sig = JSON.stringify([ifs.map(o => [o.iface, o.ip, o.label]), [...sel], sr.diag, sr.conn_names, [...hot], !!(App.data.send || {}).active]);
      if (sig === rowsSig) return; rowsSig = sig;
      for (const k of Object.keys(rateEls)) delete rateEls[k]; for (const k of Object.keys(resEls)) delete resEls[k];
      const rows = ifs.map(o => {
        const d = (sr.diag || {})[o.iface], name = (sr.conn_names || {})[o.iface] ? `${o.label} (${sr.conn_names[o.iface]})` : o.label;
        const rate = h('span', { class: 'num', text: '– Mbit/s hoch' }); rateEls[o.iface] = rate;
        const res = h('div', { class: 'utdiag' }); resEls[o.iface] = res;
        const state = d ? badge(d.level === 'bad' ? 'Ausgefallen' : 'Prüfen', d.level === 'bad' ? 'danger' : 'warn') : (o.ip ? badge('Bereit', 'ok') : badge('Getrennt'));
        const end = [state, hot.has(o.iface) ? badge('Hotspot der Box') : !CAN_TEST ? null : (() => { const b = btn('Testen', { size: 'sm', ico: 'activity', onclick: () => startTest({ iface: o.iface }) }); b.setAttribute('data-testbtn', ''); b.setAttribute('data-shape', 'pill'); return b; })(),
          sw({ checked: sel.has(o.iface), aria: `${name} zum Senden verwenden`, onchange: (on, el) => setUplinks(o.iface, on, el) })].filter(Boolean);
        const r = row({ icon: o.iface.startsWith('wlan') ? 'wifi' : 'ethernet', title: Neu.named(name, Neu.iconBtn('pencil', 'Leitung umbenennen', () => Neu.rename('net:' + o.iface, (sr.conn_names || {})[o.iface] || ''))), desc: h('span', null, o.ip || 'Keine Adresse', ' · ', rate), end });
        const extra = [d ? alertBox({ tone: d.level === 'bad' ? 'danger' : 'warn', text: d.text + (d.hint ? ' ' + d.hint : '') }) : null, res].filter(Boolean);
        return h('li', { data: { s: `Leitung ${o.iface} zum Senden verwenden`, k: 'netz upload senden lan wlan hotspot ' + o.label } }, h('div', { class: 'row' }, ...r.childNodes),
          h('div', { style: 'padding:0 var(--space-4) var(--space-3);display:grid;gap:var(--space-2)' }, extra));
      });
      for (const u of sr.settings.uplinks) if (!ifs.some(o => o.iface === u)) rows.push(row({ icon: 'ethernet', title: u, desc: 'Gerade nicht verbunden', end: sw({ checked: true, aria: `${u} zum Senden verwenden`, onchange: (on, el) => setUplinks(u, on, el) }) }));
      leitungen.replaceChildren(
        ...(sr.settings.uplinks.length === 0 ? [alertBox({ tone: 'warn', text: 'Keine Leitung zum Senden gewählt.' })] : []),
        card({ title: 'Leitungen zum Senden', sub: 'Wähle, welche Leitungen die Box zum Senden nutzt.', body: rows.length ? list(rows) : h('div', { class: 'empty' }, 'Keine Netzwerkkarte gefunden.'), flush: true }),
        linkLines,
        h('p', { class: 'muted', style: 'font-size:var(--text-sm)' }, 'Der Test misst Herunterladen, Hochladen und Antwortzeit der Leitung (höchstens etwa 45 MB Datenvolumen je Leitung).'));
      renderLinkLines(); paintTests(); document.getElementById('net-sub').textContent = `${sr.settings.uplinks.length} von ${ifs.length} Leitungen zum Senden gewählt`;
      const bad = Object.values(sr.diag || {}).some(d => d.level === 'bad'), warn = Object.keys(sr.diag || {}).length > 0, nd = document.getElementById('nd-netz'); nd.hidden = !warn; nd.dataset.tone = bad ? 'danger' : 'warn';
    }
    function paintRates() { const net = (App.data.metrics || {}).net || {}; for (const [k, el] of Object.entries(rateEls)) el.textContent = `${fmt((net[k] || {}).tx_mbit)} Mbit/s hoch`; }

    /* ================= Server und Bitrate ================= */
    function serverForm(srv) {
      const name = input({ value: srv ? srv.name : '', placeholder: 'z. B. Frankfurt', maxlength: 40 }), host = input({ value: srv ? srv.host : '', placeholder: 'z. B. srt.example.com', autocomplete: 'off' }),
        port = input({ type: 'number', value: srv ? srv.port : 5000, min: 1, max: 65535 }), sid = input({ type: 'password', placeholder: srv && srv.has_streamid ? 'Gespeichert (leer lassen = unverändert)' : 'Optional', autocomplete: 'off' });
      let loaded = false;
      const body = [field({ label: 'Name', control: name }), field({ label: 'Adresse', control: host }), field({ label: 'Port', control: port }), field({ label: 'Stream-ID', control: sid, hint: 'Wird nur auf der Box gespeichert.' })];
      if (srv && srv.has_streamid) body.push(btn('Stream-ID anzeigen', { size: 'sm', onclick: async ev => { if (loaded) { sid.type = sid.type === 'text' ? 'password' : 'text'; return; } try { const r = await api('POST', `/api/srtla/${srv.id}/streamid`, {}); sid.value = r.streamid || ''; loaded = true; sid.type = 'text'; sid.placeholder = 'Leer = entfernen'; } catch (e) { toast(e.message); } } }));
      const save = btn('Speichern', { variant: 'primary', run: async () => {
        const b = { name: name.value, host: host.value, port: +port.value, streamid: sid.value };
        if (srv && loaded && !b.streamid) b.clear_streamid = true;
        if (srv) await api('POST', '/api/srtla/' + srv.id, b); else await api('POST', '/api/srtla', b);
        closeSheet(); App.set('srtla', await api('GET', '/api/srtla')); App.data['send:refresh']();
      }, ok: 'Server gespeichert' });
      sheet({ title: srv ? 'Server bearbeiten' : 'Server hinzufügen', body, foot: [btn('Abbrechen', { onclick: closeSheet }), save] });
    }
    let draft = null, srvSig = '';
    function renderServer() {
      const sr = App.data.srtla; if (!sr) return;
      const sg = JSON.stringify([sr.servers, sr.selected, sr.settings]); if (sg === srvSig && draft) return; srvSig = sg;
      if (!draft) draft = { ...sr.settings };
      const cur = sr.servers.find(s => s.id === sr.selected);
      const sel = select(sr.servers.map(s => [s.id, `${s.name} · ${s.host}:${s.port}`]), sr.selected, v => run(null, async () => { await api('POST', '/api/srtla/select', { id: v }); App.set('srtla', await api('GET', '/api/srtla')); App.data['send:refresh'](); }, 'Server gewählt'));
      sel.disabled = !sr.servers.length;
      const mx = range({ s: 'Höchste Bitrate', k: 'bitrate kbit qualität maximum', label: 'Höchste Bitrate', min: 1000, max: 20000, step: 500, value: Math.min(20000, Math.max(1000, draft.max_kbps)), unit: ' kbit/s', oninput: v => { draft.max_kbps = v; } });
      const mn = range({ s: 'Niedrigste Bitrate', k: 'bitrate kbit minimum', label: 'Niedrigste Bitrate', min: 450, max: 2000, step: 50, value: Math.min(2000, Math.max(450, draft.min_kbps)), unit: ' kbit/s', oninput: v => { draft.min_kbps = v; } });
      const lat = range({ s: 'Latenz', k: 'verzögerung puffer ms latenz', label: 'Latenz', min: 1000, max: 8000, step: 100, value: Math.min(8000, Math.max(1000, draft.latency_ms || 4000)), unit: ' ms', oninput: v => { draft.latency_ms = v; } });
      const spread = seg('spread', [['best', 'Beste bevorzugen'], ['all', 'Alle gleichzeitig']], draft.spread || 'best', v => { draft.spread = v; }, 'Verteilung');
      server.replaceChildren(
        card({ title: 'SRTLA-Server', sub: sr.servers.length ? null : 'Noch kein Server angelegt. Ohne Server kannst du nicht live gehen.', actions: [btn('Neu', { size: 'sm', ico: 'plus', onclick: () => serverForm(null) })], body: [
          field({ s: 'Aktiver SRTLA-Server', k: 'server frankfurt stream-id srt wählen', label: 'Aktiver Server', control: sel, hint: cur ? (cur.has_streamid ? 'Stream-ID gespeichert.' : 'Keine Stream-ID gespeichert.') : null }),
          h('div', { class: 'cluster' }, btn('Bearbeiten', { size: 'sm', disabled: !cur, onclick: () => serverForm(cur) }),
            btn('Löschen', { size: 'sm', variant: 'danger', disabled: !cur, onclick: async () => { if (await ask({ title: `„${cur.name}“ löschen?`, text: 'Der Server wird aus der Box entfernt.', ok: 'Löschen', danger: true })) { await run(null, async () => { await api('DELETE', '/api/srtla/' + cur.id); App.set('srtla', await api('GET', '/api/srtla')); App.data['send:refresh'](); }, 'Server gelöscht'); } } }))] }),
        card({ title: 'Bitrate und Latenz', body: [mx, mn, field({ s: 'Verteilung auf Leitungen', k: 'beste alle spread', label: 'Verteilung auf Leitungen', control: h('div', null, spread), hint: 'Beste bevorzugen ist stabiler. Alle gleichzeitig nutzt auch langsamere Leitungen.' }),
          h('div', { class: 'field' }, lat, h('span', { class: 'field__hint', text: 'Höher ist stabiler, verzögert aber das Bild. Standard: 4000 ms.' }))],
          foot: [btn('Speichern', { variant: 'primary', run: async () => { await api('POST', '/api/srtla/settings', { ...draft, uplinks: sr.settings.uplinks }); draft = null; srvSig = ''; App.set('srtla', await api('GET', '/api/srtla')); App.data['send:refresh'](); }, ok: 'Gespeichert' })] }));
    }

    App.on('srtla', () => { renderLeitungen(); renderServer(); });
    App.on('metrics', paintRates); App.on('uplinktest', () => { paintTests(); if (ut().busy) pollTest(); });
    App.on('send', renderLeitungen);
    App.on('link', () => { renderLink(); renderLinkLines(); });
  });
})();
