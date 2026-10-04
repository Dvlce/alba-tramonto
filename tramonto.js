'use strict';
const $=id=>document.getElementById(id), NS='http://www.w3.org/2000/svg';
const TAGS=['p','div','br','strong','b','em','i','u','s','h1','h2','h3','h4','ul','ol','li','blockquote','pre','code','table','thead','tbody','tr','td','th','sub','sup','hr','img'];
const DEFAULT={schema:1,html:'',font:'serif',paper:'plain',formulas:[],graph:{expressions:['sin(x)','cos(x)'],x_min:-10,x_max:10,y_min:-2,y_max:2},limit:{expression:'sin(x)/x',point:'0',direction:'both'},drawing:{strokes:[]},circuit:{components:[],wires:[]},network:{nodes:[],links:[]},images:[]};
const clone=value=>JSON.parse(JSON.stringify(value));
let csrf='',books=[],bookId=null,notes=[],doc=null,dirty=false,saving=false,uploading=false,opening=false,openSequence=0,revision=0,saveTimer=0,activePane='text';
let drawingHistory=[],circuitHistory=[],stroke=null,erasing=false,circuitMode='select',placing=null,selectedPart=null,selectedWire=null,wireStart=null,drag=null;
function node(tag,text){const element=document.createElement(tag);if(text!==undefined)element.textContent=text;return element;}
function svgNode(tag,attrs={},text){const element=document.createElementNS(NS,tag);for(const [key,value]of Object.entries(attrs))element.setAttribute(key,String(value));if(text!==undefined)element.textContent=text;return element;}
function cleanHtml(value){return DOMPurify.sanitize(value,{ALLOWED_TAGS:TAGS,ALLOWED_ATTR:['src','width','alt','data-layout','align'],ALLOW_DATA_ATTR:false});}
function error(message=''){$('notesError').textContent=message;}
function preference(key,fallback){try{return localStorage.getItem('alba.'+key)||fallback;}catch(_){return fallback;}}
function appearance(){
  const theme=preference('tramontoTheme',preference('theme',matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light')),style=preference('tramontoStyle',preference('surfaceStyle','classic')),palette=preference('tramontoPalette','sage');
  document.documentElement.dataset.theme=['light','dark','gray','black'].includes(theme)?theme:'light';
  document.documentElement.dataset.style=['classic','neo','glass','clay','cyber','brutal','scrap','surreal'].includes(style)?style:'classic';
  document.documentElement.dataset.palette=['sage','graphite','ocean','violet','rose','amber'].includes(palette)?palette:'sage';
  $('notesTheme').value=document.documentElement.dataset.theme;$('notesStyle').value=document.documentElement.dataset.style;$('notesPalette').value=document.documentElement.dataset.palette;
}
appearance();
for(const [id,key]of [['notesTheme','tramontoTheme'],['notesStyle','tramontoStyle'],['notesPalette','tramontoPalette']])$(id).addEventListener('change',()=>{try{localStorage.setItem('alba.'+key,$(id).value);}catch(_){}appearance();window.TramontoLab?.fitPage();});
async function api(path,method='GET',body){
  const response=await fetch(path,{method,credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:body===undefined?undefined:JSON.stringify(body)});
  let data;try{data=await response.json();}catch(_){throw new Error('Il server non è disponibile. Le modifiche restano in questa pagina: esportale prima di chiudere.');}
  if(!response.ok){if(data.code==='auth_expired'){
    if(!dirty&&!uploading)location.assign('/?next=tramonto');
    else data.error='Accesso scaduto. Esporta le modifiche prima di accedere di nuovo: questa pagina non è stata salvata.';
  }const failure=new Error(data.error||'Operazione non riuscita.');failure.code=data.code;throw failure;}return data;
}
function changed(){if(!doc)return;dirty=true;revision++;$('saveStatus').textContent='Modifiche da salvare…';clearTimeout(saveTimer);saveTimer=setTimeout(saveDoc,1200);}
async function saveDoc(){
  if(uploading){error('Attendi che le immagini siano state importate.');return false;}
  if(!doc||!dirty)return true;
  if(saving){await saving;if(dirty)return saveDoc();return true;}
  const current=doc,id=current.id,stamp=revision;current.content.html=cleanHtml($('richEditor').innerHTML);
  const payload={title:$('noteTitle').value.trim()||'Senza titolo',subject:$('noteSubject').value,notebook_id:current.notebook_id,version:current.version,content:clone(current.content)};
  $('saveStatus').textContent='Salvataggio…';
  saving=(async()=>{try{const result=await api('/api/tramonto/notes/'+id,'PUT',payload);if(doc&&doc.id===id){doc.version=result.version;doc.updated=result.updated;doc.title=payload.title;doc.subject=payload.subject;if(revision===stamp)dirty=false;error();$('saveStatus').textContent=dirty?'Modifiche da salvare…':'Salvato · '+new Date().toLocaleTimeString('it-IT',{hour:'2-digit',minute:'2-digit'});const record=notes.find(note=>note.id===id);if(record){Object.assign(record,{title:payload.title,subject:payload.subject,updated:result.updated});renderNotes();}}return true;}
    catch(failure){$('saveStatus').textContent='Non salvato';error(failure.message);return false;}})();
  const result=await saving;saving=false;if(result&&dirty)saveTimer=setTimeout(saveDoc,400);return result;
}
async function loadBooks(){
  books=(await api('/api/tramonto/notebooks')).notebooks;
  if(!books.length){await api('/api/tramonto/notebooks','POST',{title:'Il mio quaderno'});books=(await api('/api/tramonto/notebooks')).notebooks;}
  if(!books.some(book=>book.id===bookId))bookId=books[0].id;
  $('bookList').replaceChildren();
  for(const book of books){const button=node('button',book.title);button.type='button';button.className=book.id===bookId?'active':'';button.appendChild(node('small',String(book.note_count)));button.addEventListener('click',async()=>{if(!await saveDoc())return;bookId=book.id;doc=null;dirty=false;$('noteEditor').hidden=true;$('emptyNote').hidden=false;await loadBooks();await loadNotes();if(notes.length)await openNote(notes[0].id,true);});$('bookList').appendChild(button);}
}
async function loadNotes(){
  notes=(await api('/api/tramonto/notes?notebook='+bookId+'&q='+encodeURIComponent($('noteSearch').value))).notes;
  renderNotes();
}
function renderNotes(){
  $('noteList').replaceChildren();
  for(const record of notes){const button=node('button',record.title);button.type='button';button.className=doc&&record.id===doc.id?'active':'';button.appendChild(node('small','p. '+record.page_number+' · '+record.subject+' · '+new Date(record.updated*1000).toLocaleDateString('it-IT')));button.addEventListener('click',()=>openNote(record.id));$('noteList').appendChild(button);}
  if(!notes.length)$('noteList').appendChild(node('p','Nessuna pagina, per ora.'));
}
async function openNote(id,skipSave=false){
  if(!skipSave&&doc?.id===id)return;
  const sequence=++openSequence;opening=true;$('noteEditor').inert=true;
  try{if(!skipSave&&!await saveDoc())return;const record=await api('/api/tramonto/notes/'+id);if(sequence!==openSequence)return;doc=record;dirty=false;revision=0;drawingHistory=[];circuitHistory=[];selectedPart=selectedWire=wireStart=null;error();
    $('emptyNote').hidden=true;$('noteEditor').hidden=false;$('noteTitle').value=doc.title;$('noteSubject').value=doc.subject;
    $('noteFont').value=doc.content.font;$('notePaper').value=doc.content.paper;$('noteEditor').dataset.font=doc.content.font;$('noteEditor').dataset.paper=doc.content.paper;
    $('sheetTitle').textContent=doc.title;$('richEditor').innerHTML=cleanHtml(doc.content.html);$('saveStatus').textContent='Salvato';
    $('plotExpressions').value=doc.content.graph.expressions.join('\n');
    for(const [id,key]of [['xMin','x_min'],['xMax','x_max'],['yMin','y_min'],['yMax','y_max']])$(id).value=doc.content.graph[key];
    $('limitExpression').value=doc.content.limit.expression;$('limitPoint').value=doc.content.limit.point;$('limitDirection').value=doc.content.limit.direction;
    renderFormulas();renderImages();redrawDrawing();renderCircuit();if(activePane==='math')plot(false);await loadNotes();window.TramontoLab?.openNote();
  }catch(failure){error(failure.message);}finally{if(sequence===openSequence){opening=false;$('noteEditor').inert=false;}}
}
async function newNote(){
  $('newNote').disabled=true;$('noteEditor').inert=true;
  try{if(!await saveDoc())return;const result=await api('/api/tramonto/notes','POST',{notebook_id:bookId,title:'Una nuova idea',subject:'generale',content:clone(DEFAULT)});await loadBooks();await openNote(result.id,true);$('noteTitle').focus();$('noteTitle').select();}catch(failure){error(failure.message);}finally{$('newNote').disabled=false;if(!opening)$('noteEditor').inert=false;}
}
$('newBookForm').addEventListener('submit',async event=>{event.preventDefault();try{if(!await saveDoc())return;const record=await api('/api/tramonto/notebooks','POST',{title:$('newBookName').value.trim()});bookId=record.id;doc=null;dirty=false;$('noteEditor').hidden=true;$('emptyNote').hidden=false;$('newBookName').value='';await loadBooks();await loadNotes();}catch(failure){error(failure.message);}});
$('newNote').addEventListener('click',newNote);
$('renameBook').addEventListener('click',async()=>{const book=books.find(record=>record.id===bookId),title=prompt('Nome del quaderno',book?.title||'');if(!title)return;try{await api('/api/tramonto/notebooks/'+bookId,'PATCH',{title});await loadBooks();}catch(failure){error(failure.message);}});
$('deleteBook').addEventListener('click',async()=>{if(!confirm('Eliminare questo quaderno e tutte le sue pagine e immagini?'))return;try{if(!await saveDoc())return;await api('/api/tramonto/notebooks/'+bookId,'DELETE');if(doc&&doc.notebook_id===bookId){doc=null;dirty=false;$('noteEditor').hidden=true;$('emptyNote').hidden=false;}bookId=null;await loadBooks();await loadNotes();}catch(failure){error(failure.message);}});
$('deleteNote').addEventListener('click',async()=>{if(uploading){error('Attendi il completamento dell’importazione.');return;}if(!doc||!confirm('Eliminare questa pagina e le sue immagini?'))return;try{clearTimeout(saveTimer);if(saving)await saving;await api('/api/tramonto/notes/'+doc.id,'DELETE');doc=null;dirty=false;$('noteEditor').hidden=true;$('emptyNote').hidden=false;await loadBooks();await loadNotes();}catch(failure){error(failure.message);}});
let searchTimer=0;$('noteSearch').addEventListener('input',()=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>loadNotes().catch(failure=>error(failure.message)),250);});
for(const id of ['noteTitle','noteSubject'])$(id).addEventListener('input',()=>{if(id==='noteTitle')$('sheetTitle').textContent=$('noteTitle').value;changed();});
for(const [id,key]of [['noteFont','font'],['notePaper','paper']])$(id).addEventListener('change',()=>{if(!doc)return;doc.content[key]=$(id).value;$('noteEditor').dataset[key]=$(id).value;redrawDrawing();window.TramontoLab?.fitPage();changed();});
$('richEditor').addEventListener('input',changed);
$('richEditor').addEventListener('paste',event=>{if(Array.from(event.clipboardData.files).some(f=>f.type.startsWith('image/')))return;event.preventDefault();const pasted=event.clipboardData.getData('text/html'),plain=event.clipboardData.getData('text/plain');document.execCommand('insertHTML',false,pasted?cleanHtml(pasted):plain.split('\n').map(line=>'<p>'+line.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))+'</p>').join(''));changed();});
document.querySelectorAll('[data-format]').forEach(button=>{button.addEventListener('mousedown',event=>event.preventDefault());button.addEventListener('click',()=>{window.TramontoLab.format(button.dataset.format,button.dataset.value);});});
document.querySelectorAll('[data-pane]').forEach(button=>button.addEventListener('click',()=>{activePane=button.dataset.pane;document.querySelectorAll('[data-pane]').forEach(item=>item.classList.toggle('active',item===button));document.querySelectorAll('.tool-pane').forEach(item=>item.hidden=item.id!=='pane-'+activePane);if(activePane==='math')plot(false);if(activePane==='draw')redrawDrawing();if(activePane==='circuit')renderCircuit();window.TramontoLab?.fitPage();}));
$('saveNote').addEventListener('click',saveDoc);

function latex(target,value){katex.render(value,target,{displayMode:true,throwOnError:false,trust:false,maxExpand:500,maxSize:20});}
$('formulaInput').addEventListener('input',()=>latex($('formulaPreview'),$('formulaInput').value));
document.querySelectorAll('[data-latex]').forEach(button=>button.addEventListener('click',()=>{$('formulaInput').value=button.dataset.latex.replace(/\\\\/g,'\\');latex($('formulaPreview'),$('formulaInput').value);}));
$('addFormula').addEventListener('click',async()=>{if(!doc||!$('formulaInput').value.trim()||uploading)return;const value=$('formulaInput').value.trim();$('addFormula').disabled=true;try{if(await window.TramontoLab.snapshot('formulaPreview')){doc.content.formulas.push(value);$('formulaInput').value='';$('formulaPreview').replaceChildren();renderFormulas();changed();}}finally{$('addFormula').disabled=false;}});
function renderFormulas(){
  $('formulaList').replaceChildren();if(!doc)return;
  doc.content.formulas.forEach((value,index)=>{const card=node('div');card.className='formula-card';const formula=node('div');formula.id='savedFormula'+index;latex(formula,value);card.appendChild(formula);const insert=node('button','Inserisci nel quaderno');insert.type='button';insert.className='secondary-button formula-insert';insert.addEventListener('click',()=>window.TramontoLab.snapshot(formula.id));card.appendChild(insert);const remove=node('button','×');remove.type='button';remove.setAttribute('aria-label','Elimina formula');remove.addEventListener('click',()=>{doc.content.formulas.splice(index,1);renderFormulas();changed();});card.appendChild(remove);$('formulaList').appendChild(card);});
}
const FUNCTIONS=new Set(['sin','cos','tan','asin','acos','atan','sqrt','abs','log','log10','exp','floor','ceil','sign','sinh','cosh','tanh','asinh','acosh','atanh','atan2','cbrt','log2','min','max','pow']);
function expressionFunction(expression){
  if(typeof expression!=='string'||expression.length>250)throw new Error('Funzione troppo lunga.');
  const tree=math.parse(expression);let nodes=0;
  tree.traverse(part=>{if(++nodes>100)throw new Error('Funzione troppo complessa.');
    if(!['OperatorNode','ConstantNode','SymbolNode','FunctionNode','ParenthesisNode'].includes(part.type))throw new Error('Usa solo numeri, x e funzioni matematiche.');
    if(part.type==='ConstantNode'&&(typeof part.value!=='number'||!Number.isFinite(part.value)||Math.abs(part.value)>1e12))throw new Error('Costante non valida.');
    if(part.type==='SymbolNode'&&!['x','pi','e'].includes(part.name)&&!FUNCTIONS.has(part.name))throw new Error('Simbolo non ammesso: '+part.name);
    if(part.type==='FunctionNode'&&(part.fn.type!=='SymbolNode'||!FUNCTIONS.has(part.fn.name)||part.args.length>2))throw new Error('Funzione non ammessa.');
    if(part.type==='OperatorNode'&&!['+','-','*','/','^','%'].includes(part.op))throw new Error('Operatore non ammesso.');
  });
  const compiled=tree.compile();return x=>{try{const value=compiled.evaluate({x,pi:Math.PI,e:Math.E});return typeof value==='number'&&Number.isFinite(value)?value:NaN;}catch(_){return NaN;}};
}
function graphSettings(){
  const expressions=$('plotExpressions').value.split('\n').map(value=>value.trim()).filter(Boolean);
  const value={expressions};for(const [id,key]of [['xMin','x_min'],['xMax','x_max'],['yMin','y_min'],['yMax','y_max']])value[key]=Number($(id).value);
  if(!expressions.length||expressions.length>3||Object.values(value).slice(1).some(number=>!Number.isFinite(number)||Math.abs(number)>10000)||value.x_min>=value.x_max||value.y_min>=value.y_max)throw new Error('Inserisci fino a tre funzioni e intervalli crescenti tra −10000 e 10000.');
  return value;
}
function plot(save=true){
  if(!doc)return;
  try{const settings=graphSettings(),functions=settings.expressions.map(expressionFunction),svg=$('plotSvg');svg.replaceChildren();
    const width=800,height=430,left=55,right=20,top=25,bottom=45,pw=width-left-right,ph=height-top-bottom;
    const px=x=>left+(x-settings.x_min)/(settings.x_max-settings.x_min)*pw,py=y=>height-bottom-(y-settings.y_min)/(settings.y_max-settings.y_min)*ph;
    svg.appendChild(svgNode('rect',{width,height,fill:'#fffdf7',rx:12}));
    const defs=svgNode('defs'),clip=svgNode('clipPath',{id:'plotClip'});clip.appendChild(svgNode('rect',{x:left,y:top,width:pw,height:ph}));defs.appendChild(clip);svg.appendChild(defs);
    for(let n=0;n<=8;n++){const x=settings.x_min+(settings.x_max-settings.x_min)*n/8,y=settings.y_min+(settings.y_max-settings.y_min)*n/8;
      svg.appendChild(svgNode('path',{d:'M'+px(x)+' '+top+'V'+(height-bottom)+' M'+left+' '+py(y)+'H'+(width-right),stroke:'#dedfd4',fill:'none','stroke-width':.6}));
      svg.appendChild(svgNode('text',{x:px(x),y:height-18,'text-anchor':'middle',fill:'#6b7567','font-size':10,'font-family':'sans-serif'},Number(x.toPrecision(3))));
      svg.appendChild(svgNode('text',{x:left-10,y:py(y)+4,'text-anchor':'end',fill:'#6b7567','font-size':10,'font-family':'sans-serif'},Number(y.toPrecision(3))));
    }
    if(settings.x_min<=0&&settings.x_max>=0)svg.appendChild(svgNode('path',{d:'M'+px(0)+' '+top+'V'+(height-bottom),stroke:'#87927f','stroke-width':1}));
    if(settings.y_min<=0&&settings.y_max>=0)svg.appendChild(svgNode('path',{d:'M'+left+' '+py(0)+'H'+(width-right),stroke:'#87927f','stroke-width':1}));
    const colors=['#47846b','#d68b59','#7c70aa'];
    functions.forEach((fn,index)=>{let path='',previous=null;
      for(let step=0;step<=600;step++){const x=settings.x_min+(settings.x_max-settings.x_min)*step/600,y=fn(x),current=py(y);if(!Number.isFinite(y)||Math.abs(current)>1e6){previous=null;continue;}const join=previous!==null&&Math.abs(current-previous)<ph*.7;path+=(join?' L':' M')+px(x).toFixed(2)+' '+current.toFixed(2);previous=current;}
      svg.appendChild(svgNode('path',{d:path,stroke:colors[index],fill:'none','stroke-width':2.2,'clip-path':'url(#plotClip)','data-curve':index}));
      svg.appendChild(svgNode('text',{x:left+index*240,y:15,fill:colors[index],'font-size':11,'font-family':'sans-serif'},settings.expressions[index]));
    });
    $('graphMessage').textContent='Trigonometriche in radianti · i tratti interrotti indicano campioni non finiti o possibili discontinuità.';
    if(save){doc.content.graph=settings;changed();}return true;
  }catch(failure){$('graphMessage').textContent=failure.message;return false;}
}
$('plotGraph').addEventListener('click',()=>plot(true));
function estimateLimit(){
  if(!doc)return;
  try{const expression=$('limitExpression').value,pointText=$('limitPoint').value.trim(),direction=$('limitDirection').value,fn=expressionFunction(expression);
    const infinity=/^[+−-]?(?:inf|infinity|∞)$/i.test(pointText),point=infinity?(pointText.startsWith('-')||pointText.startsWith('−')?-Infinity:Infinity):Number(pointText);
    if(!pointText||(!infinity&&(!Number.isFinite(point)||Math.abs(point)>1e8)))throw new Error('Indica un punto numerico oppure +inf o -inf.');
    const rows=[],scale=infinity?1:Math.max(1,Math.abs(point));
    for(let k=1;k<=6;k++){const offsets=infinity?[Math.sign(point)*10**k]:direction==='both'?[-scale*10**(-k),scale*10**(-k)]:[(direction==='left'?-1:1)*scale*10**(-k)];for(const offset of offsets){const x=infinity?offset:point+offset;rows.push({x,y:fn(x),side:infinity?'∞':offset<0?'sinistra':'destra'});}}
    const target=$('limitResult');target.replaceChildren();const table=node('table');table.className='limit-table';const header=node('tr');for(const title of ['x','f(x)','Direzione'])header.appendChild(node('th',title));table.appendChild(header);
    const format=value=>Number.isFinite(value)?Number(value.toPrecision(8)).toString():'non finito';
    for(const row of rows){const tr=node('tr');for(const value of [format(row.x),format(row.y),row.side])tr.appendChild(node('td',value));table.appendChild(tr);}target.appendChild(table);
    const tail=rows.slice(-Math.min(4,rows.length)),finite=tail.every(row=>Number.isFinite(row.y)),spread=finite?Math.max(...tail.map(row=>row.y))-Math.min(...tail.map(row=>row.y)):Infinity,mean=finite?tail.reduce((sum,row)=>sum+row.y,0)/tail.length:NaN;
    target.prepend(node('p',finite&&spread<1e-4*Math.max(1,Math.abs(mean))?'Stima dai campioni: '+format(mean)+'.':'I campioni non suggeriscono ancora un valore finito stabile.'));
    doc.content.limit={expression,point:pointText,direction};changed();
  }catch(failure){$('limitResult').textContent=failure.message;}
}
$('estimateLimit').addEventListener('click',estimateLimit);
function download(blob,name){const url=URL.createObjectURL(blob),link=node('a');link.href=url;link.download=name;document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);}
function exportSvg(id,name){const svg=$(id).cloneNode(true);svg.setAttribute('xmlns',NS);download(new Blob([new XMLSerializer().serializeToString(svg)],{type:'image/svg+xml'}),name);}
$('exportGraph').addEventListener('click',()=>{plot(false);exportSvg('plotSvg','grafico.svg');});

const canvas=$('drawingCanvas'),ctx=canvas.getContext('2d');
function redrawDrawing(){
  ctx.fillStyle='#fffcf3';ctx.fillRect(0,0,1000,640);if(!doc)return;
  const paper=doc.content.paper;ctx.strokeStyle='#e5e7da';ctx.fillStyle='#d6dcca';ctx.lineWidth=.7;
  if(paper==='ruled'||paper==='grid'){ctx.beginPath();for(let y=24;y<640;y+=24){ctx.moveTo(0,y);ctx.lineTo(1000,y);}if(paper==='grid')for(let x=24;x<1000;x+=24){ctx.moveTo(x,0);ctx.lineTo(x,640);}ctx.stroke();}
  if(paper==='dots')for(let x=20;x<1000;x+=20)for(let y=20;y<640;y+=20){ctx.beginPath();ctx.arc(x,y,.8,0,Math.PI*2);ctx.fill();}
  for(const line of doc.content.drawing.strokes){ctx.strokeStyle=line.color;ctx.fillStyle=line.color;ctx.lineWidth=line.size;ctx.lineCap='round';ctx.lineJoin='round';ctx.beginPath();line.points.forEach((point,index)=>index?ctx.lineTo(...point):ctx.moveTo(...point));if(line.points.length===1){ctx.arc(...line.points[0],line.size/2,0,Math.PI*2);ctx.fill();}else ctx.stroke();}
}
function canvasPoint(event){const box=canvas.getBoundingClientRect();return [Math.max(0,Math.min(1000,Math.round((event.clientX-box.left)*1000/box.width*10)/10)),Math.max(0,Math.min(640,Math.round((event.clientY-box.top)*640/box.height*10)/10))];}
canvas.addEventListener('pointerdown',event=>{if(!doc)return;event.preventDefault();canvas.setPointerCapture(event.pointerId);drawingHistory.push(doc.content.drawing.strokes.slice());drawingHistory=drawingHistory.slice(-20);if(!erasing){stroke={color:$('penColor').value,size:Number($('penSize').value),points:[canvasPoint(event)]};doc.content.drawing.strokes.push(stroke);}else stroke={erase:true};redrawDrawing();});
canvas.addEventListener('pointermove',event=>{if(!stroke||!doc)return;const point=canvasPoint(event);if(stroke.erase){doc.content.drawing.strokes=doc.content.drawing.strokes.filter(line=>!line.points.some(p=>Math.hypot(p[0]-point[0],p[1]-point[1])<12));}
  else{const last=stroke.points.at(-1);if(Math.hypot(last[0]-point[0],last[1]-point[1])<1.6)return;if(stroke.points.length<5000)stroke.points.push(point);}redrawDrawing();});
function endStroke(){if(!stroke)return;stroke=null;changed();}
canvas.addEventListener('pointerup',endStroke);canvas.addEventListener('pointercancel',endStroke);
$('eraser').addEventListener('click',()=>{erasing=!erasing;$('eraser').setAttribute('aria-pressed',String(erasing));});
$('undoDrawing').addEventListener('click',()=>{if(doc&&drawingHistory.length){doc.content.drawing.strokes=drawingHistory.pop();redrawDrawing();changed();}});
$('clearDrawing').addEventListener('click',()=>{if(doc&&confirm('Pulire il disegno? Puoi annullare subito dopo.')){drawingHistory.push(doc.content.drawing.strokes.slice());doc.content.drawing.strokes=[];redrawDrawing();changed();}});
$('exportDrawing').addEventListener('click',()=>{redrawDrawing();canvas.toBlob(blob=>download(blob,'disegno.png'));});

const PARTS={resistor:{name:'Resistenza',prefix:'R',value:'1 kΩ',ports:[[-28,0],[28,0]],path:'M-28 0h8l4-9 7 18 7-18 7 18 7-18 4 9h12'},
 capacitor:{name:'Condensatore',prefix:'C',value:'1 µF',ports:[[-28,0],[28,0]],path:'M-28 0h22m0-16v32M6-16v32M6 0h22'},
 inductor:{name:'Induttore',prefix:'L',value:'1 mH',ports:[[-28,0],[28,0]],path:'M-28 0h4c0-20 12-20 12 0c0-20 12-20 12 0c0-20 12-20 12 0h16'},
 diode:{name:'Diodo',prefix:'D',value:'',ports:[[-28,0],[28,0]],path:'M-28 0h15m0-13v26l22-13-22-13M9-14v28M9 0h19'},
 voltage:{name:'Generatore DC',prefix:'V',value:'5 V',ports:[[-28,0],[28,0]],path:'M-28 0h10M18 0h10M-6-6v12M-12 0H0M7 0h6',circle:true},
 ac:{name:'Generatore AC',prefix:'V',value:'1 kHz',ports:[[-28,0],[28,0]],path:'M-28 0h10M18 0h10M-12 0c4-13 8-13 12 0s8 13 12 0',circle:true},
 ground:{name:'Massa',prefix:'GND',value:'',ports:[[0,-25]],path:'M0-25v20M-20-5h40M-13 3h26M-6 11H6'},
 switch:{name:'Interruttore',prefix:'S',value:'aperto',ports:[[-28,0],[28,0]],path:'M-28 0h10m0 0 26-15M10 0h18'},
 npn:{name:'Transistor NPN',prefix:'Q',value:'NPN',ports:[[-28,0],[20,-25],[20,25]],path:'M-28 0h18M-10-18v36M-10-7 20-25M-10 7 20 25M15 15l5 10-11-2'},
 opamp:{name:'Operazionale',prefix:'U',value:'OPAMP',ports:[[-30,-12],[-30,12],[30,0],[0,-32],[0,32]],path:'M-30-12h12M-30 12h12M-18-26v52L22 0-18-26M22 0h8M0-15v-17M0 15v17M-13-12h7M-13 12h7M-10 9v6'}};
function historyCircuit(){circuitHistory.push(clone(doc.content.circuit));circuitHistory=circuitHistory.slice(-20);}
function portPosition(part,index){const [x,y]=PARTS[part.type].ports[index],angle=part.rotation*Math.PI/180;return{x:part.x+x*Math.cos(angle)-y*Math.sin(angle),y:part.y+x*Math.sin(angle)+y*Math.cos(angle)};}
function circuitPoint(event){const svg=$('circuitSvg'),point=svg.createSVGPoint();point.x=event.clientX;point.y=event.clientY;const pos=point.matrixTransform(svg.getScreenCTM().inverse());return{x:Math.max(40,Math.min(960,Math.round(pos.x/10)*10)),y:Math.max(40,Math.min(600,Math.round(pos.y/10)*10))};}
function renderCircuit(){
  const svg=$('circuitSvg');svg.replaceChildren();if(!doc)return;
  const defs=svgNode('defs'),pattern=svgNode('pattern',{id:'circuitGrid',width:20,height:20,patternUnits:'userSpaceOnUse'});pattern.appendChild(svgNode('circle',{cx:10,cy:10,r:1,fill:'#dddccb'}));defs.appendChild(pattern);svg.appendChild(defs);svg.appendChild(svgNode('rect',{width:1000,height:640,fill:'#fffcf3'}));svg.appendChild(svgNode('rect',{width:1000,height:640,fill:'url(#circuitGrid)'}));
  for(const wire of doc.content.circuit.wires){const a=doc.content.circuit.components.find(part=>part.id===wire.from.component),b=doc.content.circuit.components.find(part=>part.id===wire.to.component);if(!a||!b)continue;const start=portPosition(a,wire.from.port),end=portPosition(b,wire.to.port),middle=Math.round((start.x+end.x)/40)*20;
    const path=svgNode('path',{d:'M'+start.x+' '+start.y+'H'+middle+'V'+end.y+'H'+end.x,fill:'none',stroke:wire.id===selectedWire?'#d38651':'#789476','stroke-width':wire.id===selectedWire?4:2.5,'data-wire':wire.id});
    const hit=path.cloneNode();hit.setAttribute('stroke','transparent');hit.setAttribute('stroke-width',14);svg.appendChild(path);svg.appendChild(hit);}
  for(const part of doc.content.circuit.components){const spec=PARTS[part.type],group=svgNode('g',{transform:'translate('+part.x+' '+part.y+') rotate('+part.rotation+')','data-component-id':part.id,class:'circuit-part'});
    group.appendChild(svgNode('rect',{x:-34,y:-35,width:68,height:70,rx:8,fill:part.id===selectedPart?'#f8d9aa55':'transparent',stroke:part.id===selectedPart?'#d6a46a':'none'}));
    if(spec.circle)group.appendChild(svgNode('circle',{r:18,fill:'none',stroke:'#344b3e','stroke-width':2}));
    group.appendChild(svgNode('path',{d:spec.path,fill:'none',stroke:'#344b3e','stroke-width':2,'stroke-linecap':'round','stroke-linejoin':'round'}));
    spec.ports.forEach((point,index)=>group.appendChild(svgNode('circle',{cx:point[0],cy:point[1],r:4.5,fill:wireStart&&wireStart.component===part.id&&wireStart.port===index?'#d38651':'#fffcf3',stroke:'#789476','stroke-width':1.5,'data-port':index,'data-owner':part.id,class:'circuit-terminal'})));
    svg.appendChild(group);svg.appendChild(svgNode('text',{x:part.x,y:part.y+48,'text-anchor':'middle',fill:'#44543e','font-family':'sans-serif','font-size':12},part.label+(part.value?' · '+part.value:'')));
  }
  const part=doc.content.circuit.components.find(value=>value.id===selectedPart);$('componentForm').hidden=!part;if(part){$('componentLabel').value=part.label;$('componentValue').value=part.value;}window.TramontoLab?.component(part);window.TramontoLab?.circuitSelection?.render();
}
document.querySelector('.component-palette').addEventListener('click',event=>{const button=event.target.closest('[data-component]');if(!button)return;placing=button.dataset.component;circuitMode='place';wireStart=null;document.querySelectorAll('[data-component]').forEach(item=>item.classList.toggle('active',item===button));$('circuitMessage').textContent='Tocca il foglio per aggiungere: '+PARTS[placing].name+'.';});
$('selectCircuit').addEventListener('click',()=>{circuitMode='select';placing=null;wireStart=null;$('circuitMessage').textContent='Trascina un componente per spostarlo. Tocca un filo per selezionarlo.';});
$('wireCircuit').addEventListener('click',()=>{circuitMode='wire';placing=null;wireStart=null;$('circuitMessage').textContent='Tocca il terminale di partenza, poi quello di arrivo.';});
$('circuitSvg').addEventListener('pointerdown',event=>{
  if(!doc)return;event.preventDefault();const terminal=event.target.closest('[data-port]'),partNode=event.target.closest('[data-component-id]'),wire=event.target.closest('[data-wire]');
  if(circuitMode==='wire'&&terminal){const end={component:terminal.dataset.owner,port:Number(terminal.dataset.port)};if(!wireStart){wireStart=end;$('circuitMessage').textContent='Ora scegli il terminale di arrivo.';}else if(JSON.stringify(wireStart)!==JSON.stringify(end)){historyCircuit();doc.content.circuit.wires.push({id:crypto.randomUUID(),from:wireStart,to:end});wireStart=null;changed();$('circuitMessage').textContent='Collegamento creato. Puoi continuare con altri terminali.';}renderCircuit();return;}
  if(circuitMode==='place'&&!partNode&&!wire){historyCircuit();const position=circuitPoint(event),spec=PARTS[placing],count=doc.content.circuit.components.filter(part=>PARTS[part.type].prefix===spec.prefix).length+1;doc.content.circuit.components.push({id:crypto.randomUUID(),type:placing,...position,rotation:0,label:spec.prefix+count,value:spec.value});selectedPart=doc.content.circuit.components.at(-1).id;selectedWire=null;renderCircuit();changed();return;}
  if(wire){selectedWire=wire.dataset.wire;selectedPart=null;renderCircuit();return;}
  if(partNode){selectedPart=partNode.dataset.componentId;selectedWire=null;const part=doc.content.circuit.components.find(value=>value.id===selectedPart);historyCircuit();const point=circuitPoint(event);drag={id:part.id,dx:part.x-point.x,dy:part.y-point.y,moved:false};$('circuitSvg').setPointerCapture(event.pointerId);}else{selectedPart=selectedWire=null;}renderCircuit();
});
$('circuitSvg').addEventListener('pointermove',event=>{if(!drag||!doc)return;const part=doc.content.circuit.components.find(value=>value.id===drag.id),point=circuitPoint(event);part.x=Math.max(40,Math.min(960,point.x+drag.dx));part.y=Math.max(40,Math.min(600,point.y+drag.dy));drag.moved=true;renderCircuit();});
function endDrag(){if(drag?.moved)changed();drag=null;}
$('circuitSvg').addEventListener('pointerup',endDrag);$('circuitSvg').addEventListener('pointercancel',endDrag);
$('rotateCircuit').addEventListener('click',()=>{if(window.TramontoLab?.circuitSelection?.rotate())return;const part=doc?.content.circuit.components.find(value=>value.id===selectedPart);if(part){historyCircuit();part.rotation=(part.rotation+90)%360;renderCircuit();changed();}});
function deletePart(){if(window.TramontoLab?.circuitSelection?.remove())return;if(!doc||(!selectedPart&&!selectedWire))return;historyCircuit();if(selectedPart){doc.content.circuit.components=doc.content.circuit.components.filter(value=>value.id!==selectedPart);doc.content.circuit.wires=doc.content.circuit.wires.filter(value=>value.from.component!==selectedPart&&value.to.component!==selectedPart);}else doc.content.circuit.wires=doc.content.circuit.wires.filter(value=>value.id!==selectedWire);selectedPart=selectedWire=null;renderCircuit();changed();}
$('deleteCircuitPart').addEventListener('click',deletePart);$('circuitSvg').addEventListener('keydown',event=>{if(['Delete','Backspace'].includes(event.key)){event.preventDefault();deletePart();}});
$('undoCircuit').addEventListener('click',()=>{if(doc&&circuitHistory.length){doc.content.circuit=circuitHistory.pop();selectedPart=selectedWire=null;renderCircuit();changed();}});
$('componentForm').addEventListener('submit',event=>{event.preventDefault();const part=doc?.content.circuit.components.find(value=>value.id===selectedPart);if(part){historyCircuit();part.label=$('componentLabel').value;part.value=$('componentValue').value;window.TramontoLab?.updateComponent(part);renderCircuit();changed();}});
$('exportCircuit').addEventListener('click',()=>exportSvg('circuitSvg','schema.svg'));

function renderImages(){
  $('imageList').replaceChildren();if(!doc)return;
  for(const id of doc.content.images){const card=node('figure');card.className='image-card';const image=node('img');image.src='/api/tramonto/images/'+id;image.alt='Immagine del tuo appunto';image.loading='lazy';card.appendChild(image);const caption=node('figcaption','Immagine '+id),remove=node('button','Elimina');remove.type='button';remove.className='secondary-button danger-button';remove.addEventListener('click',async()=>{try{if(!await saveDoc()||!confirm('Eliminare questa immagine?'))return;await api('/api/tramonto/images/'+id,'DELETE');await openNote(doc.id,true);}catch(failure){error(failure.message);}});const insert=node('button','Inserisci nel testo');insert.type='button';insert.className='secondary-button';insert.addEventListener('click',()=>window.TramontoLab?.insertExisting(id));caption.append(insert,remove);card.appendChild(caption);$('imageList').appendChild(card);}
}
$('imageInput').addEventListener('change',async event=>{
  if(!doc||uploading)return;const current=doc;uploading=true;error();try{for(const file of event.target.files){if(current.content.images.length>=30)throw new Error('Massimo trenta immagini per pagina.');if(file.size>8*1024*1024)throw new Error('L’immagine supera 8 MB. Ridimensionala prima di importarla.');
    const response=await fetch('/api/tramonto/notes/'+doc.id+'/images',{method:'POST',credentials:'same-origin',headers:{'X-CSRF-Token':csrf,'Content-Type':file.type,'X-Image-Name':encodeURIComponent(file.name.slice(0,180))},body:file});
    const result=await response.json();if(!response.ok)throw new Error(result.error||'Immagine non valida.');current.content.images.push(result.id);changed();}renderImages();}catch(failure){error(failure.message);}finally{uploading=false;event.target.value='';if(current===doc){renderImages();await saveDoc();}}
});
$('exportNote').addEventListener('click',async()=>{if(!doc)return;try{doc.content.html=cleanHtml($('richEditor').innerHTML);const value={format:'tramonto-note-v1',title:$('noteTitle').value,subject:$('noteSubject').value,content:clone(doc.content),images:[]};
  for(const id of doc.content.images){const response=await fetch('/api/tramonto/images/'+id,{credentials:'same-origin'});if(!response.ok)throw new Error('Immagine non disponibile.');const blob=await response.blob(),data=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=reject;reader.readAsDataURL(blob);});value.images.push({id,data});}
  const name=($('noteTitle').value||'appunto').replace(/[^\p{L}\p{N} _-]/gu,'').slice(0,80);download(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}),name+'.json');
}catch(failure){error(failure.message);}});
$('printNote').addEventListener('click',async()=>{if(!doc)return;const images=Array.from($('richEditor').querySelectorAll('img'));await Promise.all(images.map(image=>image.decode().catch(()=>{})));window.print();});
window.addEventListener('beforeunload',event=>{if(dirty||uploading){event.preventDefault();event.returnValue='';}});
document.addEventListener('alba-before-space-change',event=>{
  event.detail.waitUntil((async()=>{
    if(uploading){error('Attendi il completamento dell’importazione prima di cambiare spazio.');return false;}
    clearTimeout(saveTimer);return await saveDoc();
  })());
});
window.addEventListener('online',()=>{if(doc&&dirty&&!saving&&!opening&&!uploading)saveDoc();});
window.addEventListener('focus',async()=>{if(doc&&!dirty&&!saving&&!opening&&!uploading)try{const id=doc.id,updated=await api('/api/tramonto/notes/'+id);if(doc?.id===id&&!dirty&&!saving&&!opening&&!uploading&&updated.version!==doc.version)await openNote(id,true);}catch(failure){error(failure.message);}});
window.TramontoTools={expressionFunction,estimateLimit,plot,saveDoc,redrawDrawing,renderCircuit};
window.tramontoOpenPage=openNote;
(async()=>{try{const me=await api('/api/me');if(!me.is_admin){location.replace('/');return;}csrf=me.csrf;$('notesIdentity').textContent=me.name||'Amministratore';const workspace=(await api('/api/tramonto/workspace'));bookId=workspace.notebook_id||null;await loadBooks();await loadNotes();if(notes.length)await openNote(notes.some(n=>n.id===workspace.note_id)?workspace.note_id:notes[0].id,true);if(workspace.note_id===doc?.id)window.TramontoLab?.restorePosition(workspace.scroll_y);}catch(failure){error(failure.message);}})();
