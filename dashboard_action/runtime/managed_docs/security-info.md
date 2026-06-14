# Security Info

> [!WARNING]
> The Reponomics Dashboard template is currently in a pre-release public hardening phase. It is not intended for public use, and documentation in this managed-docs bundle should not be considered authoritative.

This page explains the security model behind `data_mode: encrypted` and `data_mode: plaintext`.

## Data Modes

`data_mode: encrypted` encrypts retained CSV artifacts and dashboard payloads with `DASHBOARD_SECRET_DO_NOT_REPLACE`. It is the only supported mode for public repositories and the only mode that can publish a Pages dashboard. The action requires this key to be non-empty, but it does not enforce length, complexity, or entropy.

`data_mode: plaintext` stores retained CSV files directly in the `dashboard-data` workflow artifact. It is private-repository only, disables hosted Pages publication, and relies on GitHub repository and Actions artifact access as the privacy boundary.

## Key Strength

Encrypted dashboard artifacts can be downloaded and attacked offline by anyone who can obtain them. If your dashboard is public, hosted on public Pages, sensitive, or meant to resist a targeted attacker, use a high-entropy random key. A short or memorable key may still encrypt the artifact, but it may not survive offline guessing.

The action intentionally does not classify encrypted keys into quality tiers. Any simple threshold would be misleading: an eight-character minimum is far closer to no protection than to a randomly generated 32-byte key, and a visible mode distinction can advertise which users chose weaker keys.

## Generating A High-Entropy Key

Recommended shell-safe option:

```sh
openssl rand -hex 32
```

That produces 32 random bytes encoded as 64 hex characters. Store the value in a password manager, then save it as the repository secret `DASHBOARD_SECRET_DO_NOT_REPLACE`.

A password manager generated random password is also appropriate when it has comparable entropy. Avoid memorable phrases, reused passwords, project names, repository names, or anything you would be comfortable typing from memory.

## Rotation And Recovery

Do not overwrite `DASHBOARD_SECRET_DO_NOT_REPLACE` directly during ordinary rotation. Add the new key as `DASHBOARD_NEXT_SECRET`, run the rotate-key workflow, confirm the new dashboard opens, then promote `DASHBOARD_NEXT_SECRET` into `DASHBOARD_SECRET_DO_NOT_REPLACE` and delete `DASHBOARD_NEXT_SECRET`.

If the current key was exposed, make the dashboard repository private and disable any exposed Pages dashboard before relying on `incident-reset`. The reset flow re-encrypts retained state with `DASHBOARD_NEXT_SECRET`, uploads a new retained artifact, then deletes old workflow runs associated with previous retained artifacts.

## Trust Boundary

Encryption does not protect against people or systems that can run trusted workflows with access to repository secrets. A collaborator who can alter workflows, update secrets, or run rotation/reset workflows can potentially exfiltrate data, replace keys, delete retained history, or make current encrypted state inaccessible.

Browser-side encryption also does not protect against malicious browser extensions, compromised devices, malicious JavaScript in the trusted dashboard shell, compromised CI/CD, or supply-chain compromise of the action version your workflow runs.
