import { useState, useCallback, useEffect } from "react";

// Mirrors compiler/compile.py v0.2 for a manifest without path rules. The agent lists follow compiler/agents.json.
// shortcut: path rules are not compiled here, port Plan from compile.py when the playground should show per-path output
const COMPILER_VERSION = "0.2";
const AGENTS_UPDATED = "2026-10-22";
const TRAINING_BOTS = ["GPTBot","ClaudeBot","CCBot","Google-Extended","Applebot-Extended","Meta-ExternalAgent","FacebookBot","Amazonbot","MistralAI-Training","AI2Bot","Ai2Bot-Dolma","cohere-training-data-crawler","cohere-ai","Bytespider","TikTokSpider","DeepSeekBot","Omgilibot","omgili","Webzio-Extended","SBIntuitionsBot"];
const AI_INPUT_BOTS = ["ChatGPT-User","Claude-User","Perplexity-User","MistralAI-User","DuckAssistBot","Meta-ExternalFetcher","Amzn-User","Google-Agent"];
const CATEGORIES = ["train-ai", "train-genai", "search", "ai-input"];

const DEFAULT_MANIFEST = `{
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
}`;

const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);

// {category: state} for every category the defaults declare: standard wins, and unknown declares nothing.
function rawStates(block) {
  const out = {};
  for (const tier of ["standard", "experimental"]) {
    const entries = isObj(block[tier]) ? Object.entries(block[tier]) : [];
    for (const [cat, val] of entries) {
      const state = isObj(val) && "state" in val ? val.state : "unknown";
      if (state !== "unknown" && !(cat in out)) out[cat] = state;
    }
  }
  return out;
}

// Lower a rich authoring state to "allow", "deny" or null (unknown).
function lower(state, fallbacks) {
  if (state === "allow" || state === "deny") return state;
  if (state === "unknown") return null;
  if (state === "charge" || state === "conditional") {
    const fb = "unexpressible_state" in fallbacks ? fallbacks.unexpressible_state : "deny";
    return fb === "unknown" ? null : fb;
  }
  throw new Error(`unknown policy state ${JSON.stringify(state)}`);
}

// "deny" if either training category denies, else "allow" if either allows, else null.
function trainingDecision(policy) {
  const states = [policy["train-ai"], policy["train-genai"]];
  return states.includes("deny") ? "deny" : states.includes("allow") ? "allow" : null;
}

const labels = (pairs, word) => pairs.filter(([, d]) => word[d]).map(([l, d]) => `${l}=${word[d]}`).join(", ");

// {files, issues, stats}: files holds each compiler output under its filename, "" when the compiler emits nothing.
function compile(manifest) {
  if (!isObj(manifest) || !manifest.version) throw new Error("Invalid manifest");
  const defaults = isObj(manifest.defaults) ? manifest.defaults : {};
  const fallbacks = isObj(defaults.fallbacks) ? defaults.fallbacks : { unexpressible_state: "deny", unknown_identity: "deny" };
  const raw = rawStates(defaults);
  const policy = Object.fromEntries(CATEGORIES.map(cat => [cat, lower(cat in raw ? raw[cat] : "unknown", fallbacks)]));
  const training = trainingDecision(policy);
  const pub = isObj(manifest.publisher) ? manifest.publisher : {};

  // AIPREF Content-Usage (RFC 9651 dictionary) and the Cloudflare Content-Signal line
  const usage = labels([["train-ai", training], ["search", policy.search]], { allow: "y", deny: "n" });
  const signal = labels([["search", policy.search], ["ai-input", policy["ai-input"]], ["ai-train", training]], { allow: "yes", deny: "no" });

  // robots.txt, with the Content-Signal and Content-Usage lines merged into the "*" group, as a site deploys them
  const r = ["# robots.txt", `# Generated from consent-manifest.json by consent.txt compiler v${COMPILER_VERSION}`, `# Agents table: ${AGENTS_UPDATED}`, `# Publisher: ${pub.name ?? "Unknown"}`, "", "User-Agent: *"];
  if (signal) r.push(`Content-Signal: ${signal}`);
  if (usage) r.push(`Content-Usage: ${usage}`);
  r.push("Allow: /", "");
  if (training === "deny" && policy["ai-input"] === "allow") r.push("# Note: Google-Extended also governs Gemini grounding, and Google has no separate ai-input token.");
  if (policy["ai-input"] === "deny" && training !== "deny") r.push("# Note: Gemini grounding stays open on /: ai-input is denied there but training is not, and Google-Extended controls both.");
  if (training === "deny") r.push(...TRAINING_BOTS.map(b => `User-Agent: ${b}`), "Disallow: /", "");
  if (policy["ai-input"] === "deny") r.push("# User-triggered fetchers: several operators say robots.txt may not apply to these.", ...AI_INPUT_BOTS.map(b => `User-Agent: ${b}`), "Disallow: /", "");
  if (pub.url) r.push(`Sitemap: ${String(pub.url).replace(/\/+$/, "")}/sitemap.xml`, "");

  // X-Robots-Tag
  const x = [];
  if (policy.search === "deny") x.push("X-Robots-Tag: noindex, nofollow");
  else {
    const aiInput = (isObj(defaults.standard) && defaults.standard["ai-input"]) || (isObj(defaults.experimental) && defaults.experimental["ai-input"]);
    const cond = isObj(aiInput) && isObj(aiInput.conditions) ? aiInput.conditions : {};
    if (Number.isInteger(cond.max_excerpt_chars)) x.push(`X-Robots-Tag: max-snippet:${cond.max_excerpt_chars}`);
    if (cond.verbatim_allowed === false) x.push("X-Robots-Tag: nosnippet");
    if (training === "deny") x.push("X-Robots-Tag: googlebot: noai, noimageai");
  }

  // TDMRep (W3C CG Final Report): charge and conditional mean "reserved, see the policy"
  const policyUrl = (isObj(manifest.endpoints) && manifest.endpoints.tdm_policy) || "";
  const reserved = ["train-ai", "train-genai"].some(c => raw[c] === "charge" || raw[c] === "conditional") ? 1 : { deny: 1, allow: 0 }[training];
  let tdmJson = "";
  let tdmHeaders = "# TDMRep: the training preference is unknown everywhere, so there is nothing to declare.\n";
  if (reserved !== undefined) {
    const entry = { location: "/", "tdm-reservation": reserved };
    const h = ["# TDMRep HTTP response headers (W3C TDMRep CG Final Report, section 6.2).", `tdm-reservation: ${reserved}`];
    const meta = [`<meta name="tdm-reservation" content="${reserved}">`];
    if (reserved === 1 && policyUrl) {
      entry["tdm-policy"] = policyUrl;
      h.push(`tdm-policy: ${policyUrl}`);
      meta.push(`<meta name="tdm-policy" content="${policyUrl}">`);
    }
    tdmJson = JSON.stringify([entry], null, 2) + "\n";
    tdmHeaders = [...h, "", "# HTML <head> equivalent (section 6.3):", ...meta].join("\n") + "\n";
  }

  const issues = [];
  if (!pub.name) issues.push("Missing publisher.name");
  if (!pub.contact) issues.push("Missing publisher.contact");
  if (!manifest.defaults) issues.push("Missing defaults block");
  if (CATEGORIES.some(c => raw[c] === "charge" || raw[c] === "conditional") && !defaults.fallbacks) issues.push("charge/conditional states without fallbacks defined");
  if (Array.isArray(manifest.rules) && manifest.rules.length) issues.push("Path rules are not compiled here: run compiler/compile.py for per-path output");

  return {
    files: {
      "robots.txt": r.join("\n"),
      "aipref-header.txt": usage ? `Content-Usage: ${usage}` : "",
      "x-robots-tag.txt": x.join("\n"),
      "google-extended.txt": training === "deny" ? "User-Agent: Google-Extended\nDisallow: /\n" : "",
      "tdmrep.json": tdmJson,
      "tdmrep-headers.txt": tdmHeaders,
    },
    issues,
    stats: {
      trainingBlocked: training === "deny" ? TRAINING_BOTS.length : 0,
      aiInputBlocked: policy["ai-input"] === "deny" ? AI_INPUT_BOTS.length : 0,
    },
  };
}

const TABS = [
  { id: "robots", label: "robots.txt", file: "robots.txt" },
  { id: "aipref", label: "AIPREF header", file: "aipref-header.txt" },
  { id: "xrobots", label: "X-Robots-Tag", file: "x-robots-tag.txt" },
  { id: "gext", label: "Google-Extended", file: "google-extended.txt" },
  { id: "tdm", label: "TDMRep", file: "tdmrep.json" },
];

function tabText(files, tab) {
  if (tab.id !== "tdm") return files[tab.file];
  const json = files["tdmrep.json"];
  return (json ? `# /.well-known/tdmrep.json\n${json}\n` : "") + files["tdmrep-headers.txt"];
}

const PRESETS = {
  minimal: DEFAULT_MANIFEST,
  "news-publisher": JSON.stringify({
    version: "0.1",
    publisher: { name: "Example News", url: "https://news.example.com", contact: "mailto:ai@news.example.com", jurisdictions: ["US","EU"] },
    defaults: {
      fallbacks: { unexpressible_state: "deny", unknown_identity: "deny" },
      standard: { "train-ai": { state: "deny" }, search: { state: "allow" } },
      experimental: { "train-genai": { state: "deny" }, "ai-input": { state: "conditional", conditions: { identity: "signed", citation_required: true, max_excerpt_chars: 160 } } }
    },
    endpoints: { payment: "https://news.example.com/.well-known/ai-payment", tdm_policy: "https://news.example.com/tdm/policy.json" },
    interop: { emit: ["robots-txt","aipref-header","aipref-robots","x-robots-tag","google-extended","tdmrep","content-signal"] }
  }, null, 2),
  "open-access": JSON.stringify({
    version: "0.1",
    publisher: { name: "Open Research Lab", contact: "mailto:data@openlab.edu" },
    defaults: {
      fallbacks: { unexpressible_state: "allow", unknown_identity: "allow" },
      standard: { "train-ai": { state: "allow" }, search: { state: "allow" } },
      experimental: { "train-genai": { state: "allow" }, "ai-input": { state: "allow" }, embedding: { state: "allow" } }
    }
  }, null, 2),
  lockdown: JSON.stringify({
    version: "0.1",
    publisher: { name: "Fortress Corp", contact: "mailto:legal@fortress.io" },
    defaults: {
      fallbacks: { unexpressible_state: "deny", unknown_identity: "deny" },
      standard: { "train-ai": { state: "deny" }, search: { state: "deny" } },
      experimental: { "train-genai": { state: "deny" }, "ai-input": { state: "deny" }, "agentic-access": { state: "deny" }, transform: { state: "deny" }, "generate-media": { state: "deny" }, embedding: { state: "deny" } }
    }
  }, null, 2),
};

export default function Playground() {
  const [input, setInput] = useState(DEFAULT_MANIFEST);
  const [activeTab, setActiveTab] = useState("robots");
  const [result, setResult] = useState(null);
  const [parseError, setParseError] = useState(null);

  const recompile = useCallback((text) => {
    try {
      setResult(compile(JSON.parse(text)));
      setParseError(null);
    } catch (e) {
      setParseError(e.message);
      setResult(null);
    }
  }, []);

  useEffect(() => { recompile(input); }, []);

  const handleInput = (val) => {
    setInput(val);
    recompile(val);
  };

  const activeOutput = result ? tabText(result.files, TABS.find(t => t.id === activeTab)) || "# Nothing to emit for this manifest" : "";
  const lineCount = activeOutput ? activeOutput.split("\n").length : 0;
  const aipref = result ? result.files["aipref-header.txt"] : "";

  return (
    <div style={{ fontFamily: "'IBM Plex Mono', 'Fira Code', 'SF Mono', monospace", fontSize: 13 }}>
      <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet" />

      <div style={{ display: "flex", gap: 6, marginBottom: 12, flexWrap: "wrap" }}>
        {Object.keys(PRESETS).map(p => (
          <button key={p} onClick={() => handleInput(PRESETS[p])} style={{ fontSize: 11, padding: "4px 10px", background: "var(--color-background-secondary)", border: "0.5px solid var(--color-border-tertiary)", borderRadius: 4, color: "var(--color-text-secondary)", cursor: "pointer" }}>
            {p}
          </button>
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, minHeight: 380 }}>
        {/* Input */}
        <div style={{ display: "flex", flexDirection: "column" }}>
          <div style={{ fontSize: 11, fontWeight: 500, color: "var(--color-text-tertiary)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 6, display: "flex", justifyContent: "space-between" }}>
            <span>Manifest</span>
            {parseError && <span style={{ color: "var(--color-text-danger)", textTransform: "none", letterSpacing: 0 }}>{parseError.slice(0, 50)}</span>}
          </div>
          <textarea
            value={input}
            onChange={e => handleInput(e.target.value)}
            spellCheck={false}
            style={{
              flex: 1, resize: "none", fontFamily: "inherit", fontSize: 12, lineHeight: 1.6,
              padding: 12, background: "var(--color-background-secondary)", color: "var(--color-text-primary)",
              border: parseError ? "1px solid var(--color-border-danger)" : "0.5px solid var(--color-border-tertiary)",
              borderRadius: "var(--border-radius-md)", outline: "none", tabSize: 2, minHeight: 340,
            }}
          />
        </div>

        {/* Output */}
        <div style={{ display: "flex", flexDirection: "column" }}>
          <div style={{ display: "flex", gap: 1, marginBottom: 6, flexWrap: "wrap" }}>
            {TABS.map(t => (
              <button key={t.id} onClick={() => setActiveTab(t.id)} style={{
                fontSize: 11, fontWeight: activeTab === t.id ? 500 : 400, padding: "4px 8px",
                background: activeTab === t.id ? "var(--color-background-primary)" : "transparent",
                border: activeTab === t.id ? "0.5px solid var(--color-border-tertiary)" : "0.5px solid transparent",
                borderRadius: "4px 4px 0 0", cursor: "pointer",
                color: activeTab === t.id ? "var(--color-text-primary)" : "var(--color-text-tertiary)",
              }}>{t.label}</button>
            ))}
          </div>
          <pre style={{
            flex: 1, margin: 0, padding: 12, fontSize: 12, lineHeight: 1.6, overflow: "auto",
            background: "var(--color-background-secondary)", border: "0.5px solid var(--color-border-tertiary)",
            borderRadius: "var(--border-radius-md)", color: "var(--color-text-primary)", whiteSpace: "pre-wrap",
            minHeight: 340,
          }}>
            {result ? activeOutput : "// Waiting for valid manifest..."}
          </pre>
        </div>
      </div>

      {/* Stats bar */}
      {result && (
        <div style={{ display: "flex", gap: 16, marginTop: 12, padding: "8px 12px", background: "var(--color-background-secondary)", borderRadius: "var(--border-radius-md)", fontSize: 12, color: "var(--color-text-secondary)", flexWrap: "wrap", alignItems: "center" }}>
          <span>Training bots blocked: <span style={{ fontWeight: 500, color: result.stats.trainingBlocked > 0 ? "var(--color-text-danger)" : "var(--color-text-success)" }}>{result.stats.trainingBlocked}/{TRAINING_BOTS.length}</span></span>
          <span>AI-input bots blocked: <span style={{ fontWeight: 500, color: result.stats.aiInputBlocked > 0 ? "var(--color-text-danger)" : "var(--color-text-success)" }}>{result.stats.aiInputBlocked}/{AI_INPUT_BOTS.length}</span></span>
          <span>AIPREF header: <span style={{ fontWeight: 500 }}>{aipref ? aipref.replace("Content-Usage: ", "") : "none"}</span></span>
          <span>Output lines: <span style={{ fontWeight: 500 }}>{lineCount}</span></span>
          {result.issues.length > 0 && (
            <span style={{ color: "var(--color-text-warning)" }}>
              {result.issues.length} warning{result.issues.length > 1 ? "s" : ""}: {result.issues[0]}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
