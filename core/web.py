"""Admin-only Notte endpoints; existing session, origin and CSRF checks apply."""
import asyncio
import json
from aiohttp import web
from .runtime import Core, CONNECTORS


def setup_core(app, service):
    core = getattr(service, 'core', None) or Core(service)
    service.core = core

    def admin(request):
        identity = request.get('identity') or service.keys.identify(request.cookies.get('session',''))
        if not service.is_admin(identity['user_id']): raise PermissionError('Notte è riservata all’amministratore.')
        return identity['user_id']

    async def page(request):
        try: admin(request)
        except PermissionError: return web.HTTPFound('/?next=notte')
        return web.FileResponse(service.settings.root/'notte.html')

    async def asset(request):
        admin(request)
        name = request.match_info['name']
        if name not in ('notte.js','notte.css','marked.min.js','purify.min.js'): raise web.HTTPNotFound()
        path = service.settings.root/('vendor/'+name if name.endswith('.min.js') else name)
        return web.FileResponse(path)

    async def status(request):
        admin(request)
        return web.json_response(core.snapshot())

    async def models(request):
        admin(request)
        return web.json_response({'models':await core.inference.models()})

    async def ssd_plan(request):
        admin(request)
        try:context=int(request.query.get('context','1024'))
        except ValueError:raise ValueError('Contesto non valido.')
        return web.json_response(core.ssd.planning(request.query.get('model',core.config['advanced_code_model']),context))

    async def lab(request):
        uid=admin(request)
        if request.method=='GET':return web.json_response(core.test_lab.snapshot())
        from .test_lab import validate
        value=validate(await request.json())
        core.start('test_lab',json.dumps(value))
        core.store.audit(uid,'core_test_lab',uid)
        return web.json_response({'ok':True},status=202)

    async def lab_export(request):
        admin(request)
        try:ident=int(request.match_info['id'])
        except ValueError:raise web.HTTPNotFound()
        rows=core.store.rows('SELECT * FROM core_lab_runs WHERE id=?',(ident,))
        if not rows:raise web.HTTPNotFound()
        value={**rows[0],'config':json.loads(rows[0]['config']),'result':json.loads(rows[0]['result'])}
        return web.json_response(value,headers={'Content-Disposition':'attachment; filename=notte-lab-'+str(ident)+'.json'})

    async def optimization(request):
        return web.FileResponse(service.settings.root/'optimization.html')

    async def optimization_data(request):
        from .optimization_project import project_data
        return web.json_response(project_data(service.settings.root))

    async def native_project(request):
        admin(request)
        return await optimization_data(request)

    async def optimization_asset(request):
        name=request.match_info['name']
        if name not in ('optimization.js','optimization.css'):raise web.HTTPNotFound()
        return web.FileResponse(service.settings.root/name)

    async def optimization_report(request):
        name=request.match_info['name']
        if name not in ('SSD_RUNTIME.md','SSD_RUNTIME_RESULTS.md','SSD_RUNTIME_RESULTS.json','TEST_LAB.md','TESTING_REPORTS.md',
                        'TEST_LAB_RESULTS.md','TEST_LAB_RESULTS.json','test-lab-comparison.png','test-lab-comparison.svg',
                        '7b-decode.png','7b-decode.svg','checkpoint.png','checkpoint.svg','chat-latency.png','chat-latency.svg','14b-decode.png','14b-decode.svg'):
            raise web.HTTPNotFound()
        path=service.settings.root/'docs'/('ssd-results/'+name if name.endswith(('.png','.svg')) else name)
        if not path.is_file():raise web.HTTPNotFound()
        return web.FileResponse(path)

    async def events(request):
        admin(request)
        category = request.query.get('category','chat')
        if category not in (*CONNECTORS,'all'): raise ValueError('Connettore non valido.')
        try:
            after = int(request.query.get('after','0'))
            before = int(request.query.get('before','0'))
        except ValueError: raise ValueError('Cursore non valido.')
        if after < 0 or before < 0 or (after and before): raise ValueError('Cursore non valido.')
        if before:
            rows=list(reversed(core.store.rows('SELECT * FROM core_events WHERE id<? ORDER BY id DESC LIMIT 100',(before,)))) if category=='all' else list(reversed(core.store.rows('SELECT * FROM core_events WHERE category=? AND id<? ORDER BY id DESC LIMIT 100',(category,before))))
        elif category=='all':
            rows=core.store.rows('SELECT * FROM core_events WHERE id>? ORDER BY id LIMIT 100',(after,)) if after else list(reversed(core.store.rows('SELECT * FROM core_events ORDER BY id DESC LIMIT 100')))
        elif after:
            rows = core.store.rows('SELECT * FROM core_events WHERE category=? AND id>? ORDER BY id LIMIT 100',(category,after))
        else:
            rows = list(reversed(core.store.rows('SELECT * FROM core_events WHERE category=? ORDER BY id DESC LIMIT 100',(category,))))
        return web.json_response({'events':rows,'before':rows[0]['id'] if rows else 0})

    async def action(request):
        uid = admin(request)
        value = await request.json()
        if not isinstance(value,dict): raise ValueError('Azione non valida.')
        name = value.get('action')
        if name=='config': core.configure(value.get('config'))
        elif name in ('chat','reflection','consolidation','study','repository','tool','reddit','benchmark','ssd_benchmark','ssd_cache_probe'): core.start(name,value.get('text',''))
        elif name=='train': core.training.start()
        elif name=='stop_training': await core.training.stop()
        elif name=='personal_chat': core.start(name,value.get('text',''))
        elif name=='rollback':
            ident=value.get('id')
            if type(ident) is not int:raise ValueError('Versione non valida.')
            rows=core.store.rows("SELECT * FROM core_training WHERE id=? AND status='ready'",(ident,))
            if not rows or not (core.training.root/'runs'/str(ident)/'adapter').is_dir():raise ValueError('Checkpoint non disponibile.')
            if core.training.task and not core.training.task.done():raise ValueError('Ferma prima il training.')
            core.config['personal_model']=rows[0]['model'];core.config['personal_adapter']=str(ident);core.save()
            core.event('training','rollback','Ripristinata versione '+str(ident))
        elif name=='stop':
            if core.task and not core.task.done(): core.task.cancel(); await asyncio.gather(core.task,return_exceptions=True)
        elif name=='reset_stats':
            import time
            core.store.set_setting('core_stats_since',time.time())
        elif name=='import':
            text = value.get('text')
            if not isinstance(text,str) or not 1<=len(text)<=12000: raise ValueError('Importa al massimo 12.000 caratteri.')
            core.event('files','document',text)
        else: raise ValueError('Azione non valida.')
        core.store.audit(uid,'core_'+name,uid)
        return web.json_response({'ok':True},status=202 if name in ('chat','reflection','consolidation','study','repository','tool','reddit','benchmark','ssd_benchmark','ssd_cache_probe') else 200)

    async def diary(request):
        admin(request)
        return web.json_response({'entries':core.learning.diary(request.query.get('topic',''))})

    async def export(request):
        admin(request)
        return web.json_response(core.snapshot(),headers={'Content-Disposition':'attachment; filename=alba-core-statistiche.json'})

    async def training_files(request):
        admin(request)
        return web.json_response(core.training.files(request.match_info['id']))

    sockets = set()
    async def stream(request):
        admin(request)
        if len(sockets)>=5: raise web.HTTPTooManyRequests()
        socket = web.WebSocketResponse(heartbeat=30,max_msg_size=1024)
        await socket.prepare(request)
        sockets.add(socket)
        try:
            while not socket.closed:
                # Recheck access and revocations throughout the connection.
                identity = service.keys.identify(request.cookies.get('session',''))
                if not service.is_admin(identity['user_id']): break
                await socket.send_json({'running':core.running,'mood':core.mood(),'partial':core.partial,
                    'last_id':core.store.rows('SELECT coalesce(max(id),0) n FROM core_events')[0]['n']})
                try:
                    message = await asyncio.wait_for(socket.receive(),timeout=2)
                    if message.type in (web.WSMsgType.CLOSE,web.WSMsgType.CLOSED,web.WSMsgType.ERROR): break
                except asyncio.TimeoutError: pass
        except (PermissionError,ConnectionError,RuntimeError): pass
        finally:
            sockets.discard(socket)
            await socket.close()
        return socket

    async def cleanup(app):
        await core.training.stop()
        await asyncio.gather(*(s.close() for s in list(sockets)),return_exceptions=True)
        if core.task and not core.task.done():
            core.task.cancel()
            await asyncio.gather(core.task,return_exceptions=True)
        await core.ssd.stop()
    app.on_cleanup.append(cleanup)

    async def assetlinks(request):
        path = service.settings.root/'dist/assetlinks.json'
        if not path.exists(): return web.json_response([])
        return web.FileResponse(path,headers={'Content-Type':'application/json'})

    app.add_routes([web.get('/notte',page),web.get('/notte-assets/{name}',asset),
        web.get('/optimization',optimization),web.get('/optimization/data',optimization_data),
        web.get('/optimization/assets/{name}',optimization_asset),web.get('/optimization/reports/{name}',optimization_report),
        web.get('/api/notte/lab',lab),web.post('/api/notte/lab',lab),web.get('/api/notte/lab/{id}/export',lab_export),
        web.get('/api/notte/project',native_project),
        web.get('/api/notte/status',status),web.get('/api/notte/models',models),web.get('/api/notte/ssd-plan',ssd_plan),web.get('/api/notte/events',events),web.get('/api/notte/diary',diary),web.get('/api/notte/training/{id}',training_files),
        web.post('/api/notte/action',action),web.get('/api/notte/export',export),
        web.get('/api/notte/stream',stream),web.get('/.well-known/assetlinks.json',assetlinks)])
