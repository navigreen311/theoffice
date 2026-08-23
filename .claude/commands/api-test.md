---
name: api-test
description: Generate API contract and integration tests from an OpenAPI/GraphQL spec or from live endpoints.
---

# api-test

Generate runnable contract + integration tests for an API.

## Arguments

| Argument | Meaning | Default |
|---|---|---|
| `spec_path_or_url` | OpenAPI/GraphQL spec path or URL, or a base URL to probe | **required** |
| `auth_mode` | `none` \| `bearer` \| `api-key` \| `oauth2` \| `session` | infer from spec; else `none` + `ASSUMPTION` |
| `env` | `local` \| `staging` \| `prod` | `local` |
| `test_style` | `contract` \| `integration` \| `both` | `both` |
| `load_smoke` | `true` \| `false` | `false` |

> **`env=prod` is read-only.** Never run mutating tests against production. If prod is targeted, restrict to safe idempotent reads and say so explicitly.

## Process

### 1. Parse the spec
Enumerate every endpoint: method, path, params, request schema, response schemas, status codes, auth requirement.

If no spec exists, probe the live endpoints and **reconstruct the contract**, clearly labelled `ASSUMPTION` — an observed contract is not a specification.

Report the inventory before generating anything.

### 2. Generate tests

**Success paths** — valid request → correct status, schema-conformant body, correct headers, correct content type.

**Error paths — these matter more than the happy path and are the ones usually missing:**
- 400 — malformed body, wrong types, missing required fields, out-of-range values
- 401 / 403 — no credentials, bad credentials, **valid credentials for the wrong resource** (the authorization test people skip)
- 404 — non-existent resource
- 409 — conflict / duplicate
- 422 — semantically invalid
- 429 — rate limit, if applicable
- Payload boundaries: empty, maximum-size, oversized

**Contract assertions** — response body validated against the declared schema, not just status codes. Unexpected extra fields and missing optional fields both get asserted deliberately.

**Idempotency & state** — repeated calls behave as specified; every test cleans up what it creates.

### 3. Reusable client & helpers
One typed client wrapper handling base URL, auth, headers, retries, and error normalization. Tests must never construct raw requests inline.

### 4. Environment CLI
Run against any environment via config or env vars — never hard-code a URL or credential. Secrets come from the environment; document them in `.env.example` with placeholders (`YOUR_API_KEY_HERE`). **No real credential in any file or output.**

### 5. Load smoke (if `load_smoke=true`)
A brief, bounded concurrency check on the hottest endpoints. Report p50/p95/p99 latency and error rate. This is a smoke test, not a load test — say so.

### 6. Run & summarize
Run against `env` and report real results.

## Outputs

- `tests/api/` — runnable suites, organized by resource
- Reusable client/helpers
- `.env.example` updated
- Example commands per environment
- Report path

```
ENDPOINTS | <N discovered> / <N covered>
TESTS     | <N> (<contract> / <integration>)
RESULT    | <command> → <N passed / N failed>
UNCOVERED | <endpoints with no test, and why>
```

Plus a **Fact Check List**: auth mechanism, base URLs, rate limits, spec version, and whether the live API actually matches its spec.

## Error Handling

- **A test failure may be a real API bug, not a bad test.** Investigate before "fixing" the test — report which it is.
- Spec/implementation drift is a finding: report it explicitly rather than writing the test to match the implementation.
- Unreachable endpoint → report it; do not silently skip it.
- Never weaken an assertion to make a suite green.

## Example

```
/api-test spec_path_or_url=./openapi.yaml auth_mode=bearer env=local \
  test_style=both load_smoke=false
```
