# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Fixed

- The compiler resolves the manifest once into a `Plan` that every emitter reads, so robots.txt, AIPREF, TDMRep and Content-Signal can no longer disagree.
- A rule inherits each category it does not declare, an explicit `unknown` included, from the longest enclosing rule and then from the defaults (spec 6.6).
- A `train-genai` deny now yields `train-ai=n`.
- robots.txt emits every rule path as Allow or Disallow, so RFC 9309 longest match keeps nested denies.
- Path-level `ai-input` denies are emitted even when the default allows.
- Globs are lowered to RFC 9309 patterns: `*` and `$` are kept, `/x/*` becomes `/x/`, no `/` is appended and a leading `/` is required.
- The compiler validates the manifest first and exits 2 on errors unless `--force` is given.
- An unknown state raises an error instead of lowering to a fallback.
- TDMRep is emitted as the W3C protocol defines it, as `/.well-known/tdmrep.json` with per-path rules plus `tdm-reservation` and `tdm-policy` headers and the `<meta>` equivalent.
- The compiler no longer emits the non-standard `Link: rel="tdm-policy"` header. The Worker, playground, WordPress plugin and scanner still use it and are untouched here.
- Site-wide surfaces (`aipref-header`, `content-signal`, the `noindex` in `x-robots-tag`, the TDMRep headers) no longer publish the default value on paths that override it and list the per-path values as comments instead.
- Per-path lines are emitted only for categories a rule declares or inherits from an enclosing rule, so an unrelated or empty rule cannot reopen an overlapping deny.
- Rules that lower to the same path are merged, and two rules on one path no longer crash the compiler.
- A rule on `/` overrides the defaults.
- A `/**/` in the middle of a pattern expands to two patterns so the segment boundary survives, with at most four `/**/` per path.
- Equal-length patterns put Allow first, as RFC 9309 does, and the compiler warns when such a tie carries different decisions.
- Rules with matchers no target compiles contribute only their `deny` decisions.
- The validator CLI accepts several files and has `--help`.
- The validator requires `match.path` and rejects paths with whitespace, `#`, `?`, brackets or a non-trailing `$`.
- The validator rejects control characters in publisher and endpoint strings, and a category declared in both tiers with different states.
- The validator warns on unknown experimental categories and on matchers no target can compile.
- Malformed manifests no longer crash the validator.

### Added

- A `content-signal` emit target writes the Cloudflare Content Signals line for robots.txt and the matching response header.
- `compiler/agents.json`, a curated user-agent table with operator sources, adds the training crawlers Meta-ExternalAgent, MistralAI-Training, Ai2Bot-Dolma, cohere-training-data-crawler, TikTokSpider, DeepSeekBot, omgili, Webzio-Extended and SBIntuitionsBot, the search crawlers Amzn-SearchBot, MistralAI-Index, SBIntuitions-SearchBot and Meta-WebIndexer, and the user-triggered fetchers Perplexity-User, MistralAI-User, DuckAssistBot, Meta-ExternalFetcher, Amzn-User and Google-Agent.
- `tests/` holds golden-file tests for every example and edge case, crawl-decision tests through a small RFC 9309 evaluator, and validator and CLI tests, which a GitHub Actions workflow runs.

### Changed

- Diffbot moves from training to search, as its operator documents.
- `examples/news-publisher.json` drops its `content_types` matcher and points `tdm_policy` at a policy document rather than at `tdmrep.json`.
- The README's full example moves `ai-input` to the experimental block so it validates.
- The schema `$id` points at the real repository slug, `match.path` is required and constrained, and endpoints must be http(s) URLs.
- The `tdmrep` target writes `tdmrep.json` and `tdmrep-headers.txt` instead of `tdmrep-header.txt`, so scripts that read `--out` need updating.
- An unknown `--emit` target is an error (exit 3) rather than a skipped warning.

## [0.1.0] - 2026-03-17

### Added

- Consent Manifest v0.1 specification (CC BY 4.0)
- JSON Schema with two standard categories: `train-ai`, `search` (AIPREF-aligned)
- Six extended categories: `train-genai`, `ai-input`, `agentic-access`, `transform`, `generate-media`, `embedding`
- Five-state policy model: `allow`, `deny`, `unknown`, `charge`, `conditional`
- Validator CLI (Python, zero external dependencies)
- Compiler CLI with seven emit targets:
  - `robots-txt` — user-agent groups for 12+ AI crawlers
  - `aipref-header` — AIPREF `Content-Usage` HTTP header
  - `aipref-robots` — AIPREF `Content-Usage` directives in robots.txt
  - `x-robots-tag` — `max-snippet`, `noai`, `noimageai` directives
  - `google-extended` — Google-Extended specific robots.txt block
  - `tdmrep` — TDMRep `Link` header
  - `summary` — human-readable policy summary
- Cloudflare Worker enforcement runtime with:
  - Four-tier bot trust ladder (signed, published IP, reverse DNS, user-agent)
  - HTTP Message Signature detection for tier promotion
  - Policy resolution with longest-path-wins specificity
  - Dry-run mode (`DRY_RUN=true`)
  - Health check endpoint (`/_consent/health`)
  - Test endpoint (`/_consent/test?path=...&ua=...`)
- Domain scanner scoring four axes: access controls, usage declarations, preview controls, identity confidence
- Six example manifests: minimal, news publisher, SaaS platform, selective SaaS, open/permissive, lockdown
- AI Policy Readiness Index benchmark report (20 domains)
- WordPress plugin (shelved to month-two priority)
