/* IRL4YOU BOX · neue Oberfläche · Ergänzungen (kamera): Funktionen der bisherigen Oberfläche, die es in der Vorlage nicht gab.
   Enthält: Kamera-Rotation (Reiter in „Bild“, Schalter in der Schnellsteuerung) und kleine Formate für die Schnellleiste (Wischauswahl, Sperre). */
(() => {
  'use strict';
  const { h, api, App, poll, toast, btn, alertBox, card, row, list, sw, field, input, seg } = Neu;

  /* ---------- Formate für die Wischauswahl und die Sperre der Schnellleiste (Handy) ---------- */
  document.head.append(h('style', { text: `
    .qchip { touch-action: none; }
    .qbar .btn[data-icon][data-variant="primary"] { background: var(--accent); color: var(--on-accent); border-color: var(--accent); }
    body[data-locked] { overflow: hidden; }
    body[data-locked] .qbar { box-shadow: 0 -6px 16px oklch(0 0 0 / 0.18), inset 0 0 0 2px var(--warn); }
    .qpick { position: fixed; left: var(--space-3); right: var(--space-3); bottom: calc(var(--nav-h, 4rem) + var(--qbar-h, 0px) + var(--space-2)); z-index: var(--z-overlay, 40); max-height: 60vh; overflow: auto; display: grid; gap: var(--space-1); padding: var(--space-2); background: var(--surface-1); border: 1px solid var(--border-strong); border-radius: var(--radius-l); box-shadow: 0 -8px 24px oklch(0 0 0 / 0.3); touch-action: none; }
    .qpick__h { padding: var(--space-1) var(--space-2); font-size: var(--text-xs); color: var(--text-2); }
    .qpick__item { display: flex; align-items: center; gap: var(--space-2); min-height: 2.75rem; padding: 0 var(--space-3); border-radius: var(--radius-m); background: var(--surface-3); font-size: var(--text-sm); font-weight: var(--weight-medium); }
    .qpick__item[data-cur] { outline: 2px solid var(--accent); outline-offset: -2px; }
    .qpick__item[data-on] { background: var(--accent); color: var(--on-accent); }
    .qpick__dot { flex: none; width: 0.625rem; height: 0.625rem; border-radius: 50%; background: var(--text-3); }
    .qpick__dot[data-live] { background: var(--ok); }
    .qpick__tag { margin-left: auto; flex: none; font-size: var(--text-xs); opacity: .85; }
  ` }));

  /* ======================= Kamera-Rotation =======================
     Die Box tauscht die Kameras der gewählten Bilder reihum nach der eingestellten Zeit aus (nur bei Bild-in-Bild).
     Die Einstellung gilt sofort und wird nicht mit „Bildaufbau speichern“ gespeichert. */
  const SLOTS = ['main', 'pip', 'pip2', 'pip3'], SLOT_LABEL = { main: 'Hauptbild', pip: 'Kleines Bild 1', pip2: 'Kleines Bild 2', pip3: 'Kleines Bild 3' };
  const hosts = new Set(); let pending = {}, saveT = 0, rotMsg = '', rid = 0, lastSig = '';
  const rd = () => App.data.rotation || null;
  const qbar = () => document.getElementById('qbar');
  const refresh = poll('rotation', '/api/pipeline/rotation', 6000, () => App.view === 'bild' || App.view === 'live' || !!(qbar() && !qbar().hidden));

  async function post(body) {
    try { const r = await api('POST', '/api/pipeline/rotation', body); rotMsg = 'Gespeichert.'; App.set('rotation', r); return r; }
    catch (e) { rotMsg = e.message || 'Nicht gespeichert'; toast(rotMsg); try { App.set('rotation', await api('GET', '/api/pipeline/rotation')); } catch (x) { /* nichts */ } }
    finally { paintAll(true); }
  }
  /* Änderungen sammeln und nach kurzer Pause senden; bis dahin zeigt die Oberfläche schon den neuen Stand */
  function save(ch) {
    pending = Object.assign(pending, ch); const d = rd(); if (d) d.rotation = Object.assign({}, d.rotation, ch);
    paintAll(true); clearTimeout(saveT); saveT = setTimeout(() => { const b = pending; pending = {}; post(b); }, 250);
  }

  function build(host) {
    const d = rd(), kids = [];
    if (!d) { host.replaceChildren(h('p', { class: 'muted', text: 'Wird geladen …' })); return; }
    const r = d.rotation || {}, free = SLOTS.filter(s => d.slots && d.slots[s]);
    if (!d.pip) { host.replaceChildren(alertBox({ tone: 'info', text: 'Die Rotation braucht Bild-in-Bild: Zuerst im Reiter „Aufbau“ mindestens ein kleines Bild festlegen und speichern.' })); return; }
    kids.push(sw({ checked: !!r.on, label: 'Rotation aktiv', hint: 'Wechselt die Kameras der gewählten Bilder reihum.', s: 'Kamera-Rotation aktiv', k: 'rotation wechseln reihum kameras tauschen', onchange: v => save({ on: v }) }));
    if (r.on) {
      kids.push(field({ label: 'Welche Bilder wechseln', control: h('div', null, seg('rot-all-' + host.dataset.rid, [['true', 'Alle Bilder'], ['false', 'Nur diese Bilder']], r.all ? 'true' : 'false', v => save({ all: v === 'true' }), 'Welche Bilder wechseln')) }));
      if (!r.all) kids.push(h('div', { class: 'stack', style: '--gap:var(--space-2)' }, free.map(s => sw({ checked: (r.slots || []).includes(s), label: SLOT_LABEL[s], onchange: v => save({ slots: free.filter(x => x === s ? v : (r.slots || []).includes(x)) }) }))));
      kids.push(field({ label: 'Wechselzeit (Sekunden)', hint: '5 bis 3600 Sekunden.', control: input({ type: 'number', min: 5, max: 3600, step: 1, inputmode: 'numeric', value: r.seconds || 30, onchange: e => save({ seconds: +e.target.value }) }), s: 'Wechselzeit der Rotation', k: 'rotation sekunden zeit' }));
      const pool = Array.isArray(r.pool) ? r.pool : null, keys = (d.cameras || []).map(x => x.key);
      kids.push(h('div', { class: 'stack', style: '--gap:var(--space-2)' }, h('h4', { text: 'Kameras für den Wechsel' }),
        list((d.cameras || []).map(c => row({ icon: 'camera', title: c.name, desc: [c.inactive ? 'deaktiviert' : '', !c.online ? 'nicht verbunden' : '', c.slot >= 0 ? SLOT_LABEL[SLOTS[c.slot]] : ''].filter(Boolean).join(' · '),
          end: sw({ checked: pool ? pool.includes(c.key) : true, aria: c.name + ' wechselt mit', onchange: v => { const now = new Set(pool || keys); v ? now.add(c.key) : now.delete(c.key); save({ pool: keys.filter(k => now.has(k)) }); } }) }))),
        h('p', { class: 'field__hint', text: 'Wechseln dürfen nur verbundene Kameras, die nicht deaktiviert sind. Kameras auf Bildern, die nicht wechseln, werden nie getauscht. Die Facecam bleibt immer auf ihrem Platz, damit der Ton bei ihr bleibt. Eine deaktivierte Kamera kommt in die Rotation, sobald sie wieder aktiv ist.' })));
    }
    if (rotMsg) kids.push(h('p', { class: 'field__hint', role: 'status', text: rotMsg }));
    host.replaceChildren(...kids);
  }
  /* Alle Formulare neu zeichnen (Formulare im geschlossenen Dialog fallen weg), solange darin nicht gerade getippt wird */
  function paintAll(force) {
    for (const host of [...hosts]) {
      if (!host.isConnected && !host.dataset.keep) { hosts.delete(host); continue; }
      const a = document.activeElement; if (!force && host.contains(a) && a.tagName === 'INPUT' && a.type === 'number') continue;
      build(host);
    }
  }
  function formHost(keep) { const host = h('div', { class: 'stack', data: Object.assign({ rid: String(++rid) }, keep && { keep: '1' }) }); hosts.add(host); build(host); return host; }
  App.on('rotation', d => { const sg = JSON.stringify(d); if (sg === lastSig) return; lastSig = sg; paintAll(false); });

  Neu.rot = {
    available: () => !!(rd() && rd().pip),
    on: () => !!(rd() && rd().pip && rd().rotation && rd().rotation.on),
    set: async ch => { await post(ch); },
    open: () => { Neu.sheet({ title: 'Kamera-Rotation', body: [formHost(false)], foot: [btn('Schließen', { onclick: Neu.closeSheet })] }); refresh(); },
  };
  if (Neu.slots.bild) Neu.slots.bild.add('b-rot', 'Rotation', card({ title: 'Kamera-Rotation', sub: 'Die Box tauscht die Kameras der gewählten Bilder reihum nach der eingestellten Zeit aus. Zum Beispiel bleibt das Hauptbild fest und nur das kleine Bild 1 wechselt durch alle anderen aktiven Kameras. Standard ist aus. Die Einstellung gilt sofort und wird nicht mit „Bildaufbau speichern“ gespeichert.', body: formHost(true) }));
})();
