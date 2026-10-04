"""Public, repository-curated evolution data; never reads private lab storage."""
import json


def project_data(root):
    def read(name, fallback):
        path = root / 'docs' / name
        if not path.is_file():
            return fallback
        if path.stat().st_size > 1024 * 1024:
            raise ValueError('Report pubblico troppo grande.')
        return json.loads(path.read_text())
    return {'history': read('OPTIMIZATION_HISTORY.json', {'entries': []}),
            'measurements': read('SSD_RUNTIME_RESULTS.json', {'results': []}),
            'lab_measurements': read('TEST_LAB_RESULTS.json', {'samples': []}),
            'adaptive_measurements': read('ADAPTIVE_RESULTS.json', {'results': []}),
            'privacy': 'Only repository-published probes and aggregate metadata. Private Test Lab prompts and outputs are excluded.'}
