import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from core.model_family import create_family,configure_env

class FamilyTests(unittest.TestCase):
    def test_alias_with_changed_weights_is_rejected(self):
        settings=SimpleNamespace(llm_url='http://local')
        with patch('core.model_family.api',return_value={'models':[{'name':'qwen2.5:1.5b'}]}),patch('core.model_family.weight_id',side_effect=['a'*64,'b'*64]):
            with self.assertRaises(ValueError):create_family(settings)
    def test_env_updates_only_model_fields_preserving_private_configuration(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);env=root/'.env';env.write_text('MODEL=old\nTELEGRAM_BOT_TOKEN=fixture-secret\nCORE_CODE_MODEL=old\n');env.chmod(0o600)
            configure_env(root)
            text=env.read_text();self.assertIn('TELEGRAM_BOT_TOKEN=fixture-secret',text)
            self.assertIn('MODEL=notte:latest',text);self.assertIn('CORE_CODE_MODEL=notte-coding:latest',text)
            self.assertEqual(env.stat().st_mode&0o777,0o600)
