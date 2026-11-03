"""The playground must compile its presets exactly as compiler/compile.py does.

playground/index.jsx is run under Node without React: the file up to the component is
evaluated and compile() is called on every preset. Skipped when node is not installed.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLAYGROUND = os.path.join(ROOT, "playground", "index.jsx")
NODE = shutil.which("node")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


compile_mod = _load("consent_compile", os.path.join(ROOT, "compiler", "compile.py"))


def playground():
    """The playground's agent lists and, per preset, its manifest and compile() result."""
    with open(PLAYGROUND, encoding="utf-8") as f:
        src = f.read()
    logic = src[src.index("const COMPILER_VERSION"):src.index("export default function")]
    script = logic + """
const presets = Object.fromEntries(Object.entries(PRESETS).map(([k, v]) => [k, { manifest: JSON.parse(v), ...compile(JSON.parse(v)) }]));
console.log(JSON.stringify({ presets, train: TRAINING_BOTS, aiInput: AI_INPUT_BOTS }));
"""
    return json.loads(subprocess.run([NODE, "-e", script], check=True, capture_output=True, text=True).stdout)


def expected(manifest):
    """The compiler's files, with the Content-Signal and Content-Usage lines merged into the
    'User-Agent: *' group, as a site deploys them."""
    files = compile_mod.compile_all(manifest, [t for t in compile_mod.COMPILERS if t != "summary"])
    star = "User-Agent: *\n"
    merged = [l for l in files.get("content-signal.txt", "").splitlines() if l.startswith("Content-Signal:")][:1]
    merged += [l for l in files.get("aipref-robots.txt", "").splitlines() if l.startswith("Content-Usage:")]
    files["robots.txt"] = files["robots.txt"].replace(star, star + "".join(l + "\n" for l in merged))
    return files


@unittest.skipUnless(NODE, "node is not installed")
class PlaygroundTest(unittest.TestCase):
    def test_presets_match_compiler(self):
        got = playground()
        self.assertEqual(got["train"], [a["token"] for a in compile_mod.AGENTS["train"]])
        self.assertEqual(got["aiInput"], [a["token"] for a in compile_mod.AGENTS["ai-input"]])
        for preset, result in got["presets"].items():
            want = expected(result["manifest"])
            for name, text in result["files"].items():
                with self.subTest(preset=preset, file=name):
                    self.assertEqual(text, want.get(name, ""))


if __name__ == "__main__":
    unittest.main()
