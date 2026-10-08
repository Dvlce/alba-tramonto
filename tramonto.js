'use strict';
const $=id=>document.getElementById(id), NS='http://www.w3.org/2000/svg';
const TAGS=['p','div','br','strong','b','em','i','u','s','h1','h2','h3','h4','ul','ol','li','blockquote','pre','code','table','thead','tbody','tr','td','th','sub','sup','hr','img'];
const DEFAULT={schema:1,html:'',font:'serif',paper:'plain',formulas:[],graph:{expressions:['sin(x)','cos(x)'],x_min:-10,x_max:10,y_min:-2,y_max:2},limit:{expression:'sin(x)/x',point:'0',direction:'both'},drawing:{strokes:[]},circuit:{components:[],wires:[]},network:{nodes:[],links:[]},images:[]};
const clone=value=>JSON.parse(JSON.stringify(value));
let csrf='',books=[],bookId=null,notes=[],doc=null,dirty=false,saving=false,uploading=false,opening=false,openSequence=0,revision=0,saveTimer=0,activePane='text';
let drawingHistory=[],circuitHistory=[],stroke=null,erasing=false,circuitMode='select',placing=null,selectedPart=null,selectedWire=null,wireStart=null,drag=null;
function node(tag,text){const element=document.createElement(tag);if(text!==undefined)element.textContent=text;return element;}
function svgNode(tag,attrs={},text){const element=document.createElementNS(NS,tag);for(const [key,value]of Object.entries(attrs))element.setAttribute(key,String(value));if(text!==undefined)element.textContent=text;return element;}
function cleanHtml(value){return DOMPurify.sanitize(value.replace(/\u200b/g,''),{ALLOWED_TAGS:TAGS,ALLOWED_ATTR:['src','width','alt','data-layout','data-latex','align'],ALLOW_DATA_ATTR:false});}
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
  try{if(!skipSave&&!await saveDoc())return;const record=await api('/api/tramonto/notes/'+id);if(sequence!==openSequence)return;doc=record;wirePoints=[];wireCursor=null;wireAxis=null;circuitMode='select';placing=null;stroke=null;dirty=false;revision=0;drawingHistory=[];circuitHistory=[];selectedPart=selectedWire=wireStart=null;error();
    $('emptyNote').hidden=true;$('noteEditor').hidden=false;$('noteTitle').value=doc.title;$('noteSubject').value=doc.subject;
    $('noteFont').value=doc.content.font;$('notePaper').value=doc.content.paper;$('noteEditor').dataset.font=doc.content.font;$('noteEditor').dataset.paper=doc.content.paper;
    $('sheetTitle').textContent=doc.title;$('richEditor').innerHTML=cleanHtml(doc.content.html);$('saveStatus').textContent='Salvato';
    $('plotExpressions').value=doc.content.graph.expressions.join('\n');
    for(const [id,key]of [['xMin','x_min'],['xMax','x_max'],['yMin','y_min'],['yMax','y_max']])$(id).value=doc.content.graph[key];
    $('limitExpression').value=doc.content.limit.expression;$('limitPoint').value=doc.content.limit.point;$('limitDirection').value=doc.content.limit.direction;
    resetFormula();renderFormulas();renderImages();redrawDrawing();renderCircuit();if(activePane==='math')plot(false);window.TramontoFont?.load();await loadNotes();window.TramontoLab?.openNote();
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
// Formula source is kept alongside each notebook image, so the visual editor can reopen it.
MathfieldElement.fontsDirectory='/tramonto-assets/vendor/mathlive/fonts';
MathfieldElement.soundsDirectory=null;
let formulaEditing=null;
const visualFormula=new MathfieldElement();visualFormula.id='formulaVisual';visualFormula.mathVirtualKeyboardPolicy='manual';visualFormula.setAttribute('aria-label','Modifica visiva della formula');
$('formulaInput').before(node('label','Modifica direttamente l’equazione'),visualFormula);
const formulaHint=node('p','Clicca dentro la formula per modificare numeri, frazioni, esponenti e righe di un sistema. Puoi usare anche il codice LaTeX qui sotto.');formulaHint.className='tool-note';visualFormula.after(formulaHint);
const formulaStatus=node('p');formulaStatus.id='formulaEditStatus';formulaStatus.className='tool-message';formulaStatus.setAttribute('role','status');$('addFormula').before(formulaStatus);
const cancelFormula=node('button','Nuova formula');cancelFormula.id='cancelFormulaEdit';cancelFormula.type='button';cancelFormula.className='secondary-button';cancelFormula.hidden=true;$('addFormula').after(cancelFormula);
function setFormula(value){$('formulaInput').value=value;visualFormula.setValue(value,{silenceNotifications:true});latex($('formulaPreview'),value);}
function resetFormula(){formulaEditing=null;setFormula('');formulaStatus.textContent='';$('addFormula').textContent='Inserisci formula nel quaderno';cancelFormula.hidden=true;}
function editFormula(value,target){formulaEditing={...target,note:doc.id};setFormula(value);formulaStatus.textContent='Formula in modifica · salva per applicare i cambiamenti.';$('addFormula').textContent='Aggiorna formula';cancelFormula.hidden=false;document.querySelector('[data-pane=math]').click();visualFormula.focus();}
cancelFormula.addEventListener('click',resetFormula);
$('formulaInput').addEventListener('input',()=>{visualFormula.setValue($('formulaInput').value,{silenceNotifications:true});latex($('formulaPreview'),$('formulaInput').value);});
visualFormula.addEventListener('click',()=>visualFormula.focus());
visualFormula.addEventListener('input',()=>{const value=visualFormula.value;if(value.length>4000){formulaStatus.textContent='Massimo 4000 caratteri per formula.';return;}$('formulaInput').value=value;latex($('formulaPreview'),value);});
document.querySelectorAll('[data-latex]').forEach(button=>button.addEventListener('click',()=>{visualFormula.insert(button.dataset.latex.replace(/\\\\/g,'\\'));visualFormula.dispatchEvent(new Event('input'));visualFormula.focus();}));
const bracketTools=node('div');bracketTools.className='tool-actions bracket-tools';
const bracketType=node('select');bracketType.id='formulaBracketType';for(const [value,label]of [['system','{ Sistema'],['round','( ) Tonde'],['square','[ ] Quadre'],['brace','{ } Graffe']]){const option=node('option',label);option.value=value;bracketType.append(option);}
function bracketNumber(id,label,value,min,max){const field=node('input');field.id=id;field.type='number';field.min=min;field.max=max;field.step='0.5';field.value=value;const wrap=node('label',label);wrap.append(field);bracketTools.append(wrap);return field;}
const typeLabel=node('label','Parentesi');typeLabel.append(bracketType);bracketTools.append(typeLabel);
const bracketHeight=bracketNumber('formulaBracketHeight','Altezza (em)',4,1,20),bracketWidth=bracketNumber('formulaBracketWidth','Spazio interno (em)',0,0,20);
const bracketButton=node('button','Inserisci / ridimensiona parentesi');bracketButton.id='formulaBracketApply';bracketButton.type='button';bracketButton.className='secondary-button';bracketTools.append(bracketButton);visualFormula.before(bracketTools);
const systemRow=node('button','+ Riga al sistema');systemRow.id='formulaSystemRow';systemRow.type='button';systemRow.className='secondary-button';systemRow.addEventListener('click',()=>{visualFormula.focus();if(!visualFormula.executeCommand('addRowAfter'))formulaStatus.textContent='Clicca dentro una riga del sistema per aggiungerne una.';visualFormula.dispatchEvent(new Event('input'));});bracketTools.append(systemRow);
bracketButton.addEventListener('click',()=>{const h=Math.max(1,Math.min(20,Number(bracketHeight.value)||4)),w=Math.max(0,Math.min(20,Number(bracketWidth.value)||0));let value=$('formulaInput').value;const size=/\\vphantom\{\\rule\{0pt\}\{[\d.]+em\}\}/,space=/\\hspace\{[\d.]+em\}/;
if(/\\begin\{cases\}/.test(value)){value=value.replace('\\begin{cases}','\\left\\{\\vphantom{\\rule{0pt}{'+h+'em}}\\begin{array}{l}').replace('\\end{cases}','\\end{array}\\hspace{'+w+'em}\\right.');setFormula(value);}else if(!size.test(value)&&/^\\left(?:\\[{}]|[([])/.test(value)&&/\\right(?:\\[{}]|[)\].])$/.test(value)){value=value.replace(/^(\\left(?:\\[{}]|[([]))/,(_,left)=>left+'\\vphantom{\\rule{0pt}{'+h+'em}}').replace(/(\\right(?:\\[{}]|[)\].]))$/,'\\hspace{'+w+'em}$1');setFormula(value);}else if(size.test(value)){value=value.replace(size,'\\vphantom{\\rule{0pt}{'+h+'em}}').replace(space,'\\hspace{'+w+'em}');setFormula(value);}else{const selected=visualFormula.getValue(visualFormula.selection,'latex');const [left,right]=({system:['\\{','.'],round:['(',')'],square:['[',']'],brace:['\\{','\\}']})[bracketType.value];const body=bracketType.value==='system'?'\\begin{array}{l}'+(selected||'x+y=1\\\\x-y=0')+'\\end{array}':selected||'x';visualFormula.insert('\\left'+left+'\\vphantom{\\rule{0pt}{'+h+'em}}'+body+'\\hspace{'+w+'em}\\right'+right);visualFormula.dispatchEvent(new Event('input'));}visualFormula.focus();});
$('addFormula').addEventListener('click',async()=>{if(!doc||!$('formulaInput').value.trim()||uploading)return;const value=$('formulaInput').value.trim(),editing=formulaEditing,current=doc;if(editing&&editing.note!==doc.id)return;if(!editing&&doc.content.formulas.length>=50){error('Massimo cinquanta formule per pagina.');return;}$('addFormula').disabled=true;visualFormula.readOnly=true;$('formulaInput').disabled=true;try{
if(editing?.index!==undefined){doc.content.formulas[editing.index]=value;changed();renderFormulas();resetFormula();}
else if(await window.TramontoLab.snapshot('formulaPreview',{latex:value,replace:editing?.image})){if(doc!==current)return;if(!editing)doc.content.formulas.push(value);renderFormulas();changed();resetFormula();}
}finally{$('addFormula').disabled=false;visualFormula.readOnly=false;$('formulaInput').disabled=false;}});
function renderFormulas(){
  $('formulaList').replaceChildren();if(!doc)return;
  doc.content.formulas.forEach((value,index)=>{const card=node('div');card.className='formula-card';const formula=node('div');formula.id='savedFormula'+index;latex(formula,value);card.appendChild(formula);formula.title='Clicca per modificare';formula.addEventListener('click',()=>editFormula(value,{index}));for(const [label,action]of [['Modifica',()=>editFormula(value,{index})],['Inserisci nel quaderno',()=>window.TramontoLab.snapshot(formula.id,{latex:value})]]){const b=node('button',label);b.type='button';b.className='secondary-button formula-insert';b.addEventListener('click',action);card.appendChild(b);}const remove=node('button','×');remove.type='button';remove.setAttribute('aria-label','Elimina formula');remove.addEventListener('click',()=>{resetFormula();doc.content.formulas.splice(index,1);renderFormulas();changed();});card.appendChild(remove);$('formulaList').appendChild(card);});
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
function drawStroke(line){
 ctx.save();if(line.tool==='text'){ctx.fillStyle=line.color;ctx.font=(line.text_size||28)+'px '+(window.TramontoFont?.family(line.font)||'Georgia,serif');ctx.textBaseline='top';for(const [i,text]of line.text.split('\n').entries())ctx.fillText(text,line.points[0][0],line.points[0][1]+i*(line.text_size||28)*1.25);ctx.restore();return;}ctx.strokeStyle=line.color;ctx.fillStyle=line.color;ctx.lineWidth=line.size;ctx.lineCap='round';ctx.lineJoin='round';
 const tool=line.tool||'pen',p=line.points,a=p[0],b=p.at(-1);ctx.globalAlpha=tool==='highlighter'?.28:tool==='pencil'?.65:1;
 if(line.dash)ctx.setLineDash([line.size*3,line.size*2]);if(tool==='marker')ctx.lineCap='square';ctx.beginPath();
 const arrow=(from,to)=>{const angle=Math.atan2(to[1]-from[1],to[0]-from[0]),length=Math.max(12,line.size*4);ctx.moveTo(to[0]-length*Math.cos(angle-.45),to[1]-length*Math.sin(angle-.45));ctx.lineTo(...to);ctx.lineTo(to[0]-length*Math.cos(angle+.45),to[1]-length*Math.sin(angle+.45));};
 if(tool==='rectangle')ctx.rect(Math.min(a[0],b[0]),Math.min(a[1],b[1]),Math.abs(b[0]-a[0]),Math.abs(b[1]-a[1]));
 else if(tool==='ellipse')ctx.ellipse((a[0]+b[0])/2,(a[1]+b[1])/2,Math.abs(b[0]-a[0])/2,Math.abs(b[1]-a[1])/2,0,0,Math.PI*2);
 else if(tool==='triangle'||tool==='diamond'){const x=(a[0]+b[0])/2,y=(a[1]+b[1])/2;if(tool==='triangle'){ctx.moveTo(x,a[1]);ctx.lineTo(b[0],b[1]);ctx.lineTo(a[0],b[1]);}else{ctx.moveTo(x,a[1]);ctx.lineTo(b[0],y);ctx.lineTo(x,b[1]);ctx.lineTo(a[0],y);}ctx.closePath();}
 else if(['line','arrow','double-arrow'].includes(tool)){ctx.moveTo(...a);ctx.lineTo(...b);if(tool!=='line')arrow(a,b);if(tool==='double-arrow')arrow(b,a);}
 else {p.forEach((point,index)=>index?ctx.lineTo(...point):ctx.moveTo(...point));if(p.length===1){ctx.arc(...a,line.size/2,0,Math.PI*2);ctx.fill();}}
 if(line.fill&&['rectangle','ellipse','triangle','diamond'].includes(tool)){ctx.save();ctx.globalAlpha=.18;ctx.fill();ctx.restore();}ctx.stroke();ctx.restore();
}
function redrawDrawing(){
 ctx.clearRect(0,0,1000,640);ctx.fillStyle='#fffcf3';ctx.fillRect(0,0,1000,640);if(!doc)return;
 const paper=doc.content.paper;ctx.strokeStyle='#e5e7da';ctx.fillStyle='#d6dcca';ctx.lineWidth=.7;
 if(paper==='ruled'||paper==='grid'||paper==='engineering'){ctx.beginPath();for(let y=24;y<640;y+=24){ctx.moveTo(0,y);ctx.lineTo(1000,y);}if(paper!=='ruled')for(let x=24;x<1000;x+=24){ctx.moveTo(x,0);ctx.lineTo(x,640);}ctx.stroke();}
 if(paper==='dots')for(let x=20;x<1000;x+=20)for(let y=20;y<640;y+=20){ctx.beginPath();ctx.arc(x,y,.8,0,Math.PI*2);ctx.fill();}
 for(const line of doc.content.drawing.strokes)drawStroke(line);
}
function canvasPoint(event){const box=canvas.getBoundingClientRect();return [Math.max(0,Math.min(1000,Math.round((event.clientX-box.left)*1000/box.width*10)/10)),Math.max(0,Math.min(640,Math.round((event.clientY-box.top)*640/box.height*10)/10))];}
const shapeTools=new Set(['line','arrow','double-arrow','rectangle','ellipse','triangle','diamond']);
function eraseAt(point){doc.content.drawing.strokes=doc.content.drawing.strokes.filter(line=>{
 const p=line.points;if(line.tool==='text'){ctx.font=line.text_size+'px '+(window.TramontoFont?.family(line.font)||'Georgia');const width=Math.max(...line.text.split('\n').map(s=>ctx.measureText(s).width)),height=line.text.split('\n').length*line.text_size*1.25;return !(point[0]>=p[0][0]-8&&point[0]<=p[0][0]+width+8&&point[1]>=p[0][1]-8&&point[1]<=p[0][1]+height+8);}if(shapeTools.has(line.tool)){const a=p[0],b=p.at(-1),left=Math.min(a[0],b[0])-12,right=Math.max(a[0],b[0])+12,top=Math.min(a[1],b[1])-12,bottom=Math.max(a[1],b[1])+12;return !(point[0]>=left&&point[0]<=right&&point[1]>=top&&point[1]<=bottom);}
 return !p.some((a,i)=>{const b=p[i+1]||a,dx=b[0]-a[0],dy=b[1]-a[1],t=Math.max(0,Math.min(1,((point[0]-a[0])*dx+(point[1]-a[1])*dy)/(dx*dx+dy*dy||1)));return Math.hypot(point[0]-a[0]-t*dx,point[1]-a[1]-t*dy)<12+line.size/2;});
 });}
canvas.addEventListener('pointerdown',event=>{if(!doc||event.button>0)return;event.preventDefault();canvas.setPointerCapture(event.pointerId);drawingHistory.push(clone(doc.content.drawing.strokes));drawingHistory=drawingHistory.slice(-20);if(!erasing){if(doc.content.drawing.strokes.length>=500){$('drawingMessage').textContent='Pagina piena: crea una nuova pagina.';return;}stroke={color:$('penColor').value,size:Number($('penSize').value),tool:$('drawingTool').value,fill:$('shapeFill').checked,dash:$('penDash').checked,points:[canvasPoint(event)]};doc.content.drawing.strokes.push(stroke);}else{stroke={erase:true};eraseAt(canvasPoint(event));}redrawDrawing();});
canvas.addEventListener('pointermove',event=>{if(!stroke||!doc)return;const point=canvasPoint(event);if(stroke.erase)eraseAt(point);
 else if(shapeTools.has(stroke.tool)){if(event.shiftKey){const a=stroke.points[0],dx=point[0]-a[0],dy=point[1]-a[1];if(['line','arrow','double-arrow'].includes(stroke.tool)){if(Math.abs(dx)>Math.abs(dy))point[1]=a[1];else point[0]=a[0];}else{const size=Math.min(Math.max(Math.abs(dx),Math.abs(dy)),dx<0?a[0]:1000-a[0],dy<0?a[1]:640-a[1]);point[0]=a[0]+Math.sign(dx||1)*size;point[1]=a[1]+Math.sign(dy||1)*size;}}stroke.points[1]=point;}
 else{const last=stroke.points.at(-1);if(Math.hypot(last[0]-point[0],last[1]-point[1])<1.6)return;if(stroke.points.length<5000)stroke.points.push(point);}redrawDrawing();});
function endStroke(){if(!stroke)return;stroke=null;changed();}
canvas.addEventListener('pointerup',endStroke);canvas.addEventListener('pointercancel',endStroke);canvas.addEventListener('lostpointercapture',endStroke);
$('drawingTool').addEventListener('change',()=>{erasing=false;$('eraser').setAttribute('aria-pressed','false');document.querySelectorAll('[data-draw-tool]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.drawTool===$('drawingTool').value)));});
$('eraser').addEventListener('click',()=>{erasing=!erasing;$('eraser').setAttribute('aria-pressed',String(erasing));document.querySelectorAll('[data-draw-tool]').forEach(b=>b.setAttribute('aria-pressed',String(!erasing&&b.dataset.drawTool===$('drawingTool').value)));});
$('undoDrawing').addEventListener('click',()=>{if(doc&&drawingHistory.length){doc.content.drawing.strokes=drawingHistory.pop();redrawDrawing();changed();}});
$('clearDrawing').addEventListener('click',()=>{if(doc&&confirm('Pulire il disegno? Puoi annullare subito dopo.')){drawingHistory.push(clone(doc.content.drawing.strokes));doc.content.drawing.strokes=[];redrawDrawing();changed();}});
$('exportDrawing').addEventListener('click',()=>{redrawDrawing();canvas.toBlob(blob=>download(blob,'disegno.png'));});

const PARTS={resistor:{name:'Resistenza',prefix:'R',value:'1 kΩ',ports:[[-28,0],[28,0]],path:'M-28 0h8l4-8 8 16 8-16 8 16 8-16 4 8h8'},
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
function componentPorts(part){if(part.type==='scope')return[[-36,50],[-12,50],[12,50],[36,50]];return PARTS[part.type].ports.map(([x,y],index)=>[x,part.type==='opamp'&&part.params?.plusTop&&index<2?-y:y]);}
function portPosition(part,index){const [x,y]=componentPorts(part)[index],angle=part.rotation*Math.PI/180;return{x:part.x+x*Math.cos(angle)-y*Math.sin(angle),y:part.y+x*Math.sin(angle)+y*Math.cos(angle)};}
const CIRCUIT_LIMIT=50000;
let circuitCamera={x:0,y:0,width:1000,height:640},circuitCameraDoc=null,circuitFrame=0,circuitPan=false,circuitPanDrag=null,circuitSpaceHeld=false;
function circuitExtent(){
 const c=doc?.content.circuit,b=c?.canvas||{width:1000,height:640};return {width:b.width,height:b.height};
}
function growCircuitCanvas(){
 if(!doc)return;const c=doc.content.circuit,old=circuitExtent(),points=[...c.components,...c.wires.flatMap(w=>w.points||[]),...wirePoints];
 const xmax=Math.max(0,...points.map(p=>p.x)),ymax=Math.max(0,...points.map(p=>p.y));
 const width=Math.min(CIRCUIT_LIMIT,Math.max(old.width,Math.ceil((xmax+160)/1000)*1000,1000));
 const height=Math.min(CIRCUIT_LIMIT,Math.max(old.height,Math.ceil((ymax+120)/640)*640,640));
 if(width!==old.width||height!==old.height)c.canvas={width,height};
}
function saveCircuitCamera(){if(!doc)return;try{localStorage.setItem('alba.circuitViewport.'+doc.id,JSON.stringify(circuitCamera));}catch(_){}}
function clampCircuitCamera(){
 circuitCamera.width=Math.max(200,Math.min(CIRCUIT_LIMIT*1.6,circuitCamera.width));circuitCamera.height=Math.max(128,Math.min(CIRCUIT_LIMIT*1.6,circuitCamera.height));
 circuitCamera.x=Math.max(0,Math.min(CIRCUIT_LIMIT-circuitCamera.width,circuitCamera.x));circuitCamera.y=Math.max(0,Math.min(CIRCUIT_LIMIT-circuitCamera.height,circuitCamera.y));
}
function applyCircuitCamera(){
 clampCircuitCamera();$('circuitSvg').style.aspectRatio=circuitCamera.width+'/'+circuitCamera.height;$('circuitSvg').setAttribute('viewBox',[circuitCamera.x,circuitCamera.y,circuitCamera.width,circuitCamera.height].join(' '));
 const zoom=$('circuitZoomLabel');if(zoom)zoom.textContent=Math.round(100000/circuitCamera.width)+'%';
 const size=$('circuitCanvasSize'),extent=circuitExtent();if(size)size.textContent=extent.width.toLocaleString('it')+' × '+extent.height.toLocaleString('it')+' · '+(doc?.content.circuit.components.length||0)+' oggetti';
}
function initializeCircuitCamera(){if(!doc||circuitCameraDoc===doc.id)return;circuitCameraDoc=doc.id;circuitCamera={x:0,y:0,width:1000,height:640};try{const saved=JSON.parse(localStorage.getItem('alba.circuitViewport.'+doc.id)||'null');if(saved&&['x','y','width','height'].every(k=>Number.isFinite(saved[k])))circuitCamera=saved;}catch(_){}applyCircuitCamera();}
function scheduleCircuitRender(){if(circuitFrame)return;circuitFrame=requestAnimationFrame(()=>{circuitFrame=0;renderCircuit();});}
function zoomCircuit(factor){initializeCircuitCamera();const c=circuitCamera,cx=c.x+c.width/2,cy=c.y+c.height/2;c.width*=factor;c.height*=factor;c.x=cx-c.width/2;c.y=cy-c.height/2;applyCircuitCamera();saveCircuitCamera();scheduleCircuitRender();}
function fitCircuit(){
 if(!doc)return;initializeCircuitCamera();const c=doc.content.circuit,ratio=circuitCamera.width/circuitCamera.height,points=[...c.wires.flatMap(w=>w.points||[]),...[...circuitRoutes().values()].flat()];
 for(const part of c.components){points.push({x:Math.max(0,part.x-80),y:Math.max(0,part.y-65)},{x:part.x+150,y:part.y+100});}
 if(!points.length)circuitCamera={x:0,y:0,width:1000,height:640};
 else{const xmin=Math.min(...points.map(p=>p.x)),xmax=Math.max(...points.map(p=>p.x)),ymin=Math.min(...points.map(p=>p.y)),ymax=Math.max(...points.map(p=>p.y)),width=Math.max(200,128*ratio,xmax-xmin+40,(ymax-ymin+40)*ratio),height=width/ratio;circuitCamera={x:Math.max(0,(xmin+xmax-width)/2),y:Math.max(0,(ymin+ymax-height)/2),width,height};}
 applyCircuitCamera();saveCircuitCamera();scheduleCircuitRender();$('circuitMessage').textContent=c.components.length?'Vista centrata sul progetto · tutti gli oggetti e i collegamenti sono visibili.':'Vista riportata all’origine.';
}
function circuitEdgePan(event){
 const box=$('circuitSvg').getBoundingClientRect(),c=circuitCamera,margin=30,step=c.width*.016;let dx=0,dy=0;
 if(event.clientX<box.left+margin)dx=-step;else if(event.clientX>box.right-margin)dx=step;
 if(event.clientY<box.top+margin)dy=-step;else if(event.clientY>box.bottom-margin)dy=step;
 if(dx||dy){c.x+=dx;c.y+=dy;applyCircuitCamera();saveCircuitCamera();}return !!(dx||dy);
}
function circuitVisible(points,padding=80){const c=circuitCamera;return points.length&&Math.max(...points.map(p=>p.x))>=c.x-padding&&Math.min(...points.map(p=>p.x))<=c.x+c.width+padding&&Math.max(...points.map(p=>p.y))>=c.y-padding&&Math.min(...points.map(p=>p.y))<=c.y+c.height+padding;}
function circuitPoint(event){const svg=$('circuitSvg'),point=svg.createSVGPoint();point.x=event.clientX;point.y=event.clientY;const pos=point.matrixTransform(svg.getScreenCTM().inverse());return{x:Math.max(40,Math.min(CIRCUIT_LIMIT-40,Math.round(pos.x/10)*10)),y:Math.max(40,Math.min(CIRCUIT_LIMIT-40,Math.round(pos.y/10)*10))};}
const circuitWorkbench=node('div');circuitWorkbench.id='circuitWorkbench';circuitWorkbench.className='circuit-workbench';const viewportToolbar=node('div');viewportToolbar.className='circuit-viewport-toolbar';viewportToolbar.setAttribute('aria-label','Vista dello schema');
function viewportButton(id,label,path,action){const b=node('button');b.id=id;b.type='button';b.className='secondary-button';b.title=label;b.setAttribute('aria-label',label);const icon=svgNode('svg',{viewBox:'0 0 24 24',class:'ui-icon',fill:'none',stroke:'currentColor','stroke-width':1.8,'stroke-linecap':'round','stroke-linejoin':'round','aria-hidden':'true'});icon.appendChild(svgNode('path',{d:path}));b.append(icon,node('span',label));b.addEventListener('click',action);viewportToolbar.appendChild(b);return b;}
viewportButton('circuitZoomIn','Ingrandisci','M10 4a6 6 0 1 0 0 12a6 6 0 1 0 0-12M14 14l7 7M7 10h6M10 7v6',()=>zoomCircuit(.8));
const zoomLabel=node('output','100%');zoomLabel.id='circuitZoomLabel';viewportToolbar.appendChild(zoomLabel);
viewportButton('circuitZoomOut','Riduci','M10 4a6 6 0 1 0 0 12a6 6 0 1 0 0-12M14 14l7 7M7 10h6',()=>zoomCircuit(1.25));
viewportButton('circuitFit','Centra progetto','M3 8V3h5M16 3h5v5M21 16v5h-5M8 21H3v-5',fitCircuit);
const panButton=viewportButton('circuitPan','Sposta vista','M12 2v20M2 12h20M8 6l4-4 4 4M8 18l4 4 4-4M6 8l-4 4 4 4M18 8l4 4-4 4',()=>{circuitPan=!circuitPan;panButton.setAttribute('aria-pressed',String(circuitPan));circuitWorkbench.classList.toggle('panning',circuitPan);});panButton.setAttribute('aria-pressed','false');
const expandButton=viewportButton('circuitExpand','Schermo intero','M3 8V3h5M16 3h5v5M21 16v5h-5M8 21H3v-5',async()=>{try{if(document.fullscreenElement===circuitWorkbench)await document.exitFullscreen();else if(circuitWorkbench.requestFullscreen)await circuitWorkbench.requestFullscreen();else circuitWorkbench.classList.toggle('expanded');}catch(_){circuitWorkbench.classList.toggle('expanded');}expandButton.setAttribute('aria-pressed',String(document.fullscreenElement===circuitWorkbench||circuitWorkbench.classList.contains('expanded')));});
viewportButton('circuitOpenScope','Oscilloscopio','M2 12c3-12 7-12 10 0s7 12 10 0',()=>window.TramontoLab?.oscilloscope.select(selectedPart));
const sizeLabel=node('span');sizeLabel.id='circuitCanvasSize';viewportToolbar.appendChild(sizeLabel);$('circuitSvg').before(circuitWorkbench);circuitWorkbench.append(viewportToolbar,$('circuitSvg'));const viewportHint=node('p','Rotella: zoom · Spazio + trascina o tasto centrale: sposta vista · L’area cresce vicino ai bordi.');viewportHint.className='tool-note';circuitWorkbench.appendChild(viewportHint);
const viewportSvg=$('circuitSvg');
viewportSvg.addEventListener('wheel',e=>{e.preventDefault();initializeCircuitCamera();const point=viewportSvg.createSVGPoint();point.x=e.clientX;point.y=e.clientY;const world=point.matrixTransform(viewportSvg.getScreenCTM().inverse()),c=circuitCamera,rx=(world.x-c.x)/c.width,ry=(world.y-c.y)/c.height,factor=Math.exp(Math.max(-.3,Math.min(.3,e.deltaY*.0015)));c.width*=factor;c.height*=factor;clampCircuitCamera();c.x=world.x-rx*c.width;c.y=world.y-ry*c.height;applyCircuitCamera();saveCircuitCamera();scheduleCircuitRender();},{passive:false});
viewportSvg.addEventListener('pointerdown',e=>{if(!doc||!(circuitPan||circuitSpaceHeld||e.button===1))return;e.preventDefault();e.stopImmediatePropagation();initializeCircuitCamera();circuitPanDrag={pointer:e.pointerId,x:e.clientX,y:e.clientY,camera:{...circuitCamera}};viewportSvg.setPointerCapture(e.pointerId);},true);
viewportSvg.addEventListener('pointermove',e=>{if(!circuitPanDrag||circuitPanDrag.pointer!==e.pointerId)return;e.preventDefault();e.stopImmediatePropagation();const b=viewportSvg.getBoundingClientRect(),p=circuitPanDrag;circuitCamera={...p.camera,x:p.camera.x-(e.clientX-p.x)*1/viewportSvg.getScreenCTM().a,y:p.camera.y-(e.clientY-p.y)/viewportSvg.getScreenCTM().d};applyCircuitCamera();scheduleCircuitRender();},true);
for(const name of ['pointerup','pointercancel','lostpointercapture'])viewportSvg.addEventListener(name,e=>{if(!circuitPanDrag)return;e.stopImmediatePropagation();circuitPanDrag=null;saveCircuitCamera();},true);
document.addEventListener('keydown',e=>{if(activePane!=='circuit'||e.target.closest('input,textarea,select,[contenteditable],#oscilloscopePanel'))return;if(e.code==='Space'){e.preventDefault();circuitSpaceHeld=true;circuitWorkbench.classList.add('panning');}if(e.key==='Escape'&&circuitWorkbench.classList.contains('expanded'))circuitWorkbench.classList.remove('expanded');});
document.addEventListener('keyup',e=>{if(e.code==='Space'){circuitSpaceHeld=false;circuitWorkbench.classList.toggle('panning',circuitPan);}});window.addEventListener('blur',()=>{circuitSpaceHeld=false;circuitPanDrag=null;});
document.addEventListener('fullscreenchange',()=>{expandButton.setAttribute('aria-pressed',String(document.fullscreenElement===circuitWorkbench));scheduleCircuitRender();});

let wirePoints=[],wireCursor=null,wireAxis=null,routeCache=new Map();
const wireColor=()=>$('wireColor')?.value||'#789476';
const samePoint=(a,b)=>Math.abs(a.x-b.x)<.01&&Math.abs(a.y-b.y)<.01;
function cleanRoute(points){const result=[];for(const p of points){if(result.length&&samePoint(result.at(-1),p))continue;while(result.length>1){const a=result.at(-2),b=result.at(-1);if((Math.abs(a.x-b.x)<.01&&Math.abs(b.x-p.x)<.01&&(b.y-a.y)*(p.y-b.y)>=0)||(Math.abs(a.y-b.y)<.01&&Math.abs(b.y-p.y)<.01&&(b.x-a.x)*(p.x-b.x)>=0))result.pop();else break;}result.push({x:Math.round(p.x*100)/100,y:Math.round(p.y*100)/100});}return result;}
function portLead(endpoint){const part=doc.content.circuit.components.find(p=>p.id===endpoint.component),pos=portPosition(part,endpoint.port),local=componentPorts(part)[endpoint.port],angle=part.rotation*Math.PI/180;
 if(part.type==='junction'||part.type==='probe')return pos;
 let dx=local[0],dy=local[1];if(Math.abs(dx)>=Math.abs(dy)){dx=Math.sign(dx);dy=0;}else{dy=Math.sign(dy);dx=0;}return{x:Math.max(0,Math.min(CIRCUIT_LIMIT,pos.x+16*(dx*Math.cos(angle)-dy*Math.sin(angle)))),y:Math.max(0,Math.min(CIRCUIT_LIMIT,pos.y+16*(dx*Math.sin(angle)+dy*Math.cos(angle))))};}
function segmentBlocked(a,b,rect){if(Math.abs(a.x-b.x)<.01)return a.x>rect.left&&a.x<rect.right&&Math.max(a.y,b.y)>rect.top&&Math.min(a.y,b.y)<rect.bottom;return a.y>rect.top&&a.y<rect.bottom&&Math.max(a.x,b.x)>rect.left&&Math.min(a.x,b.x)<rect.right;}
// Orthogonal visibility grid: ports and fixed corners retain their exact coordinates.
function routeLeg(a,b,prior=[],axis=null){
 if(samePoint(a,b))return[a];const obstacles=doc.content.circuit.components.filter(p=>!['junction','probe'].includes(p.type)).map(p=>({left:p.x-(p.type==='scope'?39:24),right:p.x+(p.type==='scope'?39:24),top:p.y-(p.type==='scope'?37:24),bottom:p.y+(p.type==='scope'?37:24)})).filter(r=>![a,b].some(p=>p.x>r.left&&p.x<r.right&&p.y>r.top&&p.y<r.bottom));
 const xmin=Math.max(0,Math.min(a.x,b.x)-120),xmax=Math.min(CIRCUIT_LIMIT,Math.max(a.x,b.x)+120),ymin=Math.max(0,Math.min(a.y,b.y)-120),ymax=Math.min(CIRCUIT_LIMIT,Math.max(a.y,b.y)+120);const xs=[a.x,b.x,xmin,xmax],ys=[a.y,b.y,ymin,ymax];for(const r of obstacles){if(r.right<xmin||r.left>xmax||r.bottom<ymin||r.top>ymax)continue;xs.push(Math.max(0,r.left-10),Math.min(CIRCUIT_LIMIT,r.right+10));ys.push(Math.max(0,r.top-10),Math.min(CIRCUIT_LIMIT,r.bottom+10));}for(const path of prior)for(const p of path){if(p.x<xmin||p.x>xmax||p.y<ymin||p.y>ymax)continue;xs.push(Math.max(0,p.x-10),Math.min(CIRCUIT_LIMIT,p.x+10));ys.push(Math.max(0,p.y-10),Math.min(CIRCUIT_LIMIT,p.y+10));}
 const unique=v=>[...new Set(v.map(n=>Math.round(n*100)/100))].sort((a,b)=>a-b),x=unique(xs),y=unique(ys),width=x.length,si=x.indexOf(Math.round(a.x*100)/100)+y.indexOf(Math.round(a.y*100)/100)*width,ti=x.indexOf(Math.round(b.x*100)/100)+y.indexOf(Math.round(b.y*100)/100)*width;
 const heap=[],dist=new Map(),parent=new Map(),coord=id=>({x:x[id%width],y:y[Math.floor(id/width)]});
 function push(v){heap.push(v);let i=heap.length-1;while(i){let p=(i-1)>>1;if(heap[p].f<=v.f)break;heap[i]=heap[p];i=p;}heap[i]=v;}
 function pop(){const first=heap[0],last=heap.pop();if(heap.length){let i=0;while(i*2+1<heap.length){let c=i*2+1;if(c+1<heap.length&&heap[c+1].f<heap[c].f)c++;if(heap[c].f>=last.f)break;heap[i]=heap[c];i=c;}heap[i]=last;}return first;}
 const initial=si*3+(axis==='v'?2:axis==='h'?1:0);dist.set(initial,0);push({key:initial,g:0,f:Math.abs(a.x-b.x)+Math.abs(a.y-b.y)});let found=null;
 while(heap.length){const cur=pop();if(cur.g!==dist.get(cur.key))continue;const id=Math.floor(cur.key/3),dir=cur.key%3;if(id===ti){found=cur.key;break;}const p=coord(id),ix=id%width,iy=Math.floor(id/width);
 for(const [nx,ny,nd]of [[ix-1,iy,1],[ix+1,iy,1],[ix,iy-1,2],[ix,iy+1,2]]){if(nx<0||ny<0||nx>=width||ny>=y.length)continue;const next=nx+ny*width,q=coord(next);if(obstacles.some(r=>segmentBlocked(p,q,r)))continue;let penalty=0;
 for(const path of prior)for(let j=1;j<path.length;j++){const c=path[j-1],d=path[j];if(nd===1&&Math.abs(c.y-d.y)<.01&&Math.abs(c.y-p.y)<.01)penalty+=Math.max(0,Math.min(Math.max(p.x,q.x),Math.max(c.x,d.x))-Math.max(Math.min(p.x,q.x),Math.min(c.x,d.x)))*5;else if(nd===2&&Math.abs(c.x-d.x)<.01&&Math.abs(c.x-p.x)<.01)penalty+=Math.max(0,Math.min(Math.max(p.y,q.y),Math.max(c.y,d.y))-Math.max(Math.min(p.y,q.y),Math.min(c.y,d.y)))*5;}
 const g=cur.g+Math.abs(p.x-q.x)+Math.abs(p.y-q.y)+(dir&&dir!==nd?18:0)+penalty,key=next*3+nd;if(g>=(dist.get(key)??Infinity))continue;dist.set(key,g);parent.set(key,cur.key);push({key,g,f:g+Math.abs(q.x-b.x)+Math.abs(q.y-b.y)});}}
 if(found===null)return axis==='v'?[a,{x:a.x,y:b.y},b]:[a,{x:b.x,y:a.y},b];const result=[];for(let k=found;k!==undefined;k=parent.get(k))result.push(coord(Math.floor(k/3)));return cleanRoute(result.reverse());
}
function wireRoute(wire,prior=[]){const c=doc.content.circuit,a=c.components.find(p=>p.id===wire.from.component),b=c.components.find(p=>p.id===wire.to.component);if(!a||!b)return[];const start=portPosition(a,wire.from.port),end=portPosition(b,wire.to.port),lead=portLead(wire.from),tail=portLead(wire.to),anchors=[lead,...(wire.points||[]),tail],route=[start,lead];for(let i=1;i<anchors.length;i++)route.push(...routeLeg(anchors[i-1],anchors[i],prior,i>1&&route.length>1?(Math.abs(route.at(-1).y-route.at(-2).y)<.01?'v':'h'):null).slice(1));route.push(end);return cleanRoute(route);}
function captureCircuitWireMove(ids){
 const selected=new Set(ids);return doc.content.circuit.wires.filter(w=>selected.has(w.from.component)||selected.has(w.to.component)).map(w=>({wire:w,points:clone(w.points||[]),from:selected.has(w.from.component),to:selected.has(w.to.component),lead:portLead(w.from),tail:portLead(w.to)}));
}
function moveCircuitWireCorners(origins,dx,dy){
 for(const entry of origins||[]){const points=clone(entry.points);
  if(entry.from&&entry.to)for(const p of points){p.x+=dx;p.y+=dy;}
  else{
   const adjust=(index,anchor)=>{const original=entry.points[index],p=points[index];if(!p)return;if(samePoint(original,anchor)){p.x+=dx;p.y+=dy;}else if(Math.abs(original.y-anchor.y)<.01)p.y+=dy;else if(Math.abs(original.x-anchor.x)<.01)p.x+=dx;};
   if(entry.from)adjust(0,entry.lead);if(entry.to)adjust(points.length-1,entry.tail);
  }
  // Old bends inside a moved body are replaced by a fresh orthogonal terminal lead.
  entry.wire.points=points.filter(p=>!doc.content.circuit.components.some(part=>{if(![entry.wire.from.component,entry.wire.to.component].includes(part.id)||['junction','probe'].includes(part.type))return false;const angle=-part.rotation*Math.PI/180,x=(p.x-part.x)*Math.cos(angle)-(p.y-part.y)*Math.sin(angle),y=(p.x-part.x)*Math.sin(angle)+(p.y-part.y)*Math.cos(angle);return Math.abs(x)<(part.type==='scope'?39:24)&&Math.abs(y)<(part.type==='scope'?37:24);})).map(p=>({x:Math.max(0,Math.min(CIRCUIT_LIMIT,p.x)),y:Math.max(0,Math.min(CIRCUIT_LIMIT,p.y))}));
 }
}
const pathData=points=>points.map((p,i)=>(i?'L':'M')+p.x+' '+p.y).join(' ');
function circuitRoutes(){
 const circuit=doc.content.circuit,signature=JSON.stringify([circuit.components.map(p=>[p.id,p.type,p.x,p.y,p.rotation,p.params?.plusTop,p.params?.portsBottom]),circuit.wires.map(w=>[w.id,w.from,w.to,w.points])]);
 if(routeCache.signature===signature)return routeCache;
 const previous=routeCache,keys=previous.keysByWire||new Map();routeCache=new Map();routeCache.signature=signature;routeCache.keysByWire=new Map();const prior=[];
 for(const wire of circuit.wires){const a=circuit.components.find(p=>p.id===wire.from.component),b=circuit.components.find(p=>p.id===wire.to.component);if(!a||!b)continue;
  const old=previous.get(wire.id)||[],points=[a,b,...(wire.points||[]),...old],xmin=Math.min(...points.map(p=>p.x))-80,xmax=Math.max(...points.map(p=>p.x))+80,ymin=Math.min(...points.map(p=>p.y))-80,ymax=Math.max(...points.map(p=>p.y))+80;
  const key=JSON.stringify([wire.from,wire.to,wire.points,[a.x,a.y,a.rotation,a.params?.plusTop,a.params?.portsBottom,b.x,b.y,b.rotation,b.params?.plusTop,b.params?.portsBottom],circuit.components.filter(p=>p.x>=xmin&&p.x<=xmax&&p.y>=ymin&&p.y<=ymax).map(p=>[p.id,p.type,p.x,p.y,p.rotation,p.params?.plusTop,p.params?.portsBottom])]);
  const route=keys.get(wire.id)===key?old:wireRoute(wire,prior);routeCache.set(wire.id,route);routeCache.keysByWire.set(wire.id,key);prior.push(route);
 }return routeCache;
}
function pendingRoute(target=wireCursor){if(!wireStart)return[];const part=doc.content.circuit.components.find(p=>p.id===wireStart.component);if(!part)return[];const start=portPosition(part,wireStart.port),lead=portLead(wireStart),anchors=[lead,...wirePoints],route=[start,lead];for(let i=1;i<anchors.length;i++)route.push(...routeLeg(anchors[i-1],anchors[i],[],i>1&&route.length>1?(Math.abs(route.at(-1).y-route.at(-2).y)<.01?'v':'h'):null).slice(1));if(target)route.push(...routeLeg(anchors.at(-1),target,[...circuitRoutes().values()],wireAxis).slice(1));return cleanRoute(route);}
function renderWirePreview(){const svg=$('circuitSvg');svg.querySelectorAll('[data-wire-preview]').forEach(e=>e.remove());if(!wireStart)return;const route=pendingRoute();svg.appendChild(svgNode('path',{d:pathData(route),fill:'none',stroke:wireColor(),'stroke-width':2.5,'stroke-dasharray':'7 4','pointer-events':'none','data-wire-preview':''}));for(const p of wirePoints)svg.appendChild(svgNode('circle',{cx:p.x,cy:p.y,r:3,fill:wireColor(),'pointer-events':'none','data-wire-preview':''}));}
function cancelWire(){wireStart=null;wirePoints=[];wireCursor=null;wireAxis=null;circuitMode='select';placing=null;$('wireCircuit').setAttribute('aria-pressed','false');renderCircuit();}
function startWire(end){window.TramontoLab?.circuitSelection?.clear();wireStart=end;wirePoints=[];wireCursor=null;wireAxis=null;circuitMode='wire';placing=null;selectedPart=selectedWire=null;$('wireCircuit').setAttribute('aria-pressed','true');$('circuitMessage').textContent='Clic sul vuoto: fissa una svolta a 90°. Clic su terminale o filo: termina. Esc: annulla · Backspace: togli ultima svolta.';renderCircuit();}
function finishWire(end){if(end.component===wireStart.component&&end.port===wireStart.port)return;const c=doc.content.circuit;if(c.wires.length>=200){$('circuitMessage').textContent='Massimo 200 fili per pagina.';return;}historyCircuit();c.wires.push({id:crypto.randomUUID(),from:wireStart,to:end,points:clone(wirePoints),color:wireColor()});cancelWire();changed();$('circuitMessage').textContent='Collegamento creato. Clicca un altro terminale per continuare.';}
$('wireColor').addEventListener('input',renderWirePreview);
$('wireColor').addEventListener('change',()=>{if(!doc)return;const selected=window.TramontoLab?.circuitSelection?.items().filter(i=>i.link).map(i=>i.value)||[],wire=doc.content.circuit.wires.find(w=>w.id===selectedWire);if(wire&&!selected.includes(wire))selected.push(wire);if(selected.length){historyCircuit();selected.forEach(w=>w.color=wireColor());renderCircuit();changed();}});
$('cancelWire').addEventListener('click',cancelWire);
document.addEventListener('keydown',e=>{if(!wireStart||activePane!=='circuit')return;if(e.key!=='Escape'&&e.target.closest('input,textarea,select,[contenteditable]'))return;if(e.key==='Escape'){e.preventDefault();e.stopImmediatePropagation();cancelWire();}else if(e.key==='Backspace'){e.preventDefault();e.stopImmediatePropagation();wirePoints.pop();wireAxis=null;renderWirePreview();}},true);

function schematicInk(){const technical=preference('tramontoSchematicStyle','technical')==='technical';return technical?{technical:true,paper:'#ffffff',grid:'#aeb4be',gridStep:10,wire:'#c63b39',symbol:'#161b23',active:'#243fc3',text:'#161b23',width:1.35}:{technical:false,paper:'#fffcf3',grid:'#dddccb',gridStep:20,wire:'#789476',symbol:'#344b3e',active:'#344b3e',text:'#44543e',width:2};}
function schematicAmplitude(value){const unit=value!==0&&value<1?(value>=.001?['m',1e3]:value>=1e-6?['μ',1e6]:value>=1e-9?['n',1e9]:['p',1e12]):['',1];return Number((value*unit[1]).toPrecision(8))+' '+unit[0]+'Vpk';}
function schematicLabelLines(part){
 const lines=[part.label];if(['ac','function'].includes(part.type)){const params=part.params||{};lines.push(schematicAmplitude(params.amplitude??1),params.frequency!==undefined?params.frequency+' Hz':part.value||'1 kHz');if(params.offset)lines.push(params.offset+' V offset');if(params.phase!==undefined)lines.push(params.phase+'°');}
 else if(part.type==='summer3'){lines.push((part.params?.gainOut??1)+' V/V',(part.params?.offset??0)+' V');}
 else if(part.type==='summer'){lines.push('Σ · gA '+(part.params?.gainA??1)+' / gB '+(part.params?.gainB??1));}
 else if(part.type==='switch')lines.push(part.params?.key?'Key = '+part.params.key:(part.params?.closed?'Chiuso':'Aperto'));else if(part.value)lines.push(part.value);return lines.filter(Boolean);
}
function renderCircuit(){
 const svg=$('circuitSvg');svg.replaceChildren();if(!doc)return;initializeCircuitCamera();growCircuitCanvas();applyCircuitCamera();const extent=circuitExtent(),ink=schematicInk();svg.dataset.schematicStyle=ink.technical?'technical':'tramonto';
 const defs=svgNode('defs'),pattern=svgNode('pattern',{id:'circuitGrid',width:ink.gridStep,height:ink.gridStep,patternUnits:'userSpaceOnUse'});pattern.appendChild(svgNode('circle',{cx:ink.gridStep/2,cy:ink.gridStep/2,r:ink.technical?.55:1,fill:ink.grid}));defs.appendChild(pattern);svg.appendChild(defs);
 const bounds={width:Math.max(extent.width,circuitCamera.x+circuitCamera.width),height:Math.max(extent.height,circuitCamera.y+circuitCamera.height)};svg.appendChild(svgNode('rect',{...bounds,fill:ink.paper}));svg.appendChild(svgNode('rect',{...bounds,fill:'url(#circuitGrid)'}));
 const routes=circuitRoutes(),connections=new Map();
 for(const wire of doc.content.circuit.wires){for(const end of [wire.from,wire.to]){const key=end.component+':'+end.port,ends=connections.get(key)||[];ends.push(wire);connections.set(key,ends);}const points=routes.get(wire.id)||[];if(!circuitVisible(points))continue;
  const path=svgNode('path',{d:pathData(points),fill:'none',stroke:wire.color||ink.wire,'stroke-width':wire.id===selectedWire?3:ink.technical?1.45:2.5,'stroke-linejoin':'round','data-wire':wire.id});const hit=path.cloneNode();hit.setAttribute('stroke','transparent');hit.setAttribute('stroke-width',14);svg.append(path,hit);
 }
 const segments=[];for(const [id,points]of routes)for(let i=1;i<points.length;i++)if(circuitVisible([points[i-1],points[i]],0))segments.push({id,a:points[i-1],b:points[i]});
 for(let i=0;i<segments.length;i++)for(let j=i+1;j<segments.length;j++){const a=segments[i],b=segments[j];if(a.id===b.id)continue;const h=Math.abs(a.a.y-a.b.y)<.01?a:b,v=h===a?b:a;if(Math.abs(v.a.x-v.b.x)>.01)continue;const x=v.a.x,y=h.a.y;if(x<=Math.min(h.a.x,h.b.x)+1||x>=Math.max(h.a.x,h.b.x)-1||y<=Math.min(v.a.y,v.b.y)+1||y>=Math.max(v.a.y,v.b.y)-1)continue;const wire=doc.content.circuit.wires.find(w=>w.id===h.id);svg.appendChild(svgNode('path',{d:'M'+(x-4)+' '+y+'h8',stroke:ink.paper,'stroke-width':5,'pointer-events':'none'}));svg.appendChild(svgNode('path',{d:'M'+(x-4)+' '+y+'h8',stroke:wire.color||ink.wire,'stroke-width':ink.technical?1.45:2.5,'pointer-events':'none'}));}
 for(const part of doc.content.circuit.components){if(!circuitVisible([part],100))continue;const spec=PARTS[part.type],symbolColor=ink.technical&&['opamp','summer','summer3','and','or','not','nand','nor','xor','xnor'].includes(part.type)?ink.active:ink.symbol,group=svgNode('g',{transform:'translate('+part.x+' '+part.y+') rotate('+part.rotation+')','data-component-id':part.id,class:'circuit-part'});
  group.appendChild(svgNode('rect',{x:spec.bounds?.x??-34,y:spec.bounds?.y??-35,width:spec.bounds?.width??68,height:spec.bounds?.height??70,rx:ink.technical?2:8,fill:part.id===selectedPart?'#f8d9aa55':'transparent',stroke:part.id===selectedPart?'#d6a46a':'none'}));
  group.appendChild(svgNode('title',{},spec.name+' · '+schematicLabelLines(part).join(' · ')));
  if(part.type==='scope'){
   const wide=true;group.appendChild(svgNode('rect',{x:wide?-48:-36,y:-34,width:wide?96:72,height:68,fill:'#cacdc5',stroke:'none'}));
   group.appendChild(svgNode('rect',{x:wide?-42:-30,y:-28,width:wide?84:60,height:46,fill:'#edf1e9',stroke:'#f8faf4','stroke-width':.9,'pointer-events':'none',class:'scope-mini-screen'}));
   group.appendChild(svgNode('path',{d:wide?'M-42-5h84M0-28v46':'M-30-5h60M0-28v46',fill:'none',stroke:'#c1cbbb','stroke-width':.7,'pointer-events':'none'}));
   group.appendChild(svgNode('path',{d:wide?'M-38-5q9-28 18 0t18 0t18 0t18 0':'M-26-5q6-24 12 0t12 0t12 0t12 0',fill:'none',stroke:'#202620','stroke-width':1,'pointer-events':'none'}));
   group.appendChild(svgNode('path',{d:wide?'M-38 3q9-16 18 0t18 0t18 0t18 0':'M-26 3q6-14 12 0t12 0t12 0t12 0',fill:'none',stroke:'#3159a4','stroke-width':.9,'pointer-events':'none'}));
  }
  if(spec.circle)group.appendChild(svgNode('circle',{r:18,fill:'none',stroke:symbolColor,'stroke-width':ink.width}));
  const sourceWave=part.params?.wave||'sine',symbolPath=part.type==='switch'&&part.params?.closed?'M-28 0h56':part.type==='scope'?'M-48-34h96v68h-96zM-36 34v16M-12 34v16M12 34v16M36 34v16':part.type==='opamp'&&part.params?.plusTop?'M-30-12h12M-30 12h12M-18-26v52L22 0-18-26M22 0h8M0-15v-17M0 15v17M-13-12h7M-10-15v6M-13 12h7':part.type==='function'&&sourceWave==='sine'?PARTS.ac.path:part.type==='function'&&sourceWave==='triangle'?'M-28 0h10M18 0h10M-12 0l6-10 12 20 6-10':spec.path;
  group.appendChild(svgNode('path',{d:symbolPath,fill:'none',stroke:symbolColor,'stroke-width':ink.width,'stroke-linecap':'round','stroke-linejoin':'round'}));
  componentPorts(part).forEach((point,index)=>{const ends=connections.get(part.id+':'+index)||[],started=wireStart?.component===part.id&&wireStart.port===index,joined=part.type==='junction'||ends.length>1,color=started?'#d38651':ends[0]?.color||ink.wire;
   group.appendChild(svgNode('circle',{cx:point[0],cy:point[1],r:10,fill:'transparent',stroke:'none','data-port':index,'data-owner':part.id,class:'circuit-terminal'}));
   group.appendChild(svgNode('circle',{cx:point[0],cy:point[1],r:ink.technical?(joined?2.8:started?4:2):part.type==='junction'?5:5.5,fill:started||joined?color:ink.paper,stroke:ends.length?color:symbolColor,'stroke-width':ink.technical?.85:1.5,'pointer-events':'none',class:'terminal-dot'}));
  });
  if(spec.portLabels)componentPorts(part).forEach((point,index)=>group.appendChild(svgNode('text',{x:part.type==='scope'?point[0]:point[0]+(point[0]<0?10:point[0]>0?-10:8),y:point[1]-7,'text-anchor':part.type==='scope'?'middle':point[0]<0||point[0]===0?'start':'end',fill:ink.technical?symbolColor:index<2?'#28718d':'#b57232','font-size':9,'font-family':'sans-serif','pointer-events':'none'},spec.portLabels[index])));
  if(ink.technical&&part.type==='opamp')for(const [pin,x,y]of [['2',-27,-17],['3',-27,8],['6',25,-6],['7',5,-26],['4',5,30]])group.appendChild(svgNode('text',{x,y:part.params?.plusTop&&['2','3'].includes(pin)?(pin==='2'?8:-17):y,fill:ink.active,'font-size':7.5,'font-family':'sans-serif','pointer-events':'none'},pin));
  svg.appendChild(group);if(part.type==='junction'||ink.technical&&part.type==='ground')continue;
  const lines=schematicLabelLines(part),above=ink.technical&&part.rotation%180===0&&['resistor','capacitor','inductor','fuse','pot','transformer'].includes(part.type),side=ink.technical&&!above&&part.type!=='opamp'&&part.type!=='scope'&&part.type!=='summer'&&part.type!=='summer3',x=part.x+(side?38:part.rotation%180===90?38:0),y=part.y+(above?-38:side?-9:part.type==='scope'?-50:part.type==='opamp'?-44:spec.bounds?58:48),label=svgNode('text',{x,y,'text-anchor':side||part.rotation%180===90?'start':'middle',fill:part.type==='opamp'?ink.active:ink.text,'font-family':'Arial, sans-serif','font-size':ink.technical?10.5:12,'pointer-events':'none',class:'schematic-label'});
  lines.forEach((text,index)=>label.appendChild(svgNode('tspan',{x,dy:index?13:0,'font-weight':index?400:600},text)));svg.appendChild(label);
 }
 const part=doc.content.circuit.components.find(value=>value.id===selectedPart);$('componentForm').hidden=!part;if(part){$('componentLabel').value=part.label;$('componentValue').value=part.value;}window.TramontoLab?.component(part);window.TramontoLab?.circuitSelection?.render();if(selectedWire){const w=doc.content.circuit.wires.find(w=>w.id===selectedWire);if(w)$('wireColor').value=w.color||ink.wire;}renderWirePreview();
}
function insertSwitchOnWire(id,p){
 const c=doc.content.circuit,old=c.wires.find(w=>w.id===id),route=circuitRoutes().get(id);if(!old||!route)return;
 if(c.components.length>=100||c.wires.length>=200){$('circuitMessage').textContent='Schema pieno: crea una nuova pagina.';return;}
 let best=null;for(let i=1;i<route.length;i++){const a=route[i-1],b=route[i],dx=b.x-a.x,dy=b.y-a.y,length=Math.hypot(dx,dy);if(length<80)continue;const t=Math.max(40/length,Math.min(1-40/length,((p.x-a.x)*dx+(p.y-a.y)*dy)/(length*length))),q={x:a.x+t*dx,y:a.y+t*dy},distance=Math.hypot(p.x-q.x,p.y-q.y);if(!best||distance<best.distance)best={q,i,distance,dx:dx/length,dy:dy/length};}
 if(!best||best.distance>45){$('circuitMessage').textContent='Scegli un tratto rettilineo più lungo: servono almeno 80 unità per l’interruttore.';return;}
 if(c.components.some(part=>Math.hypot(part.x-best.q.x,part.y-best.q.y)<55)){ $('circuitMessage').textContent='Scegli un tratto libero, distante dagli altri componenti.';return;}
 historyCircuit();const part={id:crypto.randomUUID(),type:'switch',...best.q,rotation:(Math.round(Math.atan2(best.dy,best.dx)*180/Math.PI)+360)%360,label:'S'+(c.components.filter(p=>p.type==='switch').length+1),value:'aperto',params:{closed:false,key:''}};
 const tail={id:crypto.randomUUID(),from:{component:part.id,port:1},to:clone(old.to),color:old.color||schematicInk().wire,points:route.slice(best.i,-1)};old.to={component:part.id,port:0};old.points=route.slice(1,best.i);c.components.push(part);c.wires.push(tail);selectedPart=part.id;selectedWire=null;cancelWire();window.TramontoLab?.circuitSelection?.select(['c:'+part.id]);renderCircuit();changed();$('circuitMessage').textContent='Interruttore inserito in serie. Doppio clic per aprire/chiudere; «Annulla» ripristina il cavo.';
}
document.querySelector('.component-palette').addEventListener('click',event=>{const button=event.target.closest('[data-component]');if(!button)return;cancelWire();placing=button.dataset.component;circuitMode='place';document.querySelectorAll('[data-component]').forEach(item=>item.classList.toggle('active',item===button));$('circuitMessage').textContent=placing==='switch'?'Tocca un cavo per inserire l’interruttore in serie, oppure il foglio per posizionarlo. Doppio clic per aprirlo/chiuderlo.':'Tocca il foglio per aggiungere: '+PARTS[placing].name+'.';});
$('selectCircuit').addEventListener('click',()=>{cancelWire();$('circuitMessage').textContent='Trascina un componente per spostarlo. Tocca un filo per selezionarlo.';});
$('wireCircuit').addEventListener('click',()=>{cancelWire();circuitMode='wire';$('wireCircuit').setAttribute('aria-pressed','true');$('circuitMessage').textContent='Clicca un terminale per iniziare; clic sul vuoto per fissare le svolte.';});
$('circuitSvg').addEventListener('pointerdown',event=>{
  if(!doc)return;event.preventDefault();const terminal=event.target.closest('[data-port]'),partNode=event.target.closest('[data-component-id]'),wire=event.target.closest('[data-wire]');
  if(terminal){const end={component:terminal.dataset.owner,port:Number(terminal.dataset.port)};if(!wireStart)startWire(end);else finishWire(end);return;}
  if(wireStart){
    if(wire){const old=doc.content.circuit.wires.find(w=>w.id===wire.dataset.wire),route=circuitRoutes().get(old.id),p=circuitPoint(event);if(doc.content.circuit.components.length>=100||doc.content.circuit.wires.length>=199)return;
      let best=null;for(let i=1;i<route.length;i++){const a=route[i-1],b=route[i],dx=b.x-a.x,dy=b.y-a.y,t=Math.max(0,Math.min(1,((p.x-a.x)*dx+(p.y-a.y)*dy)/(dx*dx+dy*dy||1))),q={x:a.x+t*dx,y:a.y+t*dy},distance=Math.hypot(p.x-q.x,p.y-q.y);if(!best||distance<best.distance)best={q,index:i,distance};}
      for(const end of [old.from,old.to]){const part=doc.content.circuit.components.find(p=>p.id===end.component);if(samePoint(portPosition(part,end.port),best.q)){finishWire(end);return;}}
      historyCircuit();const id=crypto.randomUUID();doc.content.circuit.components.push({id,type:'junction',...best.q,rotation:0,label:'',value:''});const endpoint={component:id,port:0},tail={id:crypto.randomUUID(),from:endpoint,to:old.to,color:old.color||'#789476',points:route.slice(best.index,-1)};old.to=endpoint;old.points=route.slice(1,best.index);doc.content.circuit.wires.push(tail,{id:crypto.randomUUID(),from:wireStart,to:endpoint,color:wireColor(),points:clone(wirePoints)});cancelWire();changed();return;
    }
    if(!partNode&&wirePoints.length<100){const p=circuitPoint(event),route=pendingRoute(p);if(route.length>1){const a=route.at(-2),b=route.at(-1);wireAxis=Math.abs(a.y-b.y)<.01?'v':'h';}if(!wirePoints.length||!samePoint(wirePoints.at(-1),p))wirePoints.push(p);wireCursor=p;renderWirePreview();}return;
  }
  if(circuitMode==='place'&&placing==='switch'&&wire&&!partNode){insertSwitchOnWire(wire.dataset.wire,circuitPoint(event));return;}
  if(circuitMode==='place'&&!partNode&&!wire){if(doc.content.circuit.components.length>=100)return;historyCircuit();const position=circuitPoint(event),spec=PARTS[placing],count=doc.content.circuit.components.filter(part=>PARTS[part.type].prefix===spec.prefix).length+1;doc.content.circuit.components.push({id:crypto.randomUUID(),type:placing,...position,rotation:0,label:spec.prefix+count,value:spec.value,...(placing==='scope'?{params:{portsBottom:true}}:{})});if(placing==='scope'&&$('spiceAnalysis')?.value==='op')$('spiceAnalysis').value='tran';growCircuitCanvas();selectedPart=doc.content.circuit.components.at(-1).id;selectedWire=null;renderCircuit();changed();return;}
  if(wire){selectedWire=wire.dataset.wire;selectedPart=null;renderCircuit();return;}
  if(partNode){selectedPart=partNode.dataset.componentId;selectedWire=null;const part=doc.content.circuit.components.find(value=>value.id===selectedPart);historyCircuit();const point=circuitPoint(event);drag={id:part.id,dx:part.x-point.x,dy:part.y-point.y,moved:false};$('circuitSvg').setPointerCapture(event.pointerId);}else{selectedPart=selectedWire=null;}renderCircuit();
});
$('circuitSvg').addEventListener('pointermove',event=>{if(wireStart&&doc){circuitEdgePan(event);const terminal=event.target.closest('[data-port]');wireCursor=terminal?portPosition(doc.content.circuit.components.find(p=>p.id===terminal.dataset.owner),Number(terminal.dataset.port)):circuitPoint(event);renderWirePreview();return;}if(!drag||!doc)return;circuitEdgePan(event);const part=doc.content.circuit.components.find(value=>value.id===drag.id),point=circuitPoint(event);part.x=Math.max(40,Math.min(CIRCUIT_LIMIT-40,point.x+drag.dx));part.y=Math.max(40,Math.min(CIRCUIT_LIMIT-40,point.y+drag.dy));drag.moved=true;growCircuitCanvas();scheduleCircuitRender();});
function endDrag(){if(drag?.moved)changed();drag=null;}
$('circuitSvg').addEventListener('pointerup',endDrag);$('circuitSvg').addEventListener('pointercancel',endDrag);
$('rotateCircuit').addEventListener('click',()=>{if(window.TramontoLab?.circuitSelection?.rotate())return;const part=doc?.content.circuit.components.find(value=>value.id===selectedPart);if(part){historyCircuit();part.rotation=(part.rotation+90)%360;renderCircuit();changed();}});
function deletePart(){if(window.TramontoLab?.circuitSelection?.remove())return;if(!doc||(!selectedPart&&!selectedWire))return;historyCircuit();if(selectedPart){doc.content.circuit.components=doc.content.circuit.components.filter(value=>value.id!==selectedPart);doc.content.circuit.wires=doc.content.circuit.wires.filter(value=>value.from.component!==selectedPart&&value.to.component!==selectedPart);}else doc.content.circuit.wires=doc.content.circuit.wires.filter(value=>value.id!==selectedWire);selectedPart=selectedWire=null;renderCircuit();changed();}
$('deleteCircuitPart').addEventListener('click',deletePart);$('circuitSvg').addEventListener('keydown',event=>{if(['Delete','Backspace'].includes(event.key)){event.preventDefault();deletePart();}});
$('undoCircuit').addEventListener('click',()=>{if(doc&&circuitHistory.length){doc.content.circuit=circuitHistory.pop();cancelWire();selectedPart=selectedWire=null;renderCircuit();changed();}});
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
$('printNote').addEventListener('click',async()=>{if(!doc)return;await document.fonts.ready;const images=Array.from($('richEditor').querySelectorAll('img'));await Promise.all(images.map(image=>image.decode().catch(()=>{})));window.print();});
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
