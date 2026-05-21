"""Bootstrap empty CSV data files for first-run scenarios.

Creates the data directory, empty CSV files with correct headers, and a
fresh manifest.json with timestamps. Idempotent — skips files that already
exist.
"""

import os

from storage import (
    DATA_DIR,
    CSV_REGISTRY,
    ensure_csv,
    create_manifest,
    migrate_schema,
)


def bootstrap():
    os.makedirs(DATA_DIR, exist_ok=True)

    for filename, (fieldnames, _date_field) in CSV_REGISTRY.items():
        filepath = os.path.join(DATA_DIR, filename)
        ensure_csv(filepath, fieldnames)

    manifest_path = os.path.join(DATA_DIR, "manifest.json")
    if not os.path.exists(manifest_path):
        create_manifest(DATA_DIR)

    migrate_schema(DATA_DIR)


if __name__ == "__main__":
    bootstrap()
    print("Bootstrapped empty data files in data/")
