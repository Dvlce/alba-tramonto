import json
import os
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from core.reddit_oauth import RedditClient,listing_entries
from core.learning import PublicSourceError


def listing(**overrides):
    post={'id':'abc','subreddit':'dadjokes','subreddit_type':'public','title':'Original test joke',
          'selftext':'A test setup and punchline.','created_utc':123,'over_18':False,**overrides}
    return json.dumps({'data':{'children':[{'kind':'t3','data':post}]}}).encode()


class Response:
    def __init__(self,raw,status=200,headers=None):
        self.raw=raw;self.status=status;self.headers=headers or {};self.content=self
    async def __aenter__(self):return self
    async def __aexit__(self,*args):pass
    async def iter_chunked(self,size):
        for offset in range(0,len(self.raw),size):yield self.raw[offset:offset+size]


class OAuthTests(unittest.IsolatedAsyncioTestCase):
    def client(self):
        session=SimpleNamespace(post=Mock(),get=Mock())
        with patch.dict(os.environ,{'REDDIT_CLIENT_ID':'test_client','REDDIT_CLIENT_SECRET':'fake_test_secret','REDDIT_API_APPROVED':'1'}):
            client=RedditClient(SimpleNamespace(engine=SimpleNamespace(session=session)))
        session.post.return_value=Response(json.dumps({'access_token':'fake_test_token','token_type':'bearer','expires_in':3600}).encode())
        session.get.return_value=Response(listing())
        return client,session

    async def test_application_auth_token_cache_read_only_urls_and_no_redirects(self):
        client,session=self.client()
        first=await client.posts('dadjokes',3);second=await client.posts('dadjokes',3)
        self.assertEqual(first,second);self.assertEqual(session.post.call_count,1)
        post=session.post.call_args;get=session.get.call_args
        self.assertEqual(post.args[0],'https://www.reddit.com/api/v1/access_token')
        self.assertEqual(post.kwargs['data'],{'grant_type':'client_credentials'})
        self.assertEqual(post.kwargs['auth'].login,'test_client')
        self.assertFalse(post.kwargs['allow_redirects']);self.assertFalse(get.kwargs['allow_redirects'])
        self.assertEqual(get.args[0],'https://oauth.reddit.com/r/dadjokes/hot')
        self.assertEqual(get.kwargs['headers']['Authorization'],'Bearer fake_test_token')
        self.assertNotIn('fake_test_token',first[0]['url'])
        client.expires=time.monotonic()-1;await client.posts('dadjokes',3)
        self.assertEqual(session.post.call_count,2)

    async def test_no_application_network_access_without_explicit_approved_configuration(self):
        client,session=self.client();client.approved=False
        with self.assertRaises(ValueError):await client.posts('dadjokes',1)
        self.assertEqual(session.post.call_count,0);self.assertEqual(session.get.call_count,0)

    async def test_refused_auth_has_no_rss_fallback_or_secrets_in_the_error(self):
        client,session=self.client();session.post.return_value=Response(b'fake_test_secret',403)
        with self.assertRaises(PublicSourceError) as error:await client.posts('dadjokes',1)
        self.assertNotIn('fake_test_secret',str(error.exception));self.assertEqual(session.get.call_count,0)

    async def test_api_401_invalidates_token_and_429_preserves_retry_after(self):
        client,session=self.client();session.get.return_value=Response(b'',401)
        with self.assertRaises(PublicSourceError):await client.posts('dadjokes',1)
        self.assertEqual(client.token,'');self.assertEqual(client.expires,0)
        session.get.return_value=Response(b'',429,{'Retry-After':'7200'})
        with self.assertRaises(PublicSourceError) as error:await client.posts('dadjokes',1)
        self.assertEqual(error.exception.retry_seconds,7200)

    async def test_invalid_group_and_invalid_token_never_reach_a_listing(self):
        client,session=self.client()
        for group in ('https://evil.test/r/test/','dadjokes/../../private'):
            with self.assertRaises(ValueError):await client.posts(group,1)
        self.assertEqual(session.post.call_count,0)
        session.post.return_value=Response(b'{"access_token":"bad\\ntoken","token_type":"bearer","expires_in":3600}')
        with self.assertRaises(ValueError):await client.posts('dadjokes',1)
        self.assertEqual(session.get.call_count,0)

    async def test_token_and_listing_downloads_are_bounded(self):
        client,session=self.client();session.post.return_value=Response(b'x'*16385)
        with self.assertRaises(ValueError):await client.posts('dadjokes',1)
        client,session=self.client();session.get.return_value=Response(b'x'*262145)
        with self.assertRaises(ValueError):await client.posts('dadjokes',1)

    def test_listing_does_not_import_private_deleted_nsfw_or_other_communities(self):
        for value in ({'subreddit':None},{'subreddit':'another'},{'over_18':True},
                      {'subreddit_type':'private'},{'selftext':'[removed]'},{'id':'abc/../../secret'}):
            self.assertEqual(listing_entries(listing(**value),'dadjokes'),[])
        post=listing_entries(listing(),'dadjokes')[0]
        self.assertEqual(post['revision'],'123');self.assertNotIn('author',post)
        for raw in (b'null',b'{}',b'[]',b'bad json'):
            with self.assertRaises(ValueError):listing_entries(raw,'dadjokes')
