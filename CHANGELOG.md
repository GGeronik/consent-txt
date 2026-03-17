# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
