/* Shared, finite portal transitions. No network requests or private data. */
(() => {
  'use strict';
  const routes = {'/': 'alba', '/tramonto': 'tramonto', '/notte': 'notte'};
  const space = routes[location.pathname];
  if (!space) return;
  const root = document.documentElement;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const read = (key, fallback) => { try { return localStorage.getItem('alba.' + key) ?? fallback; } catch (_) { return fallback; } };
  const enabled = () => !reduced.matches && read('motion', 'on') !== 'off';
  const marks = {
    alba: '<svg viewBox="0 0 72 72" fill="none" stroke="currentColor" stroke-width="5.7" stroke-linecap="round" stroke-linejoin="round"><path class="portal-stroke" d="M43 22 C38 15 20 16 18 30 C15 45 33 51 41 36 C44 30 45 25 43 22"/><path class="portal-stroke portal-stroke-second" d="M46 18 C43 28 40 44 46 46 C50 47 53 40 54 35"/><g fill="currentColor" stroke="none"><ellipse cx="43" cy="22" rx="3.7" ry="3.2"/><ellipse cx="54" cy="35" rx="3.7" ry="3.2"/></g></svg>',
    tramonto: '<span class="portal-semicircle">◒</span>',
    notte: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><path class="portal-stroke" d="M20 14.3A8.5 8.5 0 0 1 9.7 4a8.5 8.5 0 1 0 10.3 10.3Z"/></svg>'
  };
  const titles = {alba: 'alba', tramonto: 'tramonto', notte: 'notte'};
  const switcher = document.querySelector('.portal-switcher');
  const trigger = switcher?.querySelector('[data-portal-trigger]');
  const menu = switcher?.querySelector('#siteMenu');
  for (const mark of document.querySelectorAll('[data-portal-mark]')) {
    if (marks[mark.dataset.portalMark]) mark.innerHTML = marks[mark.dataset.portalMark];
  }
  if (trigger && menu) {
    const chevron = document.createElement('span');
    chevron.className = 'portal-chevron'; chevron.setAttribute('aria-hidden', 'true');
    chevron.innerHTML = '<svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="m3 4.5 3 3 3-3"/></svg>';
    trigger.append(chevron);
    const links = () => [...menu.querySelectorAll('a[href]')].filter(link => !link.hidden);
    function toggle(open, focus = false) {
      menu.hidden = !open; trigger.setAttribute('aria-expanded', String(open));
      if (focus) (open ? links()[0] : trigger)?.focus();
    }
    trigger.addEventListener('click', () => toggle(menu.hidden));
    trigger.addEventListener('keydown', event => {
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault(); toggle(true);
        const items = links(); (event.key === 'ArrowUp' ? items.at(-1) : items[0])?.focus();
      }
    });
    menu.addEventListener('keydown', event => {
      const items = links(), index = items.indexOf(document.activeElement);
      if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
        event.preventDefault();
        const next = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1 : (index + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
        items[next]?.focus();
      }
    });
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && !menu.hidden) { event.preventDefault(); toggle(false, true); }
    });
    document.addEventListener('click', event => { if (!switcher.contains(event.target)) toggle(false); });
    switcher.addEventListener('focusout', event => { if (event.relatedTarget && !switcher.contains(event.relatedTarget)) toggle(false); });
    window.addEventListener('pageshow', event => { if (event.persisted) toggle(false); });
  }
  let overlay, busy = false, cleanupTimer = 0, recoverTimer = 0;
  const storageKey = 'alba.portalJourney';
  function clearJourney() { try { sessionStorage.removeItem(storageKey); } catch (_) {} }
  function reset() {
    clearTimeout(cleanupTimer); clearTimeout(recoverTimer);
    overlay?.remove(); overlay = null; busy = false;
    delete root.dataset.portalPhase; clearJourney();
  }
  function show(destination, phase) {
    overlay?.remove();
    overlay = document.createElement('div');
    overlay.className = 'portal-transition';
    overlay.dataset.space = destination;
    overlay.dataset.phase = phase;
    const dark = matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    overlay.dataset.theme = destination === 'notte' ? 'dark' : read(destination === 'tramonto' ? 'tramontoTheme' : 'theme', read('theme', dark));
    overlay.dataset.style = read(destination === 'tramonto' ? 'tramontoStyle' : 'surfaceStyle', read('surfaceStyle', 'classic'));
    overlay.dataset.palette = read(destination === 'tramonto' ? 'tramontoPalette' : 'palette', 'sage');
    overlay.setAttribute('aria-hidden', 'true');
    overlay.innerHTML = '<div class="portal-light portal-light-one"></div><div class="portal-light portal-light-two"></div><div class="portal-horizon"></div><div class="portal-stars"><i></i><i></i><i></i><i></i></div><div class="portal-signature"><div class="portal-mark">' + marks[destination] + '</div><span class="portal-wordmark">' + titles[destination] + '<b>.</b></span></div>';
    document.body.append(overlay);
    root.dataset.portalPhase = phase;
  }
  // Use the existing identities in the switcher instead of platform-dependent emoji.
  for (const link of document.querySelectorAll('.portal-menu a, .night-header nav a')) {
    const destination = routes[new URL(link.href, location.href).pathname];
    if (!destination) continue;
    if (destination === space) link.setAttribute('aria-current', 'page');
    const text = [...link.childNodes].find(node => node.nodeType === Node.TEXT_NODE);
    if (text) text.textContent = text.textContent.replace(/^[\s☀◒☾]+/u, '');
    const icon = document.createElement('span'); icon.className = 'portal-nav-mark';
    icon.setAttribute('aria-hidden', 'true'); icon.innerHTML = marks[destination]; link.prepend(icon);
  }
  if (enabled()) {
    let journey;
    try { journey = JSON.parse(sessionStorage.getItem(storageKey)); } catch (_) {}
    const continuing = journey?.space === space && Date.now() - journey.at < 8000;
    clearJourney();
    show(space, continuing ? 'arrive' : 'enter');
    cleanupTimer = setTimeout(reset, continuing ? 650 : 950);
  }
  document.addEventListener('click', async event => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const link = event.target.closest?.('a[href]');
    if (!link || link.hasAttribute('download') || (link.target && link.target !== '_self')) return;
    const url = new URL(link.href, location.href), destination = routes[url.pathname];
    if (url.origin !== location.origin || !destination || url.pathname === location.pathname || url.hash) return;
    event.preventDefault();
    if (busy) return;
    busy = true;
    // Tramonto registers its save promise; failure keeps the current editor visible.
    const pending = [];
    document.dispatchEvent(new CustomEvent('alba-before-space-change', {detail: {waitUntil: promise => pending.push(Promise.resolve(promise))}}));
    try { if ((await Promise.all(pending)).some(result => result === false)) { reset(); return; } }
    catch (_) { reset(); return; }
    if (!enabled()) { location.assign(url.href); return; }
    clearTimeout(cleanupTimer);
    show(destination, 'leave');
    cleanupTimer = setTimeout(() => {
      try { sessionStorage.setItem(storageKey, JSON.stringify({space: destination, at: Date.now()})); } catch (_) {}
      location.assign(url.href);
      // A cancelled beforeunload dialog must never strand an opaque overlay.
      recoverTimer = setTimeout(reset, 1600);
    }, 340);
  });
  window.addEventListener('pageshow', event => { if (event.persisted) reset(); });
  window.addEventListener('pagehide', () => { clearTimeout(cleanupTimer); clearTimeout(recoverTimer); });
  reduced.addEventListener('change', () => { if (!enabled() && !busy) reset(); });
  document.addEventListener('alba-motion-update', () => { if (!enabled() && !busy) reset(); });
})();
