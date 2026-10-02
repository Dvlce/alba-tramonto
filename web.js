'use strict';
let incomingWebKey = new URLSearchParams(location.hash.slice(1)).get('web_key');
if (incomingWebKey !== null) history.replaceState(null,'',location.pathname);
window.addEventListener('hashchange', () => { if (new URLSearchParams(location.hash.slice(1)).has('web_key')) location.reload(); });
let csrf = '', loggedIn = false, usageSequence = 0, lastUsage = null, selectedDay = null;
let currentJob = null, isAdmin = false, adminData = null, loginMethod = 'password', currentUserId = null;
let historyCursor = 0, historyLoading = false, chatAdmitted = false, presenceTime = 0;
let olderCursor = null, olderLoading = false;
const $ = id => document.getElementById(id);
const numbers = new Intl.NumberFormat('it-IT');
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
const osTheme = window.matchMedia('(prefers-color-scheme: dark)');
function preference(name,fallback) { try { return localStorage.getItem('alba.' + name) ?? fallback; } catch (_) { return fallback; } }
function savePreference(name,value) { try { localStorage.setItem('alba.' + name,value); } catch (_) {} }
let motionAllowed = preference('motion','on') !== 'off';
function animationsEnabled() { return motionAllowed && !reducedMotion.matches && !document.hidden; }
$('motionEnabled').checked = motionAllowed;
$('iconAnimation').value = preference('animation','auto');
if (!$('iconAnimation').value) $('iconAnimation').value = 'auto';
function motionChanged() { document.documentElement.classList.toggle('motion-off',!motionAllowed); document.dispatchEvent(new Event('alba-motion-update')); }
motionChanged();
function setSurfaceStyle(value) { const style = ['classic','neo','glass','clay','cyber','brutal','scrap','surreal'].includes(value) ? value : 'classic'; document.documentElement.dataset.style = style; $('surfaceStyle').value = style; savePreference('surfaceStyle',style); }
setSurfaceStyle(preference('surfaceStyle','classic'));
$('surfaceStyle').addEventListener('change',() => setSurfaceStyle($('surfaceStyle').value));
function setPalette(value) { const palette = ['sage','graphite','ocean','violet','rose','amber'].includes(value) ? value : 'sage'; document.documentElement.dataset.palette = palette; $('appearancePalette').value = palette; savePreference('palette',palette); }
setPalette(preference('palette','sage'));
$('appearancePalette').addEventListener('change',() => setPalette($('appearancePalette').value));
$('motionEnabled').addEventListener('change', () => { motionAllowed = $('motionEnabled').checked; savePreference('motion',motionAllowed ? 'on' : 'off'); motionChanged(); });
$('iconAnimation').addEventListener('change', () => { savePreference('animation',$('iconAnimation').value); document.dispatchEvent(new Event('alba-icon-preview')); });
$('mascotEnabled').checked = preference('mascot','on') !== 'off';
function mascotVisibility() { $('companion').hidden = !$('mascotEnabled').checked; savePreference('mascot',$('mascotEnabled').checked ? 'on' : 'off'); }
mascotVisibility(); $('mascotEnabled').addEventListener('change',mascotVisibility);
$('hideMascot').addEventListener('click', () => { $('mascotEnabled').checked = false; mascotVisibility(); });
$('login').prepend($('companion'));
let mascotTimer = 0, mascotTurn = 0;
function mascotState(state,message,persistent = false) {
  clearTimeout(mascotTimer); $('companion').dataset.state = state;
  if (message) { $('mascotMessage').textContent = message; $('companion').classList.add('show-message'); }
  if (!persistent) mascotTimer = setTimeout(() => { $('companion').dataset.state = currentJob ? 'thinking' : 'idle'; $('companion').classList.remove('show-message'); },1700);
}
$('mascotButton').addEventListener('click', () => {
  const states = [['hello','Eccomi!'],['dance','Una piccola pausa.'],['bounce','Un passo alla volta.'],['curious','C’è sempre qualcosa da scoprire.'],['spin','Un altro punto di vista.'],['celebrate','Le piccole cose contano.'],['rest','Anche riposare è una buona idea.'],['stretch','Mi sgranchisco un momento.'],['peek','Eccomi qui.'],['wiggle','Un po’ di allegria.'],['joy','Una piccola gioia.'],['sleep','Anche il silenzio ha il suo spazio.']];
  const item = states[mascotTurn++ % states.length]; mascotState(item[0],item[1]);
});
$('mascotButton').addEventListener('mouseenter', () => { if (!currentJob) mascotState('hello','Ciao, sono Albi. Un’albicocca!'); });
document.addEventListener('click', event => { for (const id of ['motionSettings','appearanceSettings']) if (!$(id).contains(event.target)) $(id).open = false; });
for (const id of ['motionSettings','appearanceSettings']) $(id).addEventListener('toggle',() => { if ($(id).open) $(id === 'motionSettings' ? 'appearanceSettings' : 'motionSettings').open = false; });
document.addEventListener('keydown',event => { if (event.key === 'Escape') for (const id of ['motionSettings','appearanceSettings']) if ($(id).open) { $(id).open = false; $(id).querySelector('summary').focus(); } });
let manualTheme = null;
try { manualTheme = localStorage.getItem('alba.theme'); } catch (_) {}
function setTheme(theme) {
  theme = ['light','dark','gray','black'].includes(theme) ? theme : (osTheme.matches ? 'dark' : 'light');
  document.documentElement.dataset.theme = theme;
  const dark = theme === 'dark' || theme === 'black';
  $('appearanceTheme').value = theme;
  $('themeToggle').setAttribute('aria-pressed', String(dark));
  $('themeToggle').setAttribute('aria-label', dark ? 'Attiva la modalità chiara' : 'Attiva la modalità scura');
  document.querySelector('meta[name="theme-color"]').content = {light:'#f4f5ee',dark:'#12171b',gray:'#dfe2e6',black:'#000000'}[theme];
}
if (!['light','dark','gray','black'].includes(manualTheme)) manualTheme = null;
setTheme(manualTheme || (osTheme.matches ? 'dark' : 'light'));
$('appearanceTheme').addEventListener('change',() => { manualTheme = $('appearanceTheme').value; setTheme(manualTheme); savePreference('theme',manualTheme); });
$('themeToggle').addEventListener('click', () => {
  manualTheme = ['dark','black'].includes(document.documentElement.dataset.theme) ? 'light' : 'dark';
  setTheme(manualTheme); try { localStorage.setItem('alba.theme', manualTheme); } catch (_) {}
});
osTheme.addEventListener('change', () => { if (!manualTheme) setTheme(osTheme.matches ? 'dark' : 'light'); });

async function api(path, body) {
  const r = await fetch(path, {method: body ? 'POST' : 'GET', credentials: 'same-origin',
    headers: {'Content-Type':'application/json','X-CSRF-Token':csrf}, body: body ? JSON.stringify(body) : undefined});
  let data;
  try { data = await r.json(); } catch (_) { throw new Error('Il server è temporaneamente occupato o in riavvio. Riprova tra pochi secondi.'); }
  if (!r.ok) {
    if (data.code === 'auth_expired' && loggedIn) { loggedIn = false; location.reload(); }
    const failure=new Error(data.error || 'Richiesta non riuscita.');failure.code=data.code;throw failure;
  }
  return data;
}
function bubble(role, content, result, animate = true, target = $('messages')) {
  const el = document.createElement('div'); el.className = 'bubble ' + (role === 'user' ? 'user' : 'assistant') + (animate ? ' new' : ''); el.textContent = content;
  el.dataset.role = role; el.dataset.rawContent = content;
  if (result?.document) {
    const bytes = Uint8Array.from(atob(result.document), c => c.charCodeAt(0));
    const url = URL.createObjectURL(new Blob([bytes], {type:'application/octet-stream'}));
    const a = document.createElement('a'); a.href = url; a.download = result.filename; a.textContent = 'Scarica ' + result.filename;
    el.appendChild(a); setTimeout(() => URL.revokeObjectURL(url), 300000);
  }
  const follow = target === $('messages') && (target.scrollHeight - target.scrollTop - target.clientHeight < 80 || (animate && role === 'user'));
  target.appendChild(el); if (follow) target.scrollTop = target.scrollHeight;
  return el;
}
async function ready() {
  const me = await api('/api/me'); csrf = me.csrf; loggedIn = true; currentUserId = me.user_id; chatAdmitted = false; $('send').disabled = true;
  $('login').hidden = true; $('dashboard').hidden = false; $('logout').hidden = false; $('account').hidden = false;
  const name = me.name || 'Tu';
  $('accountName').textContent = name; $('accountInitial').textContent = name.charAt(0).toUpperCase();
  $('telegramAvatar').onload = () => { $('telegramAvatar').hidden = false; $('accountInitial').hidden = true; };
  $('telegramAvatar').onerror = () => { $('telegramAvatar').hidden = true; $('accountInitial').hidden = false; };
  $('telegramAvatar').src = '/api/avatar';
  $('telegramBadge').hidden=!me.telegram_linked;
  $('accountRole').textContent = me.is_admin ? 'Amministratore' : me.telegram_linked ? 'Telegram · Spazio personale' : 'Account web · Spazio personale';
  arrangeAccount();
  $('scopeControl').hidden = !me.is_admin; $('usageScope').value = me.is_admin ? 'bot' : 'self';
  isAdmin = me.is_admin; $('dashboardTabs').hidden = !isAdmin;
  $('devicesButton').hidden = false; $('tramontoLink').hidden = !isAdmin; $('portalAccessNote').hidden = isAdmin;
  if (isAdmin && new URLSearchParams(location.search).get('next') === 'tramonto') { location.replace('/tramonto'); return; }
  document.querySelector('.welcome').appendChild($('companion')); mascotState('hello','Bentornato.');
  $('greeting').textContent = 'Prendiamoci un momento, ' + name + '.';
  $('messages').replaceChildren(); historyCursor = 0; const history = await api('/api/history');
  for (const row of history.messages) { bubble(row.role, row.content, null, false).dataset.messageId = row.id; historyCursor = Math.max(historyCursor,row.id); }
  if (!history.messages.length) bubble('assistant', 'Ciao. Sono Alba. Possiamo prenderci un momento per capire quello che stai vivendo. Da dove vuoi cominciare?');
  olderCursor = history.next_before; $('historyTools').hidden = !history.has_older; $('loadOlder').hidden = !history.has_older; $('historyStatus').textContent = '';
  await loadUsage();
  await refreshStatus();
  restoreMascotPosition();
}
function loginMode(mode) {
  loginMethod = mode; const key = mode === 'key';
  $('keyFields').hidden = !key; $('passwordFields').hidden = key;
  $('token').disabled = !key; $('token').required = key;
  for (const id of ['username','password']) { $(id).disabled = key; $(id).required = !key; }
  $('keyTab').setAttribute('aria-selected',String(key)); $('passwordTab').setAttribute('aria-selected',String(!key));
  $('loginIntro').textContent = key ? 'Invia /web_key in privato al bot e tocca «Entra nel sito»: l’accesso è automatico. Puoi anche inserire una chiave qui. Il tuo ID Telegram è già associato.' : 'Entra con le tue credenziali personali. Ritroverai qui le conversazioni della tua chat Telegram.';
  $('error').textContent = '';
}
$('keyTab').addEventListener('click', () => loginMode('key')); $('passwordTab').addEventListener('click', () => loginMode('password'));
$('loginForm').addEventListener('submit', async event => {
  event.preventDefault(); $('error').textContent = ''; $('loginButton').disabled = true;
  try { const body = loginMethod === 'key' ? {token:$('token').value.trim()} : {username:$('username').value.trim(),password:$('password').value}; body.remember = $('rememberDevice').checked; const data = await api('/api/login', body); csrf = data.csrf; $('token').value = ''; $('password').value = ''; await ready(); }
  catch (error) { $('error').textContent = error.message; }
  finally { $('loginButton').disabled = false; }
});
async function loadOlderMessages() {
  if (!loggedIn || olderLoading || !olderCursor) return;
  olderLoading = true; $('loadOlder').disabled = true; $('historyStatus').textContent = 'Caricamento…';
  try {
    const data = await api('/api/history?before=' + olderCursor);
    const messages = $('messages'), oldHeight = messages.scrollHeight, oldTop = messages.scrollTop;
    const fragment = document.createDocumentFragment();
    for (const row of data.messages) {
      if (!messages.querySelector('[data-message-id="' + row.id + '"]')) bubble(row.role,row.content,null,false,fragment).dataset.messageId = row.id;
    }
    messages.prepend(fragment);
    olderCursor = data.next_before; $('loadOlder').hidden = !data.has_older;
    $('historyStatus').textContent = data.has_older ? '' : 'Inizio della conversazione.';
    messages.scrollTop = oldTop + messages.scrollHeight - oldHeight;
  } catch (error) { $('historyStatus').textContent = error.message; }
  finally { olderLoading = false; $('loadOlder').disabled = false; }
}
$('loadOlder').addEventListener('click',loadOlderMessages);
function updateGeneration(state) {
  const elapsed = Math.max(0,Math.floor((performance.now() - state.started) / 1000));
  const text = state.stopRequested ? 'Interruzione della risposta…' : state.phase === 'generating' ? 'Alba sta preparando la risposta…' : 'Risposta in coda…';
  $('thinkingLabel').textContent = text;
  $('thinkingElapsed').textContent = (elapsed < 60 ? elapsed + ' s' : Math.floor(elapsed/60) + ':' + String(elapsed%60).padStart(2,'0')) + ' trascorsi';
  if ($('status').textContent !== text) $('status').textContent = text;
}
async function send(text) {
  if (currentJob || (!chatAdmitted && !text.startsWith('/'))) return;
  const state = {jobId:null,stopRequested:false,cancelSent:false,phase:'queued',started:performance.now()}; currentJob = state;
  $('send').disabled = true; $('send').hidden = true; $('stop').hidden = false; $('stop').disabled = false;
  $('thinking').hidden = false; updateGeneration(state); const timer = setInterval(() => updateGeneration(state),1000);
  $('error').textContent = ''; bubble('user', text); mascotState('thinking','Sto mettendo in ordine i pensieri…',true);
  try {
    const ticket = await api('/api/chat', {message:text});
    state.jobId = ticket.job_id;
    if (state.stopRequested) await cancelGeneration(state);
    let result;
    do {
      await new Promise(resolve => setTimeout(resolve, 1500)); result = await api('/api/jobs/' + ticket.job_id);
      if (result.pending) { state.phase = result.phase === 'generating' ? 'generating' : 'queued'; updateGeneration(state); }
    }
    while (result.pending);
    bubble('assistant', result.reply, result);
    showBreak(result.break_notice);
    if (result.cancelled) { $('messages').lastElementChild.classList.add('cancelled'); mascotState('stopped','Va bene, ci fermiamo qui.'); }
    else mascotState('celebrate','Un pensiero alla volta.');
  }
  catch (error) { $('error').textContent = error.message; }
  finally { clearInterval(timer); currentJob = null; $('send').disabled = !chatAdmitted; $('send').hidden = false; $('stop').hidden = true; $('status').textContent = ''; $('thinking').hidden = true; $('message').focus(); await syncHistory(); loadUsage(); }
}
async function cancelGeneration(state) {
  if (!state.jobId || state.cancelSent) return;
  state.cancelSent = true;
  try { await api('/api/jobs/' + state.jobId + '/cancel', {}); }
  catch (error) { state.cancelSent = false; $('stop').disabled = false; $('error').textContent = error.message; }
}
$('stop').addEventListener('click', () => { if (!currentJob) return; currentJob.stopRequested = true; $('stop').disabled = true; $('status').textContent = 'Interruzione della risposta…'; cancelGeneration(currentJob); });
document.addEventListener('keydown', event => { if (event.key !== 'Escape') return; if ($('motionSettings').open) $('motionSettings').open = false; else if (currentJob && !$('memoryDialog').open) { event.preventDefault(); $('stop').click(); } });
$('chatForm').addEventListener('submit', event => {event.preventDefault(); const text = $('message').value.trim(); if (text && !$('send').disabled) { $('message').value = ''; send(text); }});
$('message').addEventListener('keydown', event => {if(event.key === 'Enter' && !event.shiftKey){event.preventDefault();$('chatForm').requestSubmit();}});
document.querySelectorAll('[data-command]').forEach(button => button.addEventListener('click', () => send(button.dataset.command)));
$('logout').addEventListener('click', async () => {try {await api('/api/logout', {});} finally {loggedIn = false; usageSequence++; location.reload();}});
$('albaSymbol').addEventListener('click', () => { $('siteMenu').hidden = !$('siteMenu').hidden; $('albaSymbol').setAttribute('aria-expanded',String(!$('siteMenu').hidden)); });
document.addEventListener('click',event => { if (!event.target.closest('.brand')) { $('siteMenu').hidden = true; $('albaSymbol').setAttribute('aria-expanded','false'); } });
document.addEventListener('keydown',event => { if (event.key === 'Escape') { $('siteMenu').hidden = true; $('albaSymbol').setAttribute('aria-expanded','false'); } });
async function loadDevices() {
  const data = await api('/api/devices'); $('deviceList').replaceChildren();
  const current = data.devices.find(device => device.current);
  if (current) { $('deviceLabel').value = current.label; $('currentRemember').checked = Boolean(current.remembered); }
  for (const device of data.devices) {
    const row = node('div'); row.className = 'device-row'; const detail = node('div');
    detail.append(node('strong',device.label + (device.current ? ' · Questo browser' : '')),node('small',(device.remembered ? 'Accesso ricordato' : 'Sessione breve') + ' · scade ' + new Date(device.expires*1000).toLocaleDateString('it-IT')));
    row.appendChild(detail);
    if (!device.current) { const button = node('button','Disconnetti'); button.type = 'button'; button.className = 'secondary-button danger-button'; button.addEventListener('click',() => updateDevice({action:'revoke',device_id:device.device_id})); row.appendChild(button); }
    $('deviceList').appendChild(row);
  }
  $('revokeOtherDevices').disabled = data.devices.length < 2;
}
async function updateDevice(body) {
  try { await api('/api/devices',body); $('deviceMessage').textContent = 'Impostazioni aggiornate.'; await loadDevices(); }
  catch (error) { $('deviceMessage').textContent = error.message; }
}
$('devicesButton').addEventListener('click',async () => { $('deviceMessage').textContent = ''; $('deviceDialog').showModal(); try { await loadDevices(); await loadLinkedAccounts(); } catch (error) { $('deviceMessage').textContent = error.message; } });
$('closeDevices').addEventListener('click',() => $('deviceDialog').close());
$('deviceForm').addEventListener('submit',event => { event.preventDefault(); updateDevice({action:'remember',remember:$('currentRemember').checked,label:$('deviceLabel').value.trim()}); });
$('revokeOtherDevices').addEventListener('click',() => updateDevice({action:'revoke_others'}));

function currentMonth() {
  const parts = new Intl.DateTimeFormat('en-GB', {timeZone:'Europe/Rome', year:'numeric', month:'2-digit'}).formatToParts(new Date());
  return parts.find(p => p.type === 'year').value + '-' + parts.find(p => p.type === 'month').value;
}
let month = currentMonth();
function dateLabel(date, long = false) {
  return new Intl.DateTimeFormat('it-IT', {day:'numeric', month:long ? 'long' : 'short', ...(long ? {weekday:'long'} : {}), timeZone:'UTC'}).format(new Date(date + 'T12:00:00Z'));
}
function dayDescription(day) {
  if (day.future) return 'Giorno non ancora trascorso';
  if (!day.available) return 'Token non registrati';
  return numbers.format(day.total_tokens) + ' token · ' + day.requests + (day.requests === 1 ? ' generazione' : ' generazioni');
}
function detail(day) {
  const root = $('dayDetail'); root.replaceChildren();
  const heading = document.createElement('h5'); heading.textContent = dateLabel(day.date, true); root.appendChild(heading);
  if (!day.available || day.future) { const p = document.createElement('p'); p.textContent = dayDescription(day); root.appendChild(p); return; }
  const metrics = document.createElement('div'); metrics.className = 'day-metrics';
  for (const [label, value] of [['Totali', day.total_tokens], ['Ingresso', day.input_tokens], ['Uscita', day.output_tokens]]) {
    const el = document.createElement('div'), text = document.createElement('span'), count = document.createElement('strong');
    text.textContent = label; count.textContent = numbers.format(value); el.append(text, count); metrics.appendChild(el);
  }
  root.appendChild(metrics);
  const note = document.createElement('p'); note.textContent = day.requests + (day.requests === 1 ? ' generazione' : ' generazioni');
  if (day.partial) note.textContent += ' · Conteggio iniziato in questo giorno';
  if (day.unreported) note.textContent += ' · ' + day.unreported + ' conteggi non forniti dal modello';
  root.appendChild(note);
}
function showTooltip(day, cell) {
  const tip = $('dayTooltip'); tip.replaceChildren();
  const title = document.createElement('strong'); title.textContent = dateLabel(day.date, true);
  const text = document.createElement('span'); text.textContent = dayDescription(day); tip.append(title, text);
  if (day.available && !day.future) { const counts = document.createElement('div'); counts.textContent = 'Ingresso ' + numbers.format(day.input_tokens) + ' · Uscita ' + numbers.format(day.output_tokens); tip.appendChild(counts); }
  tip.hidden = false;
  const area = $('calendarWrap').getBoundingClientRect(), rect = cell.getBoundingClientRect();
  const left = Math.max(0, Math.min(rect.left - area.left + rect.width / 2 - tip.offsetWidth / 2, area.width - tip.offsetWidth));
  const top = rect.top - area.top - tip.offsetHeight - 9;
  tip.style.left = left + 'px'; tip.style.top = (top < 0 ? rect.bottom - area.top + 9 : top) + 'px';
  cell.setAttribute('aria-describedby', 'dayTooltip'); detail(day);
}
function hideTooltip(cell) {
  $('dayTooltip').hidden = true; cell.removeAttribute('aria-describedby');
  const day = lastUsage?.days.find(item => item.date === selectedDay);
  if (day) detail(day);
  else { $('dayDetail').replaceChildren(); $('dayDetail').textContent = 'Passa su un giorno o toccalo per vedere i token.'; }
}
function renderUsage(data) {
  lastUsage = data; $('usageError').textContent = ''; $('dayTooltip').hidden = true;
  $('totalTokens').textContent = numbers.format(data.totals.total_tokens);
  $('activeDays').textContent = data.totals.active_days + (data.totals.active_days === 1 ? ' giorno attivo' : ' giorni attivi');
  $('requestCount').textContent = data.totals.requests + (data.totals.requests === 1 ? ' generazione' : ' generazioni');
  $('monthLabel').textContent = new Intl.DateTimeFormat('it-IT', {month:'long', year:'numeric', timeZone:'UTC'}).format(new Date(data.month + '-01T12:00:00Z'));
  $('nextMonth').disabled = data.month >= currentMonth(); $('prevMonth').disabled = data.month <= '2000-01';
  const calendar = $('usageCalendar'); calendar.replaceChildren();
  calendar.setAttribute('aria-label', 'Utilizzo giornaliero: ' + $('monthLabel').textContent);
  const weekday = (new Date(data.month + '-01T12:00:00Z').getUTCDay() + 6) % 7;
  for (let i = 0; i < weekday; i++) { const spacer = document.createElement('span'); spacer.setAttribute('aria-hidden', 'true'); calendar.appendChild(spacer); }
  const maximum = Math.max(1, ...data.days.map(day => day.total_tokens));
  if (!selectedDay?.startsWith(data.month)) selectedDay = data.days.some(day => day.date === data.today) ? data.today : null;
  for (const day of data.days) {
    const level = day.total_tokens ? Math.ceil(day.total_tokens / maximum * 4) : 0;
    const cell = document.createElement('button'); cell.type = 'button'; cell.className = 'day level-' + level;
    cell.dataset.date = day.date; cell.textContent = String(Number(day.date.slice(-2)));
    if (!day.available && !day.future) cell.classList.add('untracked');
    if (day.future) cell.classList.add('future'); if (day.date === data.today) cell.classList.add('today');
    cell.classList.toggle('selected', day.date === selectedDay); cell.setAttribute('aria-pressed', String(day.date === selectedDay));
    cell.setAttribute('aria-label', dateLabel(day.date, true) + ': ' + dayDescription(day));
    cell.addEventListener('mouseenter', () => showTooltip(day, cell)); cell.addEventListener('focus', () => showTooltip(day, cell));
    cell.addEventListener('mouseleave', () => hideTooltip(cell)); cell.addEventListener('blur', () => hideTooltip(cell));
    cell.addEventListener('click', () => {
      selectedDay = day.date;
      calendar.querySelectorAll('.day').forEach(button => { const selected = button.dataset.date === selectedDay; button.classList.toggle('selected', selected); button.setAttribute('aria-pressed', String(selected)); });
      showTooltip(day, cell);
    });
    calendar.appendChild(cell);
  }
  const selected = data.days.find(day => day.date === selectedDay);
  if (selected) detail(selected); else $('dayDetail').textContent = 'Passa su un giorno o toccalo per vedere i token.';
  const since = new Intl.DateTimeFormat('it-IT', {day:'numeric',month:'short',year:'numeric',timeZone:'Europe/Rome'}).format(new Date(data.tracking_since));
  $('usageNote').textContent = 'Token di Telegram e sito, inclusi contesto e risposte. Conteggio dal ' + since + '; i giorni tratteggiati non sono registrati.';
  if (data.scope === 'bot') $('usageNote').textContent += ' Include anche il riordino automatico della memoria.';
  if (data.totals.unreported) $('usageNote').textContent += ' Alcuni conteggi non sono stati forniti dal modello: i totali sono parziali.';
}
async function loadUsage() {
  if (!loggedIn) return;
  const sequence = ++usageSequence;
  try { const data = await api('/api/usage?month=' + encodeURIComponent(month) + '&scope=' + encodeURIComponent($('usageScope').value)); if (sequence === usageSequence && loggedIn) renderUsage(data); }
  catch (error) { if (sequence === usageSequence && loggedIn) $('usageError').textContent = error.message; }
}
function moveMonth(offset) {
  const [year, value] = month.split('-').map(Number), target = new Date(Date.UTC(year, value - 1 + offset, 1));
  const next = target.getUTCFullYear() + '-' + String(target.getUTCMonth() + 1).padStart(2, '0');
  if (next < '2000-01' || next > currentMonth()) return;
  month = next; selectedDay = null; loadUsage();
}
$('prevMonth').addEventListener('click', () => moveMonth(-1)); $('nextMonth').addEventListener('click', () => moveMonth(1));
$('usageScope').addEventListener('change', () => loadUsage());
setInterval(() => { if (loggedIn && !document.hidden) loadUsage(); }, 30000);

function node(tag,text,className) { const element = document.createElement(tag); if (text !== undefined) element.textContent = text; if (className) element.className = className; return element; }
function adminFeedback(message,failed = false) { $('adminMessage').textContent = message; $('adminMessage').classList.toggle('failed',failed); }
async function adminRequest(path,body) {
  try { const result = await api(path,body); adminFeedback(result.message); await loadAdmin(); return true; }
  catch (error) { adminFeedback(error.message,true); return false; }
}
function actionButton(label,action,danger = false) { const button = node('button',label,'secondary-button' + (danger ? ' danger-button' : '')); button.type = 'button'; button.addEventListener('click',async () => { button.disabled = true; try { await action(); } finally { button.disabled = false; } }); return button; }
async function loadAdmin() {
  if (!isAdmin) return;
  try {
    adminData = await api('/api/admin'); const data = adminData; if(!identityConfigs && !$('identityConfigForm').contains(document.activeElement)) await loadIdentityConfigs();
    $('userCapacity').textContent = data.authorized_count + ' / ' + data.max_users;
    $('botState').textContent = data.paused ? 'In pausa' : 'Attivo'; $('pauseBot').textContent = data.paused ? 'Riattiva bot' : 'Metti in pausa';
    $('automaticAccess').checked = data.automatic_access; $('adminStats').textContent = data.stats;
    $('adminUsers').replaceChildren();
    for (const user of data.users) {
      const row = node('div',undefined,'admin-row'), info = node('div'), buttons = node('div',undefined,'row-actions');
      info.append(node('strong',user.name),node('small',user.id + ' · ' + (user.is_admin ? 'Amministratore' : user.authorized ? 'Autorizzato' : 'In attesa')));
      const budget = user.quota;
      info.appendChild(node('small',numbers.format(budget.used) + ' token questo mese' + (budget.limit ? ' / ' + numbers.format(budget.limit) : ' · senza limite') + (budget.unreported ? ' · conteggio parziale' : '')));
      buttons.appendChild(actionButton('Memorie',() => openMemories('user_id',user.id)));
      if (!user.is_admin) buttons.appendChild(actionButton(user.authorized ? 'Revoca' : 'Autorizza',() => adminRequest('/api/admin/users',{action:user.authorized ? 'deny' : 'allow',user_id:String(user.id)}),Boolean(user.authorized)));
      if (user.authorized && !user.is_admin) buttons.appendChild(actionButton('Revoca chiavi',() => adminRequest('/api/admin/users',{action:'revoke_key',user_id:String(user.id)})));
      row.append(info,buttons); $('adminUsers').appendChild(row);
      const limits = node('form',undefined,'token-limit-form'), label = node('label','Limite mensile'), input = node('input'), save = node('button','Salva limite','secondary-button');
      input.type = 'number'; input.min = '0'; input.max = '1000000000000'; input.step = '1'; input.required = true; input.value = String(budget.limit); input.setAttribute('aria-label','Limite mensile per ' + user.name); save.type = 'submit';
      label.appendChild(input); limits.append(label,save); limits.addEventListener('submit',async event => { event.preventDefault(); await adminRequest('/api/admin/users',{action:'token_limit',user_id:String(user.id),token_limit:Number(input.value)}); }); row.appendChild(limits);
    }
    $('adminGroups').replaceChildren();
    if (!data.groups.length) $('adminGroups').appendChild(node('p','Aggiungi Alba a un gruppo Telegram per vederlo qui.','empty-list'));
    for (const group of data.groups) {
      const row = node('div',undefined,'admin-row'), info = node('div'), buttons = node('div',undefined,'row-actions');
      info.append(node('strong',group.title || 'Gruppo Telegram'),node('small',group.id + ' · ' + (group.enabled ? 'Attivo' : 'Disattivo')));
      buttons.append(actionButton(group.enabled ? 'Disattiva' : 'Attiva',() => adminRequest('/api/admin/groups',{group_id:String(group.id),field:'enabled',enabled:!group.enabled})),actionButton(group.auto_mode ? 'Auto: sì' : 'Auto: no',() => adminRequest('/api/admin/groups',{group_id:String(group.id),field:'auto_mode',enabled:!group.auto_mode})),actionButton('Memorie',() => openMemories('group_id',group.id)));
      row.append(info,buttons); $('adminGroups').appendChild(row);
    }
    $('adminLogs').replaceChildren();
    for (const log of data.logs) { const row = node('tr'); row.append(node('td',new Date(log.timestamp * 1000).toLocaleString('it-IT',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'})),node('td',log.action),node('td',String(log.target_id ?? log.actor_id ?? 'Sistema')),node('td',log.outcome === 'ok' ? 'OK' : 'Negato')); $('adminLogs').appendChild(row); }
    const disk = data.disk, percent = Math.round(disk.used / disk.total * 100), gib = value => (value / 2 ** 30).toLocaleString('it-IT',{maximumFractionDigits:1}) + ' GiB';
    $('diskUsed').setAttribute('stroke-dasharray',percent + ' ' + (100 - percent)); $('diskPercent').textContent = percent + '%';
    $('diskChart').setAttribute('aria-label','Disco: ' + percent + '% utilizzato, ' + gib(disk.free) + ' liberi');
    $('diskUsedLabel').textContent = gib(disk.used); $('diskFreeLabel').textContent = gib(disk.free); $('diskTotalLabel').textContent = gib(disk.total) + ' totali';
    const schedule = data.memory_schedule; $('nightTime').value = schedule.night_time;
    if (!$('privacySettingsForm').contains(document.activeElement)) { $('privacyOwner').value = data.privacy.owner; $('privacyContact').value = data.privacy.contact; }
    if (!$('breakSettingsForm').contains(document.activeElement)) $('breakMinutes').value = String(data.break_minutes);
    $('memoryScheduleStatus').textContent = 'Ultimo salvataggio: ' + (schedule.last_flush ? new Date(Number(schedule.last_flush) * 1000).toLocaleString('it-IT') : 'in attesa') + '. Ultimo riordino notturno: ' + (schedule.last_night || 'in attesa') + '. Ora italiana.';
  } catch (error) { adminFeedback(error.message,true); }
}
let memoryExpiryTimer=null;
async function openMemories(kind,id) {
  try {
    const data = await api('/api/admin/memories?' + kind + '=' + encodeURIComponent(id));
    $('memoryOwner').textContent = data.owner; $('memoryScope').textContent = data.scope; $('memoryList').replaceChildren(); $('summaryList').replaceChildren();
    if (!data.memories.length) $('memoryList').appendChild(node('p','Nessuna memoria estratta. Le conversazioni complete restano salvate.','empty-list'));
    for (const memory of data.memories) { const card = node('article',undefined,'memory-card'), tags = node('div',undefined,'memory-tags'); tags.append(node('span',memory.evidence === 'fact' ? 'FATTO DICHIARATO' : memory.evidence === 'inference' ? 'INFERENZA' : 'INCERTO'),node('span',memory.category),node('span',memory.status)); card.append(tags,node('p',memory.content),node('small','#' + memory.id + ' · ' + new Date(memory.timestamp * 1000).toLocaleDateString('it-IT') + ' · Fonti: ' + JSON.parse(memory.source_ids).join(', ') + ' · Confidenza: ' + Math.round(memory.confidence * 100) + '%')); $('memoryList').appendChild(card); }
    if (!data.summaries.length) $('summaryList').appendChild(node('p','I riassunti vengono aggiornati automaticamente ogni dieci minuti.','empty-list'));
    for (const summary of data.summaries) { const card = node('article',undefined,'memory-card'); card.appendChild(node('small',(summary.summary_kind === 'consolidated' ? 'Rielaborato da Alba · citazioni originali · ' : 'Riassunto con fonti · ') + new Date(summary.timestamp * 1000).toLocaleString('it-IT'))); for (const quote of JSON.parse(summary.content)) card.appendChild(node('p','«' + quote.quote + '» [messaggio ' + quote.message_id + ', utente ' + quote.user_id + ']')); $('summaryList').appendChild(card); }
    clearTimeout(memoryExpiryTimer);
    if (data.expires) memoryExpiryTimer=setTimeout(() => { $('memoryDialog').close(); adminFeedback('Il consenso temporaneo è scaduto. Chiedi un nuovo codice all’utente.'); },Math.max(0,data.expires*1000-Date.now()));
    $('memoryDialog').showModal();
  } catch (error) { if(error.code==='memory_consent_required'&&kind==='user_id')showMemoryAccess(id);else adminFeedback(error.message,true); }
}
$('memoryDialog').addEventListener('close',()=>{clearTimeout(memoryExpiryTimer);$('memoryList').replaceChildren();$('summaryList').replaceChildren();});
$('closeMemory').addEventListener('click', () => $('memoryDialog').close());
function dashboardView(admin) { $('conversationView').hidden = admin; $('adminView').hidden = !admin; $('adminTab').classList.toggle('active',admin); $('conversationTab').classList.toggle('active',!admin); presenceTime = 0; if (admin) { loadAdmin(); api('/api/presence',{leave:true}).catch(() => {}); } else refreshStatus(); }
$('adminTab').addEventListener('click', () => dashboardView(true)); $('conversationTab').addEventListener('click', () => dashboardView(false));
$('authorizeForm').addEventListener('submit',async event => { event.preventDefault(); if (await adminRequest('/api/admin/users',{action:'allow',user_id:$('authorizeId').value.trim()})) $('authorizeId').value = ''; });
$('pauseBot').addEventListener('click', () => { if (adminData) adminRequest('/api/admin/action',{action:adminData.paused ? 'resume' : 'pause'}); });
$('automaticAccess').addEventListener('change', () => adminRequest('/api/admin/action',{action:'automatic_access',enabled:$('automaticAccess').checked}));
$('adminBackup').addEventListener('click', () => adminRequest('/api/admin/action',{action:'backup'})); $('adminRefresh').addEventListener('click',loadAdmin);
$('memoryScheduleForm').addEventListener('submit',event => { event.preventDefault(); adminRequest('/api/admin/action',{action:'memory_schedule',night_time:$('nightTime').value}); });
$('memoryFlush').addEventListener('click', () => adminRequest('/api/admin/action',{action:'memory_flush'}));
setInterval(() => { if (isAdmin && !$('adminView').hidden && !document.hidden && !$('adminUsers').contains(document.activeElement)) loadAdmin(); },60000);
function gib(value) { return value == null ? '—' : (value / 2 ** 30).toLocaleString('it-IT',{maximumFractionDigits:1}) + ' GiB'; }
let statusLoading = false, lastBreak = 0;
$('performanceEnabled').checked = preference('performance','on') !== 'off';
function performanceVisibility() { $('systemBar').hidden = !loggedIn || !$('performanceEnabled').checked; }
$('performanceEnabled').addEventListener('change', () => { savePreference('performance',$('performanceEnabled').checked ? 'on' : 'off'); performanceVisibility(); });
function showBreak(notice) {
  if (!notice || !notice.id || notice.id <= lastBreak || !loggedIn || location.pathname !== '/') return;
  const owner = String(currentUserId);
  const seen = Number(preference('break.' + owner,'0'));
  lastBreak = notice.id;
  if (notice.id <= seen) return;
  savePreference('break.' + owner,String(notice.id)); $('breakMessage').textContent = notice.message;
  if (!$('memoryDialog').open && !$('breakDialog').open) $('breakDialog').showModal();
  mascotState('rest','Un momento per te.');
}
$('takeBreak').addEventListener('click', () => { $('breakDialog').close(); $('status').textContent = 'Prenditi il tuo tempo. La conversazione resta qui.'; mascotState('rest','Io aspetto qui.'); });
$('continueChat').addEventListener('click', () => { $('breakDialog').close(); $('message').focus(); });
async function refreshStatus() {
  if (!loggedIn || document.hidden || statusLoading) return;
  statusLoading = true;
  try {
    if (!$('conversationView').hidden && Date.now() - presenceTime >= 20000) { await api('/api/presence',{}); presenceTime = Date.now(); }
    const data = await api('/api/status'), perf = data.performance; performanceVisibility();
    const cap = data.capacity; chatAdmitted = cap.admitted;
    $('capacityNotice').hidden = cap.admitted || $('conversationView').hidden;
    $('capacityNotice').textContent = 'I ' + cap.max_online + ' posti in chat sono occupati. Aspetta il tuo turno: il sito controlla automaticamente quando si libera un posto.' + (cap.position ? ' Posizione in attesa: ' + cap.position + '.' : '');
    if (!currentJob) $('send').disabled = !chatAdmitted;
    $('cpuValue').textContent = perf.cpu_percent == null ? 'in attesa' : perf.cpu_percent.toLocaleString('it-IT') + '%'; $('cpuBar').value = perf.cpu_percent || 0;
    $('ramValue').textContent = gib(perf.ram.used) + ' / ' + gib(perf.ram.total); $('ramBar').value = perf.ram.percent || 0;
    $('diskValue').textContent = gib(perf.disk.free) + ' liberi'; $('spaceBar').value = perf.disk.percent;
    $('performanceTime').textContent = 'Aggiornato ' + new Date(perf.timestamp * 1000).toLocaleTimeString('it-IT');
    if (isAdmin && !$('adminView').hidden) {
      const d = perf.disk, percent = Math.round(d.percent); $('diskUsed').setAttribute('stroke-dasharray',percent + ' ' + (100 - percent)); $('diskPercent').textContent = percent + '%'; $('diskUsedLabel').textContent = gib(d.used); $('diskFreeLabel').textContent = gib(d.free); $('diskTotalLabel').textContent = gib(d.total) + ' totali';
    }
    $('maintenanceNotice').hidden = !data.maintenance.running; $('maintenanceNotice').textContent = data.maintenance.message;
    const q = data.quota;
    $('quotaNotice').hidden = !q.exhausted; $('quotaNotice').textContent = 'Limite mensile raggiunto. Memorie, consultazione ed esportazione restano disponibili.';
    $('quotaDetail').replaceChildren();
    if (q.limit) { $('quotaDetail').append(node('strong','Budget del mese'),node('p',numbers.format(q.used) + ' / ' + numbers.format(q.limit) + ' token · ' + numbers.format(q.remaining) + ' disponibili')); const bar = node('progress'); bar.max = q.limit; bar.value = Math.min(q.used,q.limit); bar.setAttribute('aria-label','Budget mensile utilizzato'); $('quotaDetail').appendChild(bar); if (q.unreported) $('quotaDetail').appendChild(node('small','Il modello non ha fornito tutti i conteggi: il totale è parziale.')); }
    showBreak(data.break_notice);
  } catch (_) { $('performanceTime').textContent = 'Aggiornamento temporaneamente non disponibile'; }
  finally { statusLoading = false; }
}
setInterval(refreshStatus,2000);
document.addEventListener('visibilitychange', () => { if (!document.hidden) { presenceTime = 0; refreshStatus(); } else releasePresence(); });
function releasePresence() { if (loggedIn && !currentJob) fetch('/api/presence',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({leave:true}),keepalive:true}).catch(() => {}); }
window.addEventListener('pagehide',releasePresence);
async function syncHistory() {
  if (!loggedIn || historyLoading || currentJob || document.hidden) return;
  historyLoading = true;
  try {
    const data = await api('/api/history?after=' + historyCursor);
    if (currentJob) return;
    for (const row of data.messages) {
      const pending = [...$('messages').querySelectorAll('.bubble')].find(el => !el.dataset.messageId && el.dataset.role === row.role && el.dataset.rawContent === row.content);
      (pending || bubble(row.role,row.content,null,false)).dataset.messageId = row.id;
      historyCursor = Math.max(historyCursor,row.id);
    }
  } catch (_) {} finally { historyLoading = false; }
}
setInterval(() => syncHistory(),4000);
$('breakSettingsForm').addEventListener('submit',event => { event.preventDefault(); adminRequest('/api/admin/action',{action:'break_interval',minutes:Number($('breakMinutes').value)}); });
$('privacySettingsForm').addEventListener('submit',event => { event.preventDefault(); adminRequest('/api/admin/action',{action:'privacy',owner:$('privacyOwner').value.trim(),contact:$('privacyContact').value.trim()}); });
async function loadPolicy() {
  $('login').hidden = true; $('policyView').hidden = false; $('companion').hidden = true;
  const names = {'/privacy':['privacyArticle','Privacy e dati personali'],'/cookies':['cookieArticle','Cookie e preferenze'],'/policy':['termsArticle','Regole di utilizzo']};
  const [article,title] = names[location.pathname]; $(article).hidden = false; $('policyTitle').textContent = title; document.title = title + ' · Alba';
  try { const data = await api('/policy-info'); document.querySelectorAll('.policy-owner').forEach(el => el.textContent = data.owner); document.querySelectorAll('.policy-contact').forEach(el => el.textContent = data.contact); $('sessionHours').textContent = data.session_hours; document.querySelectorAll('.remember-days').forEach(el => el.textContent = data.remember_days); document.querySelectorAll('.session-hours').forEach(el => el.textContent = data.session_hours); $('backupRetention').textContent = data.retention.daily + ' copie giornaliere, ' + data.retention.weekly + ' settimanali e ' + data.retention.monthly + ' mensili'; }
  catch (error) { $('error').textContent = error.message; }
}
$('cookieNote').hidden = preference('cookie-note','') === 'read';
document.querySelector('footer').before($('cookieNote'));
$('cookieUnderstood').addEventListener('click', () => { $('cookieNote').hidden = true; savePreference('cookie-note','read'); });
$('clearPreferences').addEventListener('click', () => { try { Object.keys(localStorage).filter(key => key.startsWith('alba.')).forEach(key => localStorage.removeItem(key)); $('preferencesStatus').textContent = 'Preferenze cancellate. Si applicheranno le impostazioni predefinite alla prossima apertura.'; } catch (_) { $('preferencesStatus').textContent = 'Il browser non permette di modificare le preferenze.'; } });

// Albi can move around free space; chat, data panels and controls remain uncovered.
$('mascotDraggable').checked = preference('mascot-draggable','on') !== 'off';
$('mascotDraggable').addEventListener('change', () => savePreference('mascot-draggable',$('mascotDraggable').checked ? 'on' : 'off'));
let mascotPosition = null, mascotDrag = null, suppressMascotClick = false;
function protectedRects() { return [...document.querySelectorAll('#chat,#usagePanel,#adminView .panel,#systemBar,.header-actions,#account,#albaSymbol,#siteMenu,#loginForm,#policyView,#cookieNote,.footer-links')].filter(el => el.getClientRects().length).map(el => el.getBoundingClientRect()); }
function safeMascotPosition(x,y) {
  const size = innerWidth <= 500 ? 64 : 88, pad = 8;
  const clamp = (value,max) => Math.max(pad,Math.min(value,max - size - pad));
  x = clamp(x,innerWidth); y = clamp(y,innerHeight);
  const rects = protectedRects(), candidates = [[x,y],[pad,pad],[innerWidth-size-pad,pad],[pad,innerHeight-size-pad],[innerWidth-size-pad,innerHeight-size-pad]];
  for (const r of rects) candidates.push([r.left-size-pad,y],[r.right+pad,y],[x,r.top-size-pad],[x,r.bottom+pad]);
  const valid = candidates.map(([a,b]) => [clamp(a,innerWidth),clamp(b,innerHeight)]).filter(([a,b]) => !rects.some(r => a < r.right+4 && a+size > r.left-4 && b < r.bottom+4 && b+size > r.top-4));
  valid.sort((a,b) => Math.hypot(a[0]-x,a[1]-y)-Math.hypot(b[0]-x,b[1]-y));
  return valid.length ? {x:valid[0][0],y:valid[0][1]} : null;
}
function placeMascot(position,save = false) {
  if (!position) return;
  mascotPosition = position; document.body.appendChild($('companion')); $('companion').classList.add('mascot-floating');
  $('companion').style.left = position.x + 'px'; $('companion').style.top = position.y + 'px';
  $('companion').classList.toggle('mascot-message-right',position.x < innerWidth / 2);
  if (save) savePreference('mascot-position',JSON.stringify(position));
}
function restoreMascotPosition() { try { const saved = JSON.parse(preference('mascot-position','null')); if (saved && Number.isFinite(saved.x) && Number.isFinite(saved.y)) placeMascot(safeMascotPosition(saved.x,saved.y)); } catch (_) {} }
$('resetMascot').addEventListener('click', () => { mascotPosition = null; savePreference('mascot-position','null'); $('companion').classList.remove('mascot-floating'); $('companion').style.removeProperty('left'); $('companion').style.removeProperty('top'); (loggedIn ? document.querySelector('.welcome') : $('login')).appendChild($('companion')); mascotState('hello','Eccomi al mio posto.'); });
$('mascotButton').addEventListener('pointerdown',event => {
  if (!$('mascotDraggable').checked || event.button !== 0) return;
  const rect = $('companion').getBoundingClientRect(); mascotDrag = {id:event.pointerId,x:event.clientX,y:event.clientY,offsetX:event.clientX-rect.left,offsetY:event.clientY-rect.top,moved:false};
  $('mascotButton').setPointerCapture(event.pointerId);
});
$('mascotButton').addEventListener('pointermove',event => {
  if (!mascotDrag || mascotDrag.id !== event.pointerId || Math.hypot(event.clientX-mascotDrag.x,event.clientY-mascotDrag.y)<8) return;
  mascotDrag.moved = true; $('companion').classList.add('dragging'); $('companion').dataset.state = 'fly';
  placeMascot(safeMascotPosition(event.clientX-mascotDrag.offsetX,event.clientY-mascotDrag.offsetY));
});
function endMascotDrag() { if (!mascotDrag) return; suppressMascotClick = mascotDrag.moved; if (mascotDrag.moved && mascotPosition) placeMascot(mascotPosition,true); $('companion').classList.remove('dragging'); mascotDrag = null; if (suppressMascotClick) mascotState('hello','Lascio libera la conversazione.'); }
$('mascotButton').addEventListener('pointerup',endMascotDrag); $('mascotButton').addEventListener('pointercancel',endMascotDrag);
$('mascotButton').addEventListener('click',event => { if (suppressMascotClick) { event.stopImmediatePropagation(); suppressMascotClick = false; } },true);
$('mascotButton').addEventListener('keydown',event => { const moves = {ArrowLeft:[-20,0],ArrowRight:[20,0],ArrowUp:[0,-20],ArrowDown:[0,20]}; if (!moves[event.key] || !$('mascotDraggable').checked) return; event.preventDefault(); const rect = $('companion').getBoundingClientRect(), [dx,dy] = moves[event.key]; placeMascot(safeMascotPosition(rect.left+dx,rect.top+dy),true); });
window.addEventListener('resize', () => { if (mascotPosition) { const position = safeMascotPosition(mascotPosition.x,mascotPosition.y); if (position) placeMascot(position); else $('resetMascot').click(); } });
window.addEventListener('scroll', () => { if (mascotPosition && !mascotDrag) { const position = safeMascotPosition(mascotPosition.x,mascotPosition.y); if (position) placeMascot(position); else $('resetMascot').click(); } },{passive:true});
restoreMascotPosition();
function arrangeAccount() {
  if (!loggedIn) return;
  const mobile = innerWidth <= 740; $('account').classList.toggle('mobile-account',mobile);
  if (mobile) document.querySelector('.welcome').appendChild($('account'));
  else document.querySelector('.header-actions').insertBefore($('account'),$('logout'));
}
window.addEventListener('resize',arrangeAccount);

// Paths animate only while the logo is active.
(() => {
  const logo = $('albaSymbol'); let frame = 0, started = 0, leaving = 0, active = false, hovered = false, focused = false, tapUntil = 0, mode = 'snakes', turn = 0;
  const modes = ['snakes','orbit','vortex','wave','braid','bounce','spark','breathe'];
  const snakes = [1, 2].map(number => {
    const guide = $('snakeGuide' + number), length = guide.getTotalLength();
    return {path:$('snake' + number), head:$('snakeHead' + number), original:guide.getAttribute('d'), transform:$('snakeHead' + number).getAttribute('transform'), points:Array.from({length:65}, (_, i) => { const p = guide.getPointAtLength(i / 64 * length); return {x:p.x, y:p.y}; })};
  });
  function reset() { snakes.forEach(snake => { snake.path.setAttribute('d', snake.original); snake.head.setAttribute('transform', snake.transform); }); $('iconParticles').style.opacity = '0'; frame = 0; }
  function animate(now) {
    if (!animationsEnabled()) { active = false; reset(); return; }
    const wanted = hovered || focused || now < tapUntil;
    if (!wanted && !leaving) leaving = now;
    if (wanted) leaving = 0;
    if (leaving && now - leaving >= 250) { active = false; reset(); return; }
    const elapsed = (now - started) / 1000, gathering = Math.min(1, elapsed / .65), settle = 1 - Math.pow(1 - gathering, 3), fade = leaving ? 1 - (now - leaving) / 250 : 1;
    snakes.forEach((snake, index) => {
      const points = snake.points.map((p, i) => {
        const t = i / 64, before = snake.points[Math.max(0, i - 1)], after = snake.points[Math.min(64, i + 1)], dx = after.x - before.x, dy = after.y - before.y, length = Math.hypot(dx, dy) || 1;
        const coil = t * Math.PI * 3.1 + index * 2.5 + elapsed * 3;
        const coilX = 35 + Math.cos(coil) * (9 + 11 * t), coilY = 34 + Math.sin(coil) * (9 + 11 * t);
        const wave = Math.sin(elapsed * 13 - t * 10 + index * 2) * (index ? .75 : .9) * fade;
        let x = p.x, y = p.y;
        if (mode === 'snakes') { x += (coilX - p.x) * (1 - settle) - dy / length * wave; y += (coilY - p.y) * (1 - settle) + dx / length * wave; }
        else if (mode === 'wave') { x += Math.sin(elapsed * 9 - t * 12) * 2.4; y += Math.cos(elapsed * 9 - t * 12) * 1.4; }
        else if (mode === 'braid') { const twist = Math.sin(elapsed * 10 - t * 15 + index * Math.PI) * 3; x -= dy / length * twist; y += dx / length * twist; }
        else if (mode === 'bounce') { x = 36 + (p.x - 36) * (1 + Math.sin(elapsed * 10) * .045); y -= Math.abs(Math.sin(elapsed * 5)) * 7; }
        else if (mode === 'breathe') { const scale = 1 + Math.sin(elapsed * 3) * .08; x = 36 + (p.x - 36) * scale; y = 36 + (p.y - 36) * scale; }
        else if (mode === 'orbit' || mode === 'vortex') { const angle = mode === 'orbit' ? Math.sin(elapsed * 4) * .45 : (1 - Math.min(1,elapsed / 1.2)) * Math.PI * 2 + Math.sin(elapsed * 4) * .1; const scale = mode === 'vortex' ? .4 + .6 * settle : 1; const px = (p.x - 36) * scale, py = (p.y - 36) * scale; x = 36 + px * Math.cos(angle) - py * Math.sin(angle); y = 36 + px * Math.sin(angle) + py * Math.cos(angle); }
        else if (mode === 'spark') { x += Math.sin(elapsed * 12 - t * 6) * .8; y += Math.cos(elapsed * 12 - t * 6) * .8; }
        return {x:p.x + (x - p.x) * fade, y:p.y + (y - p.y) * fade};
      });
      let d = 'M' + points[0].x.toFixed(2) + ' ' + points[0].y.toFixed(2);
      for (let i = 1; i < points.length - 1; i++) { const p = points[i], next = points[i + 1]; d += ' Q' + p.x.toFixed(2) + ' ' + p.y.toFixed(2) + ' ' + ((p.x + next.x) / 2).toFixed(2) + ' ' + ((p.y + next.y) / 2).toFixed(2); }
      const headIndex = index ? points.length - 1 : 0, head = points[headIndex], adjacent = points[index ? headIndex - 1 : 1];
      const angle = Math.atan2(head.y - adjacent.y, head.x - adjacent.x) * 180 / Math.PI;
      const end = points[points.length - 1]; d += ' L' + end.x.toFixed(2) + ' ' + end.y.toFixed(2);
      snake.path.setAttribute('d', d); snake.head.setAttribute('transform', 'translate(' + head.x.toFixed(2) + ' ' + head.y.toFixed(2) + ') rotate(' + angle.toFixed(2) + ')');
    });
    const particles = mode === 'orbit' || mode === 'spark'; $('iconParticles').style.opacity = particles ? String((.6 + Math.sin(elapsed * 8) * .3) * fade) : '0'; $('iconParticles').setAttribute('transform','rotate(' + (elapsed * (mode === 'orbit' ? 130 : 35)).toFixed(1) + ' 36 36)');
    frame = requestAnimationFrame(animate);
  }
  function chooseMode() { const chosen = $('iconAnimation').value; mode = chosen === 'auto' ? modes[turn++ % modes.length] : chosen; logo.dataset.animation = mode; }
  function start() { if (!animationsEnabled() || active) return; chooseMode(); active = true; started = performance.now(); leaving = 0; frame = requestAnimationFrame(animate); }
  logo.addEventListener('mouseenter', () => { hovered = true; start(); }); logo.addEventListener('mouseleave', () => { hovered = false; });
  logo.addEventListener('focus', () => { focused = true; start(); }); logo.addEventListener('blur', () => { focused = false; });
  logo.addEventListener('click', () => { tapUntil = performance.now() + 1400; if (active) { chooseMode(); started = performance.now(); } else start(); });
  document.addEventListener('alba-icon-preview', () => { tapUntil = performance.now() + 1400; if (active) { chooseMode(); started = performance.now(); } else start(); });
  document.addEventListener('alba-motion-update', () => { if (!animationsEnabled()) { cancelAnimationFrame(frame); active = false; reset(); } });
  document.addEventListener('visibilitychange', () => { if (document.hidden) { cancelAnimationFrame(frame); active = false; reset(); } else if (hovered || focused) start(); });
  reducedMotion.addEventListener('change', () => { if (reducedMotion.matches) { cancelAnimationFrame(frame); active = false; reset(); } });
})();
document.addEventListener('visibilitychange', () => document.documentElement.classList.toggle('motion-sleep',document.hidden));
if (['/privacy','/cookies','/policy'].includes(location.pathname)) loadPolicy();
else if (incomingWebKey !== null) {
  loginMode('key'); $('token').value = incomingWebKey; incomingWebKey = null;
  $('loginForm').requestSubmit();
} else ready().catch(() => {});
// Optional identity providers. Secrets are configured only through the authenticated admin panel.
let authCsrf='',identityOptions=null,identityConfigs=null;
const officialIdentity={google:'https://developers.google.com/identity/openid-connect/openid-connect',github:'https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/creating-an-oauth-app',discord:'https://discord.com/developers/applications',phone:'https://www.twilio.com/docs/verify/api'};
async function externalApi(path,body){const response=await fetch(path,{method:body?'POST':'GET',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':authCsrf,'X-Session-CSRF':csrf},body:body?JSON.stringify(body):undefined}),data=await response.json();if(!response.ok)throw Error(data.error||'Verifica non riuscita.');return data;}
async function loadIdentityOptions(){identityOptions=await externalApi('/auth/providers');authCsrf=identityOptions.csrf;const box=$('identityButtons');box.replaceChildren();for(const p of identityOptions.providers){const b=actionButton(p.title,()=>beginIdentity(p.id,'login'));b.disabled=!p.enabled;b.title=p.enabled?'Accedi o crea un account':'Da configurare dal gestore';box.appendChild(b);}$('phoneSendButton').disabled=!identityOptions.phone_enabled;$('phoneLogin').hidden=!identityOptions.phone_enabled;$('identityMessage').textContent=identityOptions.providers.some(p=>p.enabled)||identityOptions.phone_enabled?'Massimo '+identityOptions.registration_limit+' utenti autorizzati. Gli account collegati mantengono le stesse memorie.':'Google, GitHub, Discord e SMS sono predisposti. Il gestore deve inserire le credenziali per attivarli.';}
async function beginIdentity(provider,mode){try{if(mode==='login'&&!$('identityConsent').checked)throw Error('Leggi privacy e regole e seleziona la casella.');if(!authCsrf)await loadIdentityOptions();const data=await externalApi('/auth/'+provider+'/start',{mode,privacy_accepted:true,remember:mode==='link'?true:$('rememberDevice').checked});location.assign(data.url);}catch(e){(mode==='link'?$('deviceMessage'):$('identityMessage')).textContent=e.message;}}
$('phoneSend').addEventListener('submit',async e=>{e.preventDefault();try{if(!$('identityConsent').checked)throw Error('Leggi privacy e regole e seleziona la casella.');$('phoneSendButton').disabled=true;const data=await externalApi('/auth/phone/send',{phone:$('phoneNumber').value.trim(),privacy_accepted:true,remember:$('rememberDevice').checked});$('identityMessage').textContent=data.message;$('phoneCheck').hidden=false;}catch(error){$('identityMessage').textContent=error.message;}finally{$('phoneSendButton').disabled=!identityOptions?.phone_enabled;}});
$('phoneCheck').addEventListener('submit',async e=>{e.preventDefault();try{const data=await externalApi('/auth/phone/check',{code:$('phoneCode').value.trim()});csrf=data.csrf;$('phoneCode').value='';await ready();}catch(error){$('identityMessage').textContent=error.message;}});
async function loadLinkedAccounts(){const data=await api('/api/accounts');$('linkedAccounts').replaceChildren();if(data.telegram_linked)$('linkedAccounts').appendChild(node('p','Telegram · collegato'));for(const account of data.accounts)$('linkedAccounts').appendChild(node('p',(account.provider==='phone'?'Telefono verificato':account.provider)+(account.email?' · '+account.email:'')));if(!identityOptions)await loadIdentityOptions();$('linkIdentityButtons').replaceChildren();for(const p of identityOptions.providers){const b=actionButton('Collega '+p.title,()=>beginIdentity(p.id,'link'));b.disabled=!p.enabled;$('linkIdentityButtons').appendChild(b);}}
async function loadIdentityConfigs(){const data=await api('/api/admin/identity');identityConfigs=data.providers;fillIdentityConfig();}
function fillIdentityConfig(){if(!identityConfigs)return;const id=$('identityProvider').value,config=identityConfigs.find(p=>p.id===id),phone=id==='phone';$('identityClientId').value=config.client_id;$('identitySecret').value='';$('identitySecret').placeholder=config.has_secret?'Segreto già salvato · lascia vuoto per conservarlo':'Inserisci il segreto dal portale ufficiale';$('identityIdLabel').textContent=phone?'Twilio Account SID (AC…)':'Client ID';$('identityService').value=config.service_sid;$('identityService').hidden=!phone;$('identityServiceLabel').hidden=!phone;$('identityCallback').value=config.callback||'SMS verificati con Twilio Verify';$('identityEnabled').checked=config.enabled;$('identityInstructions').href=officialIdentity[id];}
$('identityProvider').addEventListener('change',fillIdentityConfig);$('identityConfigForm').addEventListener('submit',async e=>{e.preventDefault();try{const data=await api('/api/admin/identity',{provider:$('identityProvider').value,client_id:$('identityClientId').value.trim(),client_secret:$('identitySecret').value,service_sid:$('identityService').value.trim(),enabled:$('identityEnabled').checked});$('identitySecret').value='';$('identityConfigMessage').textContent=data.message;await loadIdentityConfigs();await loadIdentityOptions();}catch(error){$('identityConfigMessage').textContent=error.message;}});
loadIdentityOptions().catch(()=>{$('identityMessage').textContent='Metodi esterni temporaneamente non disponibili.';});
if(new URLSearchParams(location.search).has('auth_error')){$('identityMessage').textContent='Verifica non completata oppure account in attesa di autorizzazione. Riprova o contatta il gestore.';history.replaceState(null,'',location.pathname);}

$('messages').addEventListener('click',async event=>{const button=event.target.closest('[data-feedback]');if(!button)return;try{await api('/api/feedback',{label:button.dataset.feedback,message_id:Number(button.closest('[data-message-id]').dataset.messageId)});button.parentNode.textContent='Feedback salvato · grazie.';}catch(error){$('error').textContent=error.message;}});
const feedbackObserver=new MutationObserver(()=>{for(const el of $('messages').querySelectorAll('.assistant[data-message-id]')){if(el.querySelector('.reply-feedback'))continue;const box=node('div',undefined,'reply-feedback');for(const [label,text]of [['utile','Utile'],['ripetitiva','Ripetitiva'],['fuori_tema','Fuori tema'],['piu_concreta','Più concreta']]){const b=node('button',text);b.type='button';b.dataset.feedback=label;box.appendChild(b);}el.appendChild(box);}});feedbackObserver.observe($('messages'),{childList:true,subtree:true,attributes:true,attributeFilter:['data-message-id']});

api('/policy-info').then(data=>{if(data.telegram_url)document.querySelectorAll('[data-telegram-link]').forEach(a=>a.href=data.telegram_url);}).catch(()=>{});

let memoryAccessOwner=null;
function showMemoryAccess(id){memoryAccessOwner=id;$('memoryAccessCode').value='';$('memoryAccessMessage').textContent='Utente selezionato: '+id+'. Il codice deve appartenere a questa persona.';$('memoryAccessDialog').showModal();}
$('closeMemoryAccess').addEventListener('click',()=>$('memoryAccessDialog').close());
$('memoryAccessForm').addEventListener('submit',async event=>{event.preventDefault();const token=$('memoryAccessCode').value.trim();$('memoryAccessCode').value='';try{await api('/api/admin/memory-access',{user_id:String(memoryAccessOwner),token});$('memoryAccessDialog').close();await openMemories('user_id',memoryAccessOwner);}catch(error){$('memoryAccessMessage').textContent=error.message;}});
$('requestMemoryAccess').addEventListener('click',async()=>{try{const data=await api('/api/admin/memory-access',{action:'request',user_id:String(memoryAccessOwner)});$('memoryAccessMessage').textContent=data.message;}catch(error){$('memoryAccessMessage').textContent=error.message;}});
