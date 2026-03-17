# AI Policy Readiness Index: A 20-Domain Sample, March 2026

**In our March 2026 sample of 20 domains, the average AI policy readiness score was 25 out of 100. Even the most aggressive blockers fail on three of four axes.**

We scanned 20 domains across news publishers, tech media, SaaS platforms, and open content sites. Each was scored on four axes: access controls (robots.txt coverage), usage declarations (AIPREF headers, TDMRep), preview controls (X-Robots-Tag, snippet directives), and identity confidence (bot-specific rules, verification endpoints).

The results are bad across the board.

## The numbers

Average scores across 20 domains:

| Axis | Average | What it measures |
|------|---------|-----------------|
| Access controls | 58/100 | robots.txt bot coverage |
| Usage declarations | 4/100 | AIPREF headers, TDMRep, consent manifest |
| Preview controls | 4/100 | X-Robots-Tag, snippet limits, noai directives |
| Identity confidence | 34/100 | Bot-specific rules, verification endpoints |
| **Overall** | **25/100** | |

Zero domains had a consent manifest. One domain (Cloudflare) had AIPREF Content-Usage headers. Two domains (Le Monde, Spiegel) had TDMRep declarations. One domain (Cloudflare) had X-Robots-Tag with AI-specific directives.

Grade distribution: 0 A's, 0 B's, 4 C's, 8 D's, 8 F's.

## The scorecard

| Domain | Category | Grade | Overall | Access | Usage | Preview | Identity |
|--------|----------|-------|---------|--------|-------|---------|----------|
| lemonde.fr | News (EU) | C | 42 | 85 | 25 | 0 | 60 |
| spiegel.de | News (EU) | C | 42 | 81 | 25 | 0 | 60 |
| bbc.co.uk | News | C | 40 | 100 | 0 | 0 | 60 |
| apnews.com | News | C | 40 | 100 | 0 | 0 | 60 |
| nytimes.com | News | D | 38 | 94 | 0 | 0 | 60 |
| wsj.com | News | D | 38 | 94 | 0 | 0 | 60 |
| theguardian.com | News | D | 37 | 87 | 0 | 0 | 60 |
| reuters.com | News | D | 35 | 81 | 0 | 0 | 60 |
| cloudflare.com | SaaS | D | 35 | 20 | 40 | 70 | 10 |
| cnn.com | News | D | 27 | 71 | 0 | 0 | 35 |
| washingtonpost.com | News | D | 26 | 65 | 0 | 0 | 40 |
| stackoverflow.com | Platform | D | 25 | 59 | 0 | 0 | 40 |
| techcrunch.com | Tech Media | F | 16 | 39 | 0 | 0 | 25 |
| arstechnica.com | Tech Media | F | 15 | 36 | 0 | 0 | 25 |
| medium.com | Platform | F | 8 | 33 | 0 | 0 | 0 |
| stripe.com | SaaS | F | 7 | 26 | 0 | 0 | 0 |
| wikipedia.org | Nonprofit | F | 7 | 26 | 0 | 0 | 0 |
| github.com | Platform | F | 6 | 23 | 0 | 0 | 0 |
| vercel.com | SaaS | F | 6 | 23 | 0 | 0 | 0 |
| substack.com | Platform | F | 6 | 21 | 0 | 0 | 0 |

## What the data shows

**Finding 1: The industry is 90% robots.txt, 0% everything else.** Access controls (average 58) are the only axis where publishers have made progress. Usage declarations (average 4), preview controls (average 4), and identity confidence (average 34) are near zero. The web has one policy tool — robots.txt — and it's being asked to do a job it was never designed for.

**Finding 2: Even the best-scoring sites are incomplete.** BBC and AP News block all 16 tracked AI bots and score 100 on access controls. But they score 0 on usage declarations, 0 on preview controls, and 60 on identity. Their AI policy amounts to a blunt "block everything" with no mechanism to express *how* content can be used, no snippet or preview controls, and no way to verify bot identity beyond user-agent strings.

**Finding 3: EU publishers lead because regulation forced them to.** Le Monde and Spiegel are the only two domains scoring above 40, and both benefit from TDMRep declarations required by the EU Copyright Directive. Regulatory pressure produces measurable policy completeness.

**Finding 4: SaaS and platforms are mostly unprotected.** GitHub, Stripe, Vercel, Substack, and Medium all score below 10. Their robots.txt files mention 0-4 AI bots. They have no usage declarations, no preview controls, and no identity mechanisms. Most of their content is being consumed by AI systems with zero policy friction.

**Finding 5: Cloudflare is the only domain using structured usage headers.** Cloudflare.com serves `Content-Signal` headers (Cloudflare's own Content Signals protocol, distinct from AIPREF `Content-Usage`) and X-Robots-Tag directives that affect AI features. It scores poorly on access controls (no bot-specific robots.txt rules) but leads on usage declarations and preview controls. Note: Cloudflare's `Content-Signal` is not the same as the AIPREF `Content-Usage` header, though both express similar preferences. The consent.txt compiler emits AIPREF `Content-Usage`; a future version will also emit Cloudflare `Content-Signal`.

**Finding 6: Nobody has a consent manifest.** Zero domains have deployed a consent manifest or any equivalent unified policy file. Every domain maintains between 1 and 3 policy surfaces (robots.txt, sometimes TDMRep, rarely AIPREF) but none ties them together into a single source of truth.

## What would change with consent.txt

A consent manifest addresses all four axes simultaneously. If the NYT deployed one:

Their access score stays at 94 (robots.txt rules already compiled). Their usage score jumps from 0 to 60+ (the compiler emits AIPREF headers from the manifest). Their preview score jumps from 0 to 30-70 (the compiler emits X-Robots-Tag with max-snippet and noai from the manifest's conditions). Their identity score jumps from 60 to 90 (the manifest declares verification endpoints and the Worker enforces the trust ladder).

Overall: from 38/100 to roughly 70-80/100. One file, one `wrangler deploy`.

## Methodology

Each domain scored on four axes (0-100), overall is the unweighted average.

Access controls: +20 for robots.txt present, +0-50 for proportion of 16 tracked bots mentioned, +15 for Google-Extended rules, +15 for 10+ bots addressed.

Usage declarations: +40 for AIPREF header, +35 for consent manifest, +25 for TDMRep.

Preview controls: +40 for snippet controls, +30 for X-Robots-Tag AI directives, +30 for consent manifest with conditional states.

Identity confidence: +25 for 5+ bots addressed, +15 for 10+ bots, +30 for consent manifest with endpoints, +10 for AIPREF, +20 for Google-Extended.

Data sources: BuzzStream Dec 2025, Press Gazette Jan 2026, Paul Calvano CrUX Aug 2025, individual robots.txt files March 2026.

The full dataset with per-domain notes is available in the companion spreadsheet.

---

*AI Policy Readiness Index is published by the consent.txt project. Methodology and scoring rubric are open. Corrections welcome via [GitHub](https://github.com/GGeronik/consent.txt).*
