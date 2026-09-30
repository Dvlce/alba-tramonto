"""Configuration without shell evaluation; secrets are never logged."""
import os
from dataclasses import dataclass, field
from pathlib import Path


def load_env(path: Path):
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip().strip('\"\''))


@dataclass
class Settings:
    root: Path = field(default_factory=lambda: Path(__file__).resolve().parent)
    bot_token: str = ''
    admins: tuple = ()
    allowed: tuple = ()
    model: str = 'qwen3:4b-instruct-2507-q4_K_M'
    backend: str = 'ollama'
    llm_url: str = 'http://127.0.0.1:11434'
    context_tokens: int = 4096
    context_chars: int = 7000
    output_tokens: int = 350
    max_users: int = 20
    max_online: int = 5
    web_port: int = 8088
    public_url: str = ''
    key_ttl: int = 900
    session_ttl: int = 43200
    daily_retention: int = 7
    weekly_retention: int = 4
    monthly_retention: int = 3

    @property
    def data(self):
        return self.root / 'data'

    @classmethod
    def from_env(cls,root=None):
        root = Path(root).resolve() if root else Path(__file__).resolve().parent
        load_env(root / '.env')
        ids = lambda name: tuple(int(x) for x in os.getenv(name, '').split(',') if x.strip())
        return cls(root=root, bot_token=os.getenv('TELEGRAM_BOT_TOKEN', ''),
                   admins=ids('ADMIN_IDS'), allowed=ids('ALLOWED_USER_IDS'),
                   model=os.getenv('MODEL', 'qwen3:4b-instruct-2507-q4_K_M'),
                   backend=os.getenv('LLM_BACKEND', 'ollama'),
                   llm_url=os.getenv('LLM_URL', 'http://127.0.0.1:11434').rstrip('/'),
                   public_url=os.getenv('PUBLIC_URL', '').rstrip('/'),
                   context_chars=int(os.getenv('CONTEXT_CHARS', '7000')),
                   context_tokens=int(os.getenv('CONTEXT_TOKENS', '4096')),
                   output_tokens=int(os.getenv('OUTPUT_TOKENS', '350')),
                   web_port=int(os.getenv('WEB_PORT', '8088')),
                   max_users=int(os.getenv('MAX_USERS','20')),
                   max_online=int(os.getenv('MAX_ONLINE','5')),
                   daily_retention=int(os.getenv('BACKUP_DAILY', '7')),
                   weekly_retention=int(os.getenv('BACKUP_WEEKLY', '4')),
                   monthly_retention=int(os.getenv('BACKUP_MONTHLY', '3')))
