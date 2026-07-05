# Secure Dashboard Key

> [!NOTE]
> These docs describe the official Reponomics generated workflows for the `v0` external beta. Repository owners can modify their copies; modified workflows may behave differently from what these docs describe.

Encrypted mode uses `DASHBOARD_SECRET_DO_NOT_REPLACE` to encrypt retained artifacts and dashboard payloads. The action requires that key to be non-empty, but it does not enforce length, complexity, or entropy.

For key-generation guidance, offline attack risk, rotation limits, and trust-boundary details, see [Security Info](security-info.md).
