<!-- SPDX-License-Identifier: CC-BY-4.0 -->
<!-- Copyright 2026 George Geronikolas. Licensed under CC BY 4.0. -->

# Consent Manifest v0.1

**Working codename:** `consent.txt`
**Status:** Draft / March 2026
**Author:** George Geronikolas
**License (spec text):** CC BY 4.0
**License (code):** Apache-2.0
**Intended role:** Open authoring standard for AI access, usage, pricing, and verification policy

## 1. Abstract

This document defines a **Consent Manifest**: one machine-readable policy document that website operators can use as the source of truth for how automated systems may access and use site content.

The Consent Manifest is **not** intended to replace robots.txt, page-level search controls, AIPREF, TDMRep, crawler-specific controls, or payment enforcement. Instead, it acts as a **control-plane manifest** that can be compiled into the mechanisms that already exist today.

The core design goal is simple:

> Website owners should not need to hand-maintain six different policy surfaces for AI systems.

A Consent Manifest lets a publisher express, in one place:

- who they are;
- what classes of AI use they allow, deny, or conditionally permit;
- whether payment or attribution is required;
- how crawlers can prove identity;
- where audit and compliance receipts can be retrieved;
- which legacy and emerging protocol surfaces should be emitted.

## 2. Why this exists

The current ecosystem is fragmented:

- **robots.txt** controls crawl access, but not all downstream AI uses;
- **AIPREF** is emerging for usage preferences in HTTP and robots.txt;
- **meta robots / X-Robots-Tag / data-nosnippet** control indexing and previews;
- **Google-Extended** controls certain Google AI uses;
- **TDMRep** covers rights reservation and licensing in relevant jurisdictions;
- **Web Bot Auth** addresses crawler identity, not rights;
- **402/payment flows** address monetization, not policy declaration.

No single document gives a publisher one coherent authoring surface.

The Consent Manifest fills that gap.

## 3. Design principles

### 3.1 Immediate value without industry adoption

A Consent Manifest MUST be useful even if no AI crawler consumes it directly.

Therefore, implementations SHOULD compile it into existing mechanisms such as:

- robots.txt user-agent groups;
- AIPREF `Content-Usage` HTTP headers;
- AIPREF `Content-Usage` rules inside robots.txt;
- `X-Robots-Tag` and HTML meta robots directives;
- crawler-specific allow/block rules;
- TDMRep policy and link surfaces;
- payment and verification hooks at the edge.

### 3.2 Interoperate, do not compete

The Consent Manifest MUST NOT redefine meanings already standardized elsewhere when a compatible mapping exists.

In particular:

- `train-ai` and `search` SHOULD map cleanly to AIPREF where possible.
- Snippet and preview restrictions SHOULD map to search preview controls rather than being reinterpreted as crawl rules.
- TDM rights reservation SHOULD be linkable and mappable rather than duplicated in incompatible semantics.

### 3.3 Separate authoring semantics from wire semantics

The authoring model may be richer than current crawler-facing standards.

For example:

- `charge`
- `conditional`
- `identity: "signed"`
- `citation_required: true`
- `max_excerpt_chars`
- `max_tokens`

may exist in the Consent Manifest even if a target surface can express only `allow`, `deny`, or `unknown`.

Compilers MUST apply explicit fallback rules when lowering rich authoring states into limited wire formats.

### 3.4 Standard core, experimental edge

The Consent Manifest has two policy layers:

1. **Standard categories**: concepts that map to recognized public standards.
2. **Experimental categories**: higher-resolution concepts used by enforcement runtimes and early adopters.

This allows ecosystem progress without forcing the core spec to freeze immature semantics too early.

### 3.5 Enforcement is out of scope for the file

The file declares policy. Enforcement belongs to edge runtimes, CDNs, reverse proxies, middleware, and legal/commercial agreements.

## 4. Non-goals

The Consent Manifest is **not**:

- a guarantee that any crawler will comply;
- a replacement for access control or authentication;
- a legal determination of rights in any jurisdiction;
- a substitute for robots.txt;
- a substitute for AIPREF or TDMRep;
- a payment rail;
- a transparency log by itself.

## 5. Resource location and media type

### 5.1 Working deployment recommendation

For this draft, a publisher SHOULD expose the manifest at:

`/.well-known/consent-manifest.json`

This URI is a working placeholder for experimentation and SHOULD NOT be treated as a final standards-track registration yet.

### 5.2 Media type

The representation SHOULD be served as:

`application/json`

### 5.3 HTTP caching

Publishers SHOULD serve the manifest with `Cache-Control: public, max-age=86400` (24 hours). Consumers MUST re-fetch the manifest at least every 7 days. Note that changes to compiled surfaces (robots.txt) may take up to 24 hours to propagate to some crawlers (OpenAI documents this delay explicitly).

### 5.4 Branding note

The public-facing project name may still be **consent.txt** for communications and outreach. However, the canonical machine format for v0.1 is JSON.

## 6. Policy model

### 6.1 State model

Each policy statement resolves to one of five authoring states:

- `allow`
- `deny`
- `unknown`
- `charge`
- `conditional`

Definitions:

- **allow**: the operator permits the described use under baseline terms.
- **deny**: the operator does not permit the described use.
- **unknown**: no preference is expressed in this manifest.
- **charge**: the use may be permitted only after payment or a paid agreement.
- **conditional**: the use may be permitted if additional obligations are met.

### 6.2 Standard usage categories

The v0.1 core recognizes these standard categories:

| Category | Description | Wire mappings |
|----------|-------------|---------------|
| `train-ai` | Model training, fine-tuning, RLHF | AIPREF `Content-Usage`, Google-Extended, robots.txt |
| `search` | Traditional search indexing | AIPREF `Content-Usage`, meta robots, X-Robots-Tag |

These two categories are aligned with the IETF AIPREF working group vocabulary (draft-ietf-aipref-vocab). Only standard categories are emitted into AIPREF `Content-Usage` headers and robots.txt rules.

### 6.3 Extended usage categories

Implementations MAY use higher-resolution categories in the experimental block, including but not limited to:

- `train-genai` — generative AI model training specifically (discussed in AIPREF, not yet standardized);
- `ai-input` — real-time grounding, RAG, or prompt-time input (used by Cloudflare Content Signals as `ai-input`, not yet an AIPREF category);
- `agentic-access` — user-triggered automated browsing or task execution;
- `transform` — summarization, answer synthesis, or derivative text generation from the asset;
- `generate-media` — use of the asset in image/audio/video generation workflows;
- `embedding` — vectorization or semantic indexing for non-search AI use.

Extended categories are authoring conveniences. They MUST NOT be emitted into AIPREF `Content-Usage` headers or other standards-track surfaces. They ARE consumed by the robots.txt compiler (for bot-blocking decisions), edge enforcement runtimes, and commercial agreements.

### 6.4 Conditions and obligations

A policy in state `conditional` or `charge` MAY include obligations such as:

| Condition | Type | Description |
|-----------|------|-------------|
| `identity` | `none` / `verified` / `signed` | Required level of crawler identity verification |
| `citation_required` | boolean | Whether citation of the source is required |
| `link_required` | boolean | Whether a link back to the source is required |
| `attribution_required` | boolean | Whether attribution to the publisher is required |
| `max_excerpt_chars` | integer | Maximum characters that may be excerpted per request |
| `max_tokens` | integer | Maximum tokens that may be extracted per request |
| `verbatim_allowed` | boolean | Whether verbatim reproduction is permitted |
| `freshness_delay_seconds` | integer | Minimum delay before content may be used |
| `rate_limit_per_day` | integer | Maximum requests per day |
| `region_scope` | array of strings | Region codes where the policy applies |
| `payment_plan` | string | Reference to pricing information |

### 6.5 Fallback semantics

Because many target surfaces cannot express `charge` or `conditional`, the manifest MUST define lowering behavior.

Default fallback:

- unexpressible state -> `deny`
- unknown operator identity -> `deny`
- unsupported experimental category -> omit from standard emissions

An implementation MAY override these defaults explicitly.

### 6.6 Path specificity

When multiple rules match a request path, the **longest matching path pattern wins**. This follows robots.txt precedent (RFC 9309). Path-specific rules override the default policy for categories they explicitly declare; categories not mentioned in the rule inherit the default policy.

## 7. Document structure

A Consent Manifest contains:

- `version` (REQUIRED)
- `publisher` (REQUIRED)
- `defaults` (REQUIRED)
- `rules` (OPTIONAL)
- `endpoints` (OPTIONAL)
- `interop` (OPTIONAL)
- `signature` (OPTIONAL)
- `extensions` (OPTIONAL)

### 7.1 Publisher

`publisher` identifies the declaring party.

Fields:

- `name` (REQUIRED): publisher name
- `contact` (REQUIRED): contact URI (mailto: or URL)
- `url` (RECOMMENDED): canonical site URL
- `jurisdictions` (OPTIONAL): array of jurisdiction codes (ISO 3166-1 alpha-2 or "EU")
- `terms_url` (OPTIONAL): URL to AI usage terms

### 7.2 Defaults

`defaults` define the site-wide baseline policy. Contains:

- `fallbacks`: lowering behavior for unexpressible states and unknown identity
- `standard`: standard category policies
- `experimental`: experimental category policies

### 7.3 Rules

`rules` provide path-level or content-scope overrides.

A rule MAY match on:

- `path`: glob pattern
- `hostname`: for multi-tenant hosts
- `content_types`: array of MIME types
- `languages`: array of language codes
- `labels`: array of content labels

### 7.4 Endpoints

`endpoints` provide machine-discoverable URLs for adjacent systems:

- `payment`: payment flow endpoint
- `receipts`: audit receipt endpoint
- `verification`: bot identity verification / public key directory
- `tdm_policy`: TDMRep policy document

### 7.5 Interop

`interop.emit` tells compilers which surfaces to emit.

Valid emit targets: `robots-txt`, `aipref-header`, `aipref-robots`, `x-robots-tag`, `google-extended`, `tdmrep`.

## 8. Compiler profile

A conforming compiler SHOULD be able to emit some or all of the following:

### 8.1 robots.txt user-agent groups

Emit vendor-specific access groups. Known AI user-agents include: GPTBot, OAI-SearchBot, ChatGPT-User, ClaudeBot, Claude-SearchBot, Claude-User, Google-Extended, CCBot, FacebookBot, Bytespider, Diffbot, Amazonbot, cohere-ai, AI2Bot, Applebot-Extended, PerplexityBot.

### 8.2 AIPREF response headers

For standard categories, emit `Content-Usage` on HTTP responses.

Example: `Content-Usage: train-ai=n, search=y, ai-input=n`

### 8.3 AIPREF rules in robots.txt

For path-scoped standard categories, emit `Content-Usage` rules within robots.txt groups.

### 8.4 Search preview controls

Emit preview/index controls where the policy requires snippet or preview restrictions. Outputs: HTML robots meta tags, `X-Robots-Tag`, `data-nosnippet`.

### 8.5 TDMRep integration

When relevant, expose or reference machine-readable TDM reservation / licensing resources via `Link` header.

### 8.6 Lowering rules

For standard categories:

| Authoring state | Wire value |
|----------------|------------|
| `allow` | `y` |
| `deny` | `n` |
| `unknown` | omit |
| `charge` | apply fallback (`deny` by default) |
| `conditional` | apply fallback (`deny` by default) |

Experimental categories SHOULD NOT be emitted into standards-track surfaces. They SHOULD be handled by edge enforcement runtimes, crawler-specific rules, payment gateways, and compliance logic.

## 9. Security and trust considerations

### 9.1 Unsigned manifests

An unsigned manifest can be altered by any attacker who can modify origin content or traffic.

### 9.2 Signed manifests

Implementations MAY support detached signatures or DSSE/JWS-style signing for manifest integrity.

### 9.3 Bot identity

Publisher policy can only be enforced reliably when bot identity is credible. Implementations SHOULD support cryptographic bot identity where available (e.g., HTTP Message Signatures, Web Bot Auth).

### 9.4 Abuse resistance

Publishing a policy does not prevent unauthorized scraping. Operators SHOULD combine declaration with rate limiting, bot management, WAF controls, and logging.

## 10. Conformance classes

### 10.1 Publisher

A publisher conforms if it publishes a syntactically valid manifest at the specified well-known path.

### 10.2 Compiler

A compiler conforms if it: validates the manifest; applies fallback rules deterministically; emits requested protocol surfaces consistently.

### 10.3 Enforcement runtime

An enforcement runtime conforms if it: consumes the manifest or compiled policy; applies access/use decisions consistently; logs enforcement actions with timestamps and identifiers.

## 11. Open questions

The following are intentionally unresolved in v0.1:

1. Final well-known URI registration.
2. Whether the long-term canonical form should remain JSON or add a secondary text profile.
3. The exact boundary between use categories and output obligations.
4. The best namespace strategy for experimental categories.
5. Whether a receipt format should be standardized separately.
6. Whether payment plans should be described directly or referenced externally.
7. How to express policy inheritance across subdomains and multi-tenant hosts.

## Appendix A: Revision history

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | March 2026 | Initial draft. Two standard categories (`train-ai`, `search`) aligned with AIPREF vocab draft. Six extended categories (`train-genai`, `ai-input`, `agentic-access`, `transform`, `generate-media`, `embedding`). Compiler profile for six emit targets. |
