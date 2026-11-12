#!/usr/bin/env python3
"""Run real PromQL rule tests using the deployed Prometheus version."""
import json
import os
import subprocess
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
IMAGE = 'quay.io/prometheus/prometheus:v3.16.0-distroless@sha256:9764044e09eb2c9e1abdb12d0f0188d4efb7384b0262d3c080f0fc59045c89ba'


def main():
    # Keep this version aligned with infrastructure-modules/kubernetes/main.tf.
    rendered = subprocess.check_output(['helm', 'template', 'flux2', 'flux2', '--version', '2.20.0',
        '--repo', 'https://fluxcd-community.github.io/helm-charts', '--namespace', 'flux-system'], text=True)
    monitor = yaml.safe_load((ROOT / 'observability/flux-monitor.yaml').read_text())['spec']
    expression = monitor['selector']['matchExpressions'][0]
    assert expression['key'] == 'app' and expression['operator'] == 'In'
    expected = set(expression['values'])
    selected = set()
    for resource in yaml.safe_load_all(rendered):
        if not resource or resource.get('kind') != 'Deployment':
            continue
        template = resource['spec']['template']
        app = template['metadata']['labels'].get('app')
        if app in expected:
            assert any(port['name'] == monitor['podMetricsEndpoints'][0]['port']
                       for container in template['spec']['containers'] for port in container.get('ports', []))
            selected.add(app)
    assert selected == expected and len(selected) == 6, 'PodMonitor must match all six installed Flux controllers'
    print('Flux PodMonitor matches the pinned Helm chart pods and ports', flush=True)
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
            subprocess.run(['docker', 'run', '--rm', '--user', f'{os.getuid()}:{os.getgid()}',
                            '--entrypoint', '/bin/promtool',
                            '-v', f'{temp}:/test:ro', IMAGE, *arguments], check=True)


if __name__ == '__main__':
    main()
