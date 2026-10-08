"""Admin-only notebooks. Structured records and images stay in local SQLite/backups."""
import html
import json
import math
import re
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote
from aiohttp import web
from lab import PORTS,validate_network,validate_params,setup_labs

SUBJECTS={'generale','italiano','storia','matematica','telecomunicazioni','sistemi_reti','scienze','altro'}
TAGS={'p','div','br','strong','b','em','i','u','s','h1','h2','h3','h4','ul','ol','li','blockquote','pre','code','table','thead','tbody','tr','td','th','sub','sup','hr','img'}

class RichText(HTMLParser):
    def __init__(self,images=(),formula_sources=None): super().__init__(convert_charrefs=True); self.output=[]; self.images=set(images); self.formula_sources=formula_sources or {}
    def handle_starttag(self,tag,attrs):
        if tag not in TAGS: return
        attributes={k:v or '' for k,v in attrs}; safe=[]
        if tag=='img':
            match=re.fullmatch(r'/api/tramonto/images/([0-9]+)(?:\?v=[0-9]+)?',attributes.get('src',''))
            if not match or int(match[1]) not in self.images: return
            safe.append(('src',match[0]))
            width=attributes.get('width','400')
            if not width.isdigit() or not 40<=int(width)<=674: width='400'
            safe.append(('width',width)); safe.append(('alt',attributes.get('alt','Immagine')[:180]))
            layout=attributes.get('data-layout','inline')
            if layout in ('inline','left','right','center'): safe.append(('data-layout',layout))
            formula=attributes.get('data-latex',self.formula_sources.get(int(match[1])))
            if formula is not None: safe.append(('data-latex',text(formula,4000)))
        if tag in ('p','div','td','th','h1','h2','h3','h4','li','blockquote','pre') and attributes.get('align') in ('left','center','right','justify'): safe.append(('align',attributes['align']))
        self.output.append('<'+tag+''.join(' '+k+'="'+html.escape(v,quote=True)+'"' for k,v in safe)+'>')
    def handle_endtag(self,tag):
        if tag in TAGS and tag not in ('br','hr','img'): self.output.append('</'+tag+'>')
    def handle_data(self,data): self.output.append(html.escape(data))

def rich_text(value,images=()):
    parser=RichText(images); parser.feed(text(value,200000)); return ''.join(parser.output)

def text(value,limit,empty=True):
    if not isinstance(value,str) or len(value)>limit or (not empty and not value.strip()): raise ValueError('Testo non valido o troppo lungo.')
    return value

def number(value,low=-10000,high=10000):
    if type(value) not in (int,float) or not math.isfinite(value) or not low<=value<=high: raise ValueError('Numero non valido.')
    return value

def identifier(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',value): raise ValueError('Identificatore non valido.')
    return value

def content_data(data):
    if not isinstance(data,dict): raise ValueError('Appunto non valido.')
    if len(json.dumps(data).encode())>1000000: raise ValueError('Appunto troppo grande; suddividilo in più pagine.')
    result={'schema':1}
    for key,choices,default in (('font',{'custom','sans','serif','mono','round','book','classic','humanist','geometric','slab','hand','script','typewriter'},'serif'),('paper',{'plain','ruled','grid','dots','cornell','engineering','music','isometric'},'plain')):
        value=data.get(key,default)
        if not isinstance(value,str) or value not in choices: raise ValueError('Stile non valido.')
        result[key]=value
    formulas=data.get('formulas',[])
    if not isinstance(formulas,list) or len(formulas)>50: raise ValueError('Troppe formule.')
    result['formulas']=[text(value,4000) for value in formulas]
    graph=data.get('graph',{'expressions':['sin(x)','cos(x)'],'x_min':-10,'x_max':10,'y_min':-2,'y_max':2})
    if not isinstance(graph,dict) or not isinstance(graph.get('expressions'),list) or not 1<=len(graph['expressions'])<=3: raise ValueError('Grafico non valido.')
    result['graph']={'expressions':[text(value,250,False) for value in graph['expressions']]}
    for key in ('x_min','x_max','y_min','y_max'): result['graph'][key]=number(graph.get(key))
    if graph['x_min']>=graph['x_max'] or graph['y_min']>=graph['y_max']: raise ValueError('Gli intervalli del grafico devono essere crescenti.')
    if 'study' in graph:
        study=graph['study']
        if not isinstance(study,dict) or type(study.get('show_area')) is not bool or type(study.get('show_derivative')) is not bool: raise ValueError('Studio del grafico non valido.')
        result['graph']['study']={'show_area':study['show_area'],'show_derivative':study['show_derivative'],'area_from':number(study.get('area_from')),'area_to':number(study.get('area_to'))}
        if result['graph']['study']['area_from']>=result['graph']['study']['area_to']: raise ValueError('Intervallo dell’area non valido.')
    limit=data.get('limit',{'expression':'sin(x)/x','point':'0','direction':'both'})
    if not isinstance(limit,dict) or limit.get('direction') not in ('left','right','both'): raise ValueError('Limite non valido.')
    result['limit']={'expression':text(limit.get('expression'),250),'point':text(limit.get('point'),40),'direction':limit['direction']}
    drawing=data.get('drawing',{'strokes':[]})
    if not isinstance(drawing,dict) or not isinstance(drawing.get('strokes'),list) or len(drawing['strokes'])>500: raise ValueError('Disegno non valido.')
    strokes=[]; total=0
    for stroke in drawing['strokes']:
        if not isinstance(stroke,dict) or not re.fullmatch(r'#[a-fA-F0-9]{6}',str(stroke.get('color',''))): raise ValueError('Colore non valido.')
        points=stroke.get('points'); total+=len(points) if isinstance(points,list) else 50001
        if not isinstance(points,list) or not 1<=len(points)<=5000 or total>50000: raise ValueError('Disegno troppo dettagliato; crea un’altra pagina.')
        if any(not isinstance(point,list) or len(point)!=2 for point in points): raise ValueError('Punto non valido.')
        clean_stroke={'color':stroke['color'],'size':number(stroke.get('size'),1,30),'points':[[number(p[0],0,1000),number(p[1],0,640)] for p in points]}
        if 'tool' in stroke:
            if stroke['tool'] not in ('pen','pencil','marker','highlighter','line','arrow','double-arrow','rectangle','ellipse','triangle','diamond','text'): raise ValueError('Strumento di disegno non valido.')
            clean_stroke['tool']=stroke['tool']
        if stroke.get('tool')=='text':
            clean_stroke.update(text=text(stroke.get('text',''),1000),font=text(stroke.get('font','serif'),30),text_size=number(stroke.get('text_size',28),8,160))
            if clean_stroke['font'] not in ('custom','serif','sans','mono','book','classic','humanist','geometric','slab','hand','script','typewriter'): raise ValueError('Font del testo non valido.')
        if 'fill' in stroke:
            if type(stroke['fill']) is not bool: raise ValueError('Riempimento non valido.')
            clean_stroke['fill']=stroke['fill']
        if 'dash' in stroke:
            if type(stroke['dash']) is not bool: raise ValueError('Tratteggio non valido.')
            clean_stroke['dash']=stroke['dash']
        strokes.append(clean_stroke)
    result['drawing']={'strokes':strokes}
    custom=data.get('custom_font')
    if custom is not None:
        if not isinstance(custom,dict) or not isinstance(custom.get('glyphs'),dict) or len(custom['glyphs'])>160: raise ValueError('Font personale non valido.')
        glyphs={};count=0
        for char,lines in custom['glyphs'].items():
            if not isinstance(char,str) or len(char)!=1 or not isinstance(lines,list) or len(lines)>100: raise ValueError('Carattere non valido.')
            glyphs[char]=[]
            for line in lines:
                if not isinstance(line,list) or not 1<=len(line)<=1000: raise ValueError('Tratto del carattere non valido.')
                count+=len(line)
                if count>30000 or any(not isinstance(p,list) or len(p)!=2 for p in line): raise ValueError('Font troppo dettagliato.')
                glyphs[char].append([[number(p[0],0,300),number(p[1],0,300)] for p in line])
        result['custom_font']={'name':text(custom.get('name','Il mio font'),60),'glyphs':glyphs,'weight':number(custom.get('weight',10),2,24)}
        if 'templates' in custom:
            templates=custom['templates']
            if not isinstance(templates,list) or len(templates)>20: raise ValueError('Troppe formule disegnate.')
            clean=[]; ids=set()
            for template in templates:
                if not isinstance(template,dict): raise ValueError('Formula disegnata non valida.')
                key=identifier(template.get('id'))
                if key in ids: raise ValueError('Formula disegnata duplicata.')
                ids.add(key); lines=template.get('strokes')
                if not isinstance(lines,list) or not 1<=len(lines)<=100: raise ValueError('Tratti della formula non validi.')
                strokes=[]
                for line in lines:
                    if not isinstance(line,list) or not 1<=len(line)<=1000: raise ValueError('Tratto della formula non valido.')
                    count+=len(line)
                    if count>30000 or any(not isinstance(p,list) or len(p)!=2 for p in line): raise ValueError('Font e formule troppo dettagliati.')
                    strokes.append([[number(p[0],0,600),number(p[1],0,220)] for p in line])
                clean.append({'id':key,'name':text(template.get('name'),60,False),'strokes':strokes})
            result['custom_font']['templates']=clean

    circuit=data.get('circuit',{'components':[],'wires':[]})
    if not isinstance(circuit,dict) or not isinstance(circuit.get('components'),list) or not isinstance(circuit.get('wires'),list) or len(circuit['components'])>100 or len(circuit['wires'])>200: raise ValueError('Schema non valido.')
    components=[]; ids={}
    for part in circuit['components']:
        if not isinstance(part,dict) or not isinstance(part.get('type'),str) or part.get('type') not in PORTS or type(part.get('rotation')) is not int or part.get('rotation') not in (0,90,180,270): raise ValueError('Componente non valido.')
        key=identifier(part.get('id'))
        if key in ids: raise ValueError('Componente duplicato.')
        ids[key]=part['type']
        components.append({'id':key,'type':part['type'],'x':number(part.get('x'),0,50000),'y':number(part.get('y'),0,50000),'rotation':part['rotation'],'label':text(part.get('label',''),40),'value':text(part.get('value',''),40)})
        if 'params' in part: components[-1]['params']=validate_params(part['params'])
    wires=[]; wire_ids=set()
    for wire in circuit['wires']:
        if not isinstance(wire,dict): raise ValueError('Filo non valido.')
        key=identifier(wire.get('id'))
        if key in wire_ids: raise ValueError('Filo duplicato.')
        wire_ids.add(key); clean={'id':key}
        for end in ('from','to'):
            point=wire.get(end)
            if not isinstance(point,dict) or not isinstance(point.get('component'),str) or point.get('component') not in ids or type(point.get('port')) is not int or not 0<=point['port']<PORTS[ids[point['component']]]: raise ValueError('Collegamento non valido.')
            clean[end]={'component':point['component'],'port':point['port']}
        if 'color' in wire:
            if not isinstance(wire['color'],str) or not re.fullmatch(r'#[a-fA-F0-9]{6}',wire['color']): raise ValueError('Colore del collegamento non valido.')
            clean['color']=wire['color']
        if 'points' in wire:
            points=wire['points']
            if not isinstance(points,list) or len(points)>100: raise ValueError('Troppi punti di svolta.')
            clean['points']=[]
            for point in points:
                if not isinstance(point,dict) or set(point)!={'x','y'}: raise ValueError('Punto di svolta non valido.')
                clean['points'].append({'x':number(point['x'],0,50000),'y':number(point['y'],0,50000)})
        wires.append(clean)
    result['circuit']={'components':components,'wires':wires}
    if 'canvas' in circuit:
        bounds=circuit['canvas']
        if not isinstance(bounds,dict) or set(bounds)!={'width','height'}: raise ValueError('Area dello schema non valida.')
        result['circuit']['canvas']={'width':number(bounds['width'],1000,50000),'height':number(bounds['height'],640,50000)}
    images=data.get('images',[])
    if not isinstance(images,list) or len(images)>30 or any(type(item) is not int or item<=0 for item in images): raise ValueError('Immagini non valide.')
    result['images']=list(dict.fromkeys(images))
    result['html']=rich_text(data.get('html',''),result['images'])
    result['network']=validate_network(data.get('network',{'nodes':[],'links':[]}))
    return result

def setup_tramonto(app,service):
    store=service.store
    def admin(request):
        identity=request.get('identity') or service.keys.identify(request.cookies.get('session',''))
        if not service.is_admin(identity['user_id']): raise PermissionError('Tramonto è riservato agli amministratori.')
        return identity['user_id']
    def owned(table,record,uid):
        try: record=int(record)
        except (ValueError,TypeError): raise PermissionError()
        if not 0<record<2**63: raise PermissionError()
        rows=store.rows('SELECT * FROM '+table+' WHERE id=? AND user_id=?',(record,uid))
        if not rows: raise PermissionError()
        return rows[0]
    async def body(request):
        if request.content_length and request.content_length>1100000: raise ValueError('Appunto troppo grande.')
        value=await request.json()
        if not isinstance(value,dict) or any(key in value for key in ('user_id','scope','owner_id')): raise PermissionError()
        return value
    async def page(request):
        try: admin(request)
        except PermissionError:
            try: service.keys.identify(request.cookies.get('session',''))
            except PermissionError: return web.HTTPFound('/?next=tramonto')
            return web.HTTPForbidden(text='Tramonto è riservato all’amministratore. Torna ad Alba: /')
        return web.FileResponse(service.settings.root/'tramonto.html')
    async def asset(request):
        admin(request); name=request.match_info['name']
        if name not in ('tramonto.js','tramonto.css','tramonto-lab.js','tramonto-font.js','tramonto-math.js','tramonto-study.js') and not (name.startswith('vendor/') and Path(name).suffix in ('.js','.css','.woff2')): raise web.HTTPNotFound()
        target=(service.settings.root/name).resolve()
        if '..' in Path(name).parts or not target.is_relative_to(service.settings.root.resolve()) or not target.is_file(): raise web.HTTPNotFound()
        return web.FileResponse(target)
    async def notebooks(request):
        uid=admin(request)
        if request.method=='GET':
            if request.query: raise PermissionError()
            return web.json_response({'notebooks':store.rows('SELECT b.*, (SELECT count(*) FROM notes n WHERE n.notebook_id=b.id AND n.user_id=b.user_id) AS note_count FROM notebooks b WHERE user_id=? ORDER BY updated DESC',(uid,))})
        value=await body(request); title=text(value.get('title','Nuovo quaderno'),80,False).strip(); now=time.time()
        record=store.execute('INSERT INTO notebooks(user_id,title,created,updated) VALUES(?,?,?,?)',(uid,title,now,now)).lastrowid
        store.audit(uid,'notebook_create',uid); return web.json_response({'id':record},status=201)
    async def notebook(request):
        uid=admin(request); record=owned('notebooks',request.match_info['id'],uid)
        if request.method=='DELETE':
            with store.db:
                store.db.execute('DELETE FROM note_images WHERE user_id=? AND note_id IN (SELECT id FROM notes WHERE notebook_id=? AND user_id=?)',(uid,record['id'],uid))
                store.db.execute('DELETE FROM notes WHERE notebook_id=? AND user_id=?',(record['id'],uid))
                store.db.execute('DELETE FROM notebooks WHERE id=? AND user_id=?',(record['id'],uid))
            store.audit(uid,'notebook_delete',uid); return web.json_response({'ok':True})
        value=await body(request); title=text(value.get('title'),80,False).strip()
        store.execute('UPDATE notebooks SET title=?,updated=? WHERE id=? AND user_id=?',(title,time.time(),record['id'],uid))
        return web.json_response({'ok':True})
    async def notes(request):
        uid=admin(request)
        if request.method=='GET':
            if set(request.query)-{'notebook','q'}: raise PermissionError()
            query='SELECT id,notebook_id,title,subject,version,updated FROM notes WHERE user_id=?'; args=[uid]
            if request.query.get('notebook'):
                book=owned('notebooks',request.query['notebook'],uid); query+=' AND notebook_id=?'; args.append(book['id'])
            search=request.query.get('q','')[:100]
            if search: query+=' AND (title LIKE ? OR content LIKE ?)'; args.extend(['%'+search+'%']*2)
            query=query.replace('SELECT id,notebook_id,title,subject,version,updated','SELECT id,notebook_id,title,subject,version,updated, (SELECT count(*) FROM notes p WHERE p.user_id=notes.user_id AND p.notebook_id=notes.notebook_id AND p.id<=notes.id) AS page_number')
            return web.json_response({'notes':store.rows(query+' ORDER BY id ASC LIMIT 500',args)})
        value=await body(request); book=owned('notebooks',value.get('notebook_id'),uid); now=time.time()
        subject=value.get('subject','generale')
        if not isinstance(subject,str) or subject not in SUBJECTS: raise ValueError('Materia non valida.')
        content=content_data(value.get('content',{}))
        source_id=value.get('copy_images_from')
        if content['images']:
            source=owned('notes',source_id,uid); mapping={}
            for image_id in content['images']:
                image_record=owned('note_images',image_id,uid)
                if image_record['note_id']!=source['id']: raise PermissionError()
                mapping[image_id]=image_record
        else: mapping={} 
        record=store.execute('INSERT INTO notes(user_id,notebook_id,title,subject,content,created,updated) VALUES(?,?,?,?,?,?,?)',
                            (uid,book['id'],text(value.get('title','Nuovo appunto'),180,False).strip(),subject,json.dumps(content,ensure_ascii=False),now,now)).lastrowid
        if mapping:
            html_value=content['html']; image_ids=[]
            for old,asset in mapping.items():
                copied=store.execute('INSERT INTO note_images(user_id,note_id,name,mime,data,created) VALUES(?,?,?,?,?,?)',(uid,record,asset['name'],asset['mime'],asset['data'],now)).lastrowid
                image_ids.append(copied)
                html_value=re.sub(r'(/api/tramonto/images/)'+str(old)+r'(?=["\s>?])',lambda m:m[1]+str(copied),html_value)
            content.update(images=image_ids,html=html_value); store.execute('UPDATE notes SET content=? WHERE id=?',(json.dumps(content,ensure_ascii=False),record))
        store.execute('UPDATE notebooks SET updated=? WHERE id=?',(now,book['id']))
        return web.json_response({'id':record,'version':1},status=201)
    async def note(request):
        uid=admin(request); record=owned('notes',request.match_info['id'],uid)
        if request.method=='GET':
            record['content']=content_data(json.loads(record['content']))
            # Recover original formula images only when their order is unambiguous.
            content=record['content'];formulas=content['formulas'];assets=store.rows('SELECT id,name FROM note_images WHERE note_id=? AND user_id=? ORDER BY id',(record['id'],uid))
            primary=[a for a in assets if a['name']=='formulaPreview.png'];sources={}
            if len(primary)==len(formulas): sources={a['id']:formula for a,formula in zip(primary,formulas)}
            for asset in assets:
                saved=re.fullmatch(r'savedFormula([0-9]+)\.png',asset['name'])
                if saved and int(saved[1])<len(formulas): sources[asset['id']]=formulas[int(saved[1])]
            parser=RichText(content['images'],sources);parser.feed(content['html']);content['html']=''.join(parser.output)
            record['page_number']=store.rows('SELECT count(*) AS n FROM notes WHERE user_id=? AND notebook_id=? AND id<=?',(uid,record['notebook_id'],record['id']))[0]['n']; record.pop('user_id'); return web.json_response(record)
        if request.method=='DELETE':
            with store.db:
                store.db.execute('DELETE FROM note_images WHERE note_id=? AND user_id=?',(record['id'],uid))
                store.db.execute('DELETE FROM notes WHERE id=? AND user_id=?',(record['id'],uid))
            store.audit(uid,'note_delete',uid); return web.json_response({'ok':True})
        value=await body(request); content=content_data(value.get('content',{})); subject=value.get('subject',record['subject'])
        if not isinstance(subject,str) or subject not in SUBJECTS or type(value.get('version')) is not int: raise ValueError('Versione o materia non valida.')
        book=owned('notebooks',value.get('notebook_id',record['notebook_id']),uid)
        for image in content['images']:
            asset_record=owned('note_images',image,uid)
            if asset_record['note_id']!=record['id']: raise PermissionError()
        now=time.time()
        changed=store.execute('UPDATE notes SET title=?,subject=?,notebook_id=?,content=?,updated=?,version=version+1 WHERE id=? AND user_id=? AND version=?',
             (text(value.get('title',record['title']),180,False).strip(),subject,book['id'],json.dumps(content,ensure_ascii=False),now,record['id'],uid,value['version']))
        if not changed.rowcount: return web.json_response({'error':'La pagina è cambiata su un altro dispositivo. Esporta le modifiche o ricaricala prima di salvare.','code':'version_conflict'},status=409)
        store.execute('UPDATE notebooks SET updated=? WHERE id=?',(now,book['id']))
        return web.json_response({'ok':True,'version':value['version']+1,'updated':now})
    async def upload(request):
        uid=admin(request); record=owned('notes',request.match_info['id'],uid)
        if request.content_length and request.content_length>8*1024*1024: raise ValueError('Immagine troppo grande: massimo 8 MB.')
        data=await request.read()
        if len(data)>8*1024*1024: raise ValueError('Immagine troppo grande.')
        mime=('image/png' if data.startswith(b'\x89PNG\r\n\x1a\n') else 'image/jpeg' if data.startswith(b'\xff\xd8\xff') else 'image/gif' if data.startswith((b'GIF87a',b'GIF89a')) else 'image/webp' if data[:4]==b'RIFF' and data[8:12]==b'WEBP' else None)
        if not mime: raise ValueError('Usa PNG, JPEG, GIF o WebP.')
        replacement=request.headers.get('X-Replace-Image')
        if replacement:
            previous=owned('note_images',replacement,uid)
            if previous['note_id']!=record['id']: raise PermissionError()
        if not replacement and store.rows('SELECT count(*) AS n FROM note_images WHERE note_id=?',(record['id'],))[0]['n']>=30: raise ValueError('Massimo trenta immagini per pagina.')
        name=text(unquote(request.headers.get('X-Image-Name','Immagine')),180)
        if replacement:
            store.execute('UPDATE note_images SET mime=?,data=? WHERE id=? AND user_id=?',(mime,data,previous['id'],uid))
            return web.json_response({'id':previous['id'],'name':previous['name'],'mime':mime})
        record_id=store.execute('INSERT INTO note_images(user_id,note_id,name,mime,data,created) VALUES(?,?,?,?,?,?)',(uid,record['id'],name,mime,data,time.time())).lastrowid
        return web.json_response({'id':record_id,'name':name,'mime':mime},status=201)
    async def image(request):
        uid=admin(request); record=owned('note_images',request.match_info['id'],uid)
        if request.method=='DELETE':
            note_record=owned('notes',record['note_id'],uid); data=json.loads(note_record['content'])
            data['images']=[value for value in data['images'] if value!=record['id']]
            with store.db:
                store.db.execute('DELETE FROM note_images WHERE id=? AND user_id=?',(record['id'],uid))
                store.db.execute('UPDATE notes SET content=?,version=version+1,updated=? WHERE id=? AND user_id=?',(json.dumps(data,ensure_ascii=False),time.time(),record['note_id'],uid))
            return web.json_response({'ok':True})
        return web.Response(body=record['data'],content_type=record['mime'],headers={'Content-Disposition':'inline'})
    async def workspace(request):
        uid=admin(request)
        if request.method=='GET':
            rows=store.rows('SELECT notebook_id,note_id,scroll_y FROM workspace_state WHERE user_id=?',(uid,))
            value=rows[0] if rows else {}
            if value:
                try: owned('notes',value['note_id'],uid); owned('notebooks',value['notebook_id'],uid)
                except PermissionError: value={}
            return web.json_response(value)
        value=await body(request); note_record=owned('notes',value.get('note_id'),uid)
        if value.get('notebook_id')!=note_record['notebook_id']: raise PermissionError()
        position=number(value.get('scroll_y',0),0,100000)
        store.execute('INSERT INTO workspace_state VALUES(?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET notebook_id=excluded.notebook_id,note_id=excluded.note_id,scroll_y=excluded.scroll_y,updated=excluded.updated',
                      (uid,note_record['notebook_id'],note_record['id'],position,time.time()))
        return web.json_response({'ok':True})
    app.add_routes([web.get('/tramonto',page),web.get('/tramonto-assets/{name:.+}',asset),
        web.get('/api/tramonto/notebooks',notebooks),web.post('/api/tramonto/notebooks',notebooks),
        web.patch('/api/tramonto/notebooks/{id}',notebook),web.delete('/api/tramonto/notebooks/{id}',notebook),
        web.get('/api/tramonto/notes',notes),web.post('/api/tramonto/notes',notes),
        web.get('/api/tramonto/notes/{id}',note),web.put('/api/tramonto/notes/{id}',note),web.delete('/api/tramonto/notes/{id}',note),
        web.post('/api/tramonto/notes/{id}/images',upload),web.get('/api/tramonto/images/{id}',image),web.delete('/api/tramonto/images/{id}',image)])
    app.add_routes([web.get('/api/tramonto/workspace',workspace),web.post('/api/tramonto/workspace',workspace)])
    setup_labs(app,service,admin,owned,body)
