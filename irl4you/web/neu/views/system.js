/* Ansicht „System“: Updates, Chat und Deck, Eingabe (Controller), Sicherung, Protokolle, Hilfe, Entwickler, Box und Aussehen. */
(() => {
  'use strict';
  const { h, ico, fmt, api, App, poll, ask, toast, run, badge, btn, alertBox, card, row, list, sw, field, input, select, seg, disclosure, pageHead, view, note, prog, md, copyBtn, copyText, sleep, fdate, ftime, kv } = Neu;
  const store = (k, v) => { try { if (v === undefined) return localStorage.getItem(k); v === null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch (e) { /* privat */ } return null; };
  const pad2 = n => String(n).padStart(2, '0');
  const download = (blob, name) => { const a = h('a', { href: URL.createObjectURL(blob), download: name }); document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 20000); };
  const stamp = () => { const n = new Date(); return `${n.getFullYear()}${pad2(n.getMonth() + 1)}${pad2(n.getDate())}-${pad2(n.getHours())}${pad2(n.getMinutes())}`; };

  view('system', sec => {
    const T = Neu.slots.system = Neu.tabbed(sec, 'System');
    sec.prepend(pageHead('System', 'Updates, Chat, Sicherung, Hilfe und Aussehen.'));

    /* =================================================================
       Updates: Software (IRL4YOU BOX)
       ================================================================= */
    const swBox = h('div');
    let swChecking = 0, swPending = 0, swSaw = false, swFirst = null, swSig = '', swVersions = [], swCur = '', verInput = input({ placeholder: 'Version wählen oder eintragen, z. B. 0.9.0', maxlength: 24, list: 'sw-vers', autocomplete: 'off' }), verInfo = h('p', { class: 'field__hint' }), dl = h('datalist', { id: 'sw-vers' }), swMsg = note(), swHist = null, histSecs = null, histQ = input({ type: 'search', placeholder: 'Suchen …', maxlength: 60, 'aria-label': 'Änderungen durchsuchen', style: 'height:2rem;padding:0 var(--space-2) 0 2rem;font-size:var(--text-sm)' });
    const swPoll = poll('swupdate', '/api/swupdate', 8000, () => App.view === 'system' || swPending);
    const SW_TERMINAL = ['failed', 'refused', 'rolledback']; let swNewer = false, sysAvail = false; const navDot = () => { const nd = document.getElementById('nd-system'); nd.hidden = !(swNewer || sysAvail); nd.dataset.tone = ''; };
    const swBegin = text => { swPending = Date.now(); swSaw = false; window.pbUpdating = swPending; swMsg.set(text); swSig = ''; renderSw(); };
    function swFinish(cur) { window.pbUpdating = 0; swPending = 0; try { sessionStorage.setItem('pb_updated', cur || ''); } catch (e) { /* privat */ } swMsg.set('Das Update ist fertig. Die Seite lädt neu und zeigt bei Bedarf die Anmeldung.', 'ok'); setTimeout(() => location.reload(), 2000); }
    async function swPublic() {
      let p; try { p = await (await fetch('/api/swprogress')).json(); } catch (e) { swMsg.set('Die Oberfläche startet gerade neu, einen Moment …'); return; }
      if (p.state === 'installing') { swSaw = true; swMsg.set('Die Oberfläche startet gerade neu, das Update läuft weiter. Die Seite lädt danach von selbst neu.'); return; }
      if (p.state === 'done' || p.state === 'rolledback') { swFinish(); return; }
      if (p.state === 'failed' || p.state === 'refused') { window.pbUpdating = 0; swPending = 0; swMsg.set('Das Update ist fehlgeschlagen. Die Seite lädt neu; nach der Anmeldung steht die Meldung in dieser Karte.', 'bad'); setTimeout(() => location.reload(), 4000); return; }
      if (Date.now() - window.pbUpdating > 120000) location.reload();
    }
    setInterval(() => { if (swPending) { if (!App.data['swupdate:ok']) swPublic(); else swPoll(); } }, 2000);
    const swAct = async (body, begin) => { swBegin(begin); try { await api('POST', '/api/swupdate', body); } catch (x) { swPending = 0; window.pbUpdating = 0; swMsg.set(x.message, 'bad'); } setTimeout(swPoll, 1500); };
    /* Die Prüfung läuft im Hintergrund (Helfer); hier warten, bis ein neues Ergebnis da ist, und es sagen */
    async function swCheck() {
      const t0 = (App.data.swupdate || {}).checked_at || 0; swChecking = Date.now(); swMsg.set('Suche nach Updates …'); let d = App.data.swupdate || {};
      try {
        d = await api('GET', '/api/swupdate?check=1'); App.set('swupdate', d);
        const end = Date.now() + 30000;
        while (Date.now() < end && (d.checked_at || 0) === t0 && d.state !== 'installing') { await sleep(1500); d = await api('GET', '/api/swupdate'); App.set('swupdate', d); }
      } catch (e) { toast(e.message); } finally { swChecking = 0; swSig = ''; }
      App.set('swupdate', d);
      toast((d.checked_at || 0) === t0 ? 'Die Prüfung hat nicht geantwortet. Bitte gleich noch einmal versuchen.' : d.newer ? 'Neue Version ' + (d.latest_version || d.latest) + ' ist verfügbar.' : d.pending ? 'Neue Version ' + (d.latest_version || d.latest) + ' wird noch geprüft. Das Update kommt in wenigen Minuten.' : d.message && !/aktuell/i.test(d.message) ? d.message : 'Du hast die neueste Version.');
    }
    function renderSw() {
      const d = App.data.swupdate; if (!d) return;
      if (swFirst === null) swFirst = d.current; const installing = d.state === 'installing'; if (installing) { swSaw = true; if (!swPending) { swPending = Date.now(); window.pbUpdating = swPending; } }
      if (swFirst !== d.current && !installing) { swFinish(d.current); return; }
      if (swPending) { const age = Date.now() - swPending; if ((d.state === 'done' || (d.state === 'rolledback' && swFirst !== d.current)) && (swSaw || age > 25000)) { swFinish(d.current); return; } if (age > 10000 && SW_TERMINAL.includes(d.state)) { swPending = 0; window.pbUpdating = 0; } else if (age > 900000) { swPending = 0; window.pbUpdating = 0; } }
      const sg = JSON.stringify([d, swPending, histSecs && 1]); if (sg === swSig) return; if (swBox.contains(document.activeElement) && document.activeElement.tagName === 'INPUT') return; swSig = sg;
      const busy = installing || !!swPending; swVersions = d.versions || []; swCur = d.current; window.swCurVer = d.current;
      document.getElementById('ver').textContent = 'Version ' + d.current + (d.stage ? ' (' + d.stage + ')' : '');
      swNewer = !!d.newer; navDot();
      dl.replaceChildren(...swVersions.filter(v => !v.current).map(v => h('option', { value: v.version }, `${v.version} · ${v.relation}${v.local ? ' · gesichert' : ''}${v.github ? ' · GitHub' : ''}${v.date ? ' · ' + v.date : ''}`)));
      let m = ''; if (!d.helper_installed) m = 'Der Update-Helfer ist nicht installiert. Bitte install.sh einmal erneut ausführen.'; else if (d.error) m = d.error; else if (busy) m = (d.state === 'installing' ? 'Das Update läuft' : 'Update wird gestartet') + ' … Die Seite lädt danach von selbst neu.';
      else if (d.state === 'done' || d.state === 'rolledback' || d.state === 'refused' || d.state === 'failed') m = d.message; else if (d.sending && d.newer) m = 'Update gesperrt: Es wird gerade gesendet.'; else if (d.newer && d.bridge) m = 'Die Testphase ist beendet: Dieses Update führt zurück auf die stabile Version. Installieren geht nur, wenn nicht gesendet wird.'; else if (d.newer) m = 'Eine neue Version ist da. Installieren geht nur, wenn nicht gesendet wird.';
      else if (d.pending) m = 'Neue Version ' + (d.latest_version || d.latest) + ' wird noch von GitHub geprüft. Das Update kommt in wenigen Minuten.';
      else if (d.latest) m = 'Du hast die neueste Version.' + (d.checked_at ? ` Zuletzt geprüft um ${ftime(d.checked_at)}.` : '');
      if (swChecking && !busy) m = 'Suche nach Updates …';
      swMsg.set(m, (d.state === 'failed' || d.error) && !swPending ? 'bad' : '');
      const x = () => swVersions.find(v => v.version === verInput.value.trim().replace(/^v/, ''));
      const showInfo = () => { const raw = verInput.value.trim(), v = x(); verInfo.textContent = !raw ? (swVersions.length > 1 ? 'Verfügbar: ' + swVersions.filter(q => !q.current).slice(0, 6).map(q => q.version + (q.relation === 'älter' ? ' (älter)' : ' (neuer)')).join(', ') + '.' : 'Es sind noch keine anderen Versionen gesichert oder veröffentlicht.') : (!v || v.current) ? (v && v.current ? 'Diese Version ist schon installiert.' : 'Diese Version kennt die Box nicht (weder gesichert noch auf GitHub veröffentlicht).') : `Version ${v.version}: ${v.relation}${v.local ? ', lokal gesichert (sofort verfügbar)' : ''}${v.github ? ', auf GitHub veröffentlicht' : ''}${v.date ? ', ' + v.date : ''}.`; }; verInput.oninput = showInfo; showInfo();
      swBox.replaceChildren(card({ title: 'Software-Update (IRL4YOU BOX)', sub: 'Holt neue Versionen dieser Software aus dem Repository auf GitHub. Kameras, Server und Einstellungen bleiben erhalten. Nicht während einer Übertragung.',
        actions: [busy ? badge('läuft …', 'accent') : d.error ? badge('unbekannt') : d.newer ? badge('Update verfügbar', 'accent') : d.pending ? badge('kommt gleich', 'accent') : d.channel === 'test' ? badge('Testversion', 'warn') : badge('aktuell', 'ok')], body: [
        kv('Installiert', 'v' + d.current + (d.stage ? ' (' + d.stage + ')' : '')), kv('Neueste auf GitHub', d.latest ? 'v' + (d.latest_version || d.latest) : (d.error ? '–' : 'wird geprüft …')),
        d.newer && d.notes ? md(d.notes) : null, busy ? prog(d.progress || 0, d.step || 'Update wird gestartet') : null, swMsg,
        h('div', { class: 'cluster' }, btn('Nach Updates suchen', { size: 'sm', ico: 'refresh', disabled: busy, run: swCheck }),
          btn('Update installieren', { size: 'sm', variant: d.newer ? 'primary' : null, disabled: busy || !d.newer || d.sending || !d.helper_installed, onclick: async () => { if (await ask({ title: 'Software-Update installieren?', text: '• Es darf KEINE Übertragung laufen.\n• Die Oberfläche startet dabei kurz neu (etwa eine halbe Minute).\n• Kameras und Einstellungen bleiben erhalten; der Kamera-Dienst startet nur neu, wenn sich seine Dateien ändern.\n• Die jetzige Version wird gesichert, du kannst zurückgehen.', ok: 'Installieren' })) swAct({ action: 'install', confirm: true }, 'Update wird gestartet …'); } }),
          d.backup_version && !busy ? btn(`Zurück zu Version ${d.backup_version}`, { size: 'sm', onclick: async () => { if (await ask({ title: 'Zur vorherigen Version zurückgehen?', text: 'Die Oberfläche startet dabei kurz neu. Es darf nicht gesendet werden.', ok: 'Zurückgehen' })) swAct({ action: 'rollback', confirm: true }, 'Wird zurückgestellt …'); } }) : null),
        h('div', { class: 'stack', style: '--gap:var(--space-2)' }, h('label', { class: 'field__label', text: 'Auf eine bestimmte Version wechseln (auch ältere)' }), h('div', { class: 'cluster', style: 'flex-wrap:nowrap' }, h('div', { class: 'grow' }, verInput), dl,
          btn('Wechseln', { disabled: busy || d.sending || !d.helper_installed, onclick: async () => { const v = x(); if (!v || v.current) { showInfo(); return; } const older = v.relation === 'älter'; if (await ask({ title: `Auf Version ${v.version} wechseln?`, text: (older ? `ACHTUNG: Das ist eine ÄLTERE Version als die installierte (${swCur}). Neuere Funktionen und Korrekturen fehlen dann.\n\n` : '') + '• Es darf KEINE Übertragung laufen.\n• Die Oberfläche startet dabei kurz neu.\n• Die jetzige Version wird vorher gesichert, du kannst wieder zurück.', ok: 'Wechseln', danger: older })) swAct({ action: 'switch', version: v.version, older, confirm: true }, 'Wechsel wird gestartet …'); } })), verInfo), hist] }));      // "Alle Änderungen" klappt unten in derselben Karte auf
    }
    /* Alle Änderungen (Verlauf mit Suche) */
    const histRes = h('div'), histCount = h('p', { class: 'field__hint' });
    function parseHist(text) { const out = []; let cur = null, it = null; String(text || '').split('\n').forEach(raw => { const l = raw.replace(/\s+$/, ''); if (/^##\s+/.test(l)) { cur = { head: l, items: [] }; out.push(cur); it = null; } else if (!cur) return; else if (/^\s*[-*]\s+/.test(l)) { it = [l]; cur.items.push(it); } else if (!l.trim()) it = null; else if (it && /^\s+\S/.test(l)) it.push(l); else { it = [l]; cur.items.push(it); } }); return out; }
    function renderHist() {
      if (!histSecs) return; const toks = histQ.value.toLowerCase().split(/\s+/).filter(Boolean).slice(0, 6); let out = '', hits = 0, vers = 0;
      for (const s of histSecs) { const hl = s.head.toLowerCase(); const pick = toks.length ? s.items.filter(it => { const t = hl + ' ' + it.join(' ').toLowerCase(); return toks.every(w => t.includes(w)); }) : s.items; if (toks.length && !pick.length) continue; vers++; hits += pick.length; out += s.head + '\n' + pick.map(it => it.join('\n')).join('\n') + '\n\n'; }
      histRes.replaceChildren(md(out)); histCount.textContent = toks.length ? (hits ? `${hits} Treffer in ${vers} Versionen` : 'Keine Treffer.') : `${histSecs.length} Versionen`;
    }
    histQ.addEventListener('input', renderHist);
    async function loadHist() { histCount.textContent = 'Wird geladen …'; try { const d = await api('GET', '/api/swupdate/history'); if (!d || !d.text) throw new Error('leer'); histSecs = parseHist(d.text); renderHist(); } catch (e) { histCount.textContent = 'Der Verlauf konnte nicht geladen werden.'; } }
    const histLupe = ico('search', 'sm'); histLupe.style.cssText = 'position:absolute;left:var(--space-2);top:50%;transform:translateY(-50%);pointer-events:none;color:var(--text-3)';
    const histBody = h('div', { class: 'stack', style: '--gap:var(--space-3)', hidden: true }, h('div', { style: 'position:relative;max-width:14rem' }, histLupe, histQ), histCount, histRes);
    const histBtn = btn('Alle Änderungen', { size: 'sm', ico: 'down', onclick: () => { const auf = histBody.hidden; histBody.hidden = !auf; histBtn.setAttribute('aria-expanded', String(auf)); histBtn.querySelector('svg').style.transform = auf ? 'rotate(180deg)' : ''; if (auf && !histSecs) loadHist(); } });
    histBtn.setAttribute('aria-expanded', 'false');
    const hist = h('div', { class: 'stack', style: '--gap:var(--space-3)' }, h('div', { class: 'cluster' }, histBtn), histBody);       // Knopf mit Rahmen wie "Nach Updates suchen"; die Liste klappt darunter auf
    App.on('swupdate', renderSw);

    T.add('sy-update', 'Updates', h('div', { class: 'stack', style: '--gap:var(--space-5)' }, swBox));
    /* kleiner gelber Punkt am Reiter „Updates“, solange eine neue Version bereitliegt (wie am Menüpunkt System) */
    const updTabDot = h('i', { class: 'dot tab-dot', hidden: true, 'aria-hidden': 'true' }); { const tb = T.list.querySelector('[aria-controls="sy-update"]'); if (tb) tb.append(updTabDot); }
    const showTabDot = d => { if (d) updTabDot.hidden = !d.newer; };
    App.on('swupdate', showTabDot); App.on('hdrupd', showTabDot);
    const uf = document.createElement('div'); uf.hidden = true;

    /* =================================================================
       Chat und Deck
       ================================================================= */
    T.add('sy-chat', 'Chat und Deck', h('div', { class: 'cols-2' }, h('div', { class: 'col' }, Neu.chat.accountCard(), Neu.chat.botCard(), Neu.chat.deckSettingsCard()), h('div', { class: 'col' }, Neu.chat.batteryCard(), Neu.chat.sysAlertsCard())));

    /* =================================================================
       Eingabe: Controller-Tasten
       ================================================================= */
    const ckBox = h('div', { class: 'stack' }), ckErr = note(); let ckSig = '';
    poll('ckeys', '/api/controller-keys', 1000, () => App.view === 'system' && !document.hidden);
    function renderCk() {
      const d = App.data.ckeys; if (!d) return; const s = JSON.stringify([d.functions.map(f => f.id), d.controllers.map(c => [c.addr, c.name, c.assumed, c.keys.map(k => k.code), c.present, c.map])]);
      ckErr.set(d.error || '', 'bad'); const l = d.last || {};
      if (s !== ckSig && !ckBox.contains(document.activeElement)) { ckSig = s;
        const fnOpts = [['', '–'], ...d.functions.map(f => [f.id, f.name])];
        ckBox.replaceChildren(...(d.controllers.length ? d.controllers.map(c => card({ title: c.name, actions: [badge(c.present ? 'verbunden' : 'getrennt', c.present ? 'ok' : undefined)], body: [
          c.assumed && c.keys.length ? h('p', { class: 'field__hint', text: 'Der Controller war noch nicht verbunden. Gezeigt wird die übliche Gamepad-Belegung. Sobald er verbunden ist, erscheinen seine echten Tasten, deine Auswahl bleibt erhalten.' }) : null,
          c.keys.length ? list(c.keys.map(k => { const sel = select(fnOpts, c.map[String(k.code)] || '', async v => { try { await api('POST', '/api/controller-keys', { addr: c.addr, code: k.code, fn: v }); ckErr.set(''); } catch (e) { ckErr.set(e.message, 'bad'); } }); return h('li', { class: 'row', id: `ck-${c.addr}-${k.code}`.replace(/[^A-Za-z0-9_-]/g, '_'), data: { s: `Controller-Taste ${k.name}`, k: 'controller taste belegung gamepad' } }, h('span', { class: 'row__main' }, h('span', { class: 'row__title', text: k.name })), h('span', { class: 'row__end' }, sel)); })) : h('p', { class: 'muted', style: 'font-size:var(--text-sm)', text: 'Noch keine Tasten bekannt. Controller einschalten und eine Taste drücken, dann erscheint die Liste.' })] }))
          : [h('div', { class: 'empty card' }, h('b', null, 'Kein Controller gekoppelt'), h('span', null, 'Koppeln unter Netzwerk > Bluetooth und Geräte.'), btn('Zu Bluetooth', { onclick: () => Neu.goto('netz', 'n-bt') }))]), ckErr); }
      document.querySelectorAll('.row.hit').forEach(r => r.classList.remove('hit')); if (l.age != null && l.age < 2) { const r = document.getElementById(`ck-${l.addr}-${l.code}`.replace(/[^A-Za-z0-9_-]/g, '_')); if (r) r.classList.add('hit'); }
    }
    App.on('ckeys', renderCk);
    T.add('sy-eingabe', 'Eingabe', ckBox);

    /* =================================================================
       Sicherung
       ================================================================= */
    const BK_MIN = 8, bkBox = h('div', { class: 'stack', style: '--gap:var(--space-5)' });
    let bkDoc = null, bkInfo = null, bkPw = '', bkSending = false, hasBackup = false; const bkMsg = note(), bkIMsg = h('div', { class: 'stack', style: '--gap:var(--space-1)' }), plan = h('div'), bkProg = h('div');
    const secrets = sw({ checked: true, label: 'Passwörter mitnehmen', hint: 'WLAN, Hotspot, DJI, Stream-ID. Dann immer mit einem Passwort verschlüsselt.', onchange: () => hint() });
    const pw = input({ type: 'password', autocomplete: 'new-password', maxlength: 128 }), pw2 = input({ type: 'password', autocomplete: 'new-password', maxlength: 128 });
    const pwField = field({ label: 'Passwort zum Verschlüsseln (mindestens 8 Zeichen)', control: pw }); const hint = () => { pwField.firstChild.textContent = secrets.firstChild.checked ? `Passwort zum Verschlüsseln (mindestens ${BK_MIN} Zeichen)` : 'Passwort (leer = unverschlüsselt)'; };
    const exportBtn = btn('Datei herunterladen', { variant: 'primary', run: async () => {
      const sec2 = secrets.firstChild.checked;
      if (pw.value !== pw2.value) { bkMsg.set('Die beiden Passwörter sind nicht gleich.', 'bad'); return; } if ((sec2 || pw.value) && pw.value.length < BK_MIN) { bkMsg.set(sec2 ? `Mit Passwörtern bitte ein Passwort eingeben (mind. ${BK_MIN} Zeichen).` : `Mindestens ${BK_MIN} Zeichen (oder leer lassen).`, 'bad'); return; }
      bkMsg.set('Wird gesammelt und verschlüsselt …');
      try { const r = await api('POST', '/api/settings/export', { secrets: sec2, password: pw.value || undefined }), blob = new Blob([JSON.stringify(r.document, null, 1)], { type: 'application/json' }), name = `irl4you-einstellungen-${stamp()}.json`; download(blob, name); pw.value = ''; pw2.value = ''; bkMsg.set(`Heruntergeladen: ${name} (${Math.max(1, Math.round(blob.size / 1024))} KB). ` + (r.encrypted ? 'Verschlüsselt. Das Passwort wird nirgends gespeichert.' : 'Unverschlüsselt, ohne Passwörter.') + ((r.notes || []).length ? ' Hinweis: ' + r.notes.join('; ') : ''), 'ok'); } catch (x) { bkMsg.set('Fehler: ' + x.message, 'bad'); }
    } });
    const file = h('input', { class: 'input', type: 'file', accept: '.json,application/json', onchange: async e => {
      const f = e.target.files && e.target.files[0]; bkDoc = null; bkInfo = null; bkPw = ''; plan.replaceChildren(); ipwRow.hidden = true; bkIMsg.replaceChildren(); if (!f) return;
      if (f.size > 300000) { bkIMsg.replaceChildren(h('p', { text: 'Datei zu groß.' })); return; }
      try { bkDoc = JSON.parse(await f.text()); } catch (x) { bkDoc = null; bkIMsg.replaceChildren(h('p', { text: 'Keine Sicherung (kein JSON).' })); return; }
      if (bkDoc && bkDoc.encrypted === true) { ipwRow.hidden = false; bkIMsg.replaceChildren(h('p', { text: 'Verschlüsselt: bitte Passwort eingeben.' })); ipw.focus(); return; } preview();
    } });
    const ipw = input({ type: 'password', maxlength: 128, autocomplete: 'off', onkeydown: e => { if (e.key === 'Enter') { e.preventDefault(); preview(); } } }), ipwRow = h('div', { class: 'cluster', hidden: true, style: 'align-items:flex-end' }, field({ label: 'Passwort der Datei', control: ipw }), btn('Öffnen', { onclick: () => preview() }));
    async function preview() {
      bkIMsg.replaceChildren(h('p', { text: 'Wird geprüft …' }));
      try { bkInfo = await api('POST', '/api/settings/preview', { document: bkDoc, password: ipw.value || undefined }); } catch (x) { bkIMsg.replaceChildren(h('p', { style: 'color:var(--danger)', text: x.message })); return; }
      bkPw = ipw.value; ipwRow.hidden = true; ipw.value = ''; bkIMsg.replaceChildren(); const r = bkInfo, when = r.created ? new Date(r.created) : null, ts = when && !isNaN(when) ? when.toLocaleString('de-DE', { dateStyle: 'medium', timeStyle: 'short' }) : '';
      const checks = r.sections.map(x => x.ok ? h('label', { class: 'check' }, h('input', { type: 'checkbox', checked: true, data: { sec: x.id } }), h('span', { class: 'check__text' }, h('b', { text: x.label }), ` (${x.count})`, x.note ? h('small', { text: x.note }) : null)) : h('p', { class: 'field__hint', text: `${x.label}: nicht lesbar, wird ausgelassen. ${x.note}` }));
      plan.replaceChildren(card({ title: 'Einspielen (ersetzt die jetzigen Einstellungen)', sub: `${ts ? 'Sicherung vom ' + ts : 'Sicherung'}${r.box_version ? ' (Version ' + r.box_version + ')' : ''}, ${r.encrypted ? 'verschlüsselt' : 'nicht verschlüsselt'}, ${r.secrets ? 'mit Passwörtern' : 'ohne Passwörter'}`, body: [...checks, bkSending ? alertBox({ tone: 'warn', text: 'Es wird gesendet. Bitte erst beenden.' }) : null],
        foot: [btn('Ausgewählte Teile einspielen', { variant: 'primary', disabled: bkSending, onclick: async () => { const secs = [...plan.querySelectorAll('input[data-sec]:checked')].map(i => i.dataset.sec); if (!secs.length) { toast('Bitte mindestens einen Teil wählen.'); return; } if (!await ask({ title: 'Einstellungen einspielen?', text: 'Die gewählten Teile ersetzen die jetzigen Einstellungen. Der Stand davor wird gesichert.', ok: 'Einspielen' })) return; await withProgress(() => api('POST', '/api/settings/import', { document: bkDoc, password: bkPw || undefined, sections: secs }).then(results)); plan.replaceChildren(); bkDoc = null; file.value = ''; load(); } })] }));
    }
    async function withProgress(fn) {
      const t0 = Date.now(); bkProg.replaceChildren(prog(3, 'Der Stand davor wird gesichert')); const iv = setInterval(async () => { try { const p = await api('GET', '/api/settings/progress'); if (p.state === 'running' && p.total) bkProg.replaceChildren(prog(Math.max(5, Math.round(p.done * 100 / p.total)), p.label ? `Einspielen: ${p.label} (${p.done + 1} von ${p.total})` : 'Der Stand davor wird gesichert')); } catch (e) { /* weiter */ } }, 600);
      try { return await fn(); } catch (x) { bkIMsg.replaceChildren(h('p', { style: 'color:var(--danger)', text: 'Fehler: ' + x.message })); } finally { clearInterval(iv); bkProg.replaceChildren(prog(100, 'Fertig')); setTimeout(() => bkProg.replaceChildren(), 2500); }
    }
    const TODO = 'pb_bk_todo'; const todoState = () => { try { const v = JSON.parse(store(TODO) || 'null'); return v && typeof v === 'object' ? v : null; } catch (e) { return null; } };
    const todoBox = h('div');
    function renderTodo() {
      const st = todoState(); if (!st) { todoBox.replaceChildren(); return; }
      const items = [['dji', 'DJI-Kameras: einmal neu koppeln und verbinden (die Bluetooth-Kopplung ist nicht in der Sicherung).'], ['twitch', 'Twitch: unter System > Chat und Deck neu anmelden (Anmeldung und Token sind nicht in der Sicherung).'], ['tailscale', 'Tailscale: unter Netzwerk > Fernzugriff neu verbinden und die Freigabe wieder einschalten.'], ['net', 'Sendewege und Netzwerk für Kameras prüfen: Heißen die Netzwerkkarten auf dieser Box anders (eth0, eth1), stimmen die Einstellungen nicht.']];
      todoBox.replaceChildren(card({ title: 'Nach dem Einspielen noch zu erledigen', body: [...items.map(([k, t]) => h('label', { class: 'check' }, h('input', { type: 'checkbox', checked: !!(st.done || {})[k], onchange: e => { const s2 = todoState() || { done: {} }; s2.done = s2.done || {}; s2.done[k] = e.target.checked; store(TODO, items.every(([q]) => s2.done[q]) ? null : JSON.stringify(s2)); setTimeout(renderTodo, 400); } }), h('span', { class: 'check__text', text: t }))), h('p', { class: 'field__hint', text: 'Dein Browser merkt sich die Haken. Sind alle gesetzt, verschwindet dieser Hinweis.' })] }));
    }
    function results(r) { if (!todoState()) store(TODO, JSON.stringify({ done: {} })); renderTodo(); bkIMsg.replaceChildren(...(r.results || []).map(x => h('p', { style: 'font-size:var(--text-sm);color:' + (x.ok ? 'var(--ok)' : 'var(--danger)') }, `${x.ok ? '✓' : '✗'} `, h('b', { text: x.label }), ': ' + x.message)), btn('Seite neu laden', { size: 'sm', onclick: () => location.reload() })); [App.data['send:refresh'], Neu.bild && Neu.bild.reload].forEach(f => { try { f && f(); } catch (e) { /* weiter */ } }); }
    const restoreBtn = btn('Letzten Stand zurückholen', { hidden: true, onclick: async () => { if (!await ask({ title: 'Letzten Stand zurückholen?', text: 'Der Stand vor dem letzten Einspielen wird zurückgeholt. Die jetzigen Einstellungen werden ersetzt.', ok: 'Zurückholen' })) return; bkIMsg.replaceChildren(h('p', { text: 'Wird zurückgeholt …' })); await withProgress(() => api('POST', '/api/settings/restore', {}).then(results)); load(); } });
    async function load() { try { const d = await api('GET', '/api/settings'); bkSending = !!d.sending; hasBackup = !!d.has_backup; restoreBtn.hidden = !hasBackup; } catch (e) { /* nichts */ } }
    document.addEventListener('neu:tab', () => load());
    const what = disclosure('Was wird gesichert?', h('div', { class: 'grid-auto', style: '--min:16rem' }, h('div', null, h('h4', { text: 'Ist in der Sicherung' }), h('ul', { style: 'padding-left:var(--space-5);font-size:var(--text-sm);display:grid;gap:2px' }, ...['Kameras und ihre Netzwerkkarte', 'Bildaufbau und Sendeeinstellungen', 'SRTLA-Server (Stream-ID nur mit dem Haken oben)', 'Sendewege, Kameranetz und Hotspots (Netzwerkkarten werden über die MAC-Adresse zugeordnet)', 'Gespeicherte WLAN-Netze (Passwörter nur mit dem Haken oben)', 'DJI-Kameras: Name, Bildeinstellungen und Verbindung (Passwort nur mit dem Haken oben)', 'HDMI-Eingang und Automatischer Start', 'Eigene Namen für Verbindungen und Sticks', 'Twitch: Kanal, Schwelle und Nachricht der Akku-Warnung', 'Systemwarnungen im Twitch-Chat', 'Streamerbot Deck', 'Design und Reihenfolge der Menüs der bisherigen Oberfläche'].map(t => h('li', { text: t })))),
      h('div', null, h('h4', { text: 'Ist nicht dabei' }), h('ul', { style: 'padding-left:var(--space-5);font-size:var(--text-sm);display:grid;gap:2px' }, ...['Bluetooth-Kopplung der DJI-Kameras', 'Twitch-Anmeldung und Token', 'Tailscale-Verbindung und Freigaben', 'Feste Zusatzadresse', 'Protokolle und Mitschnitte'].map(t => h('li', { text: t }))))));
    bkBox.append(card({ title: 'Sichern', body: [secrets, pwField, field({ label: 'Passwort wiederholen', control: pw2 }), what, bkMsg], foot: [exportBtn] }),
      card({ title: 'Einspielen', sub: 'Datei wählen, Teile auswählen. Nur ohne Sendung. Der Stand davor wird gesichert.', body: [file, ipwRow, bkIMsg, bkProg], foot: [restoreBtn] }), plan, todoBox);
    hint(); renderTodo(); load(); T.add('sy-sicherung', 'Sicherung', bkBox);

    /* =================================================================
       Protokolle
       ================================================================= */
    const logBox = h('div'); let logSig = '', logModeNow = '';
    poll('logmode', '/api/logmode', 15000, () => App.view === 'system'); poll('logs', '/api/logs', 15000, () => App.view === 'system');
    const logMsg = note();
    async function logsDownload(btnEl, msgEl) {
      const wait = ms => new Promise(r => setTimeout(r, ms)); if (btnEl) btnEl.disabled = true; msgEl.set('Wird gesammelt …');
      try { let st = await api('POST', '/api/logs', { action: 'collect' }); const t0 = Date.now(); while (st.state !== 'done') { if (st.state === 'error') throw new Error(st.message || 'unbekannter Fehler'); if (Date.now() - t0 > 170000) throw new Error('Zeitüberschreitung beim Sammeln'); await wait(1500); try { st = await api('GET', '/api/logs'); } catch (e) { /* weiter */ } }
        const r = await fetch('/api/logs/file'); if (!r.ok) throw new Error('Datei konnte nicht geladen werden'); const blob = await r.blob(), now = new Date(), name = `irl4you-protokolle-${stamp()}.txt`; download(blob, name); const off = -now.getTimezoneOffset() / 60;
        msgEl.set(`Heruntergeladen: ${name} (${Math.max(1, Math.round(blob.size / 1024))} KB). ` + (off ? `Zeiten in der Datei sind UTC (bei dir UTC${off > 0 ? '+' : ''}${off}).` : 'Zeiten in der Datei sind UTC.') + (logModeNow === 'sparsam' ? ' Im Modus „Sparsam“ fehlt die Zeit vor dem letzten Start der Box.' : ''), 'ok'); } catch (x) { msgEl.set('Fehler: ' + x.message, 'bad'); }
      if (btnEl) btnEl.disabled = false;
    }
    Neu.logsDownload = logsDownload;
    function renderLog() {
      const m = App.data.logmode, b = App.data.logs; if (!m) return; const sg = JSON.stringify([m, b]); if (sg === logSig) return; logSig = sg; logModeNow = m.mode;
      const dlb = btn('Protokolle herunterladen', { variant: 'primary', ico: 'download', disabled: !(b && b.helper_installed), onclick: () => logsDownload(dlb, logMsg) });
      logBox.replaceChildren(card({ title: 'Protokolle', actions: [badge(({ sparsam: 'Sparsam', ausfuehrlich: 'Ausführlich' })[m.mode] || '–')], sub: 'Eine Textdatei mit den Meldungen der Box (Kameras, Senden, Updates, Netzwerk) für die Fehlersuche, zum Beispiel für ein Issue auf GitHub. Passwörter, Stream-ID, Servername, WLAN-Namen sowie IP- und MAC-Adressen werden vorher durch Platzhalter ersetzt. Bitte vor dem Weitergeben trotzdem kurz durchsehen.', body: [
        h('div', { class: 'cluster' }, dlb), logMsg, b && !b.helper_installed ? h('p', { class: 'muted', text: 'Kommt mit dem nächsten Software-Update.' }) : null,
        h('h3', { text: 'Speicherkarte schonen' }), h('p', { class: 'field__hint', text: 'Die Box schreibt Protokolle für die Fehlersuche. Jeder Schreibvorgang belastet die Speicherkarte, die dadurch auf Dauer kaputtgehen kann.' }),
        field({ s: 'Protokoll-Modus', k: 'log protokoll sparsam ausführlich speicherkarte', label: 'Modus', control: h('div', { class: 'stack', style: '--gap:var(--space-2)' }, ...[['sparsam', 'Sparsam', 'Protokolle nur im Arbeitsspeicher, kein Zugriffsprotokoll des Webservers. Schont die Speicherkarte. Nach einem Absturz oder Stromausfall bleibt keine Spur.'], ['ausfuehrlich', 'Ausführlich', 'Protokolle dauerhaft auf der Karte (Journal höchstens 30 MB und 7 Tage, Zustandsprotokoll höchstens 4 MB, alle 10 Sekunden, Zugriffsprotokoll des Webservers höchstens 20 MB mit drei alten Ständen). Für die Fehlersuche, zum Beispiel wenn sich die Box von selbst ausschaltet.']].map(([v, t, d2]) =>
          h('label', { class: 'radio' }, h('input', { type: 'radio', name: 'logmode', value: v, checked: m.mode === v, disabled: !m.helper_installed, onchange: async () => { logMsg.set('Wird umgestellt …'); try { await api('POST', '/api/logmode', { mode: v }); } catch (x) { logMsg.set(x.message, 'bad'); return; } setTimeout(async () => { try { App.set('logmode', await api('GET', '/api/logmode')); logMsg.set('Umgestellt.', 'ok'); } catch (e) { /* nichts */ } }, 1500); } }), h('span', { class: 'radio__text' }, h('b', { text: t }), h('small', { text: d2 }))))) })] }));
    }
    App.on('logmode', renderLog); App.on('logs', renderLog);

    /* =================================================================
       Hilfe: Problem melden oder Wunsch äußern
       ================================================================= */
    const helpBox = h('div', { class: 'stack', style: '--gap:var(--space-5)' }), rpMsg = note(), rpOut = h('div'), casesBox = h('div');
    let kind = 'issue', draft = { id: '', saved: false, title: '' }, version = '', nowSrv = 0, nowAt = 0, win = 1800;
    const NEW = 'https://github.com/IRL4YOU/IRL4YOU-BOX/issues/new', MAXURL = 7000, ALPH = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789';
    const newId = () => 'IRL-' + Array.from(crypto.getRandomValues(new Uint8Array(6)), x => ALPH[x % ALPH.length]).join('');
    const rpTitle = input({ maxlength: 100, placeholder: 'Titel', autocomplete: 'off' }), rpDesc = h('textarea', { class: 'textarea', rows: 5, maxlength: 2000, placeholder: 'Beschreibung (freiwillig)', 'aria-label': 'Beschreibung' }), rpLog = sw({ label: 'Bereinigtes Protokoll mitnehmen', hint: 'Wird als Datei geladen, die du auf GitHub anhängst; ohne Passwörter, WLAN-Namen, Adressen und Schlüssel.' });
    const kindSeg = seg('rpkind', [['issue', 'Problem'], ['feature', 'Wunsch']], 'issue', v => { kind = v; rpLog.hidden = v === 'feature'; rpDesc.placeholder = v === 'feature' ? 'Beschreibung (Pflicht)' : 'Beschreibung (freiwillig)'; }, 'Art der Meldung');
    const clean = t => String(t || '').replace(/\s+/g, ' ').trim().slice(0, 100);
    function compose() {
      const f = kind === 'feature', t = clean(rpTitle.value), body0 = rpDesc.value.trim();
      if (t.length < 3) { rpMsg.set('Bitte einen Titel eintragen (mindestens 3 Zeichen).', 'bad'); return null; } if (f && !body0) { rpMsg.set('Bei einem Wunsch ist die Beschreibung Pflicht.', 'bad'); return null; }
      if (!draft.id || (draft.saved && t !== draft.title)) draft = { id: newId(), saved: false, title: '' };
      const id = draft.id, ttl = (f ? '[FEATURE] ' : '[ISSUE] ') + t + ' (' + id + ')'; let body = (body0 ? body0 + '\n\n' : '') + '---\nBox-Version: ' + (version || '?') + '\nSupport-Nummer: ' + id + (!f && rpLog.firstChild.checked ? '\nProtokoll: als Datei angehängt' : ''), short = false;
      let url = NEW + '?title=' + encodeURIComponent(ttl) + '&body=' + encodeURIComponent(body); while (url.length > MAXURL && body.length > 200) { body = body.slice(0, Math.floor(body.length * 0.8)); short = true; url = NEW + '?title=' + encodeURIComponent(ttl) + '&body=' + encodeURIComponent(body + '\n[gekürzt]'); }
      return { f, t, id, url, short };
    }
    const goBtn = btn('Formular vorbereiten', { variant: 'primary', onclick: () => { rpMsg.set(''); if (draft.saved) draft = { id: '', saved: false, title: '' }; const c = compose(); if (!c) { rpOut.replaceChildren(); return; }
      const lm = note(), a = h('a', { class: 'btn', href: c.url, target: '_blank', rel: 'noopener noreferrer', 'data-variant': 'primary', onclick: ev => { const n = compose(); if (!n) { ev.preventDefault(); return; } a.href = n.url; if (!draft.saved) { draft.saved = true; draft.title = n.t; api('POST', '/api/support', { action: 'create', kind: n.f ? 'feature' : 'issue', title: n.t, id: n.id }).then(loadCases, () => { }); if (!n.f && rpLog.firstChild.checked) logsDownload(null, lm).then(() => lm.set(lm.textContent + ' Datei auf GitHub ins Textfeld ziehen.')); } } }, 'Formular auf GitHub öffnen');
      rpOut.replaceChildren(alertBox({ tone: 'info', title: 'Formular bereit', text: 'Das Formular öffnet in einem neuen Tab. Dort bei GitHub anmelden und unten auf „Submit new issue“ klicken.' + (c.short ? ' Die Beschreibung war für den Link zu lang und ist gekürzt: bitte auf GitHub vervollständigen.' : ''), actions: [a] }), h('p', null, 'Deine Support-Nummer: ', h('code', { text: c.id })), lm); } });
    async function loadCases() {
      try { const d = await api('GET', '/api/support'); version = d.version || ''; nowSrv = d.now || 0; win = d.delete_window || 1800; nowAt = Date.now(); const age = nowSrv + (Date.now() - nowAt) / 1000, cs = d.cases || [];
        casesBox.replaceChildren(card({ title: 'Meine Meldungen', body: cs.length ? list(cs.map(c => row({ icon: 'help', title: h('span', null, h('code', { text: c.id }), ' ', c.title), desc: `${c.kind === 'feature' ? 'Wunsch' : 'Problem'} · ${fdate(c.t)}${c.done ? ' · erledigt' : ''}`, end: [h('a', { class: 'btn', href: (d.issues || 'https://github.com/IRL4YOU/IRL4YOU-BOX/issues') + '?q=' + encodeURIComponent('is:issue ' + c.id), target: '_blank', rel: 'noopener noreferrer', 'data-size': 'sm' }, 'Auf GitHub suchen'),
          btn(c.done ? 'Wieder öffnen' : 'Erledigt', { size: 'sm', run: async () => { await api('POST', '/api/support', { action: 'done', id: c.id, done: !c.done }); loadCases(); } }), age - c.t <= win ? btn('Entfernen', { size: 'sm', variant: 'ghost', run: async () => { await api('POST', '/api/support', { action: 'delete', id: c.id }); loadCases(); } }) : null] }))) : h('p', { class: 'muted', style: 'font-size:var(--text-sm)', text: 'Noch keine Fälle.' }) })); } catch (e) { /* nichts */ }
    }
    helpBox.append(card({ title: 'Problem melden oder Wunsch äußern', sub: 'Bereitet auf GitHub ein fertig ausgefülltes Formular vor (Titel und Beschreibung sind schon eingetragen). Du meldest dich dort mit deinem eigenen GitHub-Konto an und klickst auf „Submit new issue“. Die Box sendet selbst nichts.', body: [
      field({ s: 'Problem melden oder Wunsch äußern', k: 'hilfe support melden wunsch issue github', label: 'Art', control: h('div', null, kindSeg), hint: 'Problem (ISSUE): Titel ist Pflicht, die Beschreibung ist freiwillig. Wunsch (FEATURE): Titel und Beschreibung sind Pflicht. Du bekommst jeweils eine Support-Nummer.' }),
      field({ label: 'Titel', control: rpTitle }), field({ label: 'Beschreibung', control: rpDesc }), rpLog, rpMsg, rpOut], foot: [goBtn] }), casesBox);
    loadCases(); document.addEventListener('neu:view', e => { if (e.detail === 'system') loadCases(); }); T.add('sy-hilfe', 'Hilfe', helpBox); T.add('sy-logs', 'Protokolle', logBox);

    /* =================================================================
       Entwickler (SSH)
       ================================================================= */
    const devBox = h('div'), devMsg = note(), devOut = h('div', { class: 'sens' }); let devSig = '', devPwShown = false, devTimer = 0;
    poll('developer', '/api/developer', 8000, () => App.view === 'system');
    const devRefresh = async () => { try { App.set('developer', await api('GET', '/api/developer')); } catch (e) { /* nichts */ } };
    async function devPost(body, wait) { devMsg.set(wait); try { await api('POST', '/api/developer', body); } catch (x) { devMsg.set(x.message, 'bad'); return false; } clearTimeout(devTimer); devTimer = setTimeout(devRefresh, 1200); [3000, 8000].forEach(ms => setTimeout(devRefresh, ms)); return true; }
    async function devPwShow() {
      const prev = (App.data.developer || {}).time || 0; devOut.replaceChildren(); devMsg.set('Prüfe das Passwort …'); try { await api('POST', '/api/developer', { action: 'check' }); } catch (x) { devMsg.set(x.message, 'bad'); return; }
      for (let i = 0; i < 8; i++) { await sleep(800); await devRefresh(); const d = App.data.developer; if (d && d.state !== 'working' && d.time !== prev) break; }
      devMsg.set(''); try { const r = await api('GET', '/api/developer/password'); devOut.replaceChildren(h('button', { class: 'tile mono', type: 'button', title: 'Klicken kopiert das Passwort', onclick: async () => toast(await copyText(r.password) ? 'Passwort kopiert' : 'Kopieren nicht möglich'), text: r.password }), ...(r.state === 'own' ? [h('p', { class: 'muted', text: 'Achtung: Das Passwort wurde danach von Hand geändert, dieses gilt vermutlich nicht mehr.' })] : [])); devPwShown = true; } catch (x) { devMsg.set(x.message, 'bad'); devPwShown = false; } devSig = ''; renderDev();
    }
    const devPwHide = () => { devOut.replaceChildren(); devPwShown = false; devSig = ''; renderDev(); };
    function renderDev() {
      const d = App.data.developer; if (!d) return; const sg = JSON.stringify([d, devPwShown]); if (sg === devSig) return; devSig = sg; const busy = d.state === 'working', usable = d.helper_installed && !busy;
      if (!d.helper_installed) devMsg.set('Der Helfer ist noch nicht installiert. Er kommt mit dem nächsten Software-Update (oder install.sh erneut ausführen).'); else if (busy) devMsg.set('Läuft …'); else devMsg.set(d.state === 'error' ? (d.message || 'Fehler') : '');
      devBox.replaceChildren(card({ title: 'Entwickler (SSH)', actions: [badge(!d.available ? '–' : d.active ? 'SSH an' : 'SSH aus', d.active ? 'warn' : undefined)], sub: 'Anmeldung auf der Box über SSH, nur für Entwickler und die Fehlersuche.', body: [
        h('p', { style: 'font-weight:var(--weight-medium)', text: !d.available ? 'Auf dieser Box gibt es keinen SSH-Dienst.' : (d.active ? 'SSH aktiv' : 'SSH ist ausgeschaltet') + (d.user ? ` · Benutzer: „${d.user}“` : '') }),
        h('div', { class: 'cluster' }, btn(d.active ? 'SSH ausschalten' : 'SSH einschalten', { variant: d.active ? 'danger' : 'primary', disabled: !usable || !d.available, onclick: async () => { const start = !d.active; if (await devPost({ action: start ? 'start' : 'stop' }, start ? 'Schalte SSH ein …' : 'Schalte SSH aus …') && start && devPwShown) devPwHide(); } }),
          btn(devPwShown ? 'Passwort ausblenden' : 'Passwort anzeigen', { disabled: !d.helper_installed, onclick: () => devPwShown ? devPwHide() : devPwShow() }),
          d.can_reset ? btn('Passwort zurücksetzen', { disabled: !usable, onclick: async () => { if (!await ask({ title: 'SSH-Passwort zurücksetzen?', text: 'Das alte Passwort gilt danach nicht mehr.', ok: 'Zurücksetzen', danger: true })) return; devPwHide(); const prev = (App.data.developer || {}).time || 0; if (await devPost({ action: 'reset', confirm: true }, 'Erzeuge ein neues Passwort …')) { for (let i = 0; i < 15; i++) { await sleep(800); await devRefresh(); const dd = App.data.developer; if (dd && dd.state !== 'working' && dd.time !== prev) break; } if (App.data.developer && App.data.developer.state !== 'error') devPwShow(); } } }) : null), devMsg, devOut] }));
    }
    App.on('developer', renderDev); T.add('sy-dev', 'Entwickler', devBox);

    /* =================================================================
       Box: Aussehen, Bildschirm wach, Neu starten, Ausschalten, Abmelden
       ================================================================= */
    const boxBox = h('div', { class: 'cols-2' }), powSlot = h('div'), pwSlot = h('div', { id: 'sy-box-pw' }), pwMsg = note(); let powSig = ''; poll('power', '/api/power', 15000, () => App.view === 'system');
    const cur = (store('ds_theme') || 'system');
    const viewNow = /(?:^|;\s*)pb_view_mode=mobile/.test(document.cookie) ? 'mobile' : 'auto';
    const setView = v => { try { document.cookie = 'pb_view_mode=' + (v === 'mobile' ? 'mobile; max-age=31536000' : '; max-age=0') + '; path=/; SameSite=Lax'; if (v === 'mobile') localStorage.setItem('pb_view_mode', 'mobile'); else localStorage.removeItem('pb_view_mode'); } catch (e) { /* privat */ } (window.top || window).location.reload(); };       // der Server liefert bei „Handy“ den schmalen Rahmen aus
    const look = card({ title: 'Aussehen', body: [
      field({ s: 'Helligkeit Hell Dunkel', k: 'theme design dunkel hell modus aussehen', label: 'Helligkeit', control: h('div', null, seg('theme', [['system', 'System'], ['light', 'Hell'], ['dark', 'Dunkel']], cur, v => { window.ds.applyTheme(v); store('ds_theme', v === 'system' ? null : v); }, 'Helligkeit')), hint: '„System“ folgt der Einstellung deines Geräts.' }),
      field({ s: 'Ansicht Handy Automatisch', k: 'ansicht handy mobil automatisch rahmen schmal fenster', label: 'Ansicht', control: h('div', null, seg('viewmode', [['auto', 'Automatisch'], ['mobile', 'Handy']], viewNow, setView, 'Ansicht')), hint: '„Handy“ zeigt die Seite schmal wie am Handy, auch am Computer. „Automatisch“ richtet sich nach der Fenstergröße.' }),
      (() => { const w = sw({ s: 'Bildschirm wach halten', k: 'bildschirm wach display ausschalten standby', checked: store('pb_awake') === '1', label: 'Bildschirm wach halten', hint: 'Verhindert, dass dieses Gerät den Bildschirm ausschaltet, solange die Seite offen ist.', onchange: v => { if (Neu.awake) Neu.awake.set(v); else { store('pb_awake', v ? '1' : '0'); window.neuAwake && window.neuAwake(v); } } }); w.querySelector('input').dataset.awakesw = ''; return w; })(),
      (() => { const w = sw({ s: 'Hilfetexte anzeigen', k: 'hilfe hilfetexte erklärung text ausblenden einblenden', checked: Neu.help ? Neu.help.on() : true, label: 'Hilfetexte anzeigen', hint: 'Standard: am Computer an, am Handy aus. Das (i) in der Überschrift einer Karte blendet nur deren Hilfetext ein oder aus.', onchange: v => Neu.help && Neu.help.set(v) }); w.querySelector('input').dataset.helpsw = ''; return w; })(),
      field({ s: 'Sprache', k: 'sprache language deutsch englisch', label: 'Sprache', hint: 'Gilt auf diesem Gerät auch für die bisherige Oberfläche.', control: (() => { const i = window.PB_I18N; const s = Neu.select((i ? i.languages() : [{ code: 'de', name: 'Deutsch' }]).map(l => [l.code, l.name]), i ? i.lang() : 'de', v => { if (i) i.set(v); }); s.setAttribute('translate', 'no'); return s; })() }),
      h('p', { class: 'field__hint', text: 'Die frühere Optik der bisherigen Oberfläche stellst du dort unter „Optionen“ ein.' }),
      h('div', { class: 'cluster' }, btn('Zur bisherigen Oberfläche wechseln', { size: 'sm', onclick: () => Neu.toOld() })), h('p', { class: 'field__hint', text: 'Das merkt sich dieser Browser. Zurück zur neuen Oberfläche geht es in der bisherigen unter „Optionen“ > „Design“.' })] });
    boxBox.append(powSlot, pwSlot, look);       // Reihenfolge: 1. Box aus-/neu starten, 2. Passwort ändern (aus mehr-box.js), 3. Aussehen
    function renderPower() {
      const d = App.data.power; if (!d) return;
      const sgP = JSON.stringify(d); if (sgP === powSig) return; powSig = sgP;       // nur bei Änderung neu zeichnen, sonst flackert die Karte alle 15 s
      const doit = (action, title, text, ok) => async () => { if (!d.helper_installed) { pwMsg.set('Der Helfer ist auf dieser Box noch nicht installiert (install.sh erneut ausführen).', 'bad'); return; } if (!await ask({ title, text: text + (d.sending ? '\n\nAchtung: Es wird gerade gesendet. Die Übertragung bricht dabei ab.' : ''), ok, danger: true })) return; try { await api('POST', '/api/power', { action, confirm: true }); } catch (x) { pwMsg.set(x.message, 'bad'); return; } pwMsg.set(action === 'poweroff' ? 'Die Box fährt herunter. Sobald die Lüfter stehen, ist sie aus. Diese Seite ist dann nicht mehr erreichbar.' : 'Die Box startet neu. Diese Seite lädt sich nach etwa einer Minute wieder.', 'ok'); };
      powSlot.replaceChildren(card({ title: 'Box ausschalten und abmelden', sub: 'Fährt die Box sauber herunter oder startet sie neu. Wenn die Box ausgeschaltet ist, kann sie über die Oberfläche nicht wieder eingeschaltet werden: dafür den Strom kurz trennen oder die Ein-Taste nutzen. „Abmelden“ beendet die Anmeldung auf diesem Gerät, auch eine mit „Angemeldet bleiben“ gemerkte.', flush: true, body: list(
        row({ icon: 'refresh', title: 'Box neu starten', desc: 'Dauert etwa eine Minute.', s: 'Box neu starten', k: 'neustart reboot', end: btn('Neu starten', { size: 'sm', disabled: !d.helper_installed, onclick: doit('reboot', 'Box neu starten?', 'Die Box startet neu und ist danach nach etwa einer Minute wieder erreichbar.', 'Neu starten') }) }),
        row({ icon: 'power', title: 'Box herunterfahren', desc: 'Danach nur durch erneutes Einstecken des Stroms oder die Ein-Taste wieder erreichbar.', s: 'Box ausschalten herunterfahren', k: 'herunterfahren aus power', end: btn('Herunterfahren', { size: 'sm', variant: 'danger', disabled: !d.helper_installed, onclick: doit('poweroff', 'Box herunterfahren?', 'Danach ist die Box AUS und startet nicht von selbst wieder. Zum Einschalten den Strom kurz trennen oder die Ein-Taste drücken.', 'Herunterfahren') }) }),
        row({ icon: 'lock', title: 'Abmelden', desc: 'Von dieser Box abmelden (auch eine gemerkte Anmeldung).', s: 'Abmelden', k: 'logout abmelden', end: btn('Abmelden', { size: 'sm', run: async () => { await fetch('/api/logout', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }); location.reload(); } }) })) }), pwMsg);
    }
    App.on('power', renderPower); T.add('sy-box', 'Box', boxBox);
  });
})();
