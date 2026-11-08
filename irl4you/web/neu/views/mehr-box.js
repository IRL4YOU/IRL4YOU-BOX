/* IRL4YOU BOX · neue Oberfläche · Ergänzungen (box): Funktionen der bisherigen Oberfläche, die es in der Vorlage nicht gab.
   Enthält: Streammodus blendet Vertrauliches aus, Encoder (Hardware/Software), Passwort der Oberfläche ändern, Mobilfunk-Modems. */
(() => {
  'use strict';
  const { h, api, App, poll, ask, run, badge, btn, card, sw, field, input, note, ftime } = Neu;
  const panel = id => document.getElementById(id);

  /* ---- Streammodus: Elemente mit class "sens" (WLAN-Namen und Passwörter, SSH-Passwort, Kanalnamen) verschwinden; class "sm-only" zeigt nur dort einen Hinweis ---- */
  document.head.append(h('style', { text: 'body.sm .sens { display: none !important; } .sm-only { display: none; } body.sm .sm-only { display: block; }' }));

  /* =================================================================
     Encoder (Hardware oder Software), im Reiter „Entwickler“ wie in der bisherigen Oberfläche
     ================================================================= */
  (() => {
    const dev = panel('sy-dev'); if (!dev) return;
    const host = h('div'), msg = note(); let sig = ''; dev.append(host);
    const refresh = poll('encoder', '/api/encoder', 15000, () => App.view === 'system');
    async function choose(mode, d) {
      if (d.sending && !await ask({ title: 'Encoder während der Sendung wechseln?', text: 'Die Sendung wird dabei kurz neu gestartet, das Bild setzt für einen Moment aus.', ok: 'Wechseln' })) { sig = ''; render(); return; }
      msg.set('Wird gespeichert …');
      try { const r = await api('POST', '/api/encoder', { mode }); App.set('encoder', r); msg.set(r.note || 'Gespeichert.', 'ok'); } catch (x) { msg.set(x.message, 'bad'); }
      sig = ''; refresh();
    }
    function render() {
      const d = App.data.encoder; if (!d) return; const sg = JSON.stringify(d); if (sg === sig) return; sig = sg;
      const opt = (v, t, desc, off) => h('label', { class: 'radio' }, h('input', { type: 'radio', name: 'enc-mode', value: v, checked: d.mode === v, disabled: off, onchange: () => choose(v, d) }), h('span', { class: 'radio__text' }, h('b', { text: t }), h('small', { text: desc })));
      host.replaceChildren(card({ title: 'Encoder', actions: [badge(d.mode === 'software' ? 'Software' : 'Hardware')], sub: 'Wie die Box das Bild für die Sendung kodiert.', body: [
        field({ s: 'Encoder Hardware Software', k: 'encoder hardware software x264 h265 kodierung cpu', label: 'Kodierung', control: h('div', { class: 'stack', style: '--gap:var(--space-2)' },
          opt('hardware', 'Hardware', 'Videoeinheit des Chips (H.265), geringe CPU-Last, empfohlen.'),
          opt('software', 'Software', d.software_available ? 'x264 auf den CPU-Kernen (H.264), hohe CPU-Last, nur bei Problemen mit dem Hardware-Encoder.' : 'Auf dieser Box nicht verfügbar (x264 fehlt).', !d.software_available)) }),
        msg] }));
    }
    App.on('encoder', render);
  })();

  /* =================================================================
     Passwort der Oberfläche ändern, im Reiter „Box“ (Passwörter stehen nie in Meldungen)
     ================================================================= */
  (() => {
    const box = panel('sy-box'); if (!box) return;
    const slot = panel('sy-box-pw') || box;       // Platz 2 im Reiter „Box“ (zwischen Ausschalten und Aussehen)
    const host = h('div', slot === box ? { style: 'margin-top:var(--space-5)' } : {}), msg = note(); slot.append(host);
    const bytes = t => new TextEncoder().encode(t).length;
    function render(auth) {
      if (auth.mode !== 'own') { host.replaceChildren(card({ title: 'Passwort ändern', body: h('p', { class: 'muted', style: 'font-size:var(--text-sm)', text: auth.mode === 'demo' ? 'In der Vorschau nicht möglich.' : 'Das Passwort lässt sich hier nicht ändern.' }) })); return; }
      const old = input({ type: 'password', autocomplete: 'current-password', maxlength: 128, required: true }), n1 = input({ type: 'password', autocomplete: 'new-password', maxlength: 72, minlength: 10, required: true }), n2 = input({ type: 'password', autocomplete: 'new-password', maxlength: 72, minlength: 10, required: true });
      const rem = sw({ label: 'Angemeldet bleiben', hint: 'Auf diesem Gerät auch nach dem Schließen des Browsers.' });
      const go = h('button', { class: 'btn', type: 'submit', 'data-variant': 'primary' }, 'Passwort ändern');
      const form = h('form', { class: 'stack', autocomplete: 'off', onsubmit: async e => {
        e.preventDefault();
        if (n1.value.length < 10) { msg.set('Das neue Passwort braucht mindestens 10 Zeichen.', 'bad'); return; }
        if (bytes(n1.value) > 72) { msg.set('Das neue Passwort ist zu lang (höchstens 72 Byte).', 'bad'); return; }
        if (n1.value !== n2.value) { msg.set('Die beiden neuen Passwörter sind verschieden.', 'bad'); return; }
        msg.set('');
        await run(go, async () => {
          try { await api('POST', '/api/password', { old: old.value, new: n1.value, remember: rem.firstChild.checked }); form.reset(); msg.set('Passwort geändert. Andere Geräte müssen sich neu anmelden.', 'ok'); }
          catch (x) { msg.set(x.message, 'bad'); }
        });
      } }, field({ label: 'Bisheriges Passwort', control: old, s: 'Passwort ändern', k: 'passwort ändern anmeldung login' }), field({ label: 'Neues Passwort', control: n1, hint: 'Mindestens 10 Zeichen.' }), field({ label: 'Neues Passwort wiederholen', control: n2 }), rem, msg, h('div', { class: 'cluster' }, go));
      host.replaceChildren(card({ title: 'Passwort ändern', sub: 'Das Passwort, mit dem du dich bei dieser Box anmeldest. Nach der Änderung müssen sich alle anderen Geräte neu anmelden.', body: form }));
    }
    fetch('/api/auth', { cache: 'no-store' }).then(r => r.json()).then(render).catch(() => { /* ohne Auskunft kein Formular */ });
  })();

  /* =================================================================
     Netzwerk > Mobilfunk: USB-Modems und M.2 (ModemManager)
     ================================================================= */
  (() => {
    const T = Neu.slots.netz; if (!T) return;
    const box = h('div', { class: 'stack', style: '--gap:var(--space-5)' }), msg = note();
    T.add('n-modem', 'Mobilfunk', box);
    const tab = T.list.querySelector('[aria-controls="n-modem"]'), before = T.list.querySelector('[aria-controls="n-bt"]'); if (tab && before) T.list.insertBefore(tab, before);   /* nach WLAN, vor Bluetooth */
    const STATE = { 'kein-sim': ['danger', 'Keine SIM-Karte'], 'gesperrt': ['warn', 'SIM gesperrt (PIN)'], 'fehler': ['danger', 'Fehler'], 'aus': ['warn', 'Aus'], 'suche': ['warn', 'Sucht Netz …'], 'eingebucht': ['warn', 'Eingebucht, nicht verbunden'], 'verbinde': ['warn', 'Verbindet …'], 'verbunden': ['ok', 'Verbunden'] };
    const refresh = poll('modems', '/api/modems', 6000, () => App.view === 'netz');
    const drafts = {}, opened = new Set(); let sig = '', again = 0;
    const later = () => [1200, 4000, 9000, 16000].forEach(ms => setTimeout(refresh, ms));
    const draftOf = m => drafts[m.id] || (drafts[m.id] = { autoconfig: (m.config || {}).autoconfig !== false, apn: (m.config || {}).apn || '', username: (m.config || {}).username || '', password: '', roaming: !!(m.config || {}).roaming, network: (m.config || {}).network || '', network_type: (m.config || {}).network_type || '' });

    function modemCard(m, busy) {
      const st = STATE[m.state] || ['warn', m.state], dr = draftOf(m), cfg = m.config || {};
      const parts = [m.iface, m.signal == null ? null : `Signal ${m.signal} %`, m.operator, m.roaming ? 'Roaming' : null, (m.tech || []).length ? m.tech.join('/') : null].filter(Boolean);
      const info = h('p', { class: 'muted', style: 'font-size:var(--text-sm)' }, parts.flatMap((t, i) => i ? [' · ', h('span', { text: t })] : [h('span', { text: t })]));
      const apn = input({ value: dr.apn, maxlength: 100, autocomplete: 'off', disabled: dr.autoconfig, oninput: e => { dr.apn = e.target.value.trim(); } });
      const user = input({ value: dr.username, maxlength: 64, autocomplete: 'off', disabled: dr.autoconfig, oninput: e => { dr.username = e.target.value.trim(); } });
      const pw = input({ type: 'password', maxlength: 64, autocomplete: 'new-password', disabled: dr.autoconfig, placeholder: cfg.password_set ? 'Gespeichert (leer lassen = unverändert)' : 'Meist leer', oninput: e => { dr.password = e.target.value; } });
      const auto = sw({ checked: dr.autoconfig, label: 'APN automatisch (nach SIM-Karte)', s: `Mobilfunk-Modem ${m.name}: APN automatisch`, k: 'mobilfunk modem sim apn lte', onchange: v => { dr.autoconfig = v; apn.disabled = user.disabled = pw.disabled = v; } });
      const typeSel = h('select', { class: 'select', onchange: e => { dr.network_type = e.target.value; } }, h('option', { value: '' }, 'Automatisch (wie vom Modem gewählt)'), (m.network_types || []).map(t => h('option', { value: t.key, selected: t.key === dr.network_type }, t.label)));
      const nets = m.available_networks || [];
      const netSel = h('select', { class: 'select', onchange: e => { dr.network = e.target.value; } }, h('option', { value: '' }, 'Automatisch'),
        nets.map(n => h('option', { value: n.code, selected: n.code === dr.network, disabled: !!n.forbidden }, `${n.name} (${n.code}) ${(n.tech || []).join('/')}${n.current ? ' · aktuell' : ''}${n.forbidden ? ' · gesperrt' : ''}`)),
        dr.network && !nets.some(n => n.code === dr.network) ? h('option', { value: dr.network, selected: true }, dr.network) : null);
      const save = btn('Speichern und neu verbinden', { variant: 'primary', disabled: busy, onclick: async () => {
        const body = { action: 'config', id: m.id, autoconfig: dr.autoconfig, roaming: dr.roaming, network: dr.network, network_type: dr.network_type };
        if (!dr.autoconfig) { body.apn = dr.apn; body.username = dr.username; if (dr.password) body.password = dr.password; }
        msg.set('Wird gespeichert …'); try { await api('POST', '/api/modems', body); delete drafts[m.id]; opened.delete(m.id); sig = ''; later(); } catch (x) { msg.set(x.message, 'bad'); }
      } });
      const scan = btn('Netze suchen', { ico: 'refresh', disabled: busy || m.no_sim, onclick: async () => { msg.set('Suche läuft, das kann einige Minuten dauern …'); try { await api('POST', '/api/modems', { action: 'scan', id: m.id }); later(); } catch (x) { msg.set(x.message, 'bad'); } } });
      const det = Neu.disclosure('Einstellen', auto, h('div', { class: 'grid-auto', style: '--min:14rem' }, field({ label: 'APN', control: apn }), field({ label: 'Benutzername', control: user }), field({ label: 'Passwort', control: pw })),
        h('div', { class: 'grid-auto', style: '--min:14rem' }, field({ label: 'Netztyp', control: typeSel }), field({ label: 'Netz', control: netSel, hint: m.scan_time ? `Letzte Suche: ${ftime(m.scan_time)}` : 'Mit „Netze suchen“ werden die Netze in der Nähe angezeigt.' })),
        sw({ checked: dr.roaming, label: 'Roaming erlauben', hint: 'Im Ausland, kann Kosten verursachen.', onchange: v => { dr.roaming = v; } }),
        h('div', { class: 'cluster' }, save, scan));
      det.open = opened.has(m.id); det.addEventListener('toggle', () => { if (det.open) opened.add(m.id); else opened.delete(m.id); });
      return card({ title: m.name, actions: [badge(st[1], st[0])], body: [info, det] });
    }
    function render() {
      const d = App.data.modems; if (!d) return;
      const sg = JSON.stringify([d, [...opened]]); if (sg === sig) return;
      if (box.contains(document.activeElement) && /^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement.tagName)) return; sig = sg;
      const busy = d.state === 'working' || !d.helper_installed;
      if (!d.helper_installed) msg.set('Der Mobilfunk-Helfer ist auf dieser Box noch nicht installiert (install.sh erneut ausführen).', 'bad'); else if (d.state === 'working') msg.set(d.message || 'Läuft …'); else if (d.message) msg.set(d.message, d.state === 'error' ? 'bad' : '');
      clearTimeout(again); if (d.state === 'working') again = setTimeout(refresh, 2000);
      box.replaceChildren(
        card({ title: 'Mobilfunk-Modems', sub: 'Steckt ein Mobilfunk-Modem mit SIM-Karte (USB-Stick oder M.2), richtet die Box es automatisch ein (APN nach SIM-Karte). Danach unter Leitungen zum Senden ankreuzen. Hier lassen sich APN, Roaming, Netztyp und ein festes Netz einstellen.',
          actions: [btn('Zu Leitungen', { size: 'sm', onclick: () => Neu.goto('netz', 'n1') })], body: [msg] }),
        ...(d.modems.length ? d.modems.map(m => modemCard(m, busy)) : [h('div', { class: 'empty card' }, 'Kein Modem gefunden. Mobilfunk-Sticks und M.2-Module erscheinen hier, sobald ModemManager sie erkennt.')]));
    }
    App.on('modems', render);
  })();
})();
