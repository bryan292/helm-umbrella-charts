#!/usr/bin/env python3
"""Validate the Flux repository without accessing a cluster."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ENVIRONMENT = "dev"
CLUSTER_ROOTS = (
    ROOT / "clusters" / ENVIRONMENT / "aws",
    ROOT / "clusters" / ENVIRONMENT / "azure",
)
ROOTS = CLUSTER_ROOTS + (
    ROOT / "platform" / "aws",
    ROOT / "platform" / "azure",
    ROOT / "observability",
    ROOT / "certificates" / ENVIRONMENT,
    ROOT / "applications" / ENVIRONMENT,
)
FLUX_APIS = {
    "HelmRelease": "helm.toolkit.fluxcd.io/v2",
    "HelmRepository": "source.toolkit.fluxcd.io/v1",
    "GitRepository": "source.toolkit.fluxcd.io/v1",
    "Kustomization": "kustomize.toolkit.fluxcd.io/v1",
}


def run(*args: str, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        args, cwd=ROOT, env=env, check=False, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if result.returncode:
        raise RuntimeError(f"{' '.join(args)} failed:\n{result.stderr.strip() or result.stdout.strip()}")
    return result.stdout


def docs(text: str) -> list[dict]:
    return [item for item in yaml.safe_load_all(text) if isinstance(item, dict)]


def variables() -> dict[str, str]:
    return {
        "cluster_name": "dev-test-cluster",
        "provider": "aws",
        "kubernetes_version": "1.35",
        "storage_class": "gp3",
        "region": "us-east-1",
        "vpc_id": "vpc-00000000000000000",
        "domain": "test.example.com",
        "hosted_zone_id": "ZTEST",
        "acme_email": "admin@example.com",
        "eks_lb_role_arn": "arn:aws:iam::123456789012:role/lb",
        "eks_cm_role_arn": "arn:aws:iam::123456789012:role/cert-manager",
        "eks_external_dns_role_arn": "arn:aws:iam::123456789012:role/external-dns",
        "cluster_autoscaler_role_arn": "arn:aws:iam::123456789012:role/autoscaler",
    }


def substitute(value: object, values: dict[str, str]) -> object:
    if isinstance(value, dict):
        return {key: substitute(item, values) for key, item in value.items()}
    if isinstance(value, list):
        return [substitute(item, values) for item in value]
    if not isinstance(value, str):
        return value

    def replacement(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in values:
            raise RuntimeError(f"undefined Flux substitution: {name}")
        return values[name]

    return re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", replacement, value)


def build_all() -> list[dict]:
    resources: list[dict] = []
    for path in ROOTS:
        resources.extend(docs(run("kubectl", "kustomize", str(path))))
        print(f"ok: kustomize {path.relative_to(ROOT)}")
    return resources


def check_flux(resources: list[dict]) -> None:
    for resource in resources:
        api = resource.get("apiVersion", "")
        expected = FLUX_APIS.get(resource.get("kind"))
        if expected and ".toolkit.fluxcd.io/" in api and api != expected:
            raise RuntimeError(f"{resource.get('kind')} must use {expected}, found {api}")

    for root in CLUSTER_ROOTS:
        cluster = docs(run("kubectl", "kustomize", str(root)))
        items = {
            item["metadata"]["name"]: item for item in cluster
            if item.get("apiVersion") == "kustomize.toolkit.fluxcd.io/v1"
        }
        for name, item in items.items():
            for dependency in item.get("spec", {}).get("dependsOn", []):
                if dependency["name"] not in items:
                    raise RuntimeError(f"{root.name}/{name} depends on missing {dependency['name']}")
            source = item["spec"].get("sourceRef", {})
            if source != {"kind": "GitRepository", "name": "helm-umbrella-charts"}:
                raise RuntimeError(f"{name} has unexpected sourceRef: {source}")
    print("ok: Flux APIs, dependencies and source references")


def check_security(resources: list[dict]) -> None:
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts or path.suffix not in {".yaml", ".yml"}:
            continue
        text = path.read_text(errors="replace")
        if "lookup(" in text:
            raise RuntimeError(f"live-cluster lookup found in {path.relative_to(ROOT)}")
        if re.search(
            r"apiVersion:\s*(?:helm|source|kustomize)\.toolkit\.fluxcd\.io/v1(?:alpha|beta)\d+",
            text,
        ):
            raise RuntimeError(f"deprecated Flux API in {path.relative_to(ROOT)}")
        if re.search(r"(?i)(password|token|secretAccessKey)\s*:\s*[^\s{$][^\n]*", text):
            raise RuntimeError(f"possible plaintext secret in {path.relative_to(ROOT)}")

    releases = {item["metadata"]["name"]: item for item in resources if item.get("kind") == "HelmRelease"}
    dns = releases["external-dns"]["spec"]["values"]
    if dns.get("policy") != "upsert-only" or not dns.get("domainFilters"):
        raise RuntimeError("ExternalDNS must be restricted and use upsert-only")
    grafana = releases["monitoring"]["spec"]["values"]["grafana"]
    if grafana["ingress"].get("enabled") is not False:
        raise RuntimeError("Grafana ingress must remain disabled by default")
    logs = releases['loki']['spec']['values']
    if logs['loki']['limits_config']['retention_period'] != '72h' or logs['singleBinary']['persistence']['enableStatefulSetAutoDeletePVC']:
        raise RuntimeError('Loki must retain PVCs and bound log retention')
    alloy = releases['alloy']['spec']['values']
    if alloy['controller']['type'] != 'deployment' or any(alloy['alloy']['mounts'].values()):
        raise RuntimeError('Alloy must collect through the API without host mounts')
    if alloy['rbac']['namespaces'] != ['flux-system', 'monitoring'] or any('secrets' in rule['resources'] for rule in alloy['rbac']['rules']):
        raise RuntimeError('Alloy log permissions must remain namespace-scoped without secrets')
    metric_config = releases['monitoring']['spec']['values']['kube-state-metrics']['customResourceState']['config']['spec']['resources']
    if {item['groupVersionKind']['kind'] for item in metric_config} != {'Kustomization', 'HelmRelease', 'GitRepository'}:
        raise RuntimeError('Flux resource state collectors are incomplete')
    costs = releases['opencost']['spec']['values']['opencost']
    if costs['ui']['enabled'] or not costs['metrics']['serviceMonitor']['enabled']:
        raise RuntimeError('OpenCost must expose internal metrics with its UI disabled')
    print("ok: repository security policies")


def render_charts(resources: list[dict], values: dict[str, str]) -> None:
    repositories = {
        item["metadata"]["name"]: item["spec"]["url"]
        for item in resources if item.get("kind") == "HelmRepository"
    }
    releases = [item for item in resources if item.get("kind") == "HelmRelease"]
    with tempfile.TemporaryDirectory(prefix="umbrella-helm-") as directory:
        temp = Path(directory)
        env = os.environ.copy()
        env.update({
            "HELM_CACHE_HOME": str(temp / "cache"),
            "HELM_CONFIG_HOME": str(temp / "config"),
            "HELM_DATA_HOME": str(temp / "data"),
        })
        for name, url in repositories.items():
            run("helm", "repo", "add", name, url, env=env)
        run("helm", "repo", "update", env=env)

        for release in releases:
            name = release["metadata"]["name"]
            spec = release["spec"]
            chart = spec["chart"]["spec"]
            source = chart["sourceRef"]["name"]
            values_file = temp / f"{name}.yaml"
            values_file.write_text(yaml.safe_dump(substitute(spec.get("values", {}), values), sort_keys=False))
            rendered = docs(run(
                "helm", "template", spec.get("releaseName", name),
                f"{source}/{chart['chart']}", "--version", str(chart["version"]),
                "--namespace", spec["targetNamespace"], "--values", str(values_file), env=env,
            ))
            if name in {"monitoring", "loki", "alloy", "opencost"}:
                for item in rendered:
                    if item.get("kind") in {"Ingress", "HTTPRoute", "Gateway"}:
                        raise RuntimeError(f"{name}: administrative route must remain private")
                    if item.get("kind") == "Service":
                        service = item.get("spec", {})
                        if service.get("type", "ClusterIP") != "ClusterIP" or service.get("externalIPs"):
                            raise RuntimeError(f"{name}: administrative service must remain ClusterIP")
            print(f"ok: helm render {name} ({chart['version']})")


def main() -> int:
    try:
        values = variables()
        resources = [substitute(item, values) for item in build_all()]
        check_flux(resources)
        check_security(resources)
        render_charts(resources, values)
    except (KeyError, StopIteration, RuntimeError, yaml.YAMLError) as error:
        print(f"validation failed: {error}", file=sys.stderr)
        return 1
    print("all validations passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
