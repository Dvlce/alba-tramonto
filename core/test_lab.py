"""Private, sequential same-prompt tests; never changes production profiles."""
import asyncio
import json
import re
import time


def validate(value):
    allowed = {'model', 'prompt', 'mode', 'policy', 'context', 'output'}
    if not isinstance(value, dict) or set(value) - allowed:
        raise ValueError('Configurazione Test Lab non valida.')
    model, prompt = value.get('model'), value.get('prompt')
    if not isinstance(model, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_./:-]{0,180}', model) or '..' in model:
        raise ValueError('Modello non valido.')
    if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 2000:
        raise ValueError('Prompt da 1 a 2.000 caratteri.')
    mode, policy = value.get('mode', 'compare'), value.get('policy', 'mapped')
    context, output = value.get('context', 1024), value.get('output', 96)
    if mode not in ('normal', 'optimized', 'compare') or policy not in ('adaptive','warm','cpu2','mapped','speculative','native','compact'):
        raise ValueError('Modalità Test Lab non valida.')
    if type(context) is not int or context not in (512, 1024, 2048):
        raise ValueError('Contesto: 512, 1024 o 2048 token.')
    if type(output) is not int or not 8 <= output <= 256:
        raise ValueError('Output: da 8 a 256 token.')
    # No truncation: reject prompts too long for the selected context.
    if len(prompt) // 2 + output + 96 > context:
        raise ValueError('Prompt troppo lungo per il contesto: aumenta il contesto o riduci il prompt.')
    return dict(model=model, prompt=prompt.strip(), mode=mode, policy=policy,
                context=context, output=output)


class TestLab:
    def __init__(self, core):
        self.core = core
        self.active = None
        core.store.db.executescript('''CREATE TABLE IF NOT EXISTS core_lab_runs(
            id INTEGER PRIMARY KEY, config TEXT NOT NULL, status TEXT NOT NULL,
            result TEXT NOT NULL, created REAL NOT NULL, finished REAL);''')
        # A process restart must not present abandoned tests as still running.
        core.store.execute("UPDATE core_lab_runs SET status='interrupted',finished=? WHERE status='running'", (time.time(),))

    def snapshot(self):
        rows = self.core.store.rows('SELECT * FROM core_lab_runs ORDER BY id DESC LIMIT 30')
        return {'active': self.active, 'runs': [{**r, 'config': json.loads(r['config']),
                                               'result': json.loads(r['result'])} for r in rows]}

    def persist(self, ident, config, status, result):
        self.core.store.execute('UPDATE core_lab_runs SET status=?,result=?,finished=? WHERE id=?',
                                (status, json.dumps(result, ensure_ascii=False),
                                 None if status == 'running' else time.time(), ident))

    async def identity(self, model):
        async with self.core.engine.session.post(self.core.settings.llm_url + '/api/show',
                                                json={'model': model}, timeout=20) as response:
            if response.status != 200:
                raise ValueError('Identità del modello Ollama non disponibile.')
            value = await response.json()
        found = re.search(r'^FROM\s+.*sha256[-:]([a-f0-9]{64})\s*$', value.get('modelfile', ''), re.M)
        return found[1] if found else None

    async def sample(self, config, backend, sample):
        start = time.monotonic()
        first = None
        ended = False
        sample.update({'backend': backend, 'model': config['model'], 'content': '', 'status': 'running',
                       'resources_before': self.core.resources(), 'tokens': []})
        if backend == 'normal' or config['policy'] in ('adaptive','warm','cpu2'):
            await self.core.ssd.stop()
            if backend=='normal': await self.core.ssd.unload_ollama()
            url = self.core.settings.llm_url + '/api/chat'
            headers = {}
            body = {'model': config['model'], 'stream': True, 'think': False, 'keep_alive': '2m' if config['policy'] in ('adaptive','warm','cpu2') else 0,
                    'messages': [{'role': 'user', 'content': config['prompt']}],
                    'options': {'num_ctx': config['context'], 'num_predict': config['output'],
                                'temperature': 0, 'seed': 42, 'num_thread': 4}}
        else:
            await self.core.ssd.start(config['model'], config['policy'], config['context'])
            template = await self.core.ssd.template([{'role': 'user', 'content': config['prompt']}])
            url = 'http://127.0.0.1:8092/completion'
            headers = self.core.ssd.headers
            body = {'prompt': template, 'stream': True, 'n_predict': config['output'],
                    'temperature': 0, 'seed': 42, 'cache_prompt': False, 'return_tokens': True}
            sample.update({'policy': config['policy'], 'sha256': self.core.ssd.catalog()[config['model']]['sha256']})
        if backend=='optimized' and config['policy']=='adaptive':
            from .generation_policy import plan, assemble
            from .inference import FAST_PROMPT
            selected=plan(config['prompt'],ceiling=config['context'],context_floor=config['context'])
            selected['output_tokens']=min(config['output'],selected['output_tokens'])
            messages,budget=assemble(FAST_PROMPT,config['prompt'],[],[],{},selected)
            body['messages']=messages
            body['options'].update(num_ctx=selected['context_tokens'],num_predict=selected['output_tokens'],num_thread=4,use_mmap=True)
            sample.update(policy='adaptive',sha256=await self.identity(config['model']),generation=budget)
        if backend=='optimized' and config['policy'] in ('warm','cpu2'):
            body['options']['num_thread']=2 if config['policy']=='cpu2' else 4
            sample.update(policy=config['policy'],sha256=await self.identity(config['model']))
        async with self.core.engine.session.post(url, headers=headers, json=body, timeout=240) as response:
            if response.status != 200:
                raise ValueError('Generazione Test Lab HTTP ' + str(response.status))
            async for line in response.content:
                if len(line) > 65536:
                    raise ValueError('Frame Test Lab troppo lungo.')
                if backend == 'optimized' and config['policy'] not in ('adaptive','warm','cpu2'):
                    if not line.startswith(b'data:'):
                        continue
                    line = line[5:].strip()
                    if line == b'[DONE]':
                        continue
                if not line.strip():
                    continue
                part = json.loads(line)
                if part.get('error'):
                    raise ValueError('Errore di generazione Test Lab.')
                chunk = part.get('message', {}).get('content', '') if backend == 'normal' or config['policy'] in ('adaptive','warm','cpu2') else part.get('content', '')
                if chunk and first is None:
                    first = time.monotonic()
                    sample['first_token_ms'] = round((first - start) * 1000)
                sample['content'] += chunk
                if len(sample['content']) > 16000:
                    raise ValueError('Output Test Lab troppo lungo.')
                if backend == 'optimized' and config['policy'] not in ('adaptive','warm','cpu2'):
                    sample['tokens'].extend(part.get('tokens') or [])
                if part.get('done') or part.get('stop'):
                    ended = True
                    if backend == 'normal' or config['policy'] in ('adaptive','warm','cpu2'):
                        prompt_n, output_n = part.get('prompt_eval_count'), part.get('eval_count')
                        seconds = part.get('eval_duration', 0) / 1e9
                        rate = output_n / seconds if seconds and output_n is not None else None
                        sample['load_ms'] = round(part.get('load_duration', 0) / 1e6)
                    else:
                        timing = part.get('timings', {})
                        sample['timings'] = timing
                        prompt_n, output_n = timing.get('prompt_n'), timing.get('predicted_n')
                        rate = timing.get('predicted_per_second')
                    sample.update({'prompt_tokens': prompt_n, 'output_tokens': output_n,
                                   'tokens_per_second': rate,'output_limit_reached':part.get('done_reason')=='length'})
                    self.core.tokens('benchmark', prompt_n, output_n)
        if not ended or not sample['content'].strip() or self.core.ssd.failure and backend == 'optimized' and config['policy'] not in ('adaptive','warm','cpu2'):
            raise ValueError(self.core.ssd.failure or 'Risposta Test Lab incompleta.')
        sample.update({'wall_ms': round((time.monotonic() - start) * 1000), 'status': 'ok',
                       'resources_after': self.core.resources()})
        if backend == 'optimized' and config['policy'] not in ('adaptive','warm','cpu2'):
            sample['peak'] = dict(self.core.ssd.peak)

    async def run(self, value):
        config = validate(value)
        installed = {m['name']: m for m in await self.core.inference.models()}
        if config['model'] not in installed:
            raise ValueError('Modello non installato.')
        if (config['mode'] in ('normal', 'compare') or config['policy'] in ('adaptive','warm','cpu2')) and installed[config['model']].get('size', 0) > 6 * 1024**3:
            raise ValueError('Oltre 6 GiB la prova normale Ollama non è ammessa su questo Pi; scegli solo SSD.')
        actual_sha = await self.identity(config['model'])
        if config['mode'] != 'normal' and config['policy'] not in ('adaptive','warm','cpu2'):
            self.core.ssd.planning(config['model'], config['context'])
            registered = self.core.ssd.catalog()[config['model']]['sha256']
            if not actual_sha or actual_sha != registered:
                raise ValueError('I pesi Ollama e SSD non coincidono: registra nuovamente il modello prima del confronto.')
        if config['mode']!='normal' and not actual_sha:
            raise ValueError('Identità GGUF non verificabile: confronto annullato.')
        status = 'running'
        result = {'samples': [], 'weights_sha256': actual_sha, 'same_text': None, 'same_tokens': None,
                  'quality_check': 'No automatic intelligence verdict; inspect both outputs.',
                  'conditions': 'Sequential, normal first; startup included; OS file cache not cleared; no personal history. Warm/CPU2 retain standard model for the second run. Flux changes prompt instructions and output/context budgets. KV8 changes KV precision, not weights.'}
        ident = self.core.store.execute('INSERT INTO core_lab_runs(config,status,result,created) VALUES(?,?,?,?)',
                                       (json.dumps(config), status, json.dumps(result), time.time())).lastrowid
        self.active = {'id': ident, 'backend': None, 'samples': result['samples']}
        self.core.event('activity', 'lab_start', json.dumps({'id': ident, 'model': config['model'], 'mode': config['mode']}))
        try:
            backends = ('normal', 'optimized') if config['mode'] == 'compare' else (config['mode'],)
            for backend in backends:
                sample = {}
                sample_started = time.monotonic()
                result['samples'].append(sample)
                self.active['backend'] = backend
                try:
                    await self.sample(config, backend, sample)
                except asyncio.CancelledError:
                    sample['status'] = 'interrupted'
                    raise
                except Exception as exc:
                    sample.update({'status': 'error', 'error': str(exc)[:300] or type(exc).__name__})
                finally:
                    if 'wall_ms' not in sample:sample['wall_ms']=round((time.monotonic()-sample_started)*1000)
                    await self.core.ssd.stop()
                    self.persist(ident, config, 'running', result)
            if len(result['samples']) == 2 and all(s['status'] == 'ok' for s in result['samples']):
                left, right = result['samples']
                result['same_text'] = left['content'] == right['content']
                # Ollama's chat stream does not return token IDs. Text equality
                # cannot be presented as token identity or an intelligence test.
                rates = [s.get('tokens_per_second') for s in result['samples']]
                result['decode_change_percent'] = round((rates[1] / rates[0] - 1) * 100, 2) if all(rates) else None
            status = 'ok' if all(s['status'] == 'ok' for s in result['samples']) else 'error'
        except asyncio.CancelledError:
            status = 'interrupted'
            raise
        finally:
            await self.core.ssd.stop()
            self.persist(ident, config, status, result)
            self.active = None
            self.core.event('activity', 'lab_result', json.dumps({'id': ident, 'model': config['model'], 'status': status}))
