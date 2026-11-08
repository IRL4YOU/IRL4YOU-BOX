/* Menü und Karten anpassen (System > Box): Reihenfolge und Anzeige der Menüpunkte, Karten ausblenden. Gilt für dieses Gerät und bleibt im Browser gespeichert. */
(() => {
  'use strict';
  const { h, App, ico, card, row, sw, btn, iconBtn, toast } = Neu;
  const KEY = 'pb_neu_menu', FIX = ['live', 'system'];          // Live und System bleiben immer im Menü
  const NEVER = ['Aussehen', 'Menü und Karten anpassen'];       // diese Karten lassen sich nicht ausblenden (sonst käme man nicht zurück)
  const load = () => { try { const d = JSON.parse(localStorage.getItem(KEY) || '{}'); return { order: Array.isArray(d.order) ? d.order : [], hidden: Array.isArray(d.hidden) ? d.hidden : [], cards: Array.isArray(d.cards) ? d.cards : [] }; } catch (e) { return { order: [], hidden: [], cards: [] }; } };
  const save = s => { try { localStorage.setItem(KEY, JSON.stringify(s)); } catch (e) { /* privat */ } };
  const nav = document.querySelector('.nav'); if (!nav) return;
  const links = () => [...nav.querySelectorAll('a[data-view-link]')];
  const seqOf = s => { const all = links().map(a => a.dataset.viewLink); return [...s.order.filter(v => all.includes(v)), ...all.filter(v => !s.order.includes(v))]; };
  const nameOf = v => { const a = nav.querySelector(`a[data-view-link="${v}"]`); const t = a && a.querySelector('span'); return t ? t.textContent.trim() : v; };
  const iconOf = v => { const a = nav.querySelector(`a[data-view-link="${v}"] svg use`); return a ? a.getAttribute('href').replace('#i-', '') : 'settings'; };

  /* ---------- anwenden ---------- */
  const cardKey = (sec, c) => sec.dataset.view + '|' + c.querySelector('.card__title').textContent.trim();
  function applyMenu() {
    const s = load(); seqOf(s).forEach(v => { const a = nav.querySelector(`a[data-view-link="${v}"]`); if (a) nav.append(a); });
    links().forEach(a => { a.hidden = !FIX.includes(a.dataset.viewLink) && s.hidden.includes(a.dataset.viewLink); });
  }
  const topCards = sec => [...sec.querySelectorAll('.card')].filter(c => c.querySelector(':scope > .card__head .card__title') && !c.parentElement.closest('.card') && !c.closest('.cam-grid'));
  function applyCards() {
    const off = new Set(load().cards);
    document.querySelectorAll('#views > section[data-view]').forEach(sec => {
      if (sec.dataset.view === 'live') return;
      topCards(sec).forEach(c => { const t = c.querySelector(':scope > .card__head .card__title').textContent.trim(); c.toggleAttribute('data-user-hidden', !NEVER.includes(t) && off.has(cardKey(sec, c))); });
    });
  }
  document.head.append(h('style', { text: '[data-user-hidden] { display: none !important; }' }));
  let raf = 0; const later = () => { if (raf) return; raf = requestAnimationFrame(() => { raf = 0; applyCards(); }); };
  const views = document.getElementById('views'); if (views) new MutationObserver(later).observe(views, { childList: true, subtree: true });
  applyMenu(); applyCards();

  /* ---------- Karte im Reiter „Box“ ---------- */
  const slot = document.getElementById('sy-box-menu'); if (!slot) return;
  const body = h('div', { class: 'stack', style: '--gap:var(--space-4)' });
  function draw() {
    const s = load(), seq = seqOf(s);
    const move = (v, d) => { const o = seqOf(load()), i = o.indexOf(v), k = i + d; if (k < 0 || k >= o.length) return; [o[i], o[k]] = [o[k], o[i]]; const n = load(); n.order = o; save(n); applyMenu(); draw(); };
    const menu = h('div', { class: 'list' }, seq.map((v, i) => row({
      icon: iconOf(v), title: nameOf(v), desc: FIX.includes(v) ? 'Immer sichtbar' : '',
      end: h('div', { class: 'cluster', style: 'flex-wrap:nowrap' },
        Object.assign(iconBtn('up', 'Nach oben', () => move(v, -1)), { disabled: i === 0 }), Object.assign(iconBtn('down', 'Nach unten', () => move(v, 1)), { disabled: i === seq.length - 1 }),
        sw({ checked: FIX.includes(v) || !s.hidden.includes(v), disabled: FIX.includes(v), aria: nameOf(v) + ' im Menü anzeigen', onchange: on => { const n = load(), hs = new Set(n.hidden); on ? hs.delete(v) : hs.add(v); n.hidden = [...hs]; save(n); applyMenu(); } }))
    })));
    const groups = h('div', { class: 'stack', style: '--gap:var(--space-4)' });
    const det = h('details', { class: 'disclosure' }, h('summary', null, 'Karten ausblenden'), h('div', { class: 'disclosure__body' }, groups));
    const fill = () => {
      const off = new Set(load().cards); groups.replaceChildren(h('p', { class: 'field__hint', text: 'Ausgeblendete Karten verschwinden von ihrer Seite. „Aussehen“ und „Menü und Karten anpassen“ bleiben immer sichtbar. Die Karten der Live-Seite ordnest du dort unter „Anordnen“.' }));
      document.querySelectorAll('#views > section[data-view]').forEach(sec => {
        if (sec.dataset.view === 'live') return;
        const cs = topCards(sec).map(c => [cardKey(sec, c), c.querySelector(':scope > .card__head .card__title').textContent.trim()]).filter(([, t]) => !NEVER.includes(t));
        const done = new Set(); const uniq = cs.filter(([k]) => !done.has(k) && done.add(k)); if (!uniq.length) return;
        groups.append(h('div', { class: 'stack', style: '--gap:var(--space-2)' }, h('h4', { text: nameOf(sec.dataset.view) }),
          ...uniq.map(([k, t]) => sw({ checked: !off.has(k), label: t, onchange: on => { const n = load(), cs2 = new Set(n.cards); on ? cs2.delete(k) : cs2.add(k); n.cards = [...cs2]; save(n); applyCards(); } }))));
      });
    };
    det.addEventListener('toggle', () => { if (det.open) fill(); });
    body.replaceChildren(menu, det, h('div', { class: 'cluster' }, btn('Alles zurücksetzen', { size: 'sm', onclick: () => { save({ order: [], hidden: [], cards: [] }); applyMenu(); applyCards(); draw(); toast('Menü und Karten zurückgesetzt'); } })));
  }
  slot.append(card({ title: 'Menü und Karten anpassen', sub: 'Reihenfolge und Anzeige der Menüpunkte und Karten auf diesem Gerät.', body: [body] }));
  draw();
})();
