# Changelog

## [Unreleased]

### Fixed (PR #1 review round)

- **`open-referee serve` production crash**: `create_app()` never set
  `app.state.config_path`, so every page returned 500 outside tests. It now
  defaults to `DEFAULT_CONFIG_PATH`.
- **Survey stage crash**: the surveyor's Crossref missing-reference lookups ran
  after the `async with CrossrefClient` block had exited (`RuntimeError:
  client has been closed`). The surveyor step now runs inside the client
  contexts; OpenAlex/Crossref/SearchRouter are opened once per stage via
  context managers.
- **OpenAlex client**: `_work_to_item` read nonexistent `openalexpy.Work`
  attributes (`authors`, `year`, `citations`) — authors/year/citation counts
  were silently dropped. Now maps `authorships`, `publication_year`,
  `cited_by_count`. The REST fallback client is always created (previously it
  existed only when openalexpy was missing, so an openalexpy failure crashed
  with `AttributeError`). DOIs are no longer truncated to their suffix.
- **SSE replay**: `RunState.events` was excluded from the persisted state, so
  replaying finished runs yielded nothing and always emitted a synthetic
  "done" — even for failed runs. Events are now persisted; replay ends with
  the run's real terminal status; late subscribers to finished runs get the
  buffered events instead of hanging; finished background-task references are
  bounded (max 50).
- **Budget cap behavior**: `BudgetExceeded` now drains into a partial report
  (with validator notes listing completed stages) instead of discarding
  everything. Output-token cost estimation is proportional to input size
  instead of pre-charging `max_tokens // 2` per call, which tripped the cap
  prematurely on large-context models.
- **Settings save**: hand-edited custom providers in the YAML are preserved
  (the form only manages the five well-known provider names). Settings save
  also reads the app's config path instead of the global default.
- **Upload security**: upload filenames are sanitized (basename + character
  allowlist), neutralizing path traversal via crafted multipart filenames.
- **Sections**: `Section.path` was built from a string title (`list(title)` →
  char list). Now a proper hierarchical path list.
- **Service worker**: registered from `/static/sw.js`, its default scope
  (`/static/`) controlled no app pages, so offline caching never worked.
  Now served at `/sw.js` with `Service-Worker-Allowed: /`.
- **Figure context**: figure verification used the last 60 blocks regardless
  of figure position; now centered on the caption block when available.
- Removed dead config (`ReviewConfig.language`, `SECTIONS_PER_VERIFIER_CHUNK`),
  a duplicate `ModelSpec` import, and an odd `cfg and name` expression.

### Tests

- New `tests/test_regression_fixes.py` covering every fix above (17 tests,
  total suite: 45 passing), including the production `create_app()` path with
  no test-injected state.
