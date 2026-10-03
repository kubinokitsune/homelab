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
]

# A relative markdown link to a .md doc, optionally under docs/ and with an anchor.
_DOC_LINK = re.compile(r"\[([^\]]*)\]\((?:docs/)?([a-z0-9-]+)\.md(#[^)]*)?\)")


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
                .replace("](docs/)", f"]({REPO}/tree/main/docs)"))


def main(wiki_dir: str) -> None:
    out = Path(wiki_dir)
    if not (out / ".git").exists():
        raise SystemExit(f"{out} isn't a clone of the wiki repo")
    docs = ROOT / "docs"
    missing = [s for s, _ in PAGES if not (docs / f"{s}.md").exists()]
    unlisted = sorted({p.stem for p in docs.glob("*.md")} - {s for s, _ in PAGES})
    if missing or unlisted:
        raise SystemExit(f"PAGES out of date -- missing: {missing}, unlisted: {unlisted}")

    (out / "Home.md").write_text(rewrite((ROOT / "README.md").read_text(encoding="utf-8")), encoding="utf-8")
    for stem, _ in PAGES:
        src = (docs / f"{stem}.md").read_text(encoding="utf-8")
        (out / f"{page_name(stem)}.md").write_text(rewrite(src), encoding="utf-8")
    sidebar = ["### 🏠 Homelab wiki", "", "- [Home](Home)"]
    sidebar += [f"- [{title}]({page_name(stem)})" for stem, title in PAGES]
    (out / "_Sidebar.md").write_text("\n".join(sidebar) + "\n", encoding="utf-8")
    (out / "_Footer.md").write_text(
        f"Self-hosted multi-agent homelab · [main repo]({REPO}) · MIT\n", encoding="utf-8")
    print(f"built Home + {len(PAGES)} pages into {out}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
