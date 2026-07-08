# Frequently Asked Questions

## Why are there two Reponomics repositories?

`reponomics-dashboard` is the template repository users copy. `reponomics-dashboard-action` is the versioned runtime called by generated workflows.

This keeps copied dashboard repositories small while allowing collection, encryption, rendering, rotation, incident reset, CSV export, and docs updates to improve through action releases. See [Workflows](workflows.md).

## What data mode should I choose?

Use `encrypted` unless you have a specific reason not to. It is required for public repositories and Pages dashboards.

Use `plaintext` only in private repositories where GitHub repository and Actions artifact access are the intended privacy boundary. Plaintext mode stores retained CSV files directly in `dashboard-data` and does not publish Pages. See [Privacy And Security](privacy-and-security.md).

## How do I turn on the hosted Pages dashboard?

Set `data_mode: encrypted` and `publish_pages_dashboard: true`, commit `config.yaml`, and run setup. Then open repository **Settings -> Pages** and set **Build and deployment -> Source** to **GitHub Actions**.

The action verifies the Pages setting during publish. It does not enable Pages or change the publishing source. See [Publication](publication.md).

## What dashboard key should I use?

Use a high-entropy random key such as:

```sh
openssl rand -hex 32
```

Store it in a password manager, then save it as the repository secret `DASHBOARD_SECRET_DO_NOT_REPLACE`. See [Dashboard Key And Recovery](dashboard-key-and-recovery.md).

## What does encryption protect?

Encrypted mode encrypts retained artifacts and dashboard payloads before storage or publication. It does not hide the existence of a Pages site, publication timing, payload size, workflow metadata, or metrics committed to a private README dashboard.

Encryption also does not protect against people who can alter trusted workflows, manage repository secrets, or administer the dashboard repository. See [Privacy And Security](privacy-and-security.md).

## Is dashboard data committed to git?

Only if `publish_readme_dashboard: true` is enabled in a private repository. Otherwise retained dashboard data lives in GitHub Actions artifacts, and rendered HTML dashboards are either deployed through Pages or uploaded as workflow artifacts. See [Data And Artifacts](data-and-artifacts.md).

## Who should get repository access?

In a personal private dashboard repository, treat collaborators as trusted with the dashboard control plane, not merely as people who can read a report.

Use an organization repository when you need real role separation between viewers, configuration editors, workflow operators, secret managers, and admins.

## Can browser devtools export CSV before unlock?

No. The encrypted export asset cannot produce plaintext ZIP bytes without the dashboard key. The browser verifies ciphertext size, ciphertext SHA-256, AES-GCM decryption, and plaintext ZIP SHA-256 before download.

## Why offer checksum copy if the browser verifies export integrity?

It gives users an independent verification record for support, audit, or local checksum workflows.

## How can I verify the action release?

See [Provenance And Verification](provenance.md) for manifest files, release artifacts, attestations, vendored-asset metadata, dependency locks, and local verification commands.

## Does the action enforce key strength?

No. Encrypted mode requires a non-empty key and leaves entropy to the repository owner. Simple thresholds can be misleading, and visible key-quality modes can advertise weaker dashboards.
