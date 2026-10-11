"""Read-only public listings through an explicitly approved Reddit application."""
import json
import os
import re
import time
from aiohttp import BasicAuth
from .reddit import MAX_BYTES, MAX_POSTS, subreddit_name


def listing_entries(raw, group):
    try:
        value=json.loads(raw)
        entries=value['data']['children']
        if not isinstance(entries,list):raise ValueError()
    except (ValueError,KeyError,TypeError) as exc:
        raise ValueError('Reddit non ha restituito un elenco pubblico valido.') from exc
    rows=[];seen=set()
    for item in entries[:100]:
        if not isinstance(item,dict) or item.get('kind')!='t3':continue
        post=item.get('data',{})
        if not isinstance(post,dict):continue
        ident=post.get('id','');title=post.get('title','');text=post.get('selftext','')
        subreddit=post.get('subreddit','')
        if (not isinstance(ident,str) or not re.fullmatch('[a-z0-9]+',ident) or ident in seen
                or not isinstance(title,str) or not isinstance(text,str)
                or not isinstance(subreddit,str) or subreddit.casefold()!=group or post.get('over_18')
                or post.get('subreddit_type')=='private'
                or title.strip().lower() in ('','[deleted]','[removed]')
                or text.strip().lower() in ('[deleted]','[removed]')):continue
        seen.add(ident)
        rows.append({'id':ident,'subreddit':group,'title':title[:250],'excerpt':text.strip()[:9000],
            'url':'https://www.reddit.com/r/'+group+'/comments/'+ident+'/',
            'revision':str(post.get('edited') or post.get('created_utc') or '')[:80]})
        if len(rows)>=MAX_POSTS:break
    return rows


class RedditClient:
    def __init__(self,core):
        self.core=core
        self.client_id=os.environ.get('REDDIT_CLIENT_ID','')
        self.secret=os.environ.get('REDDIT_CLIENT_SECRET','')
        self.approved=os.environ.get('REDDIT_API_APPROVED','').lower() in ('1','true','yes')
        self.token='';self.expires=0
        self.agent='Notte/1.8 (https://github.com/Dvlce/alba-tramonto; public-read-only)'

    @property
    def configured(self):
        return bool(self.approved and self.client_id and self.secret)

    async def read(self,response,limit):
        from .learning import PublicSourceError,retry_delay
        if response.status!=200:
            seconds=retry_delay(response.headers.get('Retry-After',''))
            raise PublicSourceError('Accesso API Reddit non disponibile (HTTP '+str(response.status)+'). Verifica approvazione, credenziali e quota della tua app.',response.status,seconds)
        data=bytearray()
        async for part in response.content.iter_chunked(16384):
            data.extend(part)
            if len(data)>limit:raise ValueError('Risposta API Reddit oltre i limiti locali.')
        return bytes(data)

    async def access_token(self):
        if self.token and time.monotonic()<self.expires:return self.token
        if not self.configured:raise ValueError('Configura un’app Reddit con accesso API approvato.')
        if not re.fullmatch('[A-Za-z0-9_-]{4,100}',self.client_id) or len(self.secret)>512 or '\n' in self.secret or '\r' in self.secret:
            raise ValueError('Configurazione API Reddit non valida.')
        async with self.core.engine.session.post('https://www.reddit.com/api/v1/access_token',
                data={'grant_type':'client_credentials'},auth=BasicAuth(self.client_id,self.secret),
                headers={'User-Agent':self.agent},allow_redirects=False,timeout=45) as response:
            raw=await self.read(response,16384)
        try:
            value=json.loads(raw);token=value['access_token'];expiry=value['expires_in']
            if (value.get('token_type','').lower()!='bearer' or not isinstance(token,str)
                    or not 1<=len(token)<=4096 or re.search(r'[\s\x00-\x1f]',token)
                    or type(expiry) not in (int,float) or not 60<=expiry<=86400):raise ValueError()
        except (ValueError,KeyError,TypeError) as exc:
            raise ValueError('Reddit non ha concesso un token valido all’app configurata.') from exc
        self.token=token;self.expires=time.monotonic()+expiry-30
        return token

    async def posts(self,group,count):
        group=subreddit_name(group)
        if type(count) is not int or not 1<=count<=MAX_POSTS:
            raise ValueError('Leggi da 1 a 12 post per volta.')
        token=await self.access_token()
        async with self.core.engine.session.get('https://oauth.reddit.com/r/'+group+'/hot',
                params={'limit':min(MAX_POSTS,count),'raw_json':1},
                headers={'User-Agent':self.agent,'Authorization':'Bearer '+token,'Accept':'application/json'},
                allow_redirects=False,timeout=45) as response:
            if response.status==401:self.token='';self.expires=0
            raw=await self.read(response,MAX_BYTES)
        return listing_entries(raw,group)
