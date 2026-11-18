"""Fail on a broken relative link in the repo's Markdown.

Developer docs (docs/) are plain Markdown linked by relative path, and no
site build checks them, so this does: every relative link must name a file
that exists, and a #fragment must match a heading in it (GitHub's anchors).
    uv run --no-project python dev/check-doc-links.py   (run by `just docs-check`)
"""

import re
import subprocess
import sys
from pathlib import Path

LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)\)")
HEADING = re.compile(r"^#{1,6}\s+(.*)$", re.M)
FENCE = re.compile(r"^```.*?^```", re.M | re.S)


def anchors(md: Path) -> set[str]:
    text = FENCE.sub("", md.read_text())
    out = set()
    for h in HEADING.findall(text):
        slug = re.sub(r"[^\w\- ]", "", h.strip().lower().replace("`", "")).replace(" ", "-")
        out.add(slug)
    return out


def main() -> int:
    files = subprocess.run(["git", "ls-files", "*.md"], capture_output=True, text=True, check=True).stdout.split()
    errors = []
    for name in files:
        md = Path(name)
        if name.startswith(("site/", "experiments/")):
            continue  # the site checks its own links; experiments are records
        for target in LINK.findall(FENCE.sub("", md.read_text())):
            if re.match(r"^[a-z]+:", target) or target.startswith("#") and not target[1:]:
                continue  # http:, mailto:, …
            path, _, frag = target.partition("#")
            dest = (md.parent / path).resolve() if path else md.resolve()
            if not dest.exists():
                errors.append(f"{md}: {target}: no such file")
            elif frag and dest.suffix == ".md" and frag not in anchors(dest):
                errors.append(f"{md}: {target}: no heading #{frag}")
    for e in errors:
        print(e, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
