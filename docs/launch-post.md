# Show HN: consent.txt – One manifest that compiles into robots.txt, AIPREF headers, and preview controls

I got tired of maintaining six different policy files to control how AI systems use my site's content. robots.txt blocks crawlers but can't distinguish training from search. AIPREF headers express usage preferences but nobody hand-writes them. Google-Extended only covers Google. TDMRep only matters in the EU. And none of them talk to each other.

So I built a compiler.

**consent.txt** is a JSON manifest you write once. The compiler turns it into the protocol surfaces that AI crawlers already consume: robots.txt user-agent groups, AIPREF `Content-Usage` headers, `X-Robots-Tag` directives, Google-Extended blocks, and TDMRep references. You don't need any AI company to adopt a new standard. The output is the standards they already read.

Here's the smallest possible manifest:

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

Run `python compiler/compile.py manifest.json --out build/` and you get a robots.txt that blocks GPTBot, ClaudeBot, CCBot, Google-Extended, Bytespider, Amazonbot, and 6 more training crawlers — plus a separate block for ChatGPT-User and Claude-User since ai-input is denied. The AIPREF header emits only the two standardized categories: `Content-Usage: train-ai=n, search=y`. The extended categories (`train-genai`, `ai-input`) drive bot-blocking in robots.txt but are not emitted into AIPREF — because they are not yet part of the AIPREF vocabulary.

The manifest supports five states: `allow`, `deny`, `unknown`, `charge`, and `conditional`. The last two are the interesting ones. You can say "inference access requires signed identity and attribution" or "premium content requires payment." The compiler knows that robots.txt can't express `charge`, so it applies your declared fallback rule (default: deny) when lowering to that surface. The rich semantics are preserved for enforcement runtimes that can handle them.

The spec has two tiers. **Standard** (`train-ai`, `search`) maps to the IETF AIPREF vocabulary draft. **Extended** (`train-genai`, `ai-input`, `agentic-access`, `transform`, `generate-media`, `embedding`) covers categories that are widely used but not yet formally standardized — Cloudflare Content Signals uses `ai-input`, AIPREF is discussing `train-genai`, and the rest are project-defined. Extended categories drive enforcement decisions (which bots to block) but are never emitted into AIPREF headers. I don't want to pretend my categories are internet standards when they aren't.

**"But malicious scrapers just spoof User-Agent strings."**

Yes. That's why relying on robots.txt alone is a fundamentally brittle defense. The Cloudflare Worker doesn't just match user-agent strings — it implements a four-tier trust ladder:

1. **Signed**: Checks for actual HTTP Message Signature headers (`Signature` + `Signature-Input`) on the request. OpenAI's ChatGPT agent already sends these and publishes a well-known key directory. If the headers are present, the bot is promoted to the cryptographic tier. No headers, no promotion — regardless of what the user-agent claims.
2. **Published IP**: Request IP verified against published JSON IP lists (OpenAI publishes these for GPTBot and OAI-SearchBot).
3. **Reverse DNS**: Forward-confirmed reverse DNS resolving to a known domain. Googlebot and CCBot have documented this for years.
4. **User-agent only**: The weakest tier. ClaudeBot, Bytespider, and others are here because their operators don't yet publish IP lists or support signatures.

A manifest that requires `"identity": "signed"` will reject a request from a bot that merely claims to be ChatGPT-User without carrying the actual cryptographic signature. A bot that spoofs its user-agent but doesn't have the right IP or signature gets classified at the lowest tier and denied by any policy that requires verification.

You can test this without affecting real traffic:

```
curl "https://yoursite.com/_consent/test?path=/premium/&ua=GPTBot"
```

Returns the bot identification (which tier, which org), the resolved policy, the compiled headers, and the enforcement decision. The Worker also supports `DRY_RUN=true` — log all decisions without blocking anything.

I built this because I was tired of the "just add a line to robots.txt" conversation. User-agent matching is not identity. consent.txt treats identity as a spectrum of confidence, not a binary.

The domain scanner checks any site's current AI policy posture and scores it on four axes: access controls, usage declarations, preview controls, and identity confidence. Most sites score badly because they block three bots in robots.txt and call it done. We scanned 20 major domains — the average score was 25/100 and nobody scored above a C. The full benchmark is in the repo.

**What's in the repo:**

- v0.1 spec (CC BY 4.0)
- JSON Schema (4 standard + 4 experimental categories)
- Validator CLI (Python, zero deps)
- Compiler CLI (robots.txt + AIPREF + X-Robots-Tag + Google-Extended + TDMRep)
- Cloudflare Worker runtime (trust ladder, enforcement, dry-run, health/test endpoints)
- Domain scanner (AI Policy Readiness scorecard, 4 axes)
- Badge generator (embeddable SVG for site footers — every badge links back to the scanner)
- 6 example manifests

Code is Apache-2.0. Spec text is CC BY 4.0.

GitHub: https://github.com/GGeronik/consent.txt

The IETF AIPREF working group is standardizing the vocabulary and attachment mechanism, with documents heading to the IESG around August 2026. consent.txt sits above that: one authoring surface that compiles into AIPREF and everything else, plus enforcement that AIPREF explicitly scoped out. If AIPREF changes its vocabulary, I update the compiler. Publishers don't touch their manifests.

**Where this is going:** v0.2 will integrate HTTP 402 (Payment Required) directly into the Worker. A manifest `charge` state will trigger a real payment flow — Stripe, TollBit, or Cloudflare Pay Per Crawl — gating content until the micro-transaction clears. The manifest becomes a pricing table. That's the tollbooth: not just "block AI" but "route payment from AI to publisher."

I'm not marketing this as an AI blocker or a way to rank higher in ChatGPT. Content signals are preferences, not countermeasures. What I am saying is that publishers shouldn't need to understand the difference between GPTBot, OAI-SearchBot, ChatGPT-User, ClaudeBot, Claude-SearchBot, Claude-User, Google-Extended, and CCBot just to say "don't train on my stuff."

One manifest. Every surface. Runs today.
