# geronik.com consent manifest deployment

The site is built and hosted on Lovable, which until now generated robots.txt at build time with its own TypeScript copy of the v0.1 compiler. This folder replaces that: the manifest here is the source, the Python compiler at v0.2.0 produces the files, and Lovable serves them as static files from `public/`.

- `consent-manifest.json`: the manifest. Edit it here, never inside Lovable, then rebuild.
- `python3 site.py build`: runs the compiler of the repository this folder sits in (add `--repo <clone>` when the folder is used on its own; v0.2.0, commit 2bbd292, or later), merges the Content-Signal and Content-Usage lines into the `User-Agent: *` group of robots.txt, adds the sitemap of the Drive-published articles, and writes `public/`, `headers.txt` and `lovable-prompt.md`.
- `lovable-prompt.md`: paste into the Lovable project, then publish. The first paste also stops the site's Vite plugin from generating robots.txt and adds a rule to `AGENTS.md` so later prompts and SEO review fixes leave the files alone.
- `cloudflare-headers.md`: the optional step that serves the same declarations as response headers.
- `python3 site.py check`: compares the live files with `public/`, checks that the robots meta tag agrees with the manifest on training, lists which of the four headers reach the HTML and the Markdown copy of the home page, and says whether www redirects. Only the files and the meta tag set the exit code.

## What to expect after publishing

- The next publish also carries every unpublished change in the Lovable project, at the moment the Drive publishing work of 2 November.
- Google and other crawlers may keep the old robots.txt for up to 24 hours, while `check` passes at once.
- Google Search Console may report "Syntax not understood" for the Content-Signal and Content-Usage lines. That is expected and harmless.
- v0.2.0 stops blocking Diffbot, which its operator documents as a search crawler, and adds eight training crawlers the old file lacked.
- TDMRep can only reserve all text and data mining or none, so `tdm-reservation: 1` also reserves the search and AI input uses that robots.txt allows, for agents that read TDMRep alone. That follows the manifest's `unexpressible_state: deny`. The file `tdmrep.json` is the only TDMRep technique used on the site, as the protocol asks. The optional Cloudflare header agrees with it and takes precedence where both are read.
- www.geronik.com serves the site itself rather than redirecting. Setting geronik.com as primary in Lovable's domain settings gives the declarations one origin.

## Not covered here

- The /consent-txt playground on the site still runs the v0.1 rules and will disagree with the live robots.txt.
- The Terms of Service page predates the manifest and says nothing about automated or AI use.
- The site's MCP server on supabase.co hands out article text under no stated terms.
- The manifest declares `generate-media: deny` and `embedding: allow`, which no compiled surface carries.

Each of those is a separate decision.
