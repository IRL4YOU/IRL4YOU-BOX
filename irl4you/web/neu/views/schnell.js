/* Schnellsteuerung: Hauptkamera, kleine Bilder und Ton ändern, ohne die Sendung neu zu starten.
   Zwei Orte, eine Bedienung: die Karte „Bild und Ton jetzt“ (Live) und die Leiste am unteren Rand des Handys. */
(() => {
  'use strict';
  const { h, ico, api, App, toast, run, badge, btn, row, list, sw, select, field } = Neu;
  const SLOT = ['main', 'pip', 'pip2', 'pip3'];
  const post = (p, b) => api('POST', p, b);
  async function act(fn) { try { const r = await fn(); if (r && r.note) toast(r.note); } catch (e) { toast(e.message); } finally { App.data['send:refresh'] && App.data['send:refresh'](); } }
  const A = {
    main: c => act(() => post('/api/pipeline/swap', { with: c.key })),
    view: c => act(() => post('/api/pipeline/view', { visible: { [c.slot]: c.hidden } })),
    active: c => act(() => post('/api/pipeline/active', { key: c.key, active: c.inactive })),
    audio: v => act(() => post('/api/pipeline/view', { audio: v })),
    mute: v => act(() => post('/api/pipeline/view', { mute: v })),
    assign: (slot, key) => act(() => post('/api/pipeline/assign', { slot, key })),
  };
  /* Live gehen und beenden: gleiche Regeln wie der große Knopf auf der Live-Seite */
  function liveState(s) {
    const running = s.state === 'running';
    if (s.active) return running ? { label: 'Stop', variant: 'danger', icon: 'stop' } : { label: '…', variant: '', icon: 'live', busy: true };
    return s.can_start ? { label: 'Live', variant: 'live', icon: 'play' } : { label: 'Live', variant: '', icon: 'play', dim: true };
  }
  async function goLive() {
    const s = App.data.send; if (!s) return;
    try {
      if (s.active) {
        if (s.state !== 'running') return toast('Die Sendung startet oder endet gerade, bitte kurz warten.');
        await post('/api/send', { action: 'stop' });
      } else if (s.can_start) await post('/api/send', { action: 'start', confirm: true });
      else { toast(s.state === 'refused' && s.message ? s.message : ((s.reasons || []).join(' · ') || 'Noch nicht bereit')); Neu.goto('live'); return; }
    } catch (e) { toast(e.message); }
    setTimeout(() => App.data['send:refresh'] && App.data['send:refresh'](), 700);
  }
  const footer = () => { const s = App.data.send; return s && s.footer && s.footer.cams && s.footer.cams.length ? s.footer : null; };
  const name = c => c.name || c.key;

  /* ---------- Kamera auf einen Platz legen (Hauptbild oder kleines Bild; liegt sie schon auf einem anderen Platz, tauschen beide) ---------- */
  const slotName = n => n === 0 ? 'Hauptbild' : n > 0 ? 'kleines Bild ' + n : '';
  const allCams = f => (f.all && f.all.length ? f.all : f.cams.map(c => ({ key: c.key, name: c.name, state: c.state, slot: c.slot })));
  function pickSheet(slot) {
    const f = footer(); if (!f) return;
    const cur = f.cams.find(c => c.slot === slot) || {};
    const rows = allCams(f).map(c => row({ icon: 'camera', title: name(c), desc: c.key === cur.key ? 'liegt auf diesem Platz' : c.slot >= 0 ? `liegt auf ${slotName(c.slot)}: tauscht` : 'nicht im Bild: ersetzt die Kamera auf diesem Platz', end: c.key === cur.key ? badge('hier', 'accent') : null,
      onclick: () => { Neu.closeSheet(); if (c.key !== cur.key) A.assign(slot, c.key); } }));
    Neu.sheet({ title: `Kamera für ${slotName(slot)}`, body: [list(rows), h('p', { class: 'field__hint', text: 'Tippe eine Kamera an, um sie auf diesen Platz zu legen. Liegt sie schon auf einem anderen Platz, tauschen beide.' })], foot: [btn('Abbrechen', { onclick: Neu.closeSheet })] });
  }

  /* ---------- Rotation: Schalter und Einstellungen (Zustand und Einstellungen liegen in mehr-kamera.js) ---------- */
  function rotBlock() {
    const r = Neu.rot; if (!r || !r.available()) return null;
    return h('div', { class: 'cluster', style: 'padding:var(--space-2) var(--space-4) 0' }, sw({ checked: r.on(), label: 'Kamera-Rotation', hint: 'Wechselt die Kameras der kleinen Bilder reihum.', onchange: (v, el) => run(el, () => r.set({ on: v })) }), btn('Rotation einstellen', { size: 'sm', onclick: () => r.open() }));
  }

  /* ---------- Vollständige Steuerung (Liste mit Knöpfen) ---------- */
  function body(f) {
    const rows = f.cams.map(c => {
      const end = [];
      if (c.main) end.push(badge('Hauptbild', 'accent'));
      else {
        end.push(btn('Zum Hauptbild', { size: 'sm', disabled: c.inactive || c.state === 'offline', onclick: () => A.main(c) }));
        end.push(btn(c.hidden ? 'Einblenden' : 'Ausblenden', { size: 'sm', disabled: c.inactive, onclick: () => A.view(c) }));
        end.push(btn(c.inactive ? 'Aktivieren' : 'Deaktivieren', { size: 'sm', variant: 'ghost', onclick: () => A.active(c) }));
      }
      end.push(btn('Kamera wählen', { size: 'sm', variant: 'ghost', onclick: () => pickSheet(c.slot) }));
      const desc = [c.main ? 'Großes Bild' : c.inactive ? 'Deaktiviert (nicht im Stream, kein Ton)' : c.hidden ? 'Bild ausgeblendet' : 'Kleines Bild', c.face ? 'Facecam' : '',
        f.audio && f.audio.key === c.key ? (f.audio.mute ? 'Ton stumm' : 'Ton von hier') : '', c.state === 'offline' ? 'kein Signal' : ''].filter(Boolean).join(' · ');
      return row({ icon: 'camera', title: name(c), desc, end });
    });
    const a = f.audio || {}, opts = f.cams.filter(c => !c.inactive).map(c => [SLOT[c.slot], name(c)]);
    const audioSel = select(opts, a.src || 'main', v => A.audio(v));
    return [list(rows), h('div', { class: 'cluster', style: 'padding:var(--space-3) var(--space-4) var(--space-4)' }, field({ label: 'Tonquelle', control: audioSel }),
      sw({ checked: !!a.mute, label: 'Ton stumm', onchange: (v, el) => run(el, () => post('/api/pipeline/view', { mute: v })) })), rotBlock()];
  }
  /* Nur neu zeichnen, wenn sich etwas geändert hat (sonst schließt sich zum Beispiel die geöffnete Tonauswahl alle 2 Sekunden) */
  const fill = (box, f) => {
    const sg = JSON.stringify([f, Neu.rot ? [Neu.rot.available(), Neu.rot.on()] : 0]);
    if (box.__sg === sg && box.firstChild) return; if (box.contains(document.activeElement) && document.activeElement.tagName === 'SELECT') return;
    box.__sg = sg; box.replaceChildren(...body(f).filter(Boolean));
  };

  /* ---------- Leiste am unteren Rand (nur Handy) ---------- */
  const bar = h('div', { class: 'qbar', id: 'qbar', hidden: true, role: 'toolbar', 'aria-label': 'Schnellsteuerung' });
  document.body.append(bar);
  let sig = '', sheetBox = null;
  const setH = () => { document.documentElement.style.setProperty('--qbar-h', bar.hidden ? '0px' : bar.offsetHeight + 'px'); document.body.toggleAttribute('data-qbar', !bar.hidden); };
  const side = document.querySelector('.side');
  const setNav = () => { if (side) document.documentElement.style.setProperty('--nav-h', side.offsetHeight + 'px'); setH(); };
  if (window.ResizeObserver) { new ResizeObserver(setNav).observe(side || document.body); new ResizeObserver(setH).observe(bar); } window.addEventListener('resize', setNav);

  /* Eine Taste mit drei Bedienungen: kurz, doppelt, lang. Der kurze Druck wartet einen Moment, ob ein zweiter folgt (nur wenn es eine Doppel-Bedienung gibt). */
  function gesture(el, g) {
    let pressT = 0, clickT = 0, fired = false, sx = 0, sy = 0;
    const cancel = () => clearTimeout(pressT);
    el.addEventListener('pointerdown', e => { if (e.button > 0) return; fired = false; sx = e.clientX; sy = e.clientY; cancel(); if (g.long) pressT = setTimeout(() => { fired = true; try { if (navigator.vibrate) navigator.vibrate(30); } catch (x) { /* nichts */ } g.long(); }, 520); });
    ['pointerup', 'pointercancel', 'pointerleave'].forEach(t => el.addEventListener(t, cancel));
    el.addEventListener('pointermove', e => { if (Math.abs(e.clientX - sx) > 12 || Math.abs(e.clientY - sy) > 12) cancel(); });
    el.addEventListener('contextmenu', e => e.preventDefault());
    el.addEventListener('click', e => {
      if (fired) { fired = false; e.preventDefault(); return; }               // nach langem Drücken kein zusätzlicher Klick
      if (e.detail === 0 || !g.dbl) { g.tap(); return; }                     // Tastatur oder keine Doppel-Bedienung: sofort
      if (clickT) { clearTimeout(clickT); clickT = 0; g.dbl(); return; }
      clickT = setTimeout(() => { clickT = 0; g.tap(); }, 270);
    });
  }
  /* Nach oben wischen auf einem Kamera-Knopf: alle aktiven Kameras erscheinen, wer den Finger auf einer Kamera loslässt, legt sie auf den Platz dieses Knopfes
     (liegt sie schon auf einem anderen Knopf, tauschen beide). Gleiche Bedienung wie in der bisherigen Oberfläche. */
  let swiping = false;
  function swipePick(el, c) {
    let st = null, pick = null, lastEnd = 0;
    const hit = (p, x, y) => { const e = document.elementFromPoint(x, y), it = e && e.closest ? e.closest('.qpick__item') : null; return it && p.contains(it) ? it : null; };
    el.addEventListener('pointerdown', e => { st = (e.pointerType === 'mouse' && e.button !== 0) ? null : { x: e.clientX, y: e.clientY }; });
    el.addEventListener('pointermove', e => {
      if (!st) return; const dx = e.clientX - st.x, up = st.y - e.clientY;
      if (!pick) {
        if (up < 28 || Math.abs(dx) > up) return;
        const f = footer(); if (!f) return;
        try { el.setPointerCapture(e.pointerId); if (navigator.vibrate) navigator.vibrate(15); } catch (x) { /* nichts */ }
        const items = allCams(f).map(k => h('div', { class: 'qpick__item', role: 'option', data: Object.assign({ key: k.key }, k.key === c.key && { cur: '' }) }, h('span', { class: 'qpick__dot', data: k.state !== 'offline' ? { live: '' } : {} }), h('span', { class: 'truncate', text: name(k) }),
          h('span', { class: 'qpick__tag', text: k.key === c.key ? 'dieser Knopf' : k.slot >= 0 ? `liegt auf ${slotName(k.slot)}: tauscht` : '' })));
        pick = h('div', { class: 'qpick', role: 'listbox' }, h('div', { class: 'qpick__h', text: 'Kamera für diesen Knopf wählen: Finger auf eine Kamera ziehen und loslassen' }), items);
        document.body.append(pick); swiping = true; return;
      }
      const t = hit(pick, e.clientX, e.clientY);
      pick.querySelectorAll('.qpick__item[data-on]').forEach(x => x !== t && x.removeAttribute('data-on')); if (t) t.dataset.on = '';
    });
    const end = e => {
      if (!st) return; const p = pick; st = null; pick = null; if (!p) return;
      lastEnd = Date.now(); const t = e.type === 'pointercancel' ? null : hit(p, e.clientX, e.clientY); p.remove(); swiping = false;
      if (t && t.dataset.key !== c.key) A.assign(c.slot, t.dataset.key);
    };
    el.addEventListener('pointerup', end); el.addEventListener('pointercancel', end);
    el.addEventListener('click', e => { if (Date.now() - lastEnd < 500) { e.stopImmediatePropagation(); e.preventDefault(); } }, true);   // nach dem Wischen kein Klick
  }
  /* Deaktivierte Kamera: einschalten, das kleine Bild bleibt aus (Ton nutzbar) */
  const wake = c => act(async () => { await post('/api/pipeline/active', { key: c.key, active: true }); await post('/api/pipeline/view', { visible: { [c.slot]: false } }); toast('Aktiviert, Bild ausgeblendet: Ton nutzbar.'); });
  function chip(c, a) {
    const b = h('button', { class: 'qchip', type: 'button', 'aria-pressed': String(!!c.main), title: name(c) + (c.main ? ' ist das Hauptbild' : ' zum Hauptbild machen'),
      data: Object.assign({}, c.main && { main: '' }, c.inactive && { off: '' }, c.hidden && { hid: '' }) }, h('span', { text: name(c) }), a.key === c.key ? ico(a.mute ? 'micoff' : 'mic', 'sm') : null);
    swipePick(b, c);
    gesture(b, {
      tap: () => {
        if (c.main) return toast(`${name(c)} ist schon das Hauptbild.`);
        if (c.inactive) return wake(c);
        if (c.state === 'offline') return toast(`${name(c)} ist nicht verbunden und kann nicht Hauptbild werden.`);
        A.main(c);
      },
      dbl: () => {
        if (c.main) return toast('Das Hauptbild lässt sich nicht ausblenden. Zum Tauschen kurz auf eine andere Kamera drücken.');
        if (c.inactive) return wake(c);
        A.view(c);                                                           // kleines Bild aus- oder einblenden (der Ton bleibt)
      },
      long: () => {
        if (c.main) return toast('Das Hauptbild lässt sich nicht deaktivieren.');
        A.active(c); toast(c.inactive ? 'Aktiviert.' : 'Deaktiviert: nicht mehr im Stream, Ton nicht nutzbar.');
      } });
    return b;
  }
  /* Oberfläche sperren: Inhalt lässt sich nicht mehr antippen oder scrollen (gegen Berührungen in der Tasche); Leiste und Kopfzeile bleiben bedienbar */
  let locked = false, lockY = 0;
  const lockEls = () => [document.getElementById('views'), document.querySelector('.side')].filter(Boolean);
  function setLock(v) {
    if (v === locked) return; locked = v; if (v) lockY = window.scrollY;
    lockEls().forEach(e => { e.inert = v; }); document.body.toggleAttribute('data-locked', v); if (v) window.scrollTo(0, lockY);
    sig = ''; draw();
  }
  const lockStop = e => { if (locked && !e.target.closest('.qbar, header, dialog, .qpick')) e.preventDefault(); };
  ['touchmove', 'wheel'].forEach(n => document.addEventListener(n, lockStop, { passive: false }));
  window.addEventListener('scroll', () => { if (locked && Math.abs(window.scrollY - lockY) > 1) window.scrollTo(0, lockY); });
  document.addEventListener('keydown', e => { if (locked && [' ', 'PageDown', 'PageUp', 'Home', 'End', 'ArrowUp', 'ArrowDown'].includes(e.key) && !e.target.closest('input, select, textarea')) e.preventDefault(); });

  const big = b => { const i = b.querySelector('.icon'); if (i) i.removeAttribute('data-size'); return b; };
  function draw() {
    const s = App.data.send, f = footer();
    if (swiping) return;
    if (!s || !f) { if (locked) setLock(false); }
    if (!s) { bar.hidden = true; sig = ''; setH(); return; }
    const rot = Neu.rot && Neu.rot.available();
    const sg = JSON.stringify([f, s.active, s.state, s.can_start, rot, rot && Neu.rot.on(), locked]); if (sg === sig) { bar.hidden = false; return; } sig = sg;
    const st = liveState(s), a = (f && f.audio) || {}, multi = !!f && f.cams.length >= 2;
    const go = h('button', { class: 'qlive', type: 'button', disabled: !!st.busy, 'aria-label': st.dim ? 'Live gehen (noch nicht bereit)' : st.label, data: Object.assign({}, st.variant && { tone: st.variant }, st.dim && { dim: '' }), onclick: goLive }, ico(st.icon), h('span', { text: st.label }));
    const rows = [], tools = [go];
    if (multi) rows.push(h('div', { class: 'qbar__row qbar__cams', role: 'group', 'aria-label': 'Hauptbild wählen' }, ...f.cams.map(c => chip(c, a))));
    if (f) {
      const an = a.name || a.key || '', one = !multi || (a.next || '') === (a.src || '');
      const aud = h('button', { class: 'qtool qaud', type: 'button', title: 'Tonquelle wechseln: ' + an, 'aria-label': 'Tonquelle wechseln: ' + an }, ico(a.mute ? 'micoff' : 'mic'), h('span', { text: an }));
      gesture(aud, { tap: () => one ? toast('Es gibt nur eine Tonquelle. Lang drücken schaltet stumm oder wieder laut.') : A.audio(a.next || 'main'),
        long: () => { if (!s || !s.active) return toast('Stumm schalten geht nur während der Sendung.'); A.mute(!a.mute); } });
      const mute = big(Neu.iconBtn(a.mute ? 'micoff' : 'mic', a.mute ? 'Ton einschalten' : 'Ton stumm schalten', () => { if (!s || !s.active) return toast('Stumm schalten geht nur während der Sendung.'); A.mute(!a.mute); }, { variant: a.mute ? 'danger' : '', size: '' }));
      mute.setAttribute('aria-pressed', String(!!a.mute));
      const more = big(Neu.iconBtn('sliders', 'Alle Kamera- und Toneinstellungen', () => { sheetBox = h('div', { class: 'stack' }); fill(sheetBox, footer() || f); Neu.sheet({ title: 'Bild und Ton jetzt', body: [sheetBox, h('p', { class: 'field__hint', text: 'Tipp für die Leiste: Eine Kamera kurz antippen macht sie zum Hauptbild, doppelt antippen blendet ihr kleines Bild aus oder ein, lang drücken deaktiviert oder aktiviert die Kamera, nach oben wischen legt eine andere Kamera auf diesen Platz. Beim Ton-Knopf wechselt kurz die Tonquelle, lang schaltet stumm.' }),
        h('div', { class: 'stack', style: '--gap:var(--space-2)' }, btn(locked ? 'Oberfläche entsperren' : 'Oberfläche sperren', { ico: 'lock', onclick: () => { Neu.closeSheet(); setLock(!locked); } }), h('p', { class: 'field__hint', text: 'Gesperrt lässt sich der Inhalt nicht mehr antippen oder scrollen, zum Beispiel in der Tasche. Die Leiste unten bleibt bedienbar.' }))], foot: [btn('Schließen', { onclick: Neu.closeSheet })] }); }, { variant: '', size: '' }));
      tools.push(aud, mute);
      if (rot) {
        const on = Neu.rot.on(), rb = big(Neu.iconBtn('refresh', on ? 'Kamera-Rotation ausschalten (lang drücken: einstellen)' : 'Kamera-Rotation einschalten (lang drücken: einstellen)', () => { }, { variant: on ? 'primary' : '', size: '' }));
        rb.setAttribute('aria-pressed', String(on)); gesture(rb, { tap: () => Neu.rot.set({ on: !on }), long: () => Neu.rot.open() }); tools.push(rb);
      }
      if (locked) { const lb = big(Neu.iconBtn('lock', 'Oberfläche entsperren', () => setLock(false), { variant: 'primary', size: '' })); lb.setAttribute('aria-pressed', 'true'); tools.push(lb); }
      tools.push(more);
    }
    rows.push(h('div', { class: 'qbar__row' }, ...tools));
    bar.replaceChildren(...rows); bar.hidden = false; setH();
  }
  App.on('rotation', draw);
  App.on('send', () => { draw(); if (sheetBox && sheetBox.isConnected) { const f = footer(); if (f) fill(sheetBox, f); } });
  Neu.quick = { body, fill, pickSheet };
  Neu.live = { state: liveState, go: goLive };
})();
