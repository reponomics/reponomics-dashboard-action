# ADR 016: Collection Scale, Cost Visibility, And Lazy Dashboard Data

Date: 2026-06-06

## Status

Proposed

## Context

Reponomics currently asks the user to decide which repositories to collect.
That choice is stressful because GitHub traffic data is only available for the
last 14 days. A repository omitted today may lose historical traffic that cannot
be reconstructed later.

The earlier concern was that broad collection might be constrained by artifact
storage, browser string limits, or visual clutter. Current measurements and the
active-retention policy change the priority order:

- A synthetic 50-repository, 90-day dataset using the current schema produced
  about 2.18 MB of raw CSV and manifest data.
- The same dataset produced about 1.20 MB of public dashboard HTML and about
  1.53 MB of encrypted Pages HTML.
- The canonical compressed encrypted data artifact for that dataset was about
  139 KB.
- With at most five retained data-dashboard artifacts, artifact storage is not
  the meaningful limit for ordinary Reponomics use.
- Browser string hard limits are also not the meaningful limit at current data
  sizes. Browser working memory, parse time, chart dataset count, and DOM size
  become the relevant client-side constraints first.

The realistic constraints are therefore:

- GitHub API request volume and secondary-rate-limit behavior.
- GitHub Actions runner minutes for private repositories.
- Browser responsiveness during unlock, parsing, charting, and table rendering.
- Human visual cognition: a dashboard with 50 or more simultaneous repo series
  is not useful, even if it technically renders.

GitHub's REST API best-practice documentation recommends authenticated requests,
serial request queues, appropriate rate-limit handling, and conditional requests
using `ETag` or `Last-Modified` where appropriate. An authorized conditional
`GET` that returns `304 Not Modified` does not count against the primary REST
rate limit.

GitHub REST rate-limit documentation also distinguishes primary limits from
secondary limits. Personal access tokens generally use the authenticated user's
5,000 requests/hour primary limit. The built-in `GITHUB_TOKEN` has a separate
1,000 requests/hour/repository primary limit. GitHub also enforces secondary
limits, including limits around concurrency, requests to one endpoint per
minute, CPU time, and undisclosed abuse-prevention criteria.

GitHub traffic endpoints are special. Page views, clones, popular paths, and
popular referrers return the last 14 days and require repository
`Administration` read permission for fine-grained tokens. Public repository
metadata can often be fetched with lower-risk credentials, but traffic data
cannot be replaced by ordinary public metadata calls.

Relevant GitHub documentation:

- <https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api>
- <https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api?apiVersion=2026-03-10>
- <https://docs.github.com/en/rest/metrics/traffic?apiVersion=2026-03-10>

## Decision Drivers

- Prefer broad collection so users do not have to guess which repositories will
  matter before traffic ages out.
- Keep the default product behavior understandable for non-enterprise users.
- Keep GitHub API behavior patient enough to avoid secondary limits.
- Give users visible cost forecasts instead of hiding Actions-minute impact.
- Avoid overexposing the user's high-privilege traffic token.
- Keep the first dashboard render fast even when the retained corpus is broad.
- Do not make visualizations depend on showing every collected repository at
  once.
- Preserve headroom for richer future data without redesigning the storage
  model again.

## Decision

Adopt the product principle:

> Collect broadly, display narrowly, decrypt lazily, and report cost precisely.

### Collection Scope

The collector should support a broader repository corpus than the dashboard
displays at once.

The initial product target should be up to 200 eligible repositories, not 1,000.
That is high enough to remove repo-selection anxiety for most users while
keeping daily runtime understandable. The implementation may keep this as a
configurable ceiling, but exceeding 200 repositories should require an explicit
budget acknowledgement or advanced configuration.

Eligibility means repositories for which the configured traffic credential can
read traffic data. At the current product boundary, that means repositories
where the user has suitable administrative/read access for traffic endpoints.
This ADR does not decide to collect arbitrary public repositories outside that
access boundary.

Repository configuration should shift from "choose the small set to protect" to
"collect eligible repositories unless excluded or budget-limited." Users should
still be able to exclude repositories, pin repositories for display, and set a
lower cost ceiling.

### Schedule

The default schedule should be once per day.

Reponomics is not a realtime analytics product, and GitHub traffic endpoints
return a rolling 14-day window. A once-per-day schedule is enough to preserve
daily traffic history under normal conditions. Missed runs should recover as
long as collection resumes within the 14-day traffic window.

Twice-daily collection should be treated as a resilience or advanced option, not
as the default. The product should show the expected monthly Actions-minute
impact before a user opts into a more frequent schedule.

### API Pacing

Requests should remain serial by default. The initial patient pacing target is a
0.5-second minimum gap between GitHub API requests.

This is intentionally below the theoretical 5,000 requests/hour primary limit
for an authenticated user token, but above bursty polling behavior. It also
tracks GitHub's guidance to avoid concurrent requests when trying to stay clear
of secondary limits.

The pacing layer should be endpoint-aware and credential-aware over time, but
the first implementation should prefer correctness and clear reporting over
clever concurrency.

### Conditional Requests

The collector should store and reuse HTTP validators for GitHub `GET`
endpoints:

- `ETag`
- `Last-Modified`
- endpoint URL or normalized endpoint key
- credential class used for the request
- last successful status and capture time

On a subsequent run, the collector should send `If-None-Match` when an `ETag` is
known, and `If-Modified-Since` when only `Last-Modified` is known.

For `304 Not Modified`, the collector should:

- count the request as a conditional cache hit;
- avoid rewriting the unchanged data family;
- preserve the previous logical data for merge/render;
- record the hit in collection status and run summaries;
- include the `304` in wall-clock/runtime accounting even though it does not
  count against the primary REST rate limit when correctly authorized.

Conditional requests are required for metadata endpoints where they are likely
to be effective. They should also be attempted for traffic endpoints when GitHub
returns validators, but the product must not assume that traffic endpoints will
produce high cache-hit rates. Traffic endpoints are rolling 14-day resources and
may legitimately change daily.

### Token Split

The high-privilege traffic credential should be used only where needed:

- traffic views
- traffic clones
- popular referrers
- popular paths
- any endpoint that GitHub documents as requiring repository
  `Administration` read access

The built-in `GITHUB_TOKEN` may be used for public, non-traffic metadata where
it can reduce use of the user's traffic credential without requiring broader
workflow permissions. Candidate metadata includes repository profile fields,
stars, forks, watchers/subscribers where available, and public community-health
signals.

If a metadata request cannot be fulfilled by `GITHUB_TOKEN`, the collector may
fall back to the traffic credential only when the endpoint is needed for the
current product surface and the user has not disabled fallback. This fallback
must be visible in the run summary.

This split is an optimization and privilege-reduction strategy, not a way to
collect traffic for repositories outside the traffic credential's access scope.

### Cost Estimation And Reporting

The product should provide a deterministic usage estimate before collection and
an actual usage report after collection.

The estimate should include:

- configured collection schedule;
- eligible repository count;
- selected repository count after exclusions and budget limits;
- expected API requests by credential class;
- expected requests by endpoint family;
- expected patient pacing delay;
- expected wall-clock range;
- expected monthly private-runner minutes;
- whether public standard GitHub-hosted runner minutes are expected to be free
  for the repository type;
- whether the configured repository count exceeds the recommended default
  budget.

The post-run report should include:

- actual selected repositories;
- actual GitHub API requests by endpoint family;
- actual requests by credential class;
- `200`, `304`, `403`, `404`, `429`, `5xx`, and retry counts;
- ETag/conditional hit rate;
- total sleep time from pacing and backoff;
- total wall-clock time;
- estimated monthly Actions minutes at the current schedule;
- primary rate-limit headers observed for each credential class;
- secondary-rate-limit events and retry windows, if any.

The basic request model for the current collector is:

```text
requests ~= token_validation + discovery_pages + (selected_repos * 6)
```

The six current per-repository requests are:

1. repository detail
2. community profile
3. traffic views
4. traffic clones
5. popular referrers
6. popular paths

The optimized model should separate traffic from metadata:

```text
traffic_requests ~= traffic_discovery + (selected_repos * 4)
metadata_requests ~= metadata_discovery + conditional_metadata_requests
```

The cost model should be generated by the same endpoint plan the collector will
execute. It should not be a parallel hand-maintained estimate.

### Artifact Retention

Artifact storage is not the primary scaling constraint under the active
retention policy.

The collector should retain a small number of active data-dashboard artifacts,
with a default of five or fewer. Each successful collection run should delete
older artifacts beyond the retained cushion. Retention period remains important
for outage recovery: if collection fails for several runs, the last successful
artifact should remain available long enough to resume without data loss or
manual recovery.

The tentative default retention period remains 60 days, subject to workflow and
repository policy constraints.

### Dashboard Display Limit

The dashboard must not attempt to show every collected repository as a
simultaneous chart series.

The default display set should be 10 to 20 repositories, selected by the active
metric and time window plus any user-pinned repositories. The full collected
corpus should remain searchable, filterable, and selectable.

Chart behavior should follow these rules:

- aggregate summaries use all collected repositories in scope;
- default charts show top repositories plus selected/pinned repositories;
- long-tail repositories may be grouped as `Other` when aggregate context is
  useful;
- compare mode should cap simultaneous compared repositories, initially 6 to 8;
- table views may expose the full corpus but should use search, sorting, and
  eventually virtualization for large corpora.

### Lazy Encrypted Dashboard Data

Encrypted dashboard data should be partitioned so the browser can decrypt and
parse only what it needs.

The encrypted dashboard should move toward this shape:

1. A small encrypted manifest/summary payload.
2. Per-repository encrypted data chunks.
3. Optional aggregate chunks for all-repo summary views.
4. Lazy loading and decryption when the user focuses, compares, searches, or
   drills into a repository.

Each chunk should be compressed before encryption. The current canonical data
artifact already compresses before encryption; the encrypted Pages payload
should follow the same principle.

Chunk names in public repositories must not reveal repository names. Acceptable
names include opaque content hashes, HMAC-derived identifiers, or manifest
indexes that are meaningless without the dashboard key. The authenticated
manifest should map display repository names to chunk identifiers after unlock.

### Client Secret Handling

Lazy decryption must not persist the user's dashboard secret on the client.

The browser should derive a non-extractable `CryptoKey` once per unlock and
reuse that in-memory key for chunk decryption. After key derivation, the raw
secret string should be removed from form inputs and JavaScript state as soon as
practical.

The unlocked state is tab-session state only. Reloading the page, closing the
tab, or opening the dashboard in a new browser context should require the user
to enter the dashboard secret again.

The dashboard must not write any of the following to `localStorage`,
`sessionStorage`, IndexedDB, Cache Storage, cookies, URL fragments, logs, or
downloaded files:

- the raw dashboard secret;
- password-derived key material;
- extractable wrapped keys;
- decrypted per-repository chunks;
- decrypted manifest data that would disclose private repository choices or
  traffic details in a public repository.

Decrypted chunks may be cached in memory for the current unlocked tab session.
Any persistent "remember this browser", offline cache, or trusted-device feature
requires a separate ADR because it changes the privacy and threat model.

If chunks are emitted as separate Pages assets, the downloadable standalone
artifact must still work locally. That may require either a bundled standalone
variant or a local-file-compatible loading strategy.

## Consequences

Users can safely default to broader collection without needing to predict which
repositories will matter later.

The product can make collection cost visible in practical terms: expected API
requests, expected run minutes, and expected monthly private-runner minutes.

The high-privilege traffic credential is used less broadly, and public metadata
can be collected with lower-risk credentials where practical.

The dashboard can support a larger retained corpus without turning the UI into a
50-line chart or a 200-chip strip.

The cost is implementation complexity:

- endpoint planning must become explicit;
- ETag state must become part of retained collection state;
- the renderer must support summary data separately from detailed repo chunks;
- encrypted Pages and standalone artifact delivery must preserve the same
  privacy guarantees across chunked data;
- tests need large-corpus fixtures to prevent regressions.

## Initial Implementation Plan

1. Add an endpoint planning layer that produces both a cost estimate and the
   executable collection plan.
2. Add request accounting around every GitHub API call, including credential
   class, endpoint family, status code, retry count, pacing sleep, and rate-limit
   headers.
3. Persist HTTP validator state for eligible `GET` endpoints in the canonical
   data artifact.
4. Implement conditional requests with `If-None-Match` and `If-Modified-Since`.
5. Add a run-summary section for estimated and actual API requests, wall-clock
   minutes, and projected monthly Actions minutes.
6. Split metadata collection so public non-traffic metadata can use
   `GITHUB_TOKEN` where possible, with visible fallback behavior.
7. Add a large-corpus scenario, initially 200 repositories, to test renderer and
   payload behavior.
8. Change dashboard defaults so only 10 to 20 repositories are displayed in
   charts while all collected repositories remain searchable/selectable.
9. Cap compare mode at a small number of repositories.
10. Compress encrypted dashboard payloads before encryption.
11. Introduce encrypted manifest plus per-repository chunk output behind a
    compatibility flag.
12. Promote chunked encrypted data to the default after Pages, downloadable
    artifact, and local-viewing behavior are verified.

## Open Questions

- Should the initial collection ceiling be a hard 200, a default 200 with an
  advanced override, or a budget-derived value?
- Which metadata endpoints reliably return useful `ETag` or `Last-Modified`
  values, and do GitHub traffic endpoints return validators consistently enough
  to matter?
- Should the first ETag implementation include traffic endpoints immediately or
  start with metadata endpoints and report observed traffic validator behavior?
- Should metadata collection use REST conditional requests, GraphQL batching, or
  both?
- How should chunked encrypted data support local viewing of the downloadable
  HTML dashboard when browser `file://` restrictions block fetches?
- Should users be able to set a monthly private-runner minute budget that
  automatically lowers collection scope or schedule frequency?
- What exact dashboard display defaults should ship first: top 10, top 12, top
  20, or responsive based on viewport and metric?
