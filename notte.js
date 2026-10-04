'use strict';
const $ = id => document.getElementById(id);
const fmt = new Intl.NumberFormat('it-IT');
const labels = {chat:'Chat',web:'Ricerca web',notes:'Note interne',summaries:'Riassunti',whatsapp:'WhatsApp',telegram:'Telegram',files:'File locali',consolidation:'Consolidamento',system:'Riflessione',alba:'Alba · storico chat',github:'Repository GitHub',diary:'Diario di studio',study:'Studio e programmazione'};
const colors = ['#aed087','#d58c57','#8772ad','#347c9d','#5a9672','#d36776','#8f753c'];
let csrf = '', data = null, activePanel = 'chat', socket = null, reconnectTimer = null;
let inspecting = null, refreshBusy = false, lastChatId = 0, lastBusy = false, sending = false;
let slices = [];
const when = value => value ? new Date(value*1000).toLocaleString('it-IT') : 'Mai';
function notice(text,error=false){$('notice').textContent=text;$('notice').classList.toggle('error',error);}
async function api(path,body){
  const response=await fetch(path,{credentials:'same-origin',headers:body?{'Content-Type':'application/json','X-CSRF-Token':csrf}:{},...(body?{method:'POST',body:JSON.stringify(body)}:{})});
  if(response.status===403){let result=await response.json();if(result.code==='auth_expired')location.replace('/?next=notte');throw Error(result.error||'Accesso non valido.');}
  const result=await response.json();if(!response.ok)throw Error(result.error||'Richiesta non riuscita.');return result;
}
async function action(name,extra={}){await api('/api/notte/action',{action:name,...extra});await refresh();}
function element(tag,text,className){const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(className)el.className=className;return el;}
function renderEvents(target,events,empty='Non c’è ancora nulla qui.'){
  const box=$(target),nearBottom=box.scrollHeight-box.scrollTop-box.clientHeight<60;
  const fragment=document.createDocumentFragment();
  if(!events.length)fragment.append(element('p',empty,'empty'));
  for(const item of events){
    const article=element('article',undefined,'night-event '+item.role),header=element('header');
    header.append(element('span',item.role==='user'?'Matt':item.role==='assistant'?'Notte · '+item.emotion:(labels[item.category]||item.role)),element('time',when(item.created)));
    const prose=element('div',undefined,'prose');
    prose.innerHTML=DOMPurify.sanitize(marked.parse(item.content,{breaks:true}),{FORBID_TAGS:['img','iframe','style'],FORBID_ATTR:['style']});
    for(const a of prose.querySelectorAll('a')){a.rel='noopener noreferrer';a.target='_blank';}
    article.append(header,prose);fragment.append(article);
  }
  box.replaceChildren(fragment);if(nearBottom)box.scrollTop=box.scrollHeight;
}
async function loadEvents(category,target){const result=await api('/api/notte/events?category='+category);renderEvents(target,result.events);if(category==='chat')lastChatId=result.events.at(-1)?.id||0;}
function renderStatus(){
  $('entityMood').textContent=data.mood;$('moodLabel').textContent=data.mood;
  $('toggleAutonomy').textContent=data.config.enabled?'Metti in pausa l’autonomia':'Risveglia Notte';
  $('busy').textContent=data.running?(data.learning.phase|| (data.mode==='chat'?'Sta scrivendo…':'Sta pensando…')):'In ascolto';$('sendChat').disabled=(data.running&&data.mode==='chat')||sending;
  $('chatPreview').hidden=!data.partial;$('chatPreview').innerHTML=DOMPurify.sanitize(marked.parse(data.partial||'',{breaks:true}),{FORBID_TAGS:['img','iframe','style'],FORBID_ATTR:['style']});
  $('stopCore').disabled=!data.running;
  const emotionFragment=document.createDocumentFragment();
  for(const [name,value] of Object.entries(data.emotions)){
    const row=element('div',undefined,'emotion-row'),meter=element('meter');meter.min=0;meter.max=1;meter.value=value;meter.setAttribute('aria-label',name);
    row.append(element('span',name),element('span',Math.round(value*100)+'%'),meter);emotionFragment.append(row);
  }
  $('emotions').replaceChildren(emotionFragment);
  const r=data.resources;$('cpu').textContent=r.cpu_percent==null?'—':r.cpu_percent+'%';$('ram').textContent=r.ram?.percent==null?'—':r.ram.percent+'%';$('temperature').textContent=r.temperature_c==null?'—':r.temperature_c+' °C';$('energy').textContent=r.energy+' / 100';$('modelName').textContent=r.model;$('contextSize').textContent=fmt.format(r.context_tokens);$('lastConsolidation').textContent=when(data.config.last_consolidation);$('loadStatus').textContent=r.overloaded?'Carico alto: cicli sospesi.':r.model_busy?'Modello occupato.':'Risorse disponibili.';$('embeddingStatus').textContent=data.config.embedding_error||'Memoria vettoriale · '+data.config.embedding_model;
  if(data.error)notice(data.error,true);
  if(activePanel==='memory')renderConnectors();
  if(activePanel==='tokens')renderTokens();
  if(activePanel==='system')renderEmotionLog();
  if(activePanel==='diary')renderLearning();
}
function renderConnectors(){
  const fragment=document.createDocumentFragment();
  for(const c of data.connectors){
    const row=element('div',undefined,'connector'),info=element('div');info.append(element('strong',labels[c.id]),element('small',fmt.format(c.count)+' eventi · '+fmt.format(c.chars)+' caratteri · '+when(c.modified)));
    const button=element('button','Ispeziona');button.type='button';button.onclick=async()=>{inspecting=c.id;$('inspectionTitle').textContent=labels[c.id];try{await loadEvents(c.id,'inspection');}catch(e){notice(e.message,true);}};
    const toggle=element('input');toggle.type='checkbox';toggle.checked=c.enabled;toggle.setAttribute('aria-label','Attiva '+labels[c.id]);toggle.onchange=async()=>{try{await action('config',{config:{connectors:{[c.id]:toggle.checked}}});}catch(e){notice(e.message,true);}};
    row.append(info,button,toggle);fragment.append(row);
  }
  $('connectors').replaceChildren(fragment);
  $('cycles').replaceChildren(...data.cycles.map(c=>{const el=element('article',undefined,'night-event');el.append(element('header',when(c.started)+' · '+c.status),element('p',c.learned+' chunk · '+c.detail));return el;}));
}
function renderEmotionLog(){
  $('emotionLog').replaceChildren(...data.emotion_log.map(e=>{const row=element('article',undefined,'night-event');const weights=JSON.parse(e.state);row.append(element('header',when(e.created)+' · '+e.reason),element('p',Object.entries(weights).sort((a,b)=>b[1]-a[1]).slice(0,3).map(([k,v])=>k+' '+Math.round(v*100)+'%').join(' · ')));return row;}));
}
function renderLearning(){
  const l=data.learning;
  $('studyNow').disabled=data.running;
  if($('diaryTopic').options.length===1)for(const topic of l.topics){const option=element('option',topic);option.value=topic;$('diaryTopic').append(option);}
  $('sandboxStatus').textContent=l.sandbox_available?'Esercizi in ambiente isolato · rete disattivata · test indipendenti.':'Sandbox assente: gli esercizi non vengono eseguiti.';
  $('repositoryList').replaceChildren(...l.repositories.map(r=>element('p',r.name+' · '+r.files+' file · '+r.revision.slice(0,10))));
  $('toolList').replaceChildren(...l.tools.map(t=>element('p',t.name+' '+t.version+' · '+t.status+(t.status==='error'?' · '+t.detail:''))));
}
async function loadDiary(){
  const result=await api('/api/notte/diary?topic='+encodeURIComponent($('diaryTopic').value));
  const entries=result.entries.map(d=>{
    const article=element('article',undefined,'night-event diary-entry');
    article.append(element('header',d.topic+' · '+when(d.created)),element('h3',d.title),element('p',({verified:'Test superati',failed:'Test falliti',error:'Studio non completato',interrupted:'Studio interrotto'}[d.status]||d.status),'diary-status '+d.status));
    const prose=element('div',undefined,'prose');prose.innerHTML=DOMPurify.sanitize(marked.parse(d.summary),{FORBID_TAGS:['img','iframe','style'],FORBID_ATTR:['style']});article.append(prose);
    const sources=element('p',undefined,'sources');for(const url of d.sources){const a=element('a',url);if(url.startsWith('https://github.com/'))a.href=url;a.target='_blank';a.rel='noopener noreferrer';sources.append(a,element('br'));}article.append(sources);
    if(d.code){const details=element('details'),pre=element('pre'),code=element('code',d.code);pre.append(code);details.append(element('summary','Codice e risultato'),pre,element('pre',d.result));article.append(details);}else article.append(element('p',d.result));
    return article;
  });
  $('diaryEntries').replaceChildren(...(entries.length?entries:[element('p','Il primo ciclo di studio scriverà qui fonti, scoperte e prove.','empty')]));
}
$('diaryTopic').onchange=()=>loadDiary().catch(e=>notice(e.message,true));
$('studyNow').onclick=()=>action('study').catch(e=>notice(e.message,true));
$('repoForm').onsubmit=event=>{event.preventDefault();action('repository',{text:$('repoName').value}).then(()=>notice('Lettura del repository avviata.')).catch(e=>notice(e.message,true));};
$('installTool').onclick=()=>action('tool',{text:$('toolName').value}).catch(e=>notice(e.message,true));
function renderTokens(){
  $('lifetimeTokens').textContent=fmt.format(data.lifetime_tokens);
  const total=data.tokens.reduce((a,r)=>a+r.total,0),unknown=data.tokens.reduce((a,r)=>a+(r.unknown||0),0);
  $('unknownTokens').textContent=unknown?unknown+' chiamate senza conteggio completo dal modello.':'Conteggi dichiarati dal modello locale.';
  const canvas=$('tokenChart'),ctx=canvas.getContext('2d');ctx.clearRect(0,0,300,300);
  let angle=-Math.PI/2;slices=[];
  const legend=document.createDocumentFragment();
  data.tokens.forEach((row,i)=>{const end=angle+(total?row.total/total:0)*Math.PI*2,color=colors[i%colors.length];if(row.total){ctx.beginPath();ctx.arc(150,150,115,angle,end);ctx.arc(150,150,78,end,angle,true);ctx.closePath();ctx.fillStyle=color;ctx.fill();}slices.push({start:angle,end,row});angle=end;
    const button=element('button'),dot=element('span',undefined,'legend-dot');dot.style.background=color;button.append(dot,element('span',labels[row.category]||row.category),element('span',fmt.format(row.total)));button.onclick=()=>describeTokens(row,total);legend.append(button);
  });
  if(!total){ctx.beginPath();ctx.arc(150,150,100,0,Math.PI*2);ctx.strokeStyle='#2d3f31';ctx.lineWidth=32;ctx.stroke();}
  ctx.fillStyle='#e2eadd';ctx.font='24px Georgia';ctx.textAlign='center';ctx.fillText(fmt.format(total),150,152);ctx.fillStyle='#9aa99a';ctx.font='11px sans-serif';ctx.fillText('nel periodo',150,173);$('tokenLegend').replaceChildren(legend);
  let history=data.history;if($('historyPeriod').value==='week'){const weeks=new Map();for(const r of history){const d=new Date(r.day+'T00:00:00Z');d.setUTCDate(d.getUTCDate()-((d.getUTCDay()+6)%7));const key=d.toISOString().slice(0,10);weeks.set(key,(weeks.get(key)||0)+r.total);}history=[...weeks].map(([day,total])=>({day,total}));}
  const max=Math.max(1,...history.map(r=>r.total));$('tokenHistory').replaceChildren(...history.map(r=>{const row=element('div'),meter=element('meter');meter.max=max;meter.value=r.total;meter.setAttribute('aria-label',r.day);row.append(element('span',r.day),meter,element('span',fmt.format(r.total)));return row;}));
}
$('historyPeriod').onchange=()=>renderTokens();
function describeTokens(row,total){$('chartDetail').textContent=(labels[row.category]||row.category)+': '+fmt.format(row.total)+' token · '+(total?Math.round(row.total/total*100):0)+'%';}
$('tokenChart').addEventListener('pointermove',event=>{const rect=event.currentTarget.getBoundingClientRect(),x=(event.clientX-rect.left)/rect.width*300-150,y=(event.clientY-rect.top)/rect.height*300-150,r=Math.hypot(x,y);let a=Math.atan2(y,x);if(a<-Math.PI/2)a+=2*Math.PI;const match=slices.find(s=>a>=s.start&&a<s.end);if(match&&r>=78&&r<=115)describeTokens(match.row,data.tokens.reduce((v,r)=>v+r.total,0));});
$('tokenChart').addEventListener('keydown',event=>{if(event.key==='Enter'&&slices.length)describeTokens(slices[0].row,data.tokens.reduce((v,r)=>v+r.total,0));});
async function refresh(){if(refreshBusy)return;refreshBusy=true;try{data=await api('/api/notte/status');renderStatus();if(!data.running&&lastBusy){if(activePanel==='diary')await loadDiary();await loadEvents('chat','chatEvents');if(activePanel==='summaries'){await loadEvents('summaries','summaryEvents');await loadEvents('notes','noteEvents');}if(inspecting&&activePanel==='memory')await loadEvents(inspecting,'inspection');}lastBusy=data.running;}catch(e){notice(e.message,true);}finally{refreshBusy=false;}}
async function panel(name){activePanel=name;document.querySelectorAll('[data-panel]').forEach(b=>b.setAttribute('aria-selected',String(b.dataset.panel===name)));document.querySelectorAll('[role=tabpanel]').forEach(s=>s.hidden=s.id!=='panel-'+name);if(!data)return;renderStatus();if(name==='diary'){await loadDiary();}if(name==='summaries'){await loadEvents('summaries','summaryEvents');await loadEvents('notes','noteEvents');}if(name==='system'){
  const c=data.config;$('studyMinutes').value=c.study_minutes;$('studyEnabled').checked=c.study_enabled;$('interval').value=c.interval;$('reflectionMinutes').value=c.reflection_minutes;$('initiative').value=c.initiative;$('volatility').value=c.volatility;$('webEnabled').checked=c.web_enabled;$('telegramEnabled').checked=c.telegram_enabled;$('whatsappEnabled').checked=c.whatsapp_enabled;$('mattNumber').value=c.matt_number;
}}
document.querySelectorAll('[data-panel]').forEach(button=>{button.onclick=()=>panel(button.dataset.panel).catch(e=>notice(e.message,true));button.onkeydown=event=>{if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key))return;event.preventDefault();const tabs=[...document.querySelectorAll('[data-panel]')],index=tabs.indexOf(button),next=tabs[(index+(['ArrowLeft','ArrowUp'].includes(event.key)?tabs.length-1:1))%tabs.length];next.focus();next.click();};});
for(const [id,name] of [['consolidate','consolidation'],['reflect','reflection'],['stopCore','stop']])$(id).onclick=()=>action(name).catch(e=>notice(e.message,true));
$('toggleAutonomy').onclick=()=>action('config',{config:{enabled:!data.config.enabled}}).then(()=>notice(data.config.enabled?'Autonomia attiva.':'Autonomia in pausa.')).catch(e=>notice(e.message,true));
$('chatForm').onsubmit=async event=>{event.preventDefault();if(sending)return;sending=true;$('sendChat').disabled=true;try{await action('chat',{text:$('chatText').value.trim()});$('chatText').value='';await loadEvents('chat','chatEvents');$('chatEvents').scrollTop=$('chatEvents').scrollHeight;}catch(e){notice(e.message,true);}finally{sending=false;$('sendChat').disabled=Boolean(data?.running&&data?.mode==='chat');}};
$('settingsForm').onsubmit=event=>{event.preventDefault();action('config',{config:{study_minutes:Number($('studyMinutes').value),study_enabled:$('studyEnabled').checked,interval:Number($('interval').value),reflection_minutes:Number($('reflectionMinutes').value),initiative:Number($('initiative').value),volatility:Number($('volatility').value),web_enabled:$('webEnabled').checked,telegram_enabled:$('telegramEnabled').checked,whatsapp_enabled:$('whatsappEnabled').checked,matt_number:$('mattNumber').value}}).then(()=>notice('Ritmo aggiornato.')).catch(e=>notice(e.message,true));};
$('importFile').onclick=()=>action('import',{text:$('importText').value}).then(()=>{$('importText').value='';notice('Documento salvato.');}).catch(e=>notice(e.message,true));
$('resetStats').onclick=()=>{if(confirm('Azzerare il periodo visualizzato? Il totale di vita rimane.'))action('reset_stats').catch(e=>notice(e.message,true));};
function connect(){if(socket||document.hidden)return;socket=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/api/notte/stream');socket.onopen=()=>{$('streamState').textContent='In diretta dal Raspberry';};socket.onmessage=async event=>{const update=JSON.parse(event.data);await refresh();if(update.last_id>lastChatId)await loadEvents('chat','chatEvents');};socket.onerror=()=>socket?.close();socket.onclose=()=>{socket=null;$('streamState').textContent='Riconnessione…';clearTimeout(reconnectTimer);if(!document.hidden)reconnectTimer=setTimeout(connect,5000);};}
document.addEventListener('visibilitychange',()=>{if(document.hidden){clearTimeout(reconnectTimer);socket?.close();}else{refresh();connect();}});
(async()=>{try{const me=await api('/api/me');if(!me.is_admin){notice('Notte è riservata all’amministratore.',true);return;}csrf=me.csrf;await refresh();await loadEvents('chat','chatEvents');connect();}catch(e){notice(e.message,true);}})();
