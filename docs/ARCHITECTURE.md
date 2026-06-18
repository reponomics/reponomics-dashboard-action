# Architecture

## Overview

The Reponomics Dashboard project publishes two independently versioned products that are tightly coupled, one public demo surface, and one promotional splash page. The core pieces consist of:

- `reponomics-dashboard`: the primary user-facing offering - a template repository that provides the basic scaffolding to support the Dashboard - its main functional surface is the set of workflows that consume the Dashboard Action; it also houses important repo owner documentation, and the owner's configuration files. 
- `reponomics-dashboard-action`: the GitHub Marketplace action that implements the runtime for the core Dashboard feature offerings.
- `reponomics-dashboard-demo`: a public demo repository that uses synthetic data to show prospective Dashboard repo owners the set of features that the Reponomics Dashboard has to offer.
- `reponomics-dashboard-web`: a promotional splash page that gives a public presence to the Dashboard project outside of GitHub - it presents an overview of the project and highlights the core functionality.

The `@reponomics/reponomics-dashboard-action` repository is the development repository responsible for maintaing the template repo, the GitHub action, and the demo repo. It is also the repository that Dashboard owners, project contributors, and potential collaborators are invited to use to file issues (feature enhancements, bug reports), make PRs, and review more detailed technical literature. Because it is part of the supply chain for the other products, it strives to follow Open Source best practices to the greatest extent, and produces the necessary provenance artifacts, attestations, immutable releases, and other outputs necessary for the project to establish publicly verifiable evidence regarding the claims that are made about the project. 

The dashboard-action repo is also the repo that is referenced by workflows that consume the action:

```yaml
uses: reponomics/reponomics-dashboard-action@v0
```

The reason for this bifurcated design (template + action) is due to the goal of providing maintainers with a data dashboard that is completely under their control, and at the same time offering feature updates, security patches, and bug fixes. Since the product is a data dashboard repo, a template repo is a natural way to package it. However, after copying a template, the repo owner has virtually no connection to that template. (The template repo is not "upstream" of its copies.) So, the template needs some sort of distribution channel. Since the majority of the functionality comes from the workflows (querying the GitHub API, collecting and storing the data, etc.), it is the _action_ that is the primary functional core, or "runtime", for the Reponomics Dashboard, and the template repo is supposed to be only a thin compatibility layer.

> [!NOTE]
> Maintainers who copy the Dashboard template should be referred to as "owners" when speaking in that mode, although they may also be referred to as "users" of the Dashboard action. "Consumer" is the most generic label, if one is needed, although this also applies to the workflows themselves. This is only stylistic advice.

## Compatibility

The architecture must always be designed with this constraint in mind: after copying the template, that copy owner might never update, or migrate, their data to a newer template version. Therefore, the action must _always_ be able to prove that as it evolves, it maintains compatibility with the minimum compatible template version. Breaking this contract is what decides whether a new major version of the action is justified, or required.

The project follows an asymmetric compatibility rule:

- New action releases on the same major version line must continue to work with previously published template versions.
- New template releases, however, may assume that any user who copies it will be using the action version that is current at the time of its publication, or later.

So, action releases must establish backwards-compatibility with the template version stated as the `minimum_compatible_template_version` in the `template-contract`; template releases do not have to take into account backwards compatibility at all.

## Repository Topology

The core directory structure is as follows:

```
├── .github/              # Workflows for CI/CD and release management
├── action.yml            # GitHub action metadata file
├── dashboard_action/     # Central runtime implementation
│   ├── run_modules/      # Core module files and facades
│   └── runtime/
│       └── managed-docs/ # Documentation that is shipped to Dashboard owners
│       └── scripts/      # Large collection of implementation scripts and shared logic
├── docs/                 # Maintainer documentation (live docs, ADRs)
├── scripts/              # Shared scripts/helpers
├── template/             # A sub-tree that is mostly isomorphic with the generated template repo
├── tests/                # Collected tests for both products
└── vendor/               # Vendored assets (chart.js, fonts)
```

The major areas of responsibility are:

| Area | Responsibility |
| --- | --- |
| `action.yml` | Public composite action interface. This is the Marketplace product entry point. |
| `dashboard_action/` | Action runtime package, mode dispatch, collection, publish, doctor, incident reset, managed docs sync, provenance, and rendering. |
| `dashboard_action/runtime/managed_docs/` | Source bundle for user-facing managed documentation that ships into generated repositories and can be refreshed by the action. |
| `template/` | Hand-maintained source for files that belong in the generated dashboard template repository. |
| `template-manifest.yml` | Explicit shipped-file allowlist plus forbidden-path guard for generated template output. |
| `template-contract.yml` | Template product metadata and action compatibility contract. |
| `scripts/build_template.py` | Builds `dist/template` from `template/`, overlays managed docs, and verifies output. |
| `scripts/template_contract.py` | Validates local action/template compatibility, managed docs snapshots, and action references in generated output. |
| `scripts/publish_generated_repo.py` | Publishes a generated output tree to `reponomics-dashboard` with target safety checks. |
| `scripts/template_consumer_e2e.py` and `scripts/smoke_template_release.py` | Local generated-template validation against the current action source. |
| Demo tooling | Builds and publishes `reponomics-dashboard-demo` from the generated template plus explicit synthetic data, demo fixtures, and demo-only publication overrides. |
| `tests/` | Action runtime tests, generated-template tests, scenario snapshots, security/contract checks, and compatibility fixtures. |
| `.github/workflows/` | CI, release, template publish, pre-release validation, and repository hygiene workflows. |
| `docs/` | Maintainer documentation for this development repository. |

## Product Boundaries

### Action Product

The action product consists of:

- `action.yml`
- `dashboard_action/`
- runtime dependencies and locks
- bundled runtime assets
- bundled managed docs
- Marketplace-facing README and release notes
- action release tags
- floating action tags (major and minor lines)

### Template Product

The template product consists of the generated output published to `reponomics/reponomics-dashboard`. Its source inputs are:

- `template/`
- `template-manifest.yml`
- `template-contract.yml`
- template-generator scripts
- `dashboard_action/runtime/managed_docs/`
- action metadata required by generated workflows
- template publication workflows

### Generated Template Repository

Publication should be a reproducible projection from this repository:

```text
source tree at commit S
  -> make build-template
  -> dist/template
  -> publish_generated_repo.py
  -> reponomics-dashboard main
```

### Demo Repository

Because the template repository has nothing very interesting to show when it is first copied, the demo repository is maintained as a faithful replica of the current template, seeded with synthetic data. It is intended to deviate from the genuine template to the smallest extent possible - the synthetic data is encrypted according to the same protocols, with the minor difference that the unlock key is printed directly to the unlock screen (normal templates don't expost this, for obvious reasons).


- use the same repository layout as a real generated template repository
- use the same repository layout, rendering paths, encrypted artifact format, Pages publication path, and managed docs surface wherever possible
- replace live GitHub collection with deterministic synthetic canonical data for a manicured portfolio of repositories
- publish a README dashboard even though normal public generated repositories prohibit README dashboard generation
- publish a Pages dashboard, which is normal and supported
- use encrypted dashboard mode with an intentionally public demo key so visitors can unlock the Pages dashboard
- label the public demo key unmistakably as a demo credential that must never be reused

The demo repository should be treated as a public showroom and, to some degree, a secondary integration test surface, not as a third semantically versioned product. It is regenerated every day so that the synthetic data can be advanced in time by one day, giving the impression that it is always "up to date". 
