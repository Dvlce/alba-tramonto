"""Small, attributed public RSS readings; never a model-training dataset."""
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit
from xml.etree import ElementTree


COMMUNITIES = (
    ('learnpython', 'programming'), ('dadjokes', 'humor'),
    ('webdev', 'programming'), ('cleanjokes', 'humor'),
    ('learnprogramming', 'programming'), ('jokes', 'humor'),
    ('python', 'programming'), ('programming', 'programming'),
)
HUMOR = {'dadjokes', 'cleanjokes', 'jokes', 'programmerhumor'}
RSS_NOTICE = 'https://support.reddithelp.com/hc/en-us/articles/54353370049684-Changelog-October-8-2026'
# Reddit's announced end of public RSS support, 2026-11-13 00:00 UTC.
RSS_END = 1794528000
MAX_POSTS = 12
MAX_BYTES = 262144
RETENTION_SECONDS = 7 * 86400


def humor_request(query):
    return bool(re.search(r'umor|humor|battut|barzellett|\bjokes?\b|divertent|sarcas|giochi di parole', query, re.I))


def subreddit_name(value):
    if not isinstance(value, str):
        raise ValueError('Indica il nome di un subreddit pubblico.')
    value = value.strip()
    if '://' in value:
        p = urlsplit(value)
        if (p.scheme != 'https' or p.hostname not in ('reddit.com', 'www.reddit.com')
                or p.username or p.password or p.port or p.query or p.fragment):
            raise ValueError('Usa r/nome oppure https://www.reddit.com/r/nome/.')
        value = p.path.strip('/')
    value = re.sub(r'^/?r/', '', value, flags=re.I).rstrip('/')
    if not re.fullmatch(r'[A-Za-z0-9_]{2,21}', value):
        raise ValueError('Nome subreddit non valido: da 2 a 21 lettere, numeri o underscore.')
    return value.lower()


class PostText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.hidden += 1
        if tag in ('p', 'br', 'div', 'pre', 'li'):
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in ('script', 'style') and self.hidden:
            self.hidden -= 1
        if tag in ('p', 'div', 'pre', 'li'):
            self.parts.append('\n')

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def reddit_entries(raw, subreddit=None):
    if len(raw) > MAX_BYTES or b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise ValueError('Feed Reddit oltre i limiti o con formato non supportato.')
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError as exc:
        raise ValueError('Reddit non ha restituito un feed pubblico valido.') from exc
    ns = '{http://www.w3.org/2005/Atom}'
    if root.tag != ns+'feed':
        raise ValueError('Reddit non ha restituito un feed pubblico valido.')
    rows = []
    seen = set()
    for entry in root.findall(ns+'entry')[:100]:
        link = next((e for e in entry.findall(ns+'link') if e.get('rel', 'alternate') == 'alternate'), None)
        try:
            p = urlsplit(link.get('href', '') if link is not None else '')
            port = p.port
        except ValueError:
            continue
        if (p.scheme != 'https' or p.hostname not in ('reddit.com', 'www.reddit.com')
                or p.username or p.password or port):
            continue
        match = re.fullmatch(r'/r/([A-Za-z0-9_]{2,21})/comments/([A-Za-z0-9]+)/[^/]*(?:/)?', p.path)
        if not match:
            continue
        group, ident = (s.lower() for s in match.groups())
        if subreddit and group != subreddit.lower() or ident in seen:
            continue
        title = entry.findtext(ns+'title', '').strip()[:250]
        parser = PostText()
        parser.feed(entry.findtext(ns+'content', '')[:32000])
        text = ''.join(parser.parts).split('submitted by', 1)[0]
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n\s*\n+', '\n\n', text).strip()[:9000]
        if not title or re.search(r'\bnsfw\b', title, re.I) or title.lower() in ('[deleted]', '[removed]') or text.lower() in ('[deleted]', '[removed]'):
            continue
        seen.add(ident)
        rows.append({'url': 'https://www.reddit.com/r/'+group+'/comments/'+ident+'/',
                     'id': ident, 'subreddit': group, 'title': title, 'excerpt': text,
                     'revision': entry.findtext(ns+'updated', '')[:80]})
        if len(rows) >= MAX_POSTS:
            break
    return rows
