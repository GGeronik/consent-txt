/**
 * consent.txt — Cloudflare Worker Runtime v0.1
 *
 * Enforcement middleware that reads a Consent Manifest and:
 *   1. Identifies incoming bots via a trust ladder
 *   2. Resolves the applicable policy
 *   3. Injects AIPREF, X-Robots-Tag, and TDMRep headers
 *   4. Returns 402 for charge-state requests from identified bots
 *   5. Logs enforcement actions
 *
 * Deploy: wrangler deploy
 * Config: set CONSENT_MANIFEST as a KV binding or inline the manifest.
 */

// ── Trust Ladder ─────────────────────────────────────────────────────────────
// Ordered from strongest to weakest identity confidence.

const BOT_SIGNATURES = {
  // Tier 1: Signed requests (HTTP Message Signatures)
  // NOTE: Actual signature verification requires checking the Signature and
  // Signature-Input headers against the key directory. The identifyBot function
  // below checks for signature headers and upgrades the tier accordingly.
  // No bots are pre-assigned to this tier — they are promoted at runtime.
  signed: [],
  // Tier 2: Published IP lists (verifiable via JSON endpoint)
  published_ip: [
    { ua: "GPTBot", org: "OpenAI", category: "train-ai",
      ip_url: "https://openai.com/gptbot.json" },
    { ua: "OAI-SearchBot", org: "OpenAI", category: "search",
      ip_url: "https://openai.com/searchbot.json" },
    { ua: "ChatGPT-User", org: "OpenAI", category: "ai-input",
      ip_url: "https://openai.com/chatgpt-user.json",
      note: "Also supports HTTP Message Signatures — check Signature header for tier upgrade" },
  ],
  // Tier 3: Reverse DNS / IP verification
  reverse_dns: [
    { ua: "Googlebot", org: "Google", category: "search",
      dns_suffix: ".googlebot.com" },
    { ua: "Google-Extended", org: "Google", category: "train-ai",
      dns_suffix: ".googlebot.com" },
    { ua: "CCBot", org: "Common Crawl", category: "train-ai",
      dns_suffix: ".commoncrawl.org" },
    { ua: "Bingbot", org: "Microsoft", category: "search",
      dns_suffix: ".search.msn.com" },
  ],
  // Tier 4: User-agent string only (weakest, easily spoofed)
  user_agent_only: [
    { ua: "ClaudeBot", org: "Anthropic", category: "train-ai" },
    { ua: "Claude-SearchBot", org: "Anthropic", category: "search" },
    { ua: "Claude-User", org: "Anthropic", category: "ai-input" },
    { ua: "PerplexityBot", org: "Perplexity", category: "search" },
    { ua: "Bytespider", org: "ByteDance", category: "train-ai" },
    { ua: "FacebookBot", org: "Meta", category: "train-ai" },
    { ua: "Amazonbot", org: "Amazon", category: "train-ai" },
    { ua: "Diffbot", org: "Diffbot", category: "train-ai" },
    { ua: "cohere-ai", org: "Cohere", category: "train-ai" },
    { ua: "AI2Bot", org: "AI2", category: "train-ai" },
    { ua: "Applebot-Extended", org: "Apple", category: "train-ai" },
  ],
};

// ── State lowering ───────────────────────────────────────────────────────────

function lowerState(state, fallbacks) {
  if (state === "allow" || state === "deny") return state;
  if (state === "unknown") return null;
  return fallbacks?.unexpressible_state || "deny";
}

function getState(policies, category) {
  return policies?.[category]?.state || "unknown";
}

// ── Bot identification ───────────────────────────────────────────────────────

function identifyBot(request) {
  const ua = request.headers.get("user-agent") || "";
  const hasSignature = !!(request.headers.get("signature") && request.headers.get("signature-input"));

  // Check all tiers (skip signed — it's populated at runtime).
  for (const [tier, bots] of Object.entries(BOT_SIGNATURES)) {
    if (tier === "signed") continue; // Signed tier is empty; bots are promoted below.
    for (const bot of bots) {
      if (ua.includes(bot.ua)) {
        // If the request carries HTTP Message Signatures, upgrade to signed tier.
        const effectiveTier = hasSignature ? "signed" : tier;
        return {
          matched: true,
          ua_token: bot.ua,
          org: bot.org,
          primary_category: bot.category,
          trust_tier: effectiveTier,
          has_signature: hasSignature,
          note: bot.note || null,
        };
      }
    }
  }

  return { matched: false, ua_token: null, org: null, primary_category: null, trust_tier: "none", has_signature: false };
}

// ── Policy resolution ────────────────────────────────────────────────────────

function resolvePolicy(manifest, pathname) {
  const defaults = manifest.defaults || {};
  let std = { ...(defaults.standard || {}) };
  let exp = { ...(defaults.experimental || {}) };

  if (manifest.rules) {
    let bestRule = null;
    let bestLen = -1;

    for (const rule of manifest.rules) {
      const pattern = rule.match?.path || "";
      if (pathMatches(pathname, pattern) && pattern.length > bestLen) {
        bestRule = rule;
        bestLen = pattern.length;
      }
    }

    if (bestRule) {
      if (bestRule.standard) std = { ...std, ...bestRule.standard };
      if (bestRule.experimental) exp = { ...exp, ...bestRule.experimental };
    }
  }

  return { standard: std, experimental: exp };
}

function pathMatches(testPath, pattern) {
  if (!pattern) return false;
  if (pattern.endsWith("/**")) {
    const prefix = pattern.slice(0, -3);
    return testPath === prefix || testPath.startsWith(prefix + "/");
  }
  if (pattern.endsWith("/*")) {
    const prefix = pattern.slice(0, -2);
    return testPath === prefix || testPath.startsWith(prefix + "/");
  }
  return testPath === pattern;
}

// ── Header compilation ───────────────────────────────────────────────────────

function compileHeaders(manifest, policy) {
  const headers = {};
  const fallbacks = manifest.defaults?.fallbacks || {};
  const emit = manifest.interop?.emit || [];
  const std = policy.standard;
  const exp = policy.experimental || {};
  // Merged view for enforcement decisions (not for AIPREF emission)
  const merged = { ...exp, ...std };

  // AIPREF Content-Usage header — ONLY standardized categories.
  if (emit.includes("aipref-header")) {
    const parts = [];
    for (const cat of ["train-ai", "search"]) {
      const state = getState(std, cat);
      const lowered = lowerState(state, fallbacks);
      if (lowered === "allow") parts.push(`${cat}=y`);
      else if (lowered === "deny") parts.push(`${cat}=n`);
    }
    if (parts.length) headers["Content-Usage"] = parts.join(", ");
  }

  // X-Robots-Tag — uses standard search mechanisms, reads from both blocks.
  if (emit.includes("x-robots-tag")) {
    const tags = [];
    const searchState = lowerState(getState(merged, "search"), fallbacks);
    if (searchState === "deny") {
      tags.push("noindex, nofollow");
    } else {
      const aiInput = merged["ai-input"] || {};
      const maxChars = aiInput?.conditions?.max_excerpt_chars;
      if (typeof maxChars === "number") tags.push(`max-snippet:${maxChars}`);

      const trainState = lowerState(getState(merged, "train-ai"), fallbacks);
      const trainGenaiState = lowerState(getState(merged, "train-genai"), fallbacks);
      if (trainState === "deny" || trainGenaiState === "deny") {
        tags.push("googlebot: noai, noimageai");
      }
    }
    if (tags.length) headers["X-Robots-Tag"] = tags.join(", ");
  }

  // TDMRep Link header.
  if (emit.includes("tdmrep")) {
    const tdmUrl = manifest.endpoints?.tdm_policy;
    if (tdmUrl) headers["Link"] = `<${tdmUrl}>; rel="tdm-policy"`;
  }

  return headers;
}

// ── Enforcement decision ─────────────────────────────────────────────────────

function enforce(manifest, policy, bot) {
  if (!bot.matched) return { action: "pass", reason: "not-a-bot" };

  const fallbacks = manifest.defaults?.fallbacks || {};
  const cat = bot.primary_category;

  // Check both standard and experimental for the bot's category.
  // Standard takes precedence if present in both.
  const merged = { ...(policy.experimental || {}), ...(policy.standard || {}) };
  const state = getState(merged, cat);
  const catPolicy = merged[cat] || {};

  if (state === "deny") {
    return { action: "block", reason: `${cat}=deny`, status: 403 };
  }

  if (state === "charge") {
    const paymentUrl = manifest.endpoints?.payment;
    return {
      action: "charge",
      reason: `${cat}=charge`,
      status: 402,
      payment_url: paymentUrl || null,
    };
  }

  if (state === "conditional") {
    const conditions = catPolicy.conditions || {};

    // Check identity requirement.
    if (conditions.identity === "signed" && bot.trust_tier !== "signed") {
      const fb = fallbacks.unknown_identity || "deny";
      if (fb === "deny") {
        return { action: "block", reason: `${cat}=conditional, identity=signed required, got ${bot.trust_tier}`, status: 403 };
      }
    }
    if (conditions.identity === "verified" && bot.trust_tier === "user_agent_only") {
      const fb = fallbacks.unknown_identity || "deny";
      if (fb === "deny") {
        return { action: "block", reason: `${cat}=conditional, identity=verified required, got user_agent_only`, status: 403 };
      }
    }

    return { action: "allow-conditional", reason: `${cat}=conditional, conditions accepted` };
  }

  if (state === "allow") {
    return { action: "allow", reason: `${cat}=allow` };
  }

  // Unknown — use fallback.
  const fb = lowerState(state, fallbacks);
  if (fb === "deny") return { action: "block", reason: `${cat}=unknown, fallback=deny`, status: 403 };
  return { action: "allow", reason: `${cat}=unknown, fallback=allow` };
}

// ── Worker entry point ───────────────────────────────────────────────────────

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // Serve the manifest itself at the well-known path.
    if (url.pathname === "/.well-known/consent-manifest.json" || url.pathname === "/.well-known/consent.txt") {
      const manifest = await loadManifest(env);
      return new Response(JSON.stringify(manifest, null, 2), {
        headers: {
          "Content-Type": "application/json",
          "Cache-Control": "public, max-age=86400",
          "Access-Control-Allow-Origin": "*",
          "X-Consent-Manifest-Version": manifest.version || "0.1",
        },
      });
    }

    // Health check: returns manifest, compiled defaults, and bot registry.
    if (url.pathname === "/_consent/health") {
      const manifest = await loadManifest(env);
      const defaultPolicy = resolvePolicy(manifest, "/");
      const compiledHeaders = manifest ? compileHeaders(manifest, defaultPolicy) : {};
      return new Response(JSON.stringify({
        status: manifest ? "ok" : "no_manifest",
        version: manifest?.version || null,
        publisher: manifest?.publisher?.name || null,
        compiled_headers: compiledHeaders,
        emit_targets: manifest?.interop?.emit || [],
        dry_run: env.DRY_RUN === "true",
        bots_tracked: Object.values(BOT_SIGNATURES).flat().length,
      }, null, 2), {
        headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" },
      });
    }

    // Dry-run test: simulate enforcement for any path + user-agent.
    if (url.pathname === "/_consent/test") {
      const manifest = await loadManifest(env);
      if (!manifest) {
        return new Response(JSON.stringify({ error: "no manifest loaded" }), {
          status: 500, headers: { "Content-Type": "application/json" },
        });
      }
      const testPath = url.searchParams.get("path") || "/";
      const testUA = url.searchParams.get("ua") || request.headers.get("user-agent") || "";
      const fakeRequest = { headers: { get: (h) => h === "user-agent" ? testUA : null } };
      const bot = identifyBot(fakeRequest);
      const policy = resolvePolicy(manifest, testPath);
      const headers = compileHeaders(manifest, policy);
      const decision = enforce(manifest, policy, bot);
      return new Response(JSON.stringify({
        test_path: testPath,
        test_ua: testUA,
        bot: bot.matched ? { ua: bot.ua_token, org: bot.org, tier: bot.trust_tier, category: bot.primary_category } : null,
        policy: { standard: policy.standard, experimental: policy.experimental },
        compiled_headers: headers,
        decision: decision,
      }, null, 2), {
        headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" },
      });
    }

    // Load manifest.
    const manifest = await loadManifest(env);
    if (!manifest) {
      return await fetch(request);
    }

    // Identify bot.
    const bot = identifyBot(request);

    // Resolve policy for this path.
    const policy = resolvePolicy(manifest, url.pathname);

    // Compile headers to inject.
    const policyHeaders = compileHeaders(manifest, policy);

    // Enforcement decision.
    const decision = enforce(manifest, policy, bot);
    const dryRun = env.DRY_RUN === "true";

    // Log enforcement action.
    const logEntry = {
      ts: new Date().toISOString(),
      path: url.pathname,
      bot: bot.matched ? { ua: bot.ua_token, org: bot.org, tier: bot.trust_tier } : null,
      decision: decision.action,
      reason: decision.reason,
      dry_run: dryRun,
    };

    // If blocking or charging, return immediately (unless dry-run).
    if (decision.action === "block" && !dryRun) {
      console.log(JSON.stringify(logEntry));
      return new Response(
        JSON.stringify({ error: "access denied by consent manifest", reason: decision.reason }),
        {
          status: decision.status || 403,
          headers: { "Content-Type": "application/json", ...policyHeaders },
        }
      );
    }

    if (decision.action === "charge" && !dryRun) {
      console.log(JSON.stringify(logEntry));
      const body = {
        error: "payment required",
        reason: decision.reason,
      };
      if (decision.payment_url) body.payment_url = decision.payment_url;
      return new Response(JSON.stringify(body), {
        status: 402,
        headers: { "Content-Type": "application/json", ...policyHeaders },
      });
    }

    // For allowed requests (including non-bots), fetch origin and inject headers.
    const response = await fetch(request);
    const newResponse = new Response(response.body, response);

    for (const [key, value] of Object.entries(policyHeaders)) {
      newResponse.headers.set(key, value);
    }

    // Add enforcement log header for debugging.
    if (bot.matched) {
      const decisionStr = dryRun
        ? `dry-run: would-${decision.action}: ${decision.reason}`
        : `${decision.action}: ${decision.reason}`;
      newResponse.headers.set("X-Consent-Decision", decisionStr);
      console.log(JSON.stringify(logEntry));
    }

    return newResponse;
  },
};

// ── Manifest loading ─────────────────────────────────────────────────────────

async function loadManifest(env) {
  // Option 1: KV binding.
  if (env.CONSENT_MANIFEST_KV) {
    const raw = await env.CONSENT_MANIFEST_KV.get("manifest", "json");
    if (raw) return raw;
  }

  // Option 2: Inline environment variable (JSON string).
  if (env.CONSENT_MANIFEST) {
    try {
      return JSON.parse(env.CONSENT_MANIFEST);
    } catch (e) {
      console.error("Failed to parse CONSENT_MANIFEST env var:", e);
    }
  }

  // Option 3: Fetch from origin.
  if (env.MANIFEST_ORIGIN_URL) {
    try {
      const resp = await fetch(env.MANIFEST_ORIGIN_URL, {
        cf: { cacheTtl: 3600, cacheEverything: true },
      });
      if (resp.ok) return await resp.json();
    } catch (e) {
      console.error("Failed to fetch manifest from origin:", e);
    }
  }

  return null;
}
