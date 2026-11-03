Update the static files that declare this site's AI permissions, and hand robots.txt over to a static file. Paste each file exactly as given, byte for byte, with no reformatting. Change nothing else. Leave the /consent-txt page and `src/lib/consentCompiler.ts` alone. Steps 1, 5 and 6 are one-off: skip any that is already done.

1. Stop generating robots.txt at build time. In `src/seo/vitePlugin.ts`, remove the `robots.txt` entry from `render()`, remove `robots.txt` from the name check in `configureServer`, drop the now unused `compileRobotsTxt` import, the `MANIFEST` constant and the manifest read, and change the header comment to say that sitemap.xml and llms.txt are generated here while robots.txt lives in `public/` and is compiled outside this project. In `src/seo/files.ts`, delete `buildRobotsTxt` with its comment and change the header comment to match.

2. Create `public/robots.txt` with:

```
# Compiled outside this project from /.well-known/consent-manifest.json. Do not edit by hand.
# robots.txt
# Generated from consent-manifest.json by consent.txt compiler v0.2
# Agents table: 2026-10-22
# Publisher: George Geronikolopoulos

User-Agent: *
Content-Signal: search=yes, ai-input=yes, ai-train=no
Content-Usage: train-ai=n, search=y
Allow: /

# Note: Google-Extended also governs Gemini grounding, and Google has no separate ai-input token.
User-Agent: GPTBot
User-Agent: ClaudeBot
User-Agent: CCBot
User-Agent: Google-Extended
User-Agent: Applebot-Extended
User-Agent: Meta-ExternalAgent
User-Agent: FacebookBot
User-Agent: Amazonbot
User-Agent: MistralAI-Training
User-Agent: AI2Bot
User-Agent: Ai2Bot-Dolma
User-Agent: cohere-training-data-crawler
User-Agent: cohere-ai
User-Agent: Bytespider
User-Agent: TikTokSpider
User-Agent: DeepSeekBot
User-Agent: Omgilibot
User-Agent: omgili
User-Agent: Webzio-Extended
User-Agent: SBIntuitionsBot
Disallow: /

Sitemap: https://geronik.com/sitemap.xml
Sitemap: https://hcriufirfjmudqkrrxuc.supabase.co/functions/v1/sitemap-articles
```

3. Replace `public/.well-known/consent-manifest.json` with:

```json
{
  "version": "0.1",
  "publisher": {
    "name": "George Geronikolopoulos",
    "url": "https://geronik.com",
    "contact": "mailto:george@geronik.com",
    "jurisdictions": [
      "GR",
      "GB",
      "EU"
    ]
  },
  "defaults": {
    "fallbacks": {
      "unexpressible_state": "deny",
      "unknown_identity": "deny"
    },
    "standard": {
      "train-ai": {
        "state": "deny"
      },
      "search": {
        "state": "allow"
      }
    },
    "experimental": {
      "train-genai": {
        "state": "deny"
      },
      "ai-input": {
        "state": "allow"
      },
      "embedding": {
        "state": "allow"
      },
      "generate-media": {
        "state": "deny"
      }
    }
  },
  "interop": {
    "emit": [
      "robots-txt",
      "aipref-header",
      "aipref-robots",
      "x-robots-tag",
      "google-extended",
      "tdmrep",
      "content-signal",
      "summary"
    ]
  }
}
```

4. Create `public/.well-known/tdmrep.json` with:

```json
[
  {
    "location": "/",
    "tdm-reservation": 1
  }
]
```

5. Delete `public/_headers`. The host ignores it and serves it as a file.

6. Append this rule to `AGENTS.md`:

```
- `public/robots.txt`, `public/.well-known/consent-manifest.json` and `public/.well-known/tdmrep.json` are compiled outside this project from the consent manifest. Do not edit, reformat or regenerate them, do not generate robots.txt from `src/seo/vitePlugin.ts`, and do not apply SEO review fixes to robots.txt. Why: the three files must agree with each other and with the compiler that produced them.
```

Then run the build and confirm that the built robots.txt is byte for byte the file in step 2.
