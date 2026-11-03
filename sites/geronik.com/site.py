#!/usr/bin/env python3
"""Static files geronik.com serves for its consent manifest.

    python3 site.py build --repo /path/to/consent-txt   # write public/, headers.txt and lovable-prompt.md
    python3 site.py check                               # compare the live site with public/

consent-manifest.json next to this script is the source. Edit it here, never inside Lovable,
rebuild, paste lovable-prompt.md into the Lovable project and publish.
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
PUBLIC = HERE / "public"
SITE = "https://geronik.com"
FILES = ("robots.txt", ".well-known/consent-manifest.json", ".well-known/tdmrep.json")
# Articles published daily from Google Drive, served by the site's backend.
EXTRA_SITEMAPS = ["https://hcriufirfjmudqkrrxuc.supabase.co/functions/v1/sitemap-articles"]
NOTICE = "# Compiled outside this project from /.well-known/consent-manifest.json. Do not edit by hand.\n"
UA = {"User-Agent": "Mozilla/5.0 (consent-manifest check)"}
TIMEOUT = 20

PROMPT = """Update the static files that declare this site's AI permissions, and hand robots.txt over to a static file. Paste each file exactly as given, byte for byte, with no reformatting. Change nothing else. Leave the /consent-txt page and `src/lib/consentCompiler.ts` alone. Steps 1, 5 and 6 are one-off: skip any that is already done.

1. Stop generating robots.txt at build time. In `src/seo/vitePlugin.ts`, remove the `robots.txt` entry from `render()`, remove `robots.txt` from the name check in `configureServer`, drop the now unused `compileRobotsTxt` import, the `MANIFEST` constant and the manifest read, and change the header comment to say that sitemap.xml and llms.txt are generated here while robots.txt lives in `public/` and is compiled outside this project. In `src/seo/files.ts`, delete `buildRobotsTxt` with its comment and change the header comment to match.

2. Create `public/robots.txt` with:

```
{robots}```

3. Replace `public/.well-known/consent-manifest.json` with:

```json
{manifest}```

4. Create `public/.well-known/tdmrep.json` with:

```json
{tdmrep}```

5. Delete `public/_headers`. The host ignores it and serves it as a file.

6. Append this rule to `AGENTS.md`:

```
- `public/robots.txt`, `public/.well-known/consent-manifest.json` and `public/.well-known/tdmrep.json` are compiled outside this project from the consent manifest. Do not edit, reformat or regenerate them, do not generate robots.txt from `src/seo/vitePlugin.ts`, and do not apply SEO review fixes to robots.txt. Why: the three files must agree with each other and with the compiler that produced them.
```

Then run the build and confirm that the built robots.txt is byte for byte the file in step 2.
"""


def lines(path, prefix):
    if not path.exists():
        return []
    return [l for l in path.read_text().splitlines() if l.startswith(prefix)]


def read(out, name):
    if not (out / name).exists():
        sys.exit(f"compiler wrote no {name}: check interop.emit in consent-manifest.json")
    return (out / name).read_text()


def build(repo):
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        subprocess.run([sys.executable, "-I", str(Path(repo) / "compiler" / "compile.py"),
                        str(HERE / "consent-manifest.json"), "--out", tmp],
                       check=True, stdout=subprocess.DEVNULL)
        robots = read(out, "robots.txt")
        star = "User-Agent: *\n"
        if robots.count(star) != 1:
            sys.exit("robots.txt: expected exactly one 'User-Agent: *' group")
        merged = lines(out / "content-signal.txt", "Content-Signal:")[:1] + lines(out / "aipref-robots.txt", "Content-Usage:")
        robots = NOTICE + robots.replace(star, star + "".join(l + "\n" for l in merged))
        robots += "".join(f"Sitemap: {u}\n" for u in EXTRA_SITEMAPS)
        tdmrep = read(out, "tdmrep.json")
        headers = (lines(out / "aipref-header.txt", "Content-Usage:")
                   + lines(out / "content-signal.txt", "Content-Signal:")[:1]
                   + lines(out / "tdmrep-headers.txt", "tdm-reservation:")
                   + lines(out / "x-robots-tag.txt", "X-Robots-Tag:"))
    manifest = (HERE / "consent-manifest.json").read_text().rstrip("\n") + "\n"
    prompt = PROMPT.format(robots=robots, manifest=manifest, tdmrep=tdmrep)
    (PUBLIC / ".well-known").mkdir(parents=True, exist_ok=True)
    (PUBLIC / "robots.txt").write_text(robots)
    (PUBLIC / ".well-known" / "consent-manifest.json").write_text(manifest)
    (PUBLIC / ".well-known" / "tdmrep.json").write_text(tdmrep)
    (HERE / "headers.txt").write_text("".join(l + "\n" for l in headers))
    (HERE / "lovable-prompt.md").write_text(prompt)
    print(f"built {PUBLIC}, headers.txt and lovable-prompt.md")


def fetch(url, accept=None):
    req = urllib.request.Request(url, headers={**UA, **({"Accept": accept} if accept else {})})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read().decode(), r.headers, r.url


def canon(text, rel):
    return json.dumps(json.loads(text), sort_keys=True) if rel.endswith(".json") else text


def check():
    ok = True
    for rel in FILES:
        want = (PUBLIC / rel).read_text()
        try:
            got = fetch(f"{SITE}/{rel}")[0]
            same, note = canon(got, rel) == canon(want, rel), ""
        except Exception as e:  # 404, network, or a 404 page where JSON was expected
            same, note = False, f" ({e})"
        ok &= same
        print(("ok    " if same else "DIFF  ") + rel + note)
    try:
        html, html_headers, _ = fetch(f"{SITE}/")
        _, md_headers, _ = fetch(f"{SITE}/", "text/markdown")
        www = fetch("https://www.geronik.com/")[2]
    except Exception as e:
        sys.exit(f"FAIL  {SITE} ({e})")
    expect = (HERE / "headers.txt").read_text().splitlines()
    denies_training = any(l.startswith("X-Robots-Tag:") and "noai" in l for l in expect)
    meta = re.search(r'<meta\s+name="robots"\s+content="([^"]*)"', html, re.I)
    has_noai = bool(meta and "noai" in meta.group(1))
    ok &= has_noai == denies_training
    print(("ok    " if has_noai == denies_training else "DIFF  ")
          + f"robots meta {'has' if has_noai else 'lacks'} noai, manifest {'denies' if denies_training else 'allows'} training")
    for label, h in (("html", html_headers), ("markdown", md_headers)):  # served only through Cloudflare, informational
        for line in expect:
            name, _, value = line.partition(": ")
            got = h.get(name)
            print(("ok    " if got == value else "none  " if got is None else "DIFF  ") + f"{label}: {line}")
    print(("ok    " if www.startswith(SITE + "/") else "note  ") + f"www -> {www}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    # Inside the consent-txt repository (sites/<host>/site.py) the compiler is two levels up.
    sub.add_parser("build").add_argument("--repo", default=str(HERE.parents[1]) if len(HERE.parents) > 1 else None,
                                         help="a consent-txt clone at v0.2.0 or later")
    sub.add_parser("check")
    a = p.parse_args()
    if a.cmd == "build" and not (Path(a.repo) / "compiler" / "compile.py").exists():
        sys.exit(f"no compiler at {a.repo}: pass --repo <consent-txt clone>")
    build(a.repo) if a.cmd == "build" else check()
