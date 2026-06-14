# Secure Dashboard Key

> [!WARNING]
> The Reponomics Dashboard template is currently in a pre-release public hardening phase. It is not intended for public use, and documentation in this managed-docs bundle should not be considered authoritative.

Encrypted mode uses `DASHBOARD_SECRET_DO_NOT_REPLACE` to encrypt retained artifacts and dashboard payloads. The action requires that key to be non-empty, but it does not enforce length, complexity, or entropy.

For key-generation guidance, offline attack risk, rotation limits, and trust-boundary details, see [Security Info](security-info.md).
