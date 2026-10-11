"""Explicit real-model teaching/reload probe with a temporary private database.

Run on the Pi after training: .venv/bin/python tests/notte_learning_pi_smoke.py
--model notte-personal:YYYYMMDD-ID. No external messages or production lessons.
"""
import argparse
import asyncio
import json
import secrets
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from aiohttp import ClientSession
from backups import Backups
from config import Settings
from core.runtime import Core
from engine import Engine
from security import Keys,secret_file
from service import Service
from store import Store


async def main(model):
    with tempfile.TemporaryDirectory(prefix='notte-learning-probe-') as folder:
        settings=Settings(root=Path(folder),admins=(1,))
        async with ClientSession(trust_env=False) as session:
            store=Store(settings.data/'alba.sqlite3')
            keys=Keys(store,secret_file(settings.data/'auth.key'))
            service=Service(store,settings,keys,Engine(store,settings,session),Backups(store,settings))
            core=Core(service)
            core.configure({'enabled':False,'web_enabled':False,'online_lookup':False,'personal_enabled':True})
            core.config.update(personal_model=model,model=model);core.save()
            marker='AURORA-'+secrets.token_hex(4).upper()
            core.knowledge.teach({'title':'Laboratorio Galileo',
                'text':'Il codice identificativo completo del laboratorio Galileo è '+marker+'. Il suffisso dopo il trattino è parte del codice.'})
            retrieved=await core.retrieve('parola laboratorio Galileo',prefer_lexical=True)
            assert retrieved and marker in retrieved[0]['content'],'Lesson not immediately searchable'
            await core.work('chat','Qual è il codice identificativo completo del laboratorio Galileo? Riportalo esattamente, incluso il suffisso dopo il trattino. Rispondi solo con il codice.')
            assert not core.error,core.error
            answers=store.rows("SELECT content FROM core_events WHERE category='chat' AND role='assistant' ORDER BY id DESC LIMIT 1")
            assert answers and marker in answers[0]['content'],('Real model did not use the newly taught fact: expected '+marker+'; got '+(answers[0]['content'][:500] if answers else '(empty)'))
            latency=store.rows("SELECT content FROM core_events WHERE category='activity' AND role='latency' ORDER BY id DESC LIMIT 1")
            metrics=json.loads(latency[0]['content']);store.close()
            store=Store(settings.data/'alba.sqlite3')
            keys=Keys(store,secret_file(settings.data/'auth.key'))
            service=Service(store,settings,keys,Engine(store,settings,session),Backups(store,settings))
            restored=Core(service)
            rows=await restored.retrieve('parola laboratorio Galileo',prefer_lexical=True)
            assert rows and marker in rows[0]['content'],'Stored lesson lost after reopening'
            print(json.dumps({'model':model,'new_fact_used':True,'persistent_after_reload':True,
                'retrieved_sources':len(rows),'output_tokens':metrics['output_tokens'],
                'tokens_per_second':metrics['tokens_per_second'],'total_ms':metrics['total_ms']}))
            store.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--model',required=True)
    asyncio.run(main(parser.parse_args().model))
