# consent.txt

**The control plane for AI content access on the web.**

One publisher-authored manifest that compiles into today's crawl, preview, rights, payment, and verification mechanisms. Write your AI policy once. Deploy it everywhere.

---

## The Problem

Publishers currently need to hand-maintain six different policy surfaces to control AI access to their content:

- **robots.txt** for crawl access (but it can't distinguish training from search)
- **AIPREF headers** for usage preferences (emerging IETF standard, narrow scope)
- **X-Robots-Tag / meta robots** for preview and indexing controls
- **Google-Extended** for Google's AI products specifically
- **TDMRep** for EU text and data mining rights reservation
- **Per-crawler user-agent rules** for GPTBot, ClaudeBot, CCBot, etc.

No single document gives a publisher one coherent authoring surface. consent.txt fills that gap.

## How It Works

consent.txt is a **Consent Manifest** — a JSON policy document that acts as a control-plane source of truth. You write your AI policy once. The compiler generates every protocol surface you need.

### Declaration: one manifest, many outputs

```
                    ┌──────────────────────────┐
                    │  consent-manifest.json    │  ← You author this once
                    │  (standard + extended)    │
                    └────────────┬─────────────┘
                                 │
                         ┌───────▼───────────┐
                         │     Compiler      │  ← python compile.py manifest.json --out build/
                         └──┬──┬──┬──┬──┬──┬─┘
                            │  │  │  │  │  │
              ┌─────────────┘  │  │  │  │  └──────────────┐
              ▼                ▼  ▼  ▼  ▼                 ▼
         robots.txt      AIPREF  X-Robots  Google-  TDMRep     Content-
         (agents.json)   header    -Tag   Extended json+hdrs    Signal
```

### Enforcement: the Cloudflare Worker

```
         Incoming request
              │
              ▼
    ┌─────────────────────┐
    │   Identify bot       │  ← Trust ladder:
    │   (UA → tier)        │     1. HTTP Message Signatures (cryptographic)
    └─────────┬───────────┘     2. Published IP list
              │                  3. Reverse DNS
              ▼                  4. User-agent only
    ┌─────────────────────┐
    │   Resolve policy     │  ← Longest matching path wins
    │   (manifest + path)  │
    └─────────┬───────────┘
              │
         ┌────┼────┐
         ▼    ▼    ▼
       allow  deny  charge
         │    │      │
         ▼    ▼      ▼
       pass  403    402
       +hdrs        +payment_url
```

**Try it without installing anything:** paste a manifest into the [live playground](https://consenttxt.org/playground) and see the compiled outputs in real time.

## Quick Start

### 1. Create your manifest

The simplest possible consent manifest — block AI training, allow search:

```json
{
  "version": "0.1",
  "publisher": {
    "name": "My Blog",
    "contact": "mailto:me@example.com"
  },
  "defaults": {
    "standard": {
      "train-ai": { "state": "deny" },
      "search": { "state": "allow" }
    },
    "experimental": {
      "train-genai": { "state": "deny" },
      "ai-input": { "state": "deny" }
    }
  }
}
```

### 2. Validate

```bash
python tools/validate.py manifest.json
```

### 3. Compile

```bash
# Print all outputs to stdout
python compiler/compile.py manifest.json

# Write deployable files to a directory
python compiler/compile.py manifest.json --out build/

# Emit only robots.txt
python compiler/compile.py manifest.json --emit robots-txt --out build/
```

### 4. Deploy

Copy the compiled `robots.txt` to your server root and merge the `aipref-robots.txt` and `content-signal.txt` lines into its `User-Agent: *` group. The generated robots.txt already contains Google-Extended, so `google-extended.txt` is only for sites that keep their own robots.txt. Serve `tdmrep.json` at `/.well-known/tdmrep.json`. Add the compiled HTTP headers to your server config or CDN. Headers apply to the whole site, so the compiler leaves out any usage label that a path rule overrides and lists the per-path values as comments, while preview directives such as `max-snippet` come from the default policy only. Place the manifest at `/.well-known/consent-manifest.json`.

The compiler validates the manifest first and exits with code 2 on an invalid one unless you pass `--force`. Path globs are lowered to RFC 9309 patterns (`*` and `$` pass through and `/docs/*` becomes the prefix `/docs/`), and every rule path is emitted so longest-match resolves nested rules.

## The Five-State Policy Model

Unlike robots.txt (allow/disallow) or AIPREF (y/n), the Consent Manifest supports five authoring states that capture what publishers actually want to express:

| State | Meaning | Lowers to (robots.txt) |
|-------|---------|----------------------|
| `allow` | Permitted under baseline terms | Allow |
| `deny` | Not permitted | Disallow |
| `unknown` | No preference expressed | Omitted |
| `charge` | Permitted only after payment | Deny (fallback) |
| `conditional` | Permitted if obligations are met | Deny (fallback) |

When the compiler emits into surfaces that only support allow/deny (like robots.txt), it applies **explicit fallback rules** defined in the manifest. This means the publisher controls what happens when their rich policy meets a limited wire format.

## Standard vs. Experimental Categories

### Standard (AIPREF-aligned)

These map directly to the IETF AIPREF vocabulary draft:

| Category | What it controls | Maps to |
|----------|-----------------|---------|
| `train-ai` | Model training, fine-tuning, RLHF | AIPREF `Content-Usage`, Google-Extended, robots.txt |
| `search` | Traditional search indexing | AIPREF `Content-Usage`, meta robots, X-Robots-Tag |

Only standard labels are emitted into AIPREF `Content-Usage` headers. A `train-genai` deny still sets the emitted `train-ai` to `n`, because the current AIPREF draft defines `train-ai` as training of generative models.

### Extended (project-defined)

Higher-resolution categories for enforcement runtimes. These live in the `experimental` block of the manifest and their labels are never emitted into AIPREF headers. The compiler reads `train-genai` and `ai-input` for robots.txt groups, TDMRep and Content-Signal, while the other four are declarative only in v0.1:

| Category | What it controls | Provenance |
|----------|-----------------|------------|
| `train-genai` | Generative AI training specifically | Discussed in AIPREF, not yet standardized |
| `ai-input` | Real-time RAG, grounded generation | Cloudflare Content Signals (`ai-input`) |
| `agentic-access` | Autonomous AI agents browsing on behalf of users | Project-defined |
| `transform` | Summarization, answer synthesis, derivative text | Project-defined |
| `generate-media` | Image/audio/video generation from the asset | Project-defined |
| `embedding` | Vectorization for non-search AI use | Project-defined |

## Conditions and Obligations

Policies in `conditional` or `charge` state can specify obligations:

```json
{
  "ai-input": {
    "state": "conditional",
    "conditions": {
      "identity": "signed",
      "citation_required": true,
      "link_required": true,
      "max_excerpt_chars": 160,
      "max_tokens": 500,
      "rate_limit_per_day": 1000
    }
  }
}
```

Available conditions: `identity` (none/verified/signed), `citation_required`, `link_required`, `attribution_required`, `max_excerpt_chars`, `max_tokens`, `verbatim_allowed`, `freshness_delay_seconds`, `rate_limit_per_day`, `region_scope`, `payment_plan`.

## Bot Identity: The Trust Ladder

"Just block bots in robots.txt" is a brittle defense. User-agent strings are trivially spoofed. IP addresses rotate. The consent.txt Worker addresses this with a four-tier trust ladder that reflects how bot verification actually works in production today:

| Tier | Verification method | Confidence | Example |
|------|-------------------|------------|---------|
| **Signed** | HTTP Message Signatures (`Signature` + `Signature-Input` headers verified against a published key directory) | Cryptographic | ChatGPT-User (when signed) |
| **Published IP** | Request IP checked against a published JSON IP list | Strong | GPTBot (`openai.com/gptbot.json`), OAI-SearchBot |
| **Reverse DNS** | Forward-confirmed reverse DNS resolving to a known domain | Moderate | Googlebot (`.googlebot.com`), CCBot (`.commoncrawl.org`) |
| **User-agent only** | User-agent string match with no further verification | Weak | ClaudeBot, Bytespider, FacebookBot |

The Worker checks for HTTP Message Signature headers on every request and **promotes** a bot to the signed tier at runtime when signatures are present. It does not pre-assign any bot to the signed tier based on user-agent alone. This means:

- A manifest requiring `"identity": "signed"` will reject a ClaudeBot request (user-agent only, no signature support) but accept a ChatGPT-User request that carries valid `Signature` and `Signature-Input` headers.
- A manifest requiring `"identity": "verified"` will accept bots from the signed, published IP, or reverse DNS tiers — but reject pure user-agent matches.
- A manifest requiring `"identity": "none"` accepts everything (equivalent to no identity check).

This is not a theoretical design. OpenAI's ChatGPT agent already sends HTTP Message Signatures and publishes a well-known key directory. Googlebot and Bingbot have published reverse DNS verification procedures for years. The trust ladder maps to the infrastructure that exists right now.

The `/_consent/test` endpoint lets you simulate enforcement for any user-agent and see which tier it resolves to:

```bash
curl "https://yoursite.com/_consent/test?path=/premium/&ua=ChatGPT-User"
```

Returns the bot identification, resolved policy, compiled headers, and enforcement decision — without affecting real traffic.

## Badge: Show Your Policy

After scanning your domain, generate an embeddable SVG badge for your site footer:

```bash
python badge/badge.py --domain yoursite.com --grade A --score 85
```

The badge links back to the public scanner, letting visitors verify your AI policy. Drop the HTML snippet into your footer:

```html
<!-- AI Policy Badge — powered by consent.txt -->
<a href="https://consenttxt.org/scan?domain=yoursite.com" target="_blank" rel="noopener">
  <img src="/badge.svg" alt="AI Consent: Grade A" height="20">
</a>
```

Available styles: `flat` (compact) and `detailed` (shows score). Every adopter who displays the badge drives traffic to the scanner. Every visitor who clicks the badge discovers the project.

## Safe Deployment and Kill Switch

The Cloudflare Worker sits in front of your origin. If something goes wrong, you need to disable it instantly without touching DNS or waiting for a deploy.

### Deploy safely: dry-run first

Always start with dry-run mode. Set `DRY_RUN = "true"` in `wrangler.toml`:

```toml
[vars]
DRY_RUN = "true"
```

In dry-run, the Worker logs every enforcement decision and adds `X-Consent-Decision: dry-run: would-block: ...` headers — but passes all requests through to origin. Check your headers in production for 24 hours before enabling enforcement.

### Health check before going live

```bash
curl https://yoursite.com/_consent/health
```

Returns the loaded manifest, compiled headers, emit targets, and dry-run status. If the manifest is missing or malformed, the health check will show `"status": "no_manifest"` and the Worker passes all traffic through unmodified.

### The kill switch: three ways to disable instantly

**1. Set dry-run (seconds, no redeploy):**
```bash
wrangler secret put DRY_RUN --text "true"
```
The Worker continues running but stops blocking. All enforcement decisions are logged, not acted on.

**2. Remove the manifest (seconds, no redeploy):**
If using KV storage: delete the `manifest` key. If using an env var: set `CONSENT_MANIFEST` to `{}`. The Worker detects a missing/empty manifest and passes all traffic through.

**3. Disable the Worker entirely (Cloudflare dashboard):**
Go to Workers & Pages → your Worker → Settings → Disable. All traffic goes directly to origin. The Worker can be re-enabled in one click.

### What happens if the manifest is broken

If the Worker can't load or parse the manifest, it falls back to `fetch(request)` — a clean pass-through to your origin with no modification. A broken manifest never blocks traffic. This is by design: the Worker fails open, not closed.

### Rollback

Every manifest change should be version-controlled. If a new manifest causes unexpected blocks, revert to the previous version via KV, env var, or origin file. The Worker re-reads the manifest on every request (with Cloudflare's cache layer), so changes take effect within seconds.

## Compiler Outputs

The compiler can emit:

| Target | Output | Description |
|--------|--------|-------------|
| `robots-txt` | `robots.txt` | User-agent groups from the curated table in `compiler/agents.json` |
| `aipref-header` | HTTP header | `Content-Usage: train-ai=n, search=y` (site-wide, without labels a path rule overrides) |
| `aipref-robots` | robots.txt rules | AIPREF `Content-Usage` directives in robots.txt |
| `x-robots-tag` | HTTP header | `noindex`, `max-snippet`, `nosnippet`, `noai` directives (site-wide, with per-path differences as comments) |
| `google-extended` | robots.txt block | Google-Extended specific rules |
| `tdmrep` | `tdmrep.json` + headers | `/.well-known/tdmrep.json` plus `tdm-reservation` / `tdm-policy` response headers and the `<meta>` equivalent (W3C TDMRep) |
| `content-signal` | robots.txt line + header | `Content-Signal: search=yes, ai-input=no, ai-train=no` (Cloudflare Content Signals, site-wide) |
| `summary` | Text file | Human-readable policy summary |

Control which targets are emitted via the manifest's `interop.emit` array or the `--emit` CLI flag.

## Full Example: News Publisher

```json
{
  "version": "0.1",
  "publisher": {
    "name": "Example Media Group",
    "url": "https://example.com",
    "contact": "mailto:ai-policy@example.com",
    "jurisdictions": ["GB", "EU"],
    "terms_url": "https://example.com/ai-policy"
  },
  "defaults": {
    "fallbacks": {
      "unexpressible_state": "deny",
      "unknown_identity": "deny"
    },
    "standard": {
      "train-ai": { "state": "deny" },
      "search": { "state": "allow" }
    },
    "experimental": {
      "ai-input": {
        "state": "conditional",
        "conditions": {
          "identity": "signed",
          "citation_required": true,
          "link_required": true,
          "max_excerpt_chars": 160,
          "max_tokens": 500
        }
      }
    }
  },
  "rules": [
    {
      "match": { "path": "/premium/*" },
      "experimental": {
        "ai-input": {
          "state": "charge",
          "conditions": {
            "identity": "signed",
            "payment_plan": "premium-rag"
          }
        }
      }
    }
  ],
  "endpoints": {
    "payment": "https://example.com/.well-known/ai-payment",
    "verification": "https://example.com/.well-known/http-message-signatures-directory",
    "tdm_policy": "https://example.com/tdm/policy.json"
  },
  "interop": {
    "emit": ["robots-txt", "aipref-header", "x-robots-tag", "google-extended", "tdmrep", "content-signal"]
  }
}
```

Compile it:
```bash
python compiler/compile.py examples/news-publisher.json --out build/
```

This writes the deployable files to `build/`.

## Design Principles

1. **Immediate value without industry adoption.** The compiler emits into surfaces crawlers already consume. You don't need to wait for anyone.
2. **Interoperate, do not compete.** The manifest sits above robots.txt, AIPREF, TDMRep, and search preview controls — it doesn't replace them.
3. **Separate authoring semantics from wire semantics.** The manifest can express `charge` and `conditional` even when the target surface only supports allow/deny. Fallback rules make lowering deterministic.
4. **Standard core, experimental edge.** Standard categories map to public specs. Experimental categories are for enforcement runtimes. This lets the ecosystem evolve without freezing immature semantics.
5. **Enforcement is out of scope for the file.** The file declares policy. Enforcement belongs to edge runtimes, CDNs, middleware, and legal agreements.

## What consent.txt is NOT

- A guarantee that any crawler will comply
- A replacement for robots.txt, AIPREF, or TDMRep
- A payment rail or transparency log
- A legal determination of rights in any jurisdiction

## Repo Structure

```
consent.txt/
├── SPECIFICATION.md              # v0.1 spec (CC BY 4.0)
├── LICENSE                       # Apache-2.0 (code)
├── CHANGELOG.md                  # Version history
├── CONTRIBUTING.md               # How to contribute
├── schema/
│   └── consent-manifest.schema.json
├── examples/                     # 6 example manifests
├── tools/
│   └── validate.py               # Validator CLI (zero deps)
├── tests/                        # Golden-file tests: python -m unittest discover -s tests
├── compiler/
│   ├── compile.py                # Compiler CLI (zero deps)
│   └── agents.json               # Curated AI user-agent table (train / search / ai-input)
├── worker/
│   ├── index.js                  # Cloudflare Worker runtime
│   └── wrangler.toml             # Deploy config
├── scanner/
│   └── scan.py                   # Domain scanner
├── playground/
│   └── index.jsx                 # Zero-install web compiler
├── badge/
│   └── badge.py                  # SVG badge generator
├── docs/
│   ├── benchmark-report.md       # AI Policy Readiness Index
│   └── launch-post.md            # Show HN launch post
└── wordpress-plugin/             # Month-two distribution channel
```

## Roadmap

### v0.1 — Declaration layer (current)

- [x] Consent Manifest specification
- [x] JSON Schema (2 standard + 6 extended categories)
- [x] Validator CLI
- [x] Compiler CLI (8 emit targets, golden tests)
- [x] Cloudflare Worker runtime (trust ladder, dry-run, health/test endpoints)
- [x] Domain scanner (4-axis AI Policy Readiness scorecard)
- [x] Badge generator (embeddable SVG for site footers)
- [x] Live playground (zero-install web compiler)
- [x] 6 example manifests
- [x] Benchmark report (20 domains)

### v0.1.x — Adoption tools (weeks 2-4)

- [ ] Public hosted scanner at consenttxt.org
- [ ] AI Policy Readiness Index: benchmark 200+ sites
- [ ] npm package (`@consenttxt/compiler`)
- [ ] Worker: real IP verification against published bot IP lists
- [ ] Worker: reverse DNS verification for Googlebot/CCBot/Bingbot

### v0.2 — Monetization layer

consent.txt will not just declare policy — it will route payment.

- [ ] Native HTTP 402 (Payment Required) integration in the Worker
- [ ] `charge` states trigger real payment flows: Stripe checkout, TollBit metering, or Cloudflare Pay Per Crawl
- [ ] The manifest becomes a pricing table: per-request, per-token, subscription, or revenue-share per use-type
- [ ] Cryptographic receipts: tamper-evident proof that content was accessed under agreed terms
- [ ] Settlement dashboard: publishers see what they earned, from which bots, for which content

The goal: every `charge` state in a manifest should be enforceable end-to-end. A publisher sets `"ai-input": {"state": "charge", "conditions": {"payment_plan": "premium-rag"}}` and the Worker physically gates the content until the micro-transaction clears.

### v0.3 — Observability layer

- [ ] Hosted monitoring: policy change history, enforcement logs, crawler activity
- [ ] Alerts: notify when a new bot appears, when a bot ignores policy, when crawl volume spikes
- [ ] Compliance reports: machine-readable proof of policy adherence for legal/regulatory use
- [ ] WordPress plugin (distribution channel for the hosted platform)
- [ ] Team workflows, white-label, enterprise integrations

## Contributing

consent.txt is an open standard. Contributions welcome.

- **Spec feedback**: Open an issue with the `specification` label
- **Compiler targets**: PRs for new emit targets (Nginx config, Caddy, Vercel)
- **Adoption**: Deploy consent.txt on your site and let us know

## License

- **Code**: Apache-2.0
- **Specification text**: CC BY 4.0

## Author

**George Geronik** — AI Researcher, Webroot.AI

- GitHub: [@GGeronik](https://github.com/GGeronik)
- Also: [God Clause](https://github.com/GGeronik/God_Clause) — AI governance framework

---

*One manifest. Every surface. Deploy today.*
