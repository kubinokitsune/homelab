"""Build the GitHub wiki from README.md + docs/.

The wiki is a generated copy -- edit the docs, then rebuild. Each docs/<name>.md
becomes a wiki page, README.md becomes Home, and relative links are rewritten
for wiki page names ("[printer.md](printer.md#x)" -> "[Printer](Printer#x)").

Usage:
    git clone https://github.com/kubinokitsune/homelab.wiki.git ../homelab.wiki
    python scripts/build-wiki.py ../homelab.wiki
    cd ../homelab.wiki && git add -A && git commit -m "Rebuild from docs" && git push
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = "https://github.com/kubinokitsune/homelab"
SMALL_WORDS = {"and", "of", "the"}

# Sidebar order and titles.
PAGES = [
    ("architecture", "Architecture"),
    ("agents", "The agents"),
    ("skills-library", "Skills library"),
    ("data-and-memory", "Data & memory"),
    ("printer", "The printer"),
    ("operations", "Operations"),
    ("hub", "Homelab Hub (web UI)"),
    ("history", "Development history"),
]
# Images live in docs/images/ of the main repo; the wiki is a separate repo, so
# relative image paths are pointed at the main repo's raw files.
RAW_IMAGES = "https://raw.githubusercontent.com/kubinokitsune/homelab/main/docs/images/"

# A relative markdown link to a .md doc, optionally under docs/ and with an anchor.
_DOC_LINK = re.compile(r"\[([^\]]*)\]\((?:docs/)?([a-z0-9-]+)\.md(#[^)]*)?\)")


# --- Redaction guard ---------------------------------------------------------
# The wiki is public, so the build FAILS instead of publishing internal details.
# Only generic patterns live in this file: a public script must not itself
# contain the strings it forbids. Anything naming a specific private repo, host
# or device goes in scripts/private-denylist.txt (one regex per line, '#'
# comments) -- that file is git-ignored and never published.
GUARD = [
    ("IPv4 address",          re.compile(r"\b(?!203\.0\.113\.)(?:\d{1,3}\.){3}\d{1,3}\b")),
    ("masked IP (100.x)",     re.compile(r"\b\d{1,3}\.x(?:\.x)*\b")),
    ("loopback / localhost",  re.compile(r"127\.0\.0\.1|\blocalhost\b")),
    ("port number",           re.compile(r"(?<!\d):\d{4,5}\b|(?<![\d:]):(?:22|53|80|85|111|443)\b")),
    ("container / VM id",     re.compile(r"\b(?:LXC|CT|VM|container)\s*#?\d{2,4}\b|\b(?:pct|qm)\s+[a-z]+")),
    ("private repo name",     re.compile(r"[a-z]+-ai-agent\b|\bhomelab-(?!agent-skills\b)[a-z]+\b|\bai_agent_skills_\w+")),
    ("tailnet hostname",      re.compile(r"\btail[0-9a-f]{6,}\b|(?<!<tailnet>)\.ts\.net\b")),
    ("service / unit name",   re.compile(r"\bagent-(?:forge|mason|hermes|warden|axiom|codex|chiron|kairos|iris|scout|apex|eos)\b|\.service\b|\bsystemctl\b|\bjournalctl\b")),
    ("deploy script / tool",  re.compile(r"\bdeploy-[\w-]+\.sh\b|\bpost_wiki\b|\bscp\b")),
    ("filesystem path",       re.compile(r"(?<![\w<])/(?:root|opt|etc|home|var|usr|tmp|dev/tty)\b|~/|\bOneDrive\b|\b[A-Za-z]:\\")),
    ("env var / secret",      re.compile(r"\.env\b|\b[A-Z][A-Z0-9]+_(?:TOKEN|KEY|SECRET|IPS|PASSWORD)\b|\bgh[pousr]_\w+|\bxox[bpa]-|BEGIN [A-Z ]*PRIVATE KEY")),
    ("discord id / webhook",  re.compile(r"\b\d{17,20}\b|discord(?:app)?\.com/api/webhooks")),
    ("hardware vendor/model", re.compile(r"\b(?:Dell|HP|Lenovo|Micron)\b|\bi[3579]-\d{4,5}[A-Z]{0,2}\b")),
    ("security posture",      re.compile(r"(?i)PermitRootLogin|PasswordAuthentication|\brpcbind\b|\bknown-weak\b|root password")),
]
DENYLIST = ROOT / "scripts" / "private-denylist.txt"


def _denylist() -> list[tuple[str, re.Pattern]]:
    if not DENYLIST.exists():
        print(f"WARNING: {DENYLIST.name} not found -- specific private names are NOT being checked")
        return []
    lines = [l.strip() for l in DENYLIST.read_text(encoding="utf-8").splitlines()]
    return [("private denylist", re.compile(l, re.I)) for l in lines if l and not l.startswith("#")]


def scan(name: str, text: str, rules) -> list[str]:
    hits = []
    for n, line in enumerate(text.splitlines(), 1):
        for label, rx in rules:
            if rx.search(line):
                hits.append(f"{name}:{n}: {label}")
    return hits


def check_images(images_dir: Path) -> list[str]:
    """Every image must match a hash a human approved after looking at it."""
    manifest = images_dir / "approved.sha256"      # made with: sha256sum *.png > approved.sha256
    if not manifest.exists():
        return [f"{manifest.name}: missing -- review the images, then create it"]
    approved = {}
    for line in manifest.read_text().splitlines():
        if line.strip():
            digest, fname = line.split(None, 1)
            approved[fname.strip().lstrip("*")] = digest
    return [f"{p.name}: new or changed image has not been approved"
            for p in sorted(images_dir.glob("*.png"))
            if approved.get(p.name) != hashlib.sha256(p.read_bytes()).hexdigest()]


def page_name(stem: str) -> str:
    return "-".join(p if p in SMALL_WORDS else p.capitalize() for p in stem.split("-"))


def rewrite(text: str) -> str:
    def sub(m: re.Match) -> str:
        label, stem, anchor = m.group(1), m.group(2), m.group(3) or ""
        if re.fullmatch(r"(docs/)?[a-z0-9-]+\.md", label):   # "[printer.md](...)"
            label = page_name(stem)
        return f"[{label}]({page_name(stem)}{anchor})"
    text = _DOC_LINK.sub(sub, text)
    # Links that only make sense inside the repo point back at it.
    return (text.replace("](LICENSE)", f"]({REPO}/blob/main/LICENSE)")
                .replace("](docs/)", f"]({REPO}/tree/main/docs)")
                .replace("](docs/images/", f"]({RAW_IMAGES}")
                .replace("](images/", f"]({RAW_IMAGES}"))


def main(wiki_dir: str) -> None:
    out = Path(wiki_dir)
    if not (out / ".git").exists():
        raise SystemExit(f"{out} isn't a clone of the wiki repo")
    docs = ROOT / "docs"
    missing = [s for s, _ in PAGES if not (docs / f"{s}.md").exists()]
    unlisted = sorted({p.stem for p in docs.glob("*.md")} - {s for s, _ in PAGES})
    if missing or unlisted:
        raise SystemExit(f"PAGES out of date -- missing: {missing}, unlisted: {unlisted}")

    # Build every page in memory first, scan it, and only then write anything.
    sidebar = ["### 🏠 Homelab wiki", "", "- [Home](Home)"]
    sidebar += [f"- [{title}]({page_name(stem)})" for stem, title in PAGES]
    pages = {"Home.md": rewrite((ROOT / "README.md").read_text(encoding="utf-8"))}
    for stem, _ in PAGES:
        pages[f"{page_name(stem)}.md"] = rewrite((docs / f"{stem}.md").read_text(encoding="utf-8"))
    pages["_Sidebar.md"] = "\n".join(sidebar) + "\n"
    pages["_Footer.md"] = f"Self-hosted multi-agent homelab · [main repo]({REPO}) · MIT\n"

    rules = GUARD + _denylist()
    problems = [h for name, text in pages.items() for h in scan(name, text, rules)]
    problems += check_images(docs / "images")
    if problems:
        raise SystemExit("redaction guard failed -- nothing was written:\n  " + "\n  ".join(problems))
    for name, text in pages.items():
        (out / name).write_text(text, encoding="utf-8")
    print(f"built Home + {len(PAGES)} pages into {out}")
    images = sorted(p.name for p in (docs / "images").glob("*.png")) if (docs / "images").exists() else []
    if images:
        print(f"images are served from the main repo ({len(images)}): push it before checking the wiki")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
