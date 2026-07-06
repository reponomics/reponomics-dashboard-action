# Security Info

This page summarizes the security model for `data_mode: encrypted` and `data_mode: plaintext`.

## Data Modes

`data_mode: encrypted` encrypts retained CSV artifacts and dashboard payloads with `DASHBOARD_SECRET_DO_NOT_REPLACE`. It is required for public repositories and for hosted Pages dashboards. The key must be non-empty.

`data_mode: plaintext` stores retained CSV files directly in the `dashboard-data` workflow artifact. It is private-repository only, disables hosted Pages publication, and relies on GitHub repository and Actions artifact access as the privacy boundary.

## Key Strength

Encrypted artifacts can be downloaded and attacked offline by anyone who obtains them. Use a high-entropy random key for public Pages dashboards, public repositories, sensitive metrics, or targeted-threat models.

Reponomics intentionally does not classify key quality. Simple thresholds are misleading, and visible key-quality modes can advertise which dashboards are easier to attack.

Recommended key generation is covered in [Secure Dashboard Key](secure-dashboard-key.md).

## Rotation And Recovery

Do not overwrite `DASHBOARD_SECRET_DO_NOT_REPLACE` for ordinary rotation. Add the new key as `DASHBOARD_NEXT_SECRET`, run **Rotate Key**, confirm the dashboard opens, then promote the new key and delete `DASHBOARD_NEXT_SECRET`.

If the current key was exposed, make the dashboard repository private and disable exposed Pages output before relying on **INCIDENT - Reset**. Incident reset re-encrypts retained state with `DASHBOARD_NEXT_SECRET`, uploads a new retained artifact, then deletes old workflow runs associated with previous retained artifacts.

Reponomics cannot recover encrypted retained data without a valid old or current key.

## Trust Boundary

Encryption does not protect against people or systems that can run trusted workflows with access to repository secrets. Anyone who can alter trusted workflows, manage secrets, approve protected environments, or administer the repository can affect the dashboard control plane.

Browser-side encryption also does not protect against malicious browser extensions, compromised devices, malicious JavaScript in the trusted dashboard shell, compromised CI/CD, or supply-chain compromise of the action version your workflow runs.
