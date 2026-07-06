# Secure Dashboard Key

Encrypted mode uses `DASHBOARD_SECRET_DO_NOT_REPLACE` to encrypt retained artifacts and dashboard payloads. Reponomics requires this value to be non-empty, but it does not enforce length, complexity, or entropy.

## Generate A Key

Use a high-entropy random key for public Pages dashboards, public repositories, sensitive metrics, or any threat model that includes offline guessing of downloaded encrypted artifacts.

Recommended shell-safe option:

```sh
openssl rand -hex 32
```

That command produces 32 random bytes encoded as 64 hex characters.

Password-manager generated random passwords are also appropriate when they have comparable entropy. Avoid memorable phrases, reused passwords, project names, repository names, or anything you would type from memory.

## Store The Key

1. Save the key in a password manager.
2. Add the same value as the repository secret `DASHBOARD_SECRET_DO_NOT_REPLACE`.
3. Keep access to the password-manager copy limited to people who should unlock the dashboard.

GitHub secrets do not let you read the original value back later. Reponomics cannot recover a lost key from encrypted artifacts.

## Rotate The Key

1. Generate and save a new dashboard key.
2. Add it as `DASHBOARD_NEXT_SECRET`.
3. Run **Actions -> Rotate Key -> Run workflow**.
4. Confirm the dashboard opens with the new key.
5. Replace `DASHBOARD_SECRET_DO_NOT_REPLACE` with the new key.
6. Delete `DASHBOARD_NEXT_SECRET`.

Normal collection refuses to run while `DASHBOARD_NEXT_SECRET` is set, which helps catch unfinished rotation.

## If The Key Was Exposed

Make the dashboard repository private and disable any exposed Pages dashboard before relying on `incident-reset`.

Then set `DASHBOARD_NEXT_SECRET`, run **Actions -> INCIDENT - Reset**, and follow the confirmation prompts. After a successful reset, promote `DASHBOARD_NEXT_SECRET` into `DASHBOARD_SECRET_DO_NOT_REPLACE` and delete `DASHBOARD_NEXT_SECRET`.

For the broader encryption and trust model, see [Security Info](security-info.md).
