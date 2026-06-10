# ADR 017: Staged Doctor Diagnostics

Date: 2026-06-10

## Status

Proposed

## Context

Reponomics intentionally keeps retained dashboard data and dashboard secrets under
the user's control. That design protects privacy and avoids central service
custody, but it also means the project cannot recover lost data, inspect user
secrets, or provide conventional support for many failure cases. The software
therefore needs to make its own critical path inspectable.

The first `doctor` mode answers a narrow question: whether a supplied secret can
decrypt the encrypted dashboard payload embedded in rendered dashboard HTML. That
check is useful, but it collapses several different failure domains:

- the dashboard HTML artifact might be missing;
- the HTML might contain an encrypted envelope that the browser runtime rejects;
- the supplied secret might not authenticate the encrypted summary;
- the secret might authenticate the summary but not one or more repository
  chunks;
- decrypted plaintext might fail gzip decompression, JSON parsing, schema
  validation, or semantic consistency checks;
- the rendered HTML might work while the canonical retained `dashboard-data`
  workflow artifact needed for future collection, rotation, or incident reset is
  no longer decryptable;
- plain dashboard artifacts might have valid HTML but malformed JSON chunks;
- encrypted export assets might be missing, tampered, or inconsistent with their
  manifest.

For users, these failures are materially different. A wrong secret is an operator
or trust-boundary issue. A browser envelope mismatch is a software release or
artifact-generation issue. A retained workflow artifact decryption failure is a
continuity and data-loss risk. A plain dashboard JSON failure is not a key
problem at all.

This ADR describes `doctor` as a staged diagnostic tool rather than a single
pass/fail key check.

## Decision Drivers

- Make the dashboard data pipeline inspectable without requiring project
  maintainers to see user secrets or private retained data.
- Distinguish user-key failure from software, artifact, and browser-runtime
  failures.
- Preserve the ability to diagnose both `encrypted` and `plain` modes.
- Treat dashboard readability and retained-data continuity as separate outcomes.
- Provide enough machine-readable diagnostic detail that open-source users can
  self-triage without private support channels.
- Keep diagnostics read-only by default.
- Give implementation and tests a stable stage vocabulary.

## Decision

Expand `doctor` into a staged diagnostic mode. It should report each diagnostic
stage independently and produce headline outcomes derived from those stages.

The mode model should remain `encrypted | plain`. Legacy encrypted submode names
are orthogonal to diagnosis and should not appear in the doctor result model.
Doctor should instead report the configured artifact mode separately from the
mode detected in rendered dashboard HTML. A mismatch is itself diagnostic: for
example, a workflow can expect encrypted output while the rendered dashboard is
plain, missing, or malformed.

The headline report should include these mode fields and stage-like status
outcomes rather than reducing the diagnostic to a single boolean:

- `dashboard_html_found`
- `configured_artifact_mode`
- `detected_dashboard_mode`
- `browser_payload_contract_valid`
- `key_cryptographically_accepted`
- `dashboard_data_well_formed`
- `dashboard_data_semantically_consistent`
- `repo_chunks_valid`
- `retained_data_artifact_decryptable`
- `export_artifact_valid`

These outcomes should not be collapsed into one success value. Status values
should distinguish `passed`, `failed`, `skipped`, and `warning` so doctor can
separate "not applicable", "not requested", "not restorable", and "actually
failed". In particular, `doctor` should preserve the distinction between:

- a key that cannot decrypt encrypted dashboard data;
- a key that decrypts dashboard data, but the browser would reject the envelope;
- dashboard HTML that is readable now, but retained data that cannot be
  decrypted for the next collection or rotation run;
- a plain dashboard artifact that has no secret boundary but can still have
  malformed summary or chunk data.

### Result Model

The runtime should use a structured result model similar to:

```python
DoctorStageStatus = Literal["passed", "failed", "skipped", "warning"]
DoctorArtifactMode = Literal["encrypted", "plain"]
DetectedDashboardMode = Literal["encrypted", "plain", "unknown"]


@dataclass(frozen=True)
class DoctorStage:
    name: str
    status: DoctorStageStatus
    subject: str = ""
    detail: str = ""


@dataclass(frozen=True)
class DoctorSecretResult:
    label: str
    provided: bool
    stages: list[DoctorStage]


@dataclass(frozen=True)
class DashboardDoctorResult:
    configured_artifact_mode: DoctorArtifactMode
    detected_dashboard_mode: DetectedDashboardMode
    dashboard_html_found: DoctorStageStatus
    browser_payload_contract_valid: DoctorStageStatus
    dashboard_data_well_formed: DoctorStageStatus
    dashboard_data_semantically_consistent: DoctorStageStatus
    repo_chunks_valid: DoctorStageStatus
    retained_data_artifact_decryptable: DoctorStageStatus
    export_artifact_valid: DoctorStageStatus
    secret_results: list[DoctorSecretResult]
    stages: list[DoctorStage]
```

For encrypted mode, key-dependent stages should run once per supplied secret
label. The result must not collapse key diagnostics into one ambiguous boolean.
For example, summary authentication should be reported per label:

```text
DASHBOARD_SECRET_DO_NOT_REPLACE: summary_authenticates=passed
COMPARISON_SECRET: summary_authenticates=failed
```

If `COMPARISON_SECRET` is not supplied, that labeled subject should be recorded
as `skipped`. `DASHBOARD_SECRET_DO_NOT_REPLACE` and `COMPARISON_SECRET` must
remain labels only; diagnostic output must not include secret values, derived
keys, or plaintext data rows.

For plain mode, key-dependent stages should be marked `skipped` with a clear
detail such as `plain mode has no dashboard decryption key`. Plain diagnostics
should still validate the HTML payload, chunk model, retained workflow artifact
shape, and semantic consistency.

### Diagnostic Layers

`doctor` should have five validator layers.

1. Artifact discovery:

   - locate the dashboard HTML workflow artifact or configured dashboard path;
   - locate the embedded dashboard data script;
   - locate the retained `dashboard-data` workflow artifact when available;
   - locate export manifest and export ciphertext asset when present.

2. Browser payload contract:

   - mirror the checks performed by `secure-runtime.js` for encrypted mode;
   - validate the plain dashboard object contract for plain mode;
   - report browser contract failures before attempting deeper semantic checks.

   Mirroring `secure-runtime.js` is required but not sufficient as a process
   guarantee. The implementation must include parity tests or shared contract
   fixtures covering dashboard version, cipher, KDF name/hash/iterations, salt
   length, encrypted token shape, `chunk_count`, chunk id format, and export
   manifest validation. Browser-runtime contract drift should fail tests.

3. Cryptographic and plaintext decoding:

   - derive the encrypted dashboard key;
   - authenticate summary and chunk blobs;
   - decompress gzip payloads;
   - parse decrypted JSON;
   - classify wrong-key failures at authentication stages.

4. Dashboard semantic consistency:

   - validate summary-level fields;
   - validate repo-to-chunk mappings;
   - validate chunk-to-repo agreement;
   - validate required per-repo structures;
   - validate counts and references.

5. Continuity and export checks:

   - validate the canonical retained `dashboard-data` workflow artifact
     separately from rendered dashboard HTML;
   - validate workflow artifact encryption, manifest, schema, and lineage
     metadata where available;
   - validate encrypted export manifest, asset path, ciphertext hash, decrypted
     ZIP hash, and decryptability where available.

### Diagnostic Boundary With Browser UI

Doctor is primarily responsible for encryption, storage, artifact, and dashboard
data contract diagnostics. It should identify the point where those layers have
been ruled out so remaining failures can be treated as browser UI or runtime
failures.

For a rendered dashboard, doctor reaches the UI handoff boundary when:

- the dashboard HTML is found;
- the configured artifact mode and detected dashboard mode are compatible;
- the browser payload envelope is valid;
- encrypted mode has at least one supplied secret label that authenticates the
  summary;
- authenticated encrypted plaintext decompresses and parses, or plain payload
  JSON parses;
- summary and chunk data pass minimum semantic consistency checks.

When those conditions hold, doctor should report that encryption and storage
diagnostics for the rendered dashboard payload reached the browser/UI handoff
boundary. A user-visible failure after that point is more likely in the browser
runtime, chart/table rendering, interaction state, CSS/layout, or browser
environment than in the named dashboard secret or embedded dashboard data object.
Doctor should report retained workflow artifact continuity, export artifact
validity, GitHub artifact restore, and Pages deployability as separate subjects.
Failures in those subjects are serious, but they do not prove that a user's
dashboard key is wrong or that the current in-browser dashboard payload is
undecryptable.

Doctor may still include an optional browser smoke check in a future workflow
diagnostic preset, but browser UI behavior is not the core responsibility of
doctor.

If a future browser smoke check exists, its failure should not be reported as a
key or retained-data failure unless an earlier encryption, storage, or semantic
stage also failed.

### Workflow Artifact Restore Semantics

Doctor should support explicit artifact source reporting so
`retained_artifact_found=failed` is not ambiguous.

Initial supported sources are:

- `restored-path`: inspect workflow artifact contents already restored into the
  runner workspace at an explicit path.
- `skip`: do not inspect the retained workflow artifact, and mark retained
  continuity stages `skipped`.

The first workflow implementation should prefer an explicit
`actions/download-artifact` restore step over hidden in-process GitHub API
downloads. Download failure is then isolated to a single workflow step and can
be diagnosed before doctor runs. If direct API restore is added later, it should
be a platform/workflow diagnostic layer, not part of repository-secret
validation.

The diagnostic output should distinguish:

- restore not requested;
- insufficient token or permissions;
- no matching workflow artifact;
- matching workflow artifact found but unreadable after restore;
- restored workflow artifact readable but invalid or undecryptable.

GitHub artifact restore failures include artifact name or run-id mismatch,
expired artifacts, artifacts not yet available because the producing workflow is
still running, missing `actions: read` permission, repository or fork
trust-boundary restrictions, REST API rate limiting or service failures, and
corrupt or incomplete restored ZIP contents. None of those conditions involves
the repository dashboard secret. They should never be reported as evidence that
`DASHBOARD_SECRET_DO_NOT_REPLACE` or `COMPARISON_SECRET` is incorrect.

Dashboard HTML and export assets may use the same source model. They can be
inspected from already-restored workflow artifact contents or from explicit
paths. If a future workflow downloads the HTML artifact automatically, the
summary must make that restore action visible.

### Pages Deployability

Doctor may include a platform preflight that checks whether GitHub Pages is
configured and deployable by the workflow token. This check should be reported as
a Pages/platform subject, not as a dashboard-secret or payload-validation
subject.

A useful Pages preflight should distinguish:

- Pages not enabled for the repository;
- Pages configured for a different build source than the template workflow
  expects;
- workflow token lacks the permission needed by the deploy step;
- latest Pages deployment failed or is pending;
- Pages API could not be queried because of permission, rate-limit, or service
  failure.

When this check is unavailable, doctor should mark Pages stages as `skipped` or
`warning` with the API/permission reason. A Pages failure can explain why a
hosted dashboard is absent or stale, but it does not imply that retained data or
dashboard ciphertext is unrecoverable.

### Strictness

Strictness should simplify workflow consumption rather than create a second
diagnostic model. Doctor should always emit the same detailed stage report. Any
strictness or preset setting should only decide which reported failures fail the
workflow.

The initial implementation should keep the user-facing workflow policy simple:

- encrypted mode fails when no supplied secret authenticates the rendered
  dashboard summary;
- plain mode skips key stages by design;
- a missing or unreadable dashboard target fails because no diagnosis can be
  made;
- retained artifact, export, GitHub API, and Pages checks report explicit
  statuses without being conflated with key acceptance.

If stricter policies are added later, they should be workflow-maintainer presets
rather than manual user prompts in template workflows. A future preset may say
"fail unless the full diagnostic path passes", but it should not require users
to understand each stage before running doctor.

## Scope By Mode

### Encrypted Mode

Encrypted mode doctor checks must answer:

- Does the rendered dashboard HTML exist?
- Is the encrypted dashboard envelope compatible with the browser runtime?
- Which configured secret labels can authenticate the encrypted summary?
- Do authenticated summary and chunk payloads decompress and parse?
- Do chunks match the summary and contain the expected per-repository data?
- Can the retained `dashboard-data` workflow artifact decrypt with the same
  current secret?
- If an encrypted export asset is present, is it valid and decryptable?

Encrypted mode failure reports should be explicit that a successful dashboard
HTML check does not prove retained workflow artifact continuity. The browser
could be working while future collection, rotation, or incident-reset operations
are at risk.

### Plain Mode

Plain mode has no dashboard decryption key and no encrypted browser unlock
boundary. Doctor still has useful work:

- Does the downloadable dashboard HTML artifact exist?
- Does the plain dashboard object exist?
- Does the plain dashboard object use the expected version and encoding?
- Are `summary`, `chunks`, and `chunk_count` structurally valid?
- Does every summary repo map to an emitted chunk?
- Does every chunk parse as JSON?
- Does every chunk's `repo` field match the summary repo that references it?
- Are required per-repository fields present?
- Does the retained `dashboard-data` workflow artifact exist and match expected
  schema/lineage contracts?

Plain mode diagnostics should not mention wrong keys or decryption failures for
dashboard HTML. If retained workflow artifact contents are plain CSV bundles,
doctor should report their presence, schema, and lineage integrity rather than
key acceptance.

Plain dashboards currently embed the data object as JavaScript, while encrypted
dashboards use a JSON script tag. That asymmetry makes robust diagnostics harder.
The preferred implementation is to emit a plain JSON script tag with the same
summary/chunk envelope shape used by encrypted mode:

```html
<script id="plain-dashboard-data" type="application/json">...</script>
```

Doctor should then parse `plain-dashboard-data` directly. Until that renderer
change lands, doctor may support the current JavaScript assignment as a
transitional extractor, but the transitional parser should be treated as a
compatibility bridge rather than the long-term contract.

## Stage And Test Matrix

The following matrix defines the initial implementation contract. Test fixtures
should be table-driven where possible.

| Stage | Applies To | Failure Mode | Diagnostic Meaning | Planned Validation |
| --- | --- | --- | --- | --- |
| `dashboard_html_found` | encrypted, plain | HTML path/artifact missing or unreadable | No rendered dashboard can be inspected | Point doctor at a missing path |
| `configured_artifact_mode_recorded` | encrypted, plain | Configured mode is absent or invalid | Doctor cannot compare expected and rendered mode | Run with invalid or missing mode metadata |
| `detected_dashboard_mode_recorded` | encrypted, plain | Rendered payload mode cannot be detected | HTML exists, but doctor cannot classify payload type | Remove both encrypted and plain payload markers |
| `configured_detected_mode_match` | encrypted, plain | Configured mode differs from detected dashboard mode | Workflow expected one mode but rendered another | Render plain payload while configured encrypted, and vice versa |
| `dashboard_script_found` | encrypted, plain | Expected script tag missing | Rendered HTML does not contain dashboard payload | Remove `encrypted-dashboard-data` or plain dashboard object |
| `dashboard_script_json_valid` | encrypted, plain | Script contents are not JSON object | HTML shell exists, embedded data is malformed | Replace script text with invalid JSON and with a JSON array |
| `browser_envelope_version_valid` | encrypted, plain | Unsupported dashboard data version | Browser/runtime contract mismatch | Change `version` |
| `browser_envelope_cipher_valid` | encrypted | Unsupported cipher | Browser cannot safely interpret encrypted payload | Change `cipher` |
| `browser_envelope_kdf_valid` | encrypted | KDF name/hash/iterations mismatch | Browser key derivation contract mismatch | Change KDF fields one at a time |
| `browser_envelope_encoding_valid` | encrypted, plain | Unsupported encoding | Runtime cannot decode payload format | Change `encoding` |
| `browser_envelope_salt_valid` | encrypted | Missing or wrong salt length | Key derivation cannot match browser | Remove salt and change decoded length |
| `browser_envelope_summary_token_valid` | encrypted | Missing or malformed summary token | Browser cannot decrypt summary | Remove token, remove delimiter, corrupt base64 |
| `browser_envelope_chunks_object_valid` | encrypted, plain | `chunks` missing, array, or non-object | Chunk loader cannot operate | Replace `chunks` with null, array, string |
| `browser_envelope_chunk_count_valid` | encrypted, plain | `chunk_count` disagrees with emitted chunks | Summary/chunk envelope is inconsistent | Change `chunk_count` |
| `browser_envelope_chunk_ids_valid` | encrypted, plain | Chunk id format not accepted by runtime | Runtime may reject or fail lookup | Rename one chunk id to invalid format |
| `key_derivation_ready` | encrypted | Secret missing or KDF input invalid | Doctor cannot attempt authentication | Run without secret; corrupt salt |
| `summary_authenticates` | encrypted | AES-GCM authentication failure | Supplied key does not match summary, or summary ciphertext is corrupt | Use wrong key; flip summary ciphertext byte |
| `summary_decompresses` | encrypted | Authenticated plaintext is not gzip | Key was accepted but payload bytes are wrong format | Re-encrypt non-gzip plaintext with valid key |
| `summary_json_valid` | encrypted | Decompressed summary is not JSON object | Key accepted, but summary model is malformed | Re-encrypt invalid JSON and JSON array |
| `summary_min_schema_valid` | encrypted, plain | Required summary fields missing | Dashboard model cannot support runtime | Remove `repos`, `totals`, or `repo_chunks` |
| `summary_repo_chunk_mapping_valid` | encrypted, plain | Repo mapping has non-string repo/chunk ids | Runtime cannot map repo selections to chunks | Insert invalid map entries |
| `chunk_payload_present` | encrypted, plain | Referenced chunk id missing | Summary references unavailable data | Delete one referenced chunk |
| `chunk_authenticates` | encrypted | Chunk AES-GCM authentication failure | Summary key worked, but chunk is corrupt or encrypted with another key | Flip chunk ciphertext; re-encrypt chunk with another key |
| `chunk_decompresses` | encrypted | Authenticated chunk plaintext is not gzip | Chunk key accepted but chunk format is invalid | Re-encrypt non-gzip chunk plaintext |
| `chunk_json_valid` | encrypted, plain | Chunk plaintext/string is invalid JSON object | Chunk exists but cannot be parsed | Replace chunk with invalid JSON and JSON array |
| `chunk_min_schema_valid` | encrypted, plain | Required chunk fields missing | Runtime can parse chunk but cannot render repo data | Remove `repo_series`, `repo_weekday`, `repo_referrers`, `repo_paths`, or `growth` |
| `chunk_repo_matches_summary` | encrypted, plain | Chunk `repo` differs from mapped repo | Summary/chunk integrity mismatch | Swap two chunk payloads or edit `repo` |
| `chunk_growth_contract_valid` | encrypted, plain | Chunk growth lacks expected per-repo series structure | Growth views may fail or show incorrect data | Remove `growth.per_repo.series` |
| `semantic_counts_valid` | encrypted, plain | Repo count, chunk count, or map count disagree | Dashboard is internally inconsistent | Add orphan chunk, duplicate map, or mismatched counts |
| `ui_handoff_boundary_reached` | encrypted, plain | Earlier storage, encryption, or semantic stages failed | Doctor cannot rule out data-layer causes for UI failure | Run successful encrypted and plain fixtures and assert this stage passes only after prerequisite stages pass |
| `browser_runtime_smoke_valid` | encrypted, plain | Optional browser smoke check fails after handoff | Data layer appears valid; failure is likely browser/runtime/UI | Future Playwright smoke test with intentionally broken runtime hook |
| `workflow_artifact_restore_requested` | encrypted, plain | Retained workflow artifact restore skipped | Continuity was not checked by request | Run without a restored artifact path |
| `workflow_artifact_restore_authorized` | encrypted, plain | Artifact restore step reported token or permission failure | Doctor could not inspect retained continuity, but the failure is platform/workflow scoped | Feed doctor restore-step metadata for insufficient `actions: read` permission |
| `retained_artifact_found` | encrypted, plain | `dashboard-data` workflow artifact unavailable | Future collect/publish continuity cannot be checked | Run doctor without restored contents and no matching workflow artifact |
| `retained_artifact_readable` | encrypted, plain | Restored workflow artifact contents are unreadable | Workflow artifact exists but restored contents cannot be inspected | Restore unreadable or malformed artifact contents |
| `retained_artifact_decrypts` | encrypted | Retained workflow artifact cannot decrypt with current secret | Dashboard may work now, but retained history may be unrecoverable | Encrypt retained artifact with wrong key |
| `retained_artifact_schema_valid` | encrypted, plain | Retained bundle missing manifest or CSV family | Future merge/render may fail | Remove manifest or required CSV file |
| `retained_artifact_lineage_valid` | encrypted, plain | Lineage metadata unreadable or inconsistent | Active retention and incident reset continuity at risk | Corrupt lineage metadata |
| `pages_configuration_found` | encrypted, plain | GitHub Pages is disabled or unavailable | Hosted dashboard may be absent even when dashboard data is valid | Mock Pages API disabled response or skip when no token is available |
| `pages_source_valid` | encrypted, plain | Pages source does not match expected Actions deployment model | Deploy workflow may publish nowhere or publish stale content | Mock Pages source mismatch |
| `pages_deployment_permission_valid` | encrypted, plain | Workflow token cannot deploy Pages | Hosted dashboard deployment can fail independently of dashboard data | Mock deploy permission/API denial |
| `pages_latest_deployment_valid` | encrypted, plain | Latest Pages deployment failed or is pending | Hosted dashboard may be absent or stale | Mock failed or pending Pages deployment |
| `export_manifest_found` | encrypted | Export manifest absent when export is expected | Export diagnostics cannot continue | Remove manifest from HTML |
| `export_manifest_valid` | encrypted | Export manifest schema invalid | Browser export verification cannot run | Remove asset/hash fields |
| `export_asset_found` | encrypted | Referenced ciphertext asset missing | User cannot export canonical CSV bundle | Delete export asset |
| `export_ciphertext_hash_valid` | encrypted | Asset bytes do not match manifest hash | Export asset is stale or tampered | Flip asset byte |
| `export_decrypts` | encrypted | Export asset fails authentication | Key mismatch or tampered export asset | Encrypt export with another key |
| `export_plaintext_hash_valid` | encrypted | Decrypted ZIP hash mismatches manifest | Export plaintext integrity failure | Re-encrypt altered ZIP with valid key and stale manifest |

## Reporting

The workflow summary should include:

- headline outcomes;
- configured artifact mode and detected dashboard mode;
- one row per checked secret label in encrypted mode;
- one stage table grouped by layer;
- counts of passed, failed, skipped, and warning stages;
- a short interpretation section that distinguishes user-key failures from
  software/artifact failures.

The summary should keep the layered distinction visible. It should separately
state whether:

- a named key authenticated ciphertext;
- authenticated plaintext decompressed;
- plaintext parsed as JSON;
- the dashboard model was meaningful;
- the browser envelope was compatible;
- retained `dashboard-data` workflow artifact continuity was checked;
- export artifact integrity was checked;
- the browser/UI handoff boundary was reached.

That structure preserves the key diagnostic value: a named key can work
cryptographically while the browser/runtime/data contract fails elsewhere.

Doctor should also emit a machine-readable JSON report as a workflow artifact or
action output. The JSON report should include stage names, statuses, subjects,
and details, but must not include secret values, derived keys, decrypted CSV
rows, or full dashboard payloads.

Failure commands in logs should use GitHub workflow command escaping. Warnings
and errors should report stage names and bounded diagnostics only.

## Failure Semantics

`doctor` is read-only and should avoid destructive or repair behavior.

The mode should fail the workflow when:

- encrypted mode is configured or detected, but no supplied secret authenticates
  the encrypted dashboard summary;
- a future workflow-maintainer preset requests a stricter failure policy and one
  of the preset's required diagnostic subjects fails;
- no diagnostic target can be inspected.

The mode may complete with warnings when:

- retained workflow artifact or export artifact checks are unavailable because the
  workflow did not restore those workflow artifact contents;
- optional export assets are absent;
- plain mode skips encrypted-key stages by design.

The initial implementation may keep the existing failure policy for compatibility
while adding richer stage output.

## Implementation Plan

1. Introduce `DoctorStage` and `DashboardDoctorResult`.
2. Split current `check_dashboard_key` into envelope, cryptographic, plaintext,
   semantic, retained workflow artifact, and export validators.
3. Add plain-mode dashboard object validation alongside encrypted dashboard
   validation.
4. Add a summary renderer for headline outcomes and stage records.
5. Add a JSON diagnostic report.
6. Add table-driven tamper fixtures for the matrix above.
7. Add browser contract parity tests against `secure-runtime.js` constants and
   validation behavior.
8. Update template doctor workflow docs so users understand that `doctor`
   distinguishes key acceptance, browser compatibility, artifact continuity, and
   plain-mode structural integrity.

## Implementation Notes

The initial implementation should be workflow-first. The CLI key check remains a
compatibility helper, but the supported consumption path is the GitHub Actions
summary plus a machine-readable `reponomics-doctor-report` workflow artifact.

Initial implemented scope:

- staged result objects for dashboard, stage, and per-secret diagnostics;
- encrypted dashboard payload detection and browser-envelope validation;
- per-secret key derivation, summary authentication, summary decoding, chunk
  authentication, chunk decoding, and minimum semantic checks;
- encrypted export manifest, asset, ciphertext hash, decryptability, and
  plaintext hash checks using any supplied label that authenticated the dashboard
  summary;
- plain dashboard rendering and diagnosis through the `plain-dashboard-data` JSON
  script contract, with the current runtime parsing that script into
  `dashboardDataObject`;
- retained `dashboard-data` continuity checks for already-restored workflow
  artifact contents: encrypted retained artifact readability, per-label
  decryptability, schema validation, lineage validation when lineage metadata is
  present, and plain retained directory schema validation;
- workflow summary headlines, per-secret rows, stage counts, and a JSON report
  path uploaded by the composite action;
- preservation of the existing `check_dashboard_key` helper as a compatibility
  wrapper over the staged diagnostics.

Deliberate deferrals:

- Strict failure presets remain a follow-up workflow-policy decision. The
  diagnostic model now emits the information needed for stricter policies, but
  the initial workflow behavior stays simple: encrypted doctor fails when no
  supplied secret authenticates the rendered dashboard summary, and other
  subjects report explicit statuses.
- Automatic GitHub API restore for retained `dashboard-data` workflow artifacts
  is not yet implemented, and may not be needed if template workflows use
  explicit `actions/download-artifact` restore steps. The current implementation
  inspects already-restored retained contents when present and marks retained
  continuity stages as `skipped` when no restored artifact path is available.
- Pages deployability preflight is not yet implemented. When added, it should be
  a platform/workflow diagnostic subject and should not affect dashboard-secret
  acceptance.
- Browser runtime smoke testing remains outside the first doctor slice. The
  implemented `ui_handoff_boundary_reached` stage marks the line where
  encryption, storage, and data-contract checks have been ruled out.

## Consequences

- Users get actionable diagnostics without exposing private data to maintainers.
- Reviewers can distinguish false-positive secret logging concerns from real
  diagnostic output paths.
- The implementation gains a larger test surface, but the tests map directly to
  the data-loss and unrecoverability risks that matter most.
- Doctor mode becomes a durable support boundary for both encrypted and plain
  dashboard users.

## Alternatives Considered

### Keep doctor as a key check

Pros:
- simple implementation
- easy summary

Cons:
- cannot distinguish browser-runtime failures from user-key failures
- cannot diagnose retained workflow artifact continuity
- does not help plain mode users

### Simulate the browser only

Pros:
- close to the user-visible unlock path

Cons:
- still misses retained workflow artifact continuity
- less precise for cryptographic/plaintext stage classification
- harder to run in minimal workflow contexts

### Add repair behavior

Pros:
- potentially reduces manual recovery work

Cons:
- violates the read-only diagnostic expectation
- risks destructive behavior in the highest-risk workflows
- should be handled by explicit modes such as rotate or incident reset, not
  doctor

## Non-Goals

This ADR does not define:

- automatic recovery of missing or undecryptable retained data;
- support for collecting or transmitting private diagnostic payloads to project
  maintainers;
- removal of legacy encrypted submode names from the action contract;
- a replacement for incident reset, rotate-key, or active-retention lineage
  checks;
- a general GitHub token permission doctor for repository setup.
