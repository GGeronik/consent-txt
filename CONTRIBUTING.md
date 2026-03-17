# Contributing to consent.txt

consent.txt is an open standard. Contributions are welcome from anyone who wants to help publishers control how AI systems use their content.

## How to contribute

### Spec feedback

Open an issue with the `specification` label. Include the section number you're referencing and a concrete suggestion. Philosophical disagreements are welcome; vague complaints are not.

### New standard categories

Standard categories must map to a recognized public standard or a shipping implementation from a major platform (AIPREF, Cloudflare Content Signals, etc.). Open an issue with the `vocabulary` label, include the source standard, and describe the wire mapping.

### New experimental categories

Experimental categories have a lower bar: describe the use case, propose a name, and explain what an enforcement runtime would do with it. Open an issue with the `vocabulary` label.

### Compiler targets

PRs for new emit targets are welcome. Each target needs:

- A compiler function in `compiler/compile.py`
- An entry in the `COMPILERS` dict
- A test showing the output for at least the `news-publisher.json` and `minimal.json` examples
- Documentation of any lowering rules (how `charge`/`conditional` map to the target surface)

Targets we'd particularly like: Nginx config, Caddy config, Apache `.htaccess`, Vercel `vercel.json` headers.

### Scanner improvements

The scanner (`scanner/scan.py`) has a simple scoring model. If you have evidence that the weights are wrong or a check is missing, open an issue with data.

### Worker improvements

The Cloudflare Worker (`worker/index.js`) does not currently perform actual IP verification or DNS reverse lookups. PRs that add real verification (checking requests against published IP lists, performing reverse DNS) are high priority.

### Bug reports

Include: what you did, what you expected, what happened, and the manifest JSON (or a minimal reproduction). If the compiler produced wrong output, include both the input manifest and the incorrect output.

## What not to contribute

- Changes to the spec that break backward compatibility with v0.1 manifests
- New standard categories that don't map to any shipping wire format
- Adversarial/offensive defense features (these belong in a separate enforcement product, not the open standard)
- Marketing copy or SEO-optimized content

## Code style

Python: no external dependencies in core tools. Standard library only. Run `python tools/validate.py examples/*.json` before submitting.

JavaScript (Worker): ES modules, no build step, deployable with `wrangler deploy`.

## License

By contributing, you agree that your contributions will be licensed under:

- **Apache-2.0** for code
- **CC BY 4.0** for specification text and documentation

## Issue labels

| Label | Use for |
|-------|---------|
| `specification` | Spec text changes, ambiguities, corrections |
| `vocabulary` | New or modified usage categories |
| `compiler` | Compiler bugs, new emit targets |
| `worker` | Cloudflare Worker issues |
| `scanner` | Scanner scoring, checks, reports |
| `bug` | Something is broken |
| `enhancement` | Feature requests |
| `good-first-issue` | Suitable for new contributors |
