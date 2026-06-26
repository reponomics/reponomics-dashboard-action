# ADR 029: Explicit Collection And Publish Repository Lists

Date: 2026-06-26

## Status

Proposed

## Context

Reponomics is preparing for beta users. The current repository-selection model
still reflects an earlier product direction: reduce user anxiety by discovering
eligible repositories, collecting broadly, and letting the dashboard display a
bounded subset. That model is technically feasible, but it weakens several
beta priorities.

Broad automatic selection makes the configuration harder to explain. Users must
understand `include`, `include_only`, `exclude`, `include_others`, automatic
eligibility, and default fill behavior before they can predict which
repositories will be collected. It also creates support and trust questions:
when the configured token can see many repositories, automatic collection can
look like hidden product policy rather than explicit user intent.

The visual surface has a different constraint from the retained data store. A
dashboard can technically retain and process data for many repositories, but a
multi-repository chart is not useful when too many series are shown at once.
Eight repositories is a reasonable maximum for a published comparison surface;
ten or more is already visually crowded for line charts, legends, labels, hover
states, and similar colors.

The README dashboard also matters. Unlike the Pages dashboard, README output
cannot rely on browser-only controls, tabs, or a dynamic repository picker. If
Pages supports multiple client-side repository sets while README shows only one
static set, the product becomes asymmetric across its two publication targets.

Reponomics also has a distinctive trust boundary. It is not a hosted analytics
service. Repository data, retained artifacts, dashboard output, and any
dashboard interaction stay in the user's repository boundary unless the user
chooses to disclose something. This product position is stronger when the
configured repository set is explicit, handwritten, and predictable.

There are currently no external production users. Breaking changes are
acceptable when they simplify the beta product, but they should be documented
clearly because they affect collection continuity, dashboard shape, and user
expectations.

## Decision Drivers

- Make collection consent explicit and inspectable in `config.yaml`.
- Avoid hidden repository discovery or automatic fill behavior.
- Preserve broad enough collection for beta users without making broad
  collection the default.
- Keep the published dashboard visually bounded.
- Keep README and Pages dashboard semantics aligned.
- Avoid a dashboard repository picker in the current beta plan.
- Make publication curation low-risk while making collection removal an
  intentional choice.
- Reinforce the trust-minimized product positioning.

## Decision

Adopt two explicit repository lists:

1. `collect.repositories`
2. `publish.repositories`

Both lists are handwritten by the user. Reponomics does not auto-discover,
auto-fill, or choose repositories by default.

Example:

```yaml
collect:
  repositories:
    - api
    - web
    - docs
    - sdk
    - other-owner/infra

publish:
  repositories:
    - api
    - web
    - docs
```

Repository entries may use either a bare repository name or a full
`owner/repo` name. Bare names are normalized to the owner of the dashboard
repository. Full names are available when the user wants to collect or publish
repositories from another owner.

### Collection List

`collect.repositories` is the collection registry. Reponomics collects new
observations only for repositories listed there.

Policy:

- `collect.repositories` is required.
- Entries must be explicit repository names, either as `repo` or `owner/repo`.
- No repositories are added implicitly.
- No automatic discovery fills remaining slots.
- No `include_others` style behavior remains in the beta model.
- The beta implementation should cap this list at 100 repositories.

The product guidance should treat this list as append-mostly:

> Add repositories to `collect.repositories` when you want Reponomics to start
> keeping history for them. You usually do not need to remove repositories from
> this list. To change what appears in the dashboard, edit
> `publish.repositories`.

Removing a repository from `collect.repositories` means the user has
intentionally decided to stop collecting new observations for that repository.
It does not imply deletion of retained historical data. Data deletion and
retention purging are separate concerns and are not introduced by this ADR.

### Publish List

`publish.repositories` is the dashboard surface. Reponomics publishes only the
repositories listed there.

Policy:

- `publish.repositories` is required.
- Entries must be explicit repository names, either as `repo` or `owner/repo`.
- Every published repository must also appear in `collect.repositories`.
- The list is capped at 8 repositories.
- Reponomics does not choose a default publish list.
- Changing the publish list is the supported way to look at a different subset
  of collected data.

Publishing a different subset requires editing `publish.repositories` and
running publish again. That is acceptable for beta because it keeps both Pages
and README output aligned and avoids a browser-only repository picker.

### Dashboard Behavior

The generated dashboard should be served with no more repositories than the
published surface can reasonably display.

Current product intent:

- no repository picker in the published dashboard;
- no client-side tabs for alternate repository sets in the beta surface;
- no hidden extra repository universe exposed to Pages but not README;
- comparison charts and repository tables operate on `publish.repositories`;
- README and Pages dashboards render the same repository set.

The dashboard may still support focusing or comparing within the published
list, but the published list itself is controlled by configuration and publish
time.

### Relationship To Retained Data

Retained historical data may contain repositories that are no longer published
and may contain repositories that were previously collected but later removed
from `collect.repositories`.

That retained history is not automatically deleted by removing a repository
from either list. Export and future retention behavior should continue to treat
canonical retained data as the durable local record unless an explicit,
versioned deletion or purge feature is introduced.

## Consequences

### Positive

- Configuration becomes easier to explain: collect these, publish these.
- Users can predict exactly which repositories Reponomics will collect.
- The trust boundary is clearer because Reponomics does not infer or discover
  additional repositories.
- Dashboard rendering is bounded by product semantics, not by an after-the-fact
  UI cap.
- README and Pages dashboards remain symmetric.
- Users can change dashboard attention by editing `publish.repositories`
  without stopping collection.
- The collection list becomes a deliberate repository history registry rather
  than a frequently churned display list.

### Negative

- Users must manually add new repositories they want collected.
- Users must manually maintain the published subset.
- Switching dashboard subsets requires a publish run.
- The product gives up the convenience of passive automatic coverage.
- Users with very large portfolios may need to curate collection explicitly
  instead of relying on discovery.

These tradeoffs are intentional for beta. The friction asks users to make
explicit choices about what they want Reponomics to remember and what they want
the dashboard to watch closely.

## Rejected Alternatives

### Automatic Discovery With Exclusions

Continue discovering eligible repositories and let users exclude repositories
they do not want.

Rejected for beta because it makes collection less explicit, keeps the config
model complex, and risks weakening the privacy/trust positioning.

### Broad Collection With Dashboard Picker

Collect a large repository set and expose a picker in the Pages dashboard so
users can choose up to 8 repositories at runtime.

Rejected for the current beta plan because README output cannot provide an
equivalent interaction. It would also keep a larger UI and rendering path than
the beta needs.

### Named Repository Sets In One Static Dashboard

Let users define multiple named sets and render tabs for them in Pages.

Rejected for the current beta plan because it creates a Pages-only experience
unless the README dashboard gains a different static representation. It may be
revisited after beta if users strongly need saved dashboard subsets.

### One Narrow Repository List

Use a single list for both collection and publication.

Rejected because removing a repository from the dashboard would also stop
future collection. That turns ordinary dashboard curation into a decision about
ending an ephemeral data stream.

## Compatibility And Migration Notes

If accepted, this ADR supersedes the repository-selection direction in
ADR 016 where it recommends broad automatic collection with exclusions,
display pinning, and budget-limited fill behavior.

The implementation should provide a clear migration from the old keys:

- `include_only`
- `include`
- `exclude`
- `include_others`
- `include_new`
- `include_private`
- `max_repos`

The migration should prefer explicitness over inference. If the existing config
does not unambiguously express the desired collection and publication lists, the
runtime should fail with a precise message rather than silently choosing
repositories.

Release notes must call out the breaking configuration change before beta users
are invited.

## Open Questions

- Should the `collect.repositories` cap be hard-coded at 100 for beta or be a
  documented recommended limit with a higher internal safety ceiling?
- Should export include all retained historical data, all currently collected
  repositories, or only the published set? Existing export behavior favors the
  full canonical retained history.
- Should removing a repository from `collect.repositories` emit a warning when
  retained data for that repository already exists?
- Should publish runs report repositories present in retained data but absent
  from both current lists?
