"""Each sites/<host>/ kit must rebuild to exactly what is committed."""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITES = sorted(p.parent for p in (ROOT / "sites").glob("*/site.py"))
OUTPUTS = ("public/robots.txt", "public/.well-known/consent-manifest.json",
           "public/.well-known/tdmrep.json", "headers.txt", "lovable-prompt.md")


class SiteKits(unittest.TestCase):
    def test_committed_output_is_current(self):
        self.assertTrue(SITES, "no sites/*/site.py found")
        for site in SITES:
            with self.subTest(site=site.name), tempfile.TemporaryDirectory() as tmp:
                work = Path(tmp) / site.name
                shutil.copytree(site, work)
                subprocess.run([sys.executable, "-I", str(work / "site.py"), "build", "--repo", str(ROOT)],
                               check=True, stdout=subprocess.DEVNULL)
                for rel in OUTPUTS:
                    self.assertEqual((work / rel).read_text(), (site / rel).read_text(), f"{site.name}/{rel} is stale")
