# Serving the headers through Cloudflare

Lovable does not apply a `_headers` file and has no setting for response headers, so the headers can only be added by a proxy in front of the site. Here that is your own Cloudflare zone, since the DNS for geronik.com already lives there. This step is optional. Once the Lovable prompt has been applied, robots.txt carries Content-Signal and Content-Usage, and `tdmrep.json` carries TDMRep.

The headers matter for two readers. Clients that read headers rather than robots.txt. And the Markdown copy of each page, which Lovable serves to any client that asks for `text/markdown` and which drops every meta tag, so a header is the only page-level declaration that reaches it. Cloudflare's own Markdown for Agents behaves the same way: it keeps a Content-Signal header it finds and otherwise adds a default that allows training.

Today the A records for geronik.com and www are DNS only and point at Lovable's edge, 185.158.133.1, so nothing of yours sits in front of the site. The change takes the site offline between the disconnect in Lovable and the moment Lovable shows the domain as Live again, so do the first three steps in one sitting.

## Set the SSL mode before anything is proxied

In the geronik.com zone: SSL/TLS, Overview, Configure, Custom SSL/TLS, and pick Full. Lovable answers plain HTTP with a redirect to HTTPS, so a zone left on Flexible loops as soon as the proxy is on. Full (strict) comes later, once Lovable has issued its certificate.

## Reconnect the domain in Lovable with the proxy option

Lovable offers the proxy option only while connecting a domain. In the project: Settings, Domains, open the menu next to geronik.com and choose Disconnect. Then Connect domain, Connect existing domain, enter geronik.com, choose Root domain, keep the redirect of www.geronik.com to geronik.com switched on, expand Advanced, enable "Uses Cloudflare or similar proxy", and connect. Lovable shows a CNAME record for geronik.com and one for www, both pointing at your project's `lovable.app` address, and no longer asks for a `_lovable` TXT record. From here Lovable does not configure, validate or monitor the Cloudflare side.

## Change the DNS records in Cloudflare

DNS, Records: delete the two A records pointing at 185.158.133.1 and add the two CNAME records Lovable showed, proxy status Proxied (orange cloud). Do not add AAAA records. The two `_lovable` TXT records are no longer needed. Leaving them in place is harmless.

Wait until Settings, Domains in Lovable shows geronik.com and www.geronik.com as Live. A 526 error before that only means Lovable's certificate is not issued yet. Once both are Live, set SSL/TLS to Full (strict). If 526 persists after Live, go back to Full. The mode applies to every proxied hostname in the zone, so limit it with a Configuration Rule if other hosts are proxied there.

Leave caching at Cloudflare's defaults, which do not cache HTML. Lovable caches at its own edge, and Cloudflare discourages caching on a zone that sits in front of another Cloudflare-fronted provider.

## Add the response headers

Rules, Overview, Create rule, Response Header Transform Rule. Name: consent manifest headers. When incoming requests match: All incoming requests. Under Modify response header, add one Set static row per line of `headers.txt`, with the text before the first colon as the header name and the rest as the value, so `X-Robots-Tag` takes the value `googlebot: noai, noimageai`:

```
Content-Usage: train-ai=n, search=y
Content-Signal: search=yes, ai-input=yes, ai-train=no
tdm-reservation: 1
X-Robots-Tag: googlebot: noai, noimageai
```

Deploy the rule. Response Header Transform Rules are included in the Free plan.

A second rule gives the manifest the cache lifetime the specification asks for: Response Header Transform Rule, when URI Path equals `/.well-known/consent-manifest.json`, Set static `Cache-Control` to `public, max-age=86400`.

## Check the headers are served

```bash
python3 site.py check
```

The header lines, listed for the HTML and the Markdown copy of the home page, should change from `none` to `ok`. A quick look by hand:

```bash
curl -sI https://geronik.com/ | grep -i -E 'content-usage|content-signal|tdm-|x-robots'
```

When the manifest changes, rebuild with `python3 site.py build`, paste the new prompt into Lovable, publish, and copy the new `headers.txt` values into the rule.
