'use strict';
const $ = id => document.getElementById(id);
const fmt = new Intl.NumberFormat('it-IT');
const labels = {chat:'Chat',web:'Ricerca web',notes:'Note interne',summaries:'Riassunti',whatsapp:'WhatsApp',telegram:'Telegram',files:'File locali',consolidation:'Consolidamento',system:'Riflessione',alba:'Alba · storico chat',github:'Repository GitHub',diary:'Diario di studio',study:'Studio e programmazione',reddit:'Reddit',stackoverflow:'Stack Overflow',jokes:'Battute · JokeAPI',training:'Training locale',activity:'Attività'};
const colors = ['#aed087','#d58c57','#8772ad','#347c9d','#5a9672','#d36776','#8f753c'];
let csrf = '', data = null, activePanel = 'chat', socket = null, reconnectTimer = null;
let inspecting = null, refreshBusy = false, lastChatId = 0, lastBusy = false, sending = false;
let slices = [], activityBefore = 0, activityCursor = 0;
let settingsDraftKey = '', settingsDirty = false, settingsLoaded = false, trainingDirty = false;
const settingsFields = {modelProfile:'profile',studyMinutes:'study_minutes',studyEnabled:'study_enabled',interval:'interval',reflectionMinutes:'reflection_minutes',initiative:'initiative',volatility:'volatility',webEnabled:'web_enabled',telegramEnabled:'telegram_enabled',whatsappEnabled:'whatsapp_enabled',mattNumber:'matt_number'};
function settingsValues(){return Object.fromEntries(Object.entries(settingsFields).map(([id,key])=>{const el=$(id);return [key,el.type==='checkbox'?el.checked:el.type==='range'||el.tagName==='SELECT'&&id!=='modelProfile'?Number(el.value):el.value];}));}
function updateRanges(){for(const id of ['initiative','volatility']){const el=$(id),percent=Math.round(Number(el.value)*100);$(id+'Value').value=percent+'%';el.setAttribute('aria-valuetext',percent+'%');el.style.setProperty('--range-percent',percent+'%');}}
function rememberSettings(){settingsDirty=true;updateRanges();$('settingsState').textContent='Modifiche da salvare.';try{sessionStorage.setItem(settingsDraftKey,JSON.stringify(settingsValues()));}catch{}}
function initSettingsDraft(uid){settingsDraftKey='notte-settings-draft:'+uid;}
function loadSettings(){if(settingsLoaded&&settingsDirty)return;let values=data.config;try{const saved=JSON.parse(sessionStorage.getItem(settingsDraftKey));if(saved&&typeof saved==='object'){values={...values,...saved};settingsDirty=true;}}catch{}for(const [id,key] of Object.entries(settingsFields)){const el=$(id);if(el.type==='checkbox')el.checked=Boolean(values[key]);else el.value=values[key];}settingsLoaded=true;updateRanges();$('settingsState').textContent=settingsDirty?'Modifiche da salvare.':'';}
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
async function loadEvents(category,target){const result=await api('/api/notte/events?category='+category+(target==='activityEvents'&&activityBefore?'&before='+activityBefore:''));if(target==='activityEvents'){activityCursor=result.before||result.events[0]?.id||0;$('olderActivity').disabled=!activityCursor;}renderEvents(target,result.events);if(category==='chat')lastChatId=result.events.at(-1)?.id||0;}
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
  if(activePanel==='system'){renderEmotionLog();$('benchmarkResults').replaceChildren(...(data.benchmarks||[]).map(r=>{const a=element('article',undefined,'night-event');a.append(element('h3',r.model+' · '+r.metrics.cache),element('p',r.status+' · '+JSON.stringify(r.options)),element('p',r.metrics.tokens_per_second+' token/s · primo token '+r.metrics.first_token_ms+' ms · test '+r.metrics.test_passed));return a;}));}
  if(activePanel==='diary')renderLearning();
  if(activePanel==='training')renderTraining();
  if(activePanel==='learning')renderLearningDashboard();
  if(activePanel==='lab')renderLab();
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
  if($('diaryTopic').options.length===1)for(const topic of [...new Set([...l.topics,'Reddit · learnpython','Reddit · programming','Reddit · netsec','Reddit · raspberry_pi'])]){const option=element('option',topic);option.value=topic;$('diaryTopic').append(option);}
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
    const sources=element('p',undefined,'sources');for(const url of d.sources){const a=element('a',url);if(url.startsWith('https://github.com/')||url.startsWith('https://www.reddit.com/'))a.href=url;a.target='_blank';a.rel='noopener noreferrer';sources.append(a,element('br'));}article.append(sources);
    if(d.code){const details=element('details'),pre=element('pre'),code=element('code',d.code);pre.append(code);details.append(element('summary','Codice e risultato'),pre,element('pre',d.result));article.append(details);}else article.append(element('p',d.result));
    return article;
  });
  $('diaryEntries').replaceChildren(...(entries.length?entries:[element('p','Il primo ciclo di studio scriverà qui fonti, scoperte e prove.','empty')]));
}
$('diaryTopic').onchange=()=>loadDiary().catch(e=>notice(e.message,true));
$('olderActivity').onclick=()=>{if(activityCursor){activityBefore=activityCursor;loadEvents('all','activityEvents').catch(e=>notice(e.message,true));}};
$('latestActivity').onclick=()=>{activityBefore=0;loadEvents('all','activityEvents').catch(e=>notice(e.message,true));};
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
async function refresh(){if(refreshBusy)return;refreshBusy=true;try{data=await api('/api/notte/status');renderStatus();if(activePanel==='activity')await loadEvents('all','activityEvents');if(!data.running&&lastBusy){if(activePanel==='diary')await loadDiary();await loadEvents('chat','chatEvents');if(activePanel==='summaries'){await loadEvents('summaries','summaryEvents');await loadEvents('notes','noteEvents');}if(inspecting&&activePanel==='memory')await loadEvents(inspecting,'inspection');}lastBusy=data.running;}catch(e){notice(e.message,true);}finally{refreshBusy=false;}}
async function panel(name){activePanel=name;document.querySelectorAll('[data-panel]').forEach(b=>b.setAttribute('aria-selected',String(b.dataset.panel===name)));document.querySelectorAll('[role=tabpanel]').forEach(s=>s.hidden=s.id!=='panel-'+name);if(!data)return;renderStatus();if(name==='diary'){await loadDiary();}if(name==='activity')await loadEvents('all','activityEvents');if(name==='summaries'){await loadEvents('summaries','summaryEvents');await loadEvents('notes','noteEvents');}if(name==='system'){
  loadSettings();
}if(name==='lab')await loadLabModels();if(name==='project')await loadProject();}
document.querySelectorAll('[data-panel]').forEach(button=>{button.onclick=()=>panel(button.dataset.panel).catch(e=>notice(e.message,true));button.onkeydown=event=>{if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key))return;event.preventDefault();const tabs=[...document.querySelectorAll('[data-panel]')],index=tabs.indexOf(button),next=tabs[(index+(['ArrowLeft','ArrowUp'].includes(event.key)?tabs.length-1:1))%tabs.length];next.focus();next.click();};});
for(const [id,name] of [['consolidate','consolidation'],['reflect','reflection'],['stopCore','stop']])$(id).onclick=()=>action(name).catch(e=>notice(e.message,true));
$('toggleAutonomy').onclick=()=>action('config',{config:{enabled:!data.config.enabled}}).then(()=>notice(data.config.enabled?'Autonomia attiva.':'Autonomia in pausa.')).catch(e=>notice(e.message,true));
$('chatForm').onsubmit=async event=>{event.preventDefault();if(sending)return;sending=true;$('sendChat').disabled=true;try{await action('chat',{text:$('chatText').value.trim()});$('chatText').value='';await loadEvents('chat','chatEvents');$('chatEvents').scrollTop=$('chatEvents').scrollHeight;}catch(e){notice(e.message,true);}finally{sending=false;$('sendChat').disabled=Boolean(data?.running&&data?.mode==='chat');}};
$('settingsForm').addEventListener('input',rememberSettings);
$('settingsForm').addEventListener('change',rememberSettings);
$('settingsForm').onsubmit=async event=>{event.preventDefault();const saved=settingsValues();$('saveSettings').disabled=true;try{await action('config',{config:saved});if(JSON.stringify(settingsValues())===JSON.stringify(saved)){settingsDirty=false;try{sessionStorage.removeItem(settingsDraftKey);}catch{}$('settingsState').textContent='Impostazioni salvate.';}else $('settingsState').textContent='Salvato. Ci sono altre modifiche da salvare.';notice('Ritmo aggiornato.');}catch(e){$('settingsState').textContent=e.message;notice(e.message,true);}finally{$('saveSettings').disabled=false;}};
$('importFile').onclick=()=>action('import',{text:$('importText').value}).then(()=>{$('importText').value='';notice('Documento salvato.');}).catch(e=>notice(e.message,true));
$('resetStats').onclick=()=>{if(confirm('Azzerare il periodo visualizzato? Il totale di vita rimane.'))action('reset_stats').catch(e=>notice(e.message,true));};
function connect(){if(socket||document.hidden)return;socket=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/api/notte/stream');socket.onopen=()=>{$('streamState').textContent='In diretta dal dispositivo';};socket.onmessage=async event=>{const update=JSON.parse(event.data);await refresh();if(update.last_id>lastChatId)await loadEvents('chat','chatEvents');};socket.onerror=()=>socket?.close();socket.onclose=()=>{socket=null;$('streamState').textContent='Riconnessione…';clearTimeout(reconnectTimer);if(!document.hidden)reconnectTimer=setTimeout(connect,5000);};}
document.addEventListener('visibilitychange',()=>{if(document.hidden){clearTimeout(reconnectTimer);socket?.close();}else{refresh();connect();}});
(async()=>{try{const me=await api('/api/me');if(!me.is_admin){notice('Notte è riservata all’amministratore.',true);return;}csrf=me.csrf;initLearningDraft(me.user_id);initSettingsDraft(me.user_id);await refresh();await loadEvents('chat','chatEvents');connect();if([...document.querySelectorAll('[data-panel]')].some(b=>'#'+b.dataset.panel===location.hash))await panel(location.hash.slice(1));}catch(e){notice(e.message,true);}})();

function renderTraining(){
 const t=data.training;$('trainingState').textContent=t.base+' · '+t.schedule+' · '+(t.running?t.phase:t.ready?'Pronto':'Preparazione richiesta')+' · '+(t.active_model||'Nessuna versione personale attiva');
 $('trainNow').disabled=t.running||!t.ready;$('stopTraining').disabled=!t.running;
 if(!trainingDirty){$('trainingHour').value=data.config.training_hour;$('dailyTraining').checked=data.config.training_enabled;}
 $('trainingRuns').replaceChildren(...t.runs.map(r=>{const card=element('article',undefined,'night-event');card.append(element('h3','#'+r.id+' · '+r.day+' · '+r.status),element('p',r.detail),element('p',r.model));
 const m=r.metrics;if(m.final_loss!=null)card.append(element('p','Loss '+m.initial_loss.toFixed(3)+' → '+m.final_loss.toFixed(3)+' · '+m.steps+' step · '+m.trainable_parameters+' parametri'));
 if(m.benchmark)card.append(element('p','Test funzionali '+m.benchmark.passed+'/'+m.benchmark.total));
 const inspect=element('button','Dati, verifiche e log');inspect.onclick=async()=>{try{const files=await api('/api/notte/training/'+r.id);$('trainingFiles').replaceChildren(...Object.entries(files).map(([name,value])=>{const d=element('details');d.append(element('summary',name),element('pre',value));return d;}));}catch(e){notice(e.message,true);}};card.append(inspect);
 if(r.status==='ready'){const restore=element('button','Ripristina versione');restore.onclick=()=>action('rollback',{id:r.id}).catch(e=>notice(e.message,true));card.append(restore);}return card;}));
}
$('readCommunity').onclick=()=>action('community').catch(e=>notice(e.message,true));
$('readReddit').onclick=()=>action('reddit').catch(e=>notice(e.message,true));
$('trainNow').onclick=()=>action('train').catch(e=>notice(e.message,true));
$('stopTraining').onclick=()=>action('stop_training').catch(e=>notice(e.message,true));
for(const id of ['dailyTraining','trainingHour'])$(id).addEventListener('input',()=>{trainingDirty=true;});
$('saveTraining').onclick=async()=>{const saved={training_enabled:$('dailyTraining').checked,training_hour:Number($('trainingHour').value)};$('saveTraining').disabled=true;try{await action('config',{config:saved});if(saved.training_enabled===$('dailyTraining').checked&&saved.training_hour===Number($('trainingHour').value))trainingDirty=false;notice('Orario salvato.');}catch(e){notice(e.message,true);}finally{$('saveTraining').disabled=false;}};
$('personalChat').onsubmit=e=>{e.preventDefault();action('personal_chat',{text:$('personalText').value.trim()}).then(()=>{$('personalText').value='';panel('chat');}).catch(e=>notice(e.message,true));};

$('benchmarkNow').onclick=()=>action('benchmark').catch(e=>notice(e.message,true));

let labModels=[],labRendered='';
async function loadLabModels(){
 if(!labModels.length){const value=await api('/api/notte/models');labModels=value.models||[];const selection=$('labModel');selection.replaceChildren(...labModels.map(m=>{const option=element('option',m.name);option.value=m.name;return option;}));if(labModels.some(m=>m.name==='notte-coding:latest'))selection.value='notte-coding:latest';}
 labModelNote();
}
function labModelNote(){const name=$('labModel').value,prepared=['adaptive','warm','cpu2'].includes($('labPolicy').value)||data?.ssd_runtime?.models.includes(name),oversize=(labModels.find(m=>m.name===name)?.size||0)>6*1024**3;$('labModelNote').textContent=!prepared?'SSD non preparato per questo modello: disponibile solo il percorso normale.':oversize?'Modello sopra RAM: solo percorso SSD; può essere molto lento.':'GGUF preparato: confronto ammesso dopo verifica dell’identità dei pesi.';if(!prepared&&$('labMode').value!=='normal')$('labMode').value='normal';if(oversize)$('labMode').value='optimized';}
function labGraph(samples,key,title,unit){
 const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 660 104');svg.setAttribute('class','lab-graph');svg.setAttribute('role','img');svg.setAttribute('aria-label',title);
 const put=(tag,attrs,text)=>{const el=document.createElementNS(svg.namespaceURI,tag);for(const [k,v] of Object.entries(attrs))el.setAttribute(k,String(v));if(text!==undefined)el.textContent=text;svg.append(el);return el;},max=Math.max(1,...samples.map(s=>s.status==='ok'?(s[key]||0):0));
 put('text',{x:0,y:14,class:'lab-chart-label'},title);
 samples.forEach((s,i)=>{const y=30+i*30,v=s.status==='ok'?s[key]:null;put('text',{x:0,y:y+14,class:'lab-chart-label'},s.backend==='normal'?'Normale':'Ottimizzato');if(typeof v==='number'){put('rect',{x:115,y,width:v/max*410,height:19,rx:3,class:s.backend==='normal'?'lab-chart-normal':'lab-chart-optimized'});put('text',{x:535,y:y+14,class:'lab-chart-label'},v.toFixed(2)+' '+unit);}else put('text',{x:115,y:y+14,class:'lab-chart-label'},s.status==='error'?'Fallito / N/A':'Non misurato');});return svg;
}
function labResponse(s){const card=element('article',undefined,'night-event');card.append(element('h3',(s.backend==='normal'?'Normale · Ollama':'Ottimizzato · '+(s.policy||'SSD'))+' · '+(s.status||'in preparazione')),element('p',(s.model||'')+(s.policy?' · '+s.policy:'')),element('pre',s.content||s.error||'Attendo il primo token…'));if(s.error&&s.content)card.append(element('p',s.error));card.append(element('p','Primo token '+(s.first_token_ms??'—')+' ms · totale '+(s.wall_ms??'—')+' ms · '+(s.tokens_per_second?.toFixed(2)??'—')+' token/s','muted'));return card;}
function downloadLabReport(run){
 const escape=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),graphs=[labGraph(run.result.samples,'tokens_per_second','Token/s · più alto = più veloce','token/s'),labGraph(run.result.samples,'first_token_ms','Primo token · più basso = più veloce','ms'),labGraph(run.result.samples,'wall_ms','Attesa totale · più basso = più veloce','ms'),labGraph(run.result.samples,'output_tokens','Token generati','token')];
 const html='<!doctype html><html lang="it"><meta charset="utf-8"><title>Notte Test Lab #'+run.id+'</title><style>body{font:15px/1.6 sans-serif;max-width:900px;margin:30px auto;padding:20px}pre{white-space:pre-wrap;overflow-wrap:anywhere}.lab-chart-label{font:12px sans-serif}.lab-chart-normal{fill:#788275}.lab-chart-optimized{fill:#456b43}svg{max-width:100%}</style><h1>Notte Test Lab #'+run.id+'</h1><p>'+escape(when(run.created))+' · '+escape(run.status)+'</p><p>'+escape(run.result.conditions)+'</p><pre>'+escape(JSON.stringify(run.config,null,2))+'</pre>'+graphs.map(g=>g.outerHTML).join('')+run.result.samples.map(s=>'<h2>'+escape(s.backend)+'</h2><pre>'+escape(s.content||s.error||'')+'</pre><pre>'+escape(JSON.stringify({...s,content:undefined,tokens:undefined},null,2))+'</pre>').join('')+'<p>Confronto del testo: '+escape(run.result.same_text)+' · Identità token: non disponibile tra Ollama e SSD. Nessun giudizio automatico sull’intelligenza.</p></html>';
 const url=URL.createObjectURL(new Blob([html],{type:'text/html'})),a=element('a');a.href=url;a.download='notte-lab-'+run.id+'.html';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function renderLab(){
 const lab=data.test_lab||{runs:[]},busy=Boolean(data.running||lab.active);$('labRun').disabled=busy;$('labStop').disabled=!(data.mode==='test_lab'||lab.active);$('labState').textContent=lab.active?'Prova #'+lab.active.id+' · '+lab.active.backend+' in corso':busy?'Modello occupato: attendi oppure interrompi il ciclo dalla chat.':'Pronto. Le risposte sono misurate, non stimate.';$('labLive').replaceChildren(...(lab.active?.samples||[]).map(labResponse));
 const signature=JSON.stringify(lab.runs);if(signature===labRendered)return;labRendered=signature;
 $('labRuns').replaceChildren(...lab.runs.map(run=>{const card=element('article',undefined,'night-event');card.append(element('header','#'+run.id+' · '+when(run.created)+' · '+run.status),element('h3',run.config.model),element('p',run.config.prompt));const responses=element('div',undefined,'lab-responses');responses.append(...run.result.samples.map(labResponse));card.append(responses);card.append(labGraph(run.result.samples,'tokens_per_second','Generazione · più alto = più veloce','token/s'),labGraph(run.result.samples,'first_token_ms','Primo token · più basso = più veloce','ms'),labGraph(run.result.samples,'wall_ms','Attesa totale · più basso = più veloce','ms'),labGraph(run.result.samples,'output_tokens','Token generati','token'));card.append(element('p','Testo uguale: '+(run.result.same_text===null?'non confrontato':run.result.same_text?'sì':'no')+' · identità dei token non disponibile tra Ollama e SSD. Nessun giudizio automatico sull’intelligenza.','muted'));const links=element('div',undefined,'action-row'),json=element('a','Dati JSON');json.href='/api/notte/lab/'+run.id+'/export';json.download='notte-lab-'+run.id+'.json';const report=element('button','Report con grafici');report.type='button';report.onclick=()=>downloadLabReport(run);links.append(json,report);card.append(links);return card;}));
}
async function loadProject(){const project=await api('/optimization/data');$('projectNews').replaceChildren(...project.history.entries.map(e=>{const card=element('article',undefined,'night-event');card.append(element('header',e.date+' · '+e.version+' · '+e.status),element('h3',e.title_it),element('p',e.body_it));return card;}));}
$('labModel').onchange=labModelNote;$('labMode').onchange=labModelNote;$('labPolicy').onchange=labModelNote;
$('labForm').onsubmit=async e=>{e.preventDefault();$('labRun').disabled=true;try{await api('/api/notte/lab',{model:$('labModel').value,prompt:$('labPrompt').value,mode:$('labMode').value,policy:$('labPolicy').value,context:Number($('labContext').value),output:Number($('labOutput').value)});notice('Test Lab avviata.');await refresh();}catch(error){notice(error.message,true);$('labRun').disabled=false;}};
$('labStop').onclick=()=>action('stop').catch(e=>notice(e.message,true));

let learningDraftKey='', teachingBusy=false, comparisonKey='', sourceRenderKey='';
const teachingFields=['teachTitle','teachText','teachQuestion','teachAnswer'];
const metricValue=(value,unit='')=>typeof value==='number'&&Number.isFinite(value)?fmt.format(value)+unit:'—';
function initLearningDraft(uid){
 learningDraftKey='notte-lesson-draft-'+uid;
 try{const draft=JSON.parse(sessionStorage.getItem(learningDraftKey)||'{}');for(const id of teachingFields)if(!$(id).value&&typeof draft[id]==='string')$(id).value=draft[id];}catch{}
}
function saveLearningDraft(){if(!learningDraftKey)return;try{sessionStorage.setItem(learningDraftKey,JSON.stringify(Object.fromEntries(teachingFields.map(id=>[id,$(id).value]))));}catch{}}
for(const id of teachingFields)$(id).addEventListener('input',saveLearningDraft);
function renderLearningDashboard(){
 const k=data.knowledge,t=data.training;if(!k||!t)return;
 const latest=t.runs.find(r=>typeof r.metrics?.initial_loss==='number'),m=latest?.metrics,b=t.runs.find(r=>r.metrics?.benchmark)?.metrics?.benchmark;
 $('learnWords').textContent=metricValue(k.words);$('learnIndexed').textContent=metricValue(k.indexed_percent,'%');
 $('learnSuccess').textContent=metricValue(b?.success_percent,'%');$('learnSpeed').textContent=metricValue(b?.tokens_per_second);
 $('learnSourceSummary').textContent='Archivio · '+fmt.format(k.documents)+' documenti · '+fmt.format(k.teaching_pairs)+' coppie per il training';
 $('learnTrain').disabled=t.running||!t.ready;$('learnStopTrain').disabled=!t.running;
 $('sourceImport').disabled=k.running;$('sourceStop').disabled=!k.manual_running;
 const p=k.progress||{};$('sourceProgress').textContent=k.running?`${p.detail||'Lettura…'} · ${p.completed||0}/${p.total||1} · ${p.percent||0}%`:p.detail||'Scegli una fonte da leggere.';
 $('sourceMeter').value=p.percent||0;
 const community=k.community;const counts=community?.sources||[];$('communityStats').textContent='Fonti senza chiavi · '+['stackoverflow','jokes'].map(kind=>{const row=counts.find(x=>x.kind===kind);return `${labels[kind]}: ${metricValue(row?.documents||0)} testi · ${metricValue(row?.words||0)} parole${row?.retry_after>Date.now()/1000?' · in pausa per la quota':''}`;}).join(' · ')+(community?.stackoverflow_quota!==''&&community?.stackoverflow_quota!==undefined?' · Quota Stack Overflow residua: '+community.stackoverflow_quota:'')+(data.config.enabled&&data.config.study_enabled&&data.config.web_enabled?' · Rotazione automatica oraria con i connettori attivi.':' · Rotazione automatica in pausa.');
 const reddit=k.reddit;$('redditStats').textContent=reddit?`Reddit · ${reddit.transport==='oauth_api'?'API OAuth':'RSS pubblico'} · ${metricValue(reddit.documents)} post · ${metricValue(reddit.words)} parole nella memoria consultabile. ${Date.now()/1000<reddit.retry_after?'Nuove letture dalle '+new Date(reddit.retry_after*1000).toLocaleTimeString('it-IT',{hour:'2-digit',minute:'2-digit'})+'.':data.config.enabled&&data.config.reddit_enabled&&data.config.web_enabled&&data.config.connectors.reddit&&reddit.transport==='oauth_api'?'Rotazione oraria fra Python/web e umorismo.':'Lettura automatica in pausa.'}`:'';
 const phases={baseline:'Misuro la versione precedente',loading:'Carico il modello per il training',training:'Addestramento in corso',validation:'Verifico il checkpoint',merging:'Preparo i nuovi pesi',importing:'Pubblico il modello locale',benchmark:'Misuro la nuova versione',complete:'Passi di addestramento completati'};
 const progress=t.progress||{};
 $('learnTrainingState').textContent=t.running?(t.paused?'In pausa: priorità alle risorse e alla chat.':phases[t.phase]||t.phase||'Preparazione…'):t.active_model?'Modello validato · '+t.active_model:t.ready?'Pronto per il primo addestramento.':'Ambiente di addestramento da preparare.';
 const attempt=t.runs[0];if(!t.running&&attempt&&attempt.status!=='ready')$('learnTrainingState').textContent=`Ultimo tentativo #${attempt.id}: ${attempt.detail} · Modello attivo: ${t.active_model||'nessuno'}`;
 if(t.running&&typeof progress.percent==='number'){$('learnTrainingMeter').value=progress.percent;}else if(t.running){$('learnTrainingMeter').removeAttribute('value');}else{$('learnTrainingMeter').value=100;}
 $('learnTrainingMeter').hidden=!t.running;
 $('learnTrainingDetail').textContent=t.running&&progress.total_steps?`${progress.step||0}/${progress.total_steps} passi · ${metricValue(progress.percent,'%')} · loss ${metricValue(progress.loss)}`:m?`${fmt.format(m.samples||latest.samples)} esempi · ${metricValue(m.training_words)} parole nel dataset · ${metricValue(m.seen_training_tokens)} token di risposta usati · ${metricValue(m.steps)} passi`:'Lezioni memorizzate subito; i pesi cambiano dopo addestramento, validazione e test.';
 for(const [id,key] of [['learnUseModel','personal_enabled'],['learnOnline','online_lookup']])if(document.activeElement!==$(id))$(id).checked=Boolean(data.config[key]);
 $('learnUseModel').disabled=!t.active_model;
 const rollback=t.runs.find(r=>String(r.id)===String(data.config.personal_previous_adapter)&&r.status==='ready');$('learnRollback').disabled=!rollback||t.running;
 const comparable=t.runs.filter(r=>r.metrics?.before_benchmark&&typeof r.metrics?.initial_loss==='number');
 const key=comparable.map(r=>r.id+':'+r.status).join('|');
 if($('learnComparison').dataset.options!==key){const selected=$('learnComparison').value;$('learnComparison').replaceChildren(...comparable.map(r=>{const option=element('option','#'+r.id+' · '+r.day+(r.metrics.promoted?' · validata':' · scartata'));option.value=String(r.id);return option;}));if(comparable.some(r=>String(r.id)===selected))$('learnComparison').value=selected;$('learnComparison').dataset.options=key;}
 $('learnComparison').disabled=!comparable.length;
 renderLearningComparison(comparable.find(r=>String(r.id)===$('learnComparison').value));
 const sk=JSON.stringify([k.sources,k.jobs]);if(sk===sourceRenderKey)return;sourceRenderKey=sk;
 $('learnSources').replaceChildren(...k.sources.map(source=>{const card=element('article',undefined,'night-event');card.append(element('h3',source.title),element('p',`${source.kind} · ${fmt.format(source.words)} parole · ${when(source.updated)}`));if(source.url){const link=element('a','Apri la fonte ↗');link.href=source.url;link.target='_blank';link.rel='noopener noreferrer';card.append(link);}card.append(element('p',source.license+(source.revision?' · revisione '+source.revision.slice(0,12):''),'muted'));return card;}));
 $('learnSourceJobs').replaceChildren(...k.jobs.map(job=>{const card=element('article',undefined,'night-event');card.append(element('p',job.status+' · '+job.completed+'/'+job.total+' · '+job.detail));return card;}));
}
function renderLearningComparison(run){
 const key=JSON.stringify(run?.metrics||{});if(key===comparisonKey)return;comparisonKey=key;
 const table=$('learnCompareTable').querySelector('tbody');table.replaceChildren();$('learnHistogram').replaceChildren();
 if(!run){$('learnCompareNote').textContent='Il confronto apparirà dopo la prima nuova valutazione. I vecchi report non contengono tutti questi dati.';return;}
 const m=run.metrics,old=m.before_benchmark,next=m.benchmark||{};
 $('learnCompareNote').textContent=`${m.previous_model} → ${m.candidate_model||run.model||'candidato #'+run.id} · ${m.promoted?'Versione validata e attivata.':'Versione scartata: il checkpoint precedente è conservato.'} Barre con scala propria per ogni misura.`;
 const rows=[['Loss di validazione ↓',m.initial_loss,m.final_loss,''],['Test Python ↑',old.passed/old.total*100,next.passed/next.total*100,'%'],['Controlli italiano/web ↑',old.language_passed/old.language_total*100,next.language_passed/next.language_total*100,'%'],['Velocità di generazione ↑',old.tokens_per_second,next.tokens_per_second,' token/s']];
 for(const [label,a,b,unit] of rows){
  const tr=element('tr');tr.append(element('th',label),element('td',metricValue(a,unit)),element('td',metricValue(b,unit)));tr.firstChild.scope='row';table.append(tr);
  const pair=element('div',undefined,'learn-bar-pair');pair.append(element('h4',label));const max=Math.max(a||0,b||0,.001);
  for(const [name,value,isNew] of [['Precedente',a,false],['Nuova',b,true]]){const row=element('div',undefined,'learn-bar-row'),track=element('div',undefined,'learn-bar-track'),bar=element('span',undefined,'learn-bar'+(isNew?' new':''));bar.style.width=Number.isFinite(value)?Math.max(0,value)/max*100+'%':'0%';track.append(bar);track.setAttribute('aria-hidden','true');row.append(element('span',name),track,element('strong',metricValue(value,unit)));pair.append(row);}
  $('learnHistogram').append(pair);
 }
}
$('learnComparison').onchange=()=>{comparisonKey='';renderLearningDashboard();};
$('teachForm').onsubmit=async e=>{
 e.preventDefault();if(teachingBusy)return;teachingBusy=true;$('teachSave').disabled=true;
 const captured=Object.fromEntries(teachingFields.map(id=>[id,$(id).value]));
 try{const result=await api('/api/notte/knowledge',{title:captured.teachTitle,text:captured.teachText,question:captured.teachQuestion,answer:captured.teachAnswer});
  if(teachingFields.every(id=>$(id).value===captured[id]))for(const id of teachingFields)$(id).value='';saveLearningDraft();
  $('teachResult').textContent=`Lezione ${result.changed?'salvata':'già presente'} · ${fmt.format(result.words)} parole. ${result.training_pair?'Coppia aggiunta al prossimo training.':'Disponibile subito nella memoria.'}`;await refresh();
 }catch(e){$('teachResult').textContent=e.message;notice(e.message,true);}finally{teachingBusy=false;$('teachSave').disabled=false;}
};
function updateSourceOptions(){
 const kind=$('sourceKind').value,wiki=kind==='wikipedia',reddit=kind==='reddit',stack=kind==='stackoverflow',jokes=kind==='jokes',community=stack||jokes;
 $('sourceLanguage').disabled=!wiki;$('sourceLanguage').closest('label').hidden=!wiki;$('sourceCount').disabled=kind==='github';
 $('redditCommunityLabel').hidden=!reddit;$('redditSourceNote').hidden=!reddit;
 $('communityPresetLabel').hidden=!community;$('communitySourceNote').hidden=!community;
 const presets=stack?[['python','Python'],['javascript','JavaScript'],['html','HTML'],['css','CSS'],['flask','Flask'],['django','Django'],['typescript','TypeScript']]:[['Programming','Programmazione'],['Pun','Giochi di parole'],['Misc','Battute varie']];
 $('communityPreset').replaceChildren(...presets.map(([value,title])=>{const option=element('option',title);option.value=value;return option;}));
 $('sourceQueryLabel').textContent=reddit?'Subreddit pubblico':wiki?'Argomento o link Wikipedia':stack?'Tag o ricerca Stack Overflow':jokes?'Categoria delle battute':'Repository pubblico';
 $('sourceQuery').placeholder=reddit?'r/learnpython, r/dadjokes oppure un link Reddit':wiki?'Python, HTML o un link Wikipedia':stack?'python, javascript oppure Python asyncio':jokes?'Programming, Pun oppure Misc':'owner/repo o link GitHub';
 $('sourceQuery').readOnly=jokes;
 $('sourceCountLabel').textContent=reddit?'Post da leggere':stack?'Soluzioni da leggere':jokes?'Battute da leggere':'Articoli per ricerca';
 $('sourceCount').replaceChildren(...(reddit?[1,3,6,12]:community?[1,3,6,10]:[1,2,3]).map(n=>{const option=element('option',n+(reddit?' post':stack?' soluzioni':jokes?' battute':n===1?' articolo':' articoli'));option.value=String(n);return option;}));
 if(reddit){$('sourceCount').value='6';$('sourceQuery').value='r/'+$('redditCommunity').value;}else if(community){$('sourceCount').value='6';$('sourceQuery').value=$('communityPreset').value;}else $('sourceQuery').value='';
}
$('sourceKind').onchange=updateSourceOptions;
$('redditCommunity').onchange=()=>{$('sourceQuery').value='r/'+$('redditCommunity').value;};
$('communityPreset').onchange=()=>{$('sourceQuery').value=$('communityPreset').value;};
$('sourceForm').onsubmit=async e=>{e.preventDefault();$('sourceImport').disabled=true;try{await api('/api/notte/sources',{kind:$('sourceKind').value,query:$('sourceQuery').value.trim(),language:$('sourceLanguage').value,count:Number($('sourceCount').value)});await refresh();}catch(e){notice(e.message,true);$('sourceImport').disabled=false;}};
$('sourceStop').onclick=()=>action('stop_sources').catch(e=>notice(e.message,true));
$('learnTrain').onclick=()=>action('train').catch(e=>notice(e.message,true));
$('learnStopTrain').onclick=()=>action('stop_training').catch(e=>notice(e.message,true));
for(const [id,key] of [['learnUseModel','personal_enabled'],['learnOnline','online_lookup']])$(id).onchange=()=>action('config',{config:{[key]:$(id).checked}}).catch(e=>notice(e.message,true));
$('learnRollback').onclick=()=>action('rollback',{id:Number(data.config.personal_previous_adapter)}).catch(e=>notice(e.message,true));
$('learnVersions').onclick=()=>panel('training');
