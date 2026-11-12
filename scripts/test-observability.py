#!/usr/bin/env python3
"""Run real PromQL rule tests using the deployed Prometheus version."""
import json
import subprocess
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
IMAGE = 'quay.io/prometheus/prometheus:v3.16.0-distroless@sha256:9764044e09eb2c9e1abdb12d0f0188d4efb7384b0262d3c080f0fc59045c89ba'


def main():
    rules = yaml.safe_load((ROOT / 'observability/rules.yaml').read_text())['spec']
    dashboard = yaml.safe_load((ROOT / 'observability/dashboard.yaml').read_text())
    panels = json.loads(dashboard['data']['multicloud-platform.json'])['panels']
    # Parse every dashboard PromQL expression with the same engine as the alert rules.
    rules['groups'].append({'name': 'dashboard.syntax', 'rules': [
        {'record': f'dashboard:panel_{panel["id"]}', 'expr': target['expr']}
        for panel in panels if panel['datasource']['type'] == 'prometheus' for target in panel['targets']
    ]})
    with tempfile.TemporaryDirectory(prefix='observability-rules-') as directory:
        temp = Path(directory)
        (temp / 'rules.yaml').write_text(yaml.safe_dump(rules))
        (temp / 'test.yaml').write_text((ROOT / 'tests/observability.test.yaml').read_text())
        for arguments in [('check', 'rules', '/test/rules.yaml'), ('test', 'rules', '/test/test.yaml')]:
            subprocess.run(['docker', 'run', '--rm', '--entrypoint', '/bin/promtool',
                            '-v', f'{temp}:/test:ro', IMAGE, *arguments], check=True)


if __name__ == '__main__':
    main()
