# Secure Dashboard Key Generation

> [!WARNING]
> The Reponomics Dashboard template is currently in a pre-release public hardening phase. It is not intended for public use, and documentation in this managed-docs bundle should not be considered authoritative.

`privacy-mode=strong` and `privacy-mode=casual` use
`DASHBOARD_SECRET_DO_NOT_REPLACE` to encrypt retained artifacts and hosted dashboard
data. Anyone with this key can decrypt the dashboard and CSV export. GitHub
will not show the secret value again after you save it, so store it somewhere
private.

Do not replace `DASHBOARD_SECRET_DO_NOT_REPLACE` directly if you forget the key. That cannot recover existing encrypted data. Despite the name, there is one safe time to replace it: after the rotation workflow completes successfully and tells you to promote `DASHBOARD_NEXT_SECRET`.

Do not choose a memorable password for `strong`. Generate a random dashboard
key.

## Recommended: Command Line

Use a shell-safe 256-bit hex key:

```sh
openssl rand -hex 32
```

Save the generated value in a password manager, then add it as the repository
secret named `DASHBOARD_SECRET_DO_NOT_REPLACE`.

## Password Manager

Use your password manager to generate a random password of at least 64
characters. Store it as `Reponomics dashboard key`, then paste it into the
repository secret named `DASHBOARD_SECRET_DO_NOT_REPLACE`.

## Browser Console On A Blank Tab

Use this only on a new blank tab. Do not paste code into the browser console on
an untrusted website.

```js
Array.from(crypto.getRandomValues(new Uint8Array(32)), (byte) =>
  byte.toString(16).padStart(2, "0")
).join("")
```

Copy the generated value, store it somewhere private, and save it as
`DASHBOARD_SECRET_DO_NOT_REPLACE`.

## Strong Versus Casual

`strong` requires a generated, high-entropy secret. Setup rejects short secrets
for this mode.

`casual` accepts any non-empty secret and still encrypts artifacts and hosted
dashboard output, but weak or shared secrets can be brute-forced offline from
the encrypted payload. Use it only when the goal is preventing accidental
viewing, crawling, or casual discovery.

`plain` does not use a dashboard secret. It stores retained CSV artifacts
without encryption and is only supported in private repositories.

## Rotation

1. Generate and save a new key.
2. Add it as `DASHBOARD_NEXT_SECRET`.
3. Run **Actions -> Rotate Reponomics dashboard key -> Run workflow**.
4. Confirm the dashboard opens with the new key.
5. Replace `DASHBOARD_SECRET_DO_NOT_REPLACE` with the new key.
6. Delete `DASHBOARD_NEXT_SECRET`.

If the old `DASHBOARD_SECRET_DO_NOT_REPLACE` was deleted or overwritten before
rotation, the previous encrypted artifact cannot be recovered.
