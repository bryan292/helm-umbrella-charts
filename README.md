# Multi-cloud Kubernetes platform configuration with Flux

This repository contains the declarative platform configuration reconciled by
Flux after an EKS or AKS cluster has been created. It intentionally does not
create cloud infrastructure; that remains the responsibility of the
infrastructure repository.

## Layout

```text
clusters/dev/aws/     EKS Flux entry point
clusters/dev/azure/   AKS Flux entry point
platform/common/      provider-neutral controllers and observability
platform/aws/         EKS-only controllers and IAM values
platform/azure/       AKS overlay using managed Azure capabilities
certificates/dev/     certificate issuers
applications/dev/     application composition for the environment
applications/example/ immutable Git source example (not enabled by default)
```

The provider-specific `clusters/dev/<provider>` entry point applies components
in dependency order. The infrastructure repository creates the non-secret
`cluster-settings` ConfigMap before Flux reconciliation, so dynamic cluster IDs
and storage classes do not need commits in this repository.

1. `platform` installs controllers and observability.
2. `certificates` creates the ACME staging issuer.
3. `applications` is reconciled only after both dependencies are ready.

All Flux custom resources use stable APIs. Environment-specific values are
declared once in `clusters/dev/settings.yaml` and injected by Flux
`postBuild.substituteFrom`; templates do not use live-cluster `lookup` calls.

## Bootstrap contract

The Flux bootstrap must create a `GitRepository` named
`helm-umbrella-charts` in `flux-system` and reconcile `./clusters/dev`.

```sh
flux bootstrap github \
  --owner=<owner> \
  --repository=<repository> \
  --branch=main \
  --path=clusters/dev
```

Before bootstrapping another environment, copy the four `dev` directories
and replace every value in its `settings.yaml`. IAM role ARNs are identifiers,
not credentials. Secrets and private Git credentials must be created outside
Git or encrypted with SOPS.

## Safe defaults

- Let's Encrypt uses the staging endpoint until certificate issuance is proven.
- ExternalDNS is restricted to one hosted zone and uses `upsert-only` policy.
- Grafana has no public ingress; use port-forwarding or an authenticated private
  ingress.
- The sample application is disabled and pins a full Git commit.
- Releases have retries, timeouts, drift detection and explicit chart versions.

## Validation

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python scripts/validate.py
```

The validator builds every Kustomize root, performs strict Flux substitution,
checks dependency/source references and security policies, downloads each
pinned chart and renders it with the configured values. It does not connect to
a Kubernetes cluster or modify AWS.

## Migration warning

Do not point Flux at this repository while Terraform (or another Flux source)
still owns HelmReleases with the same names. First choose one owner, migrate
state deliberately and then bootstrap this path. Two reconcilers managing the
same resources will cause drift and unstable rollouts.
