"""Explicit Pi-only real-model smoke test. Temporary memory; no external sends."""
import asyncio
import json
import sys
import tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from aiohttp import ClientSession
from config import Settings
from store import Store
from security import Keys,secret_file
from backups import Backups
from engine import Engine
from service import Service
from core.runtime import Core


async def main():
    with tempfile.TemporaryDirectory(prefix='alba-core-smoke-') as folder:
        settings=Settings(root=Path(folder),admins=(1,))
        store=Store(settings.data/'alba.sqlite3')
        async with ClientSession(trust_env=False) as session:
            keys=Keys(store,secret_file(settings.data/'auth.key'))
            service=Service(store,settings,keys,Engine(store,settings,session),Backups(store,settings))
            core=Core(service);service.core=core
            core.configure({'enabled':False,'web_enabled':False})
            await core.work('chat','Mi interessano i telescopi. Quale curiosità vorresti esplorare?')
            assert not core.error,core.error
            assert store.rows("SELECT * FROM core_events WHERE role='assistant'"),'Nessun messaggio dal modello.'
            await core.work('consolidation')
            assert not core.error,core.error
            assert not core.config['embedding_error'],core.config['embedding_error']
            vectors=store.rows('SELECT embedding FROM core_chunks WHERE embedding IS NOT NULL')
            assert vectors,'Nessun embedding reale.'
            retrieved=await core.retrieve('telescopi')
            assert retrieved,'Memoria non recuperata.'
            state=core.snapshot()
            print(json.dumps({'model':core.config['model'],'events':store.rows('SELECT count(*) n FROM core_events')[0]['n'],
                'chunks':len(vectors),'dimensions':len(json.loads(vectors[0]['embedding'])),
                'retrieved':len(retrieved),'mood':state['mood'],'tokens':state['lifetime_tokens'],
                'temperature':state['resources'].get('temperature_c'),'cycles':state['cycles'][0]['status']},ensure_ascii=False))
        store.close()


if __name__=='__main__':asyncio.run(main())
