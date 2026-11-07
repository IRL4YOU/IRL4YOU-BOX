/* IRL4YOU BOX · neue Oberfläche · Ergänzungen (chat): Funktionen der bisherigen Oberfläche, die es in der Vorlage nicht gab.
   Chat-Quellen (Twitch, YouTube, Kick einzeln an/aus), YouTube- und Kick-Kanal, Streamerhub-Chat (Adresse und Größen).
   Die Karten landen in System > Chat und Deck; die Anzeige des Streamerhub-Chats steht auf der Live-Seite unter dem Chat (chat.js). */
(() => {
  "use strict";
  const { h, api, App, poll, toast, run, btn, card, field, input, note, kv } = Neu;
  if (!Neu.chat || !Neu.chat.sourceSwitches) return;
  const onSystem = () => App.view === 'system' && !document.hidden;

  /* ---------- Welche Chats ---------- */
  function sourcesCard() {
    return card({ title: 'Welche Chats', sub: 'Die Nachrichten aus Twitch, YouTube und Kick erscheinen zusammen im Chat auf der Live-Seite. Hier schaltest du jede Quelle einzeln ein oder aus.',
      body: [Neu.chat.sourceSwitches(true)] });
  }

  /* ---------- YouTube und Kick: Kanal eintragen, Verbindung anzeigen ---------- */
  const STATE = {
    youtube: { ok: ['Livechat verbunden', 'ok'], 'kein-stream': ['Kein laufender YouTube-Stream gefunden. Die Box sucht jede Minute, solange der Chat geöffnet ist.', 'warn'], fehler: ['Keine Verbindung zu YouTube.', 'bad'], verbinde: ['Verbinde mit YouTube …', ''] },
    kick: { ok: ['Livechat verbunden', 'ok'], 'kein-kanal': ['Diesen Kanal gibt es auf Kick nicht.', 'bad'], fehler: ['Keine Verbindung zu Kick.', 'bad'], verbinde: ['Verbinde mit Kick …', ''] },
  };
  function channelCard(o) {
    poll(o.key, o.path, 15000, onSystem);
    const chan = input({ maxlength: 200, placeholder: o.ph, autocomplete: 'off', autocapitalize: 'off', spellcheck: 'false' }), status = h('div', { class: 'stack', style: '--gap:var(--space-1)', role: 'status' }), err = note();
    const save = btn('Kanal speichern', { variant: 'primary', run: async () => { err.set(''); try { App.set(o.key, await api('POST', o.path, { action: 'channel', channel: chan.value })); } catch (x) { err.set(x.message, 'bad'); } } });
    chan.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); save.click(); } });
    function render(d) {
      if (!d) return; const c = d.chat || {}, st = d.handle && STATE[o.key][c.state];
      if (document.activeElement !== chan) chan.value = d.handle || '';
      const kids = [d.handle ? kv('Kanal', d.handle) : h('p', { class: 'muted', style: 'font-size:var(--text-sm)', text: 'Noch kein Kanal eingetragen.' })];
      if (st) kids.push(h('p', { style: `font-size:var(--text-sm);color:${st[1] === 'ok' ? 'var(--ok)' : st[1] === 'bad' ? 'var(--danger)' : st[1] === 'warn' ? 'var(--warn)' : 'var(--text-2)'}`, text: st[0] }));
      if (st && c.state === 'ok' && c.title && o.showTitle) kids.push(kv('Stream', c.title));
      if (d.handle && c.error) kids.push(h('p', { class: 'muted', style: 'font-size:var(--text-sm)', text: c.error, translate: 'no' }));
      status.replaceChildren(...kids);
    }
    App.on(o.key, render);
    return card({ title: o.title, sub: o.sub, body: [field({ label: o.label, control: chan, s: o.title, k: o.keys }), status, err], foot: [save] });
  }
  const youtubeCard = () => channelCard({ key: 'youtube', path: '/api/youtube', title: 'YouTube-Chat', label: 'YouTube-Kanal', ph: '@meinkanal', showTitle: true, keys: 'youtube kanal livechat chat handle',
    sub: 'Trage deinen YouTube-Kanal ein. Die Box findet deinen laufenden Livestream selbst, zeigt den öffentlichen Chat zusammen mit den anderen Chats (jede Nachricht mit einem Abzeichen für ihre Herkunft) und holt sich bei jedem neuen Stream den neuen Chat von selbst. Keine Anmeldung und kein Google-Konto nötig.' });
  const kickCard = () => channelCard({ key: 'kick', path: '/api/kick', title: 'Kick-Chat', label: 'Kick-Kanal', ph: 'meinkanal', showTitle: false, keys: 'kick kanal livechat chat',
    sub: 'Trage deinen Kick-Kanal ein. Die Box liest den öffentlichen Chat und zeigt ihn zusammen mit den anderen Chats (jede Nachricht mit einem Abzeichen für ihre Herkunft). Keine Anmeldung nötig, die Box kann auf Kick nicht schreiben.' });

  /* ---------- Streamerhub-Chat: Adresse und Größen (die Anzeige steht in chat.js auf der Live-Seite) ---------- */
  const cleanUrl = v => { v = String(v || '').trim(); if (!v) return ''; if (v.length > 500) return null; let u; try { u = new URL(v); } catch (e) { return null; } return u.protocol === 'https:' && u.hostname && !u.username && !u.password ? u.href : null; };
  function hubCard() {
    const num = () => input({ type: 'number', inputmode: 'numeric', min: 200, max: 4000, step: 10 }), u = input({ type: 'url', maxlength: 500, placeholder: 'https://streamerhub.app/chat-overlay?id=…', autocomplete: 'off', autocapitalize: 'off', spellcheck: 'false' });
    const w = num(), hh = num(), mw = num(), mh = num(), info = note(), all = [u, w, hh, mw, mh];
    App.on('hub', d => { if (!d || all.includes(document.activeElement)) return; const x = Neu.chat.hubOf(d); u.value = x.url; w.value = x.width; hh.value = x.height; mw.value = x.mobile_width; mh.value = x.mobile_height; });
    const save = btn('Speichern', { variant: 'primary', run: async () => {
      const c = cleanUrl(u.value); if (c === null) { info.set('Die Adresse muss mit https:// beginnen.', 'bad'); return; }
      try { App.set('hub', await api('POST', '/api/hub', { url: c, width: +w.value || 500, height: +hh.value || 500, mobile_width: +mw.value || 500, mobile_height: +mh.value || 500 })); info.set('Gespeichert. Gilt auf allen Geräten.', 'ok'); }
      catch (e) { info.set('Nicht auf der Box gespeichert: ' + e.message, 'bad'); }
    } });
    all.forEach(i => i.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); save.click(); } }));
    return card({ title: 'Streamerhub-Chat', sub: 'Zeigt den Chat von Streamerhub auf der Live-Seite unter dem Chat. Die Box ruft die Seite selbst auf und zeigt sie dort an, auch wenn die Seite das Einbetten eigentlich verbietet. Adresse und Größen sind auf der Box gespeichert und gelten für alle Geräte.',
      body: [field({ label: 'Adresse des Chat-Overlays', control: u, hint: 'Leer lassen entfernt den Chat. Er lässt sich nur anzeigen, wenn die Box über http geöffnet ist (nicht über https).', s: 'Streamerhub-Chat Adresse', k: 'streamerhub hub chat overlay iframe' }),
        h('div', { class: 'grid-auto', style: '--min:9rem' }, field({ label: 'Breite Desktop (px)', control: w }), field({ label: 'Höhe Desktop (px)', control: hh }), field({ label: 'Breite Handy (px)', control: mw }), field({ label: 'Höhe Handy (px)', control: mh })),
        h('p', { class: 'field__hint', text: 'Ist der Bildschirm schmaler als die Breite, wird der Chat auf die Bildschirmbreite verkleinert.' }), info], foot: [save] });
  }

  /* ---------- Einbau in System > Chat und Deck ---------- */
  const panel = document.getElementById('sy-chat');
  const find = t => panel && [...panel.querySelectorAll('section.card')].find(c => ((c.querySelector('.card__title') || {}).textContent || '') === t);
  if (!panel) return;
  const acc = find('Twitch-Konto'), bot = find('Bot-Konto (freiwillig)'), deck = find('Streamerbot Deck'), bat = find('Akku-Warnung im Twitch-Chat');
  const src = sourcesCard(), yt = youtubeCard(), kick = kickCard(), hub = hubCard();
  const c2 = bat && bat.parentNode;
  if (acc && bot && deck && c2 && c2 !== acc.parentNode) {
    /* Spalte 1: Konto, Chats, YouTube, Kick. Spalte 2: Bot, Deck, Streamerhub, Warnungen. Am Handy ergibt das die Reihenfolge von oben nach unten. */
    acc.after(src, yt, kick); c2.prepend(bot, deck, hub);
  } else {
    const col = (acc && acc.parentNode) || panel; (acc ? acc.after(src, yt, kick) : col.append(src, yt, kick)); (deck ? deck.after(hub) : col.append(hub));
  }
})();
