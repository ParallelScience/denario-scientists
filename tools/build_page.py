#!/usr/bin/env python3
"""Build GitHub Pages site for a Denario research project.

Reads paper.tex and classification.json from the project,
copies assets into docs/, and generates index.html from the template.

Usage:
    python build_page.py <project_dir> --repo-url <url> [--author <name>]
    python build_page.py <project_dir> --validate  # check page has all required fields

Expects in <project_dir>:
    paper.tex, paper.pdf, presentation.mp3 (optional)
    Iteration<N>/input_files/classification.json (optional)
"""

import argparse
import glob
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone, timedelta


def extract_title(tex: str) -> str:
    m = re.search(r"\\title\{(.+?)\}", tex, re.DOTALL)
    return m.group(1).strip() if m else "Untitled"


def extract_abstract(tex: str) -> str:
    m = re.search(r"\\begin\{abstract\}(.+?)\\end\{abstract\}", tex, re.DOTALL)
    if not m:
        return ""
    abstract = m.group(1).strip()
    # Clean LaTeX artifacts
    abstract = abstract.replace("\\%", "%")
    abstract = re.sub(r"~", " ", abstract)
    abstract = re.sub(r"\\[a-zA-Z]+\{([^}]*)\}", r"\1", abstract)  # \textbf{x} -> x
    abstract = re.sub(r"[{}]", "", abstract)
    abstract = re.sub(r"\$[^$]+\$", "", abstract)  # remove inline math
    return abstract


def _cited_keys_from_aux(aux_path: str) -> set[str]:
    """Extract keys actually cited in the compiled paper from its .aux file."""
    if not os.path.exists(aux_path):
        return set()
    with open(aux_path, encoding="utf-8", errors="replace") as f:
        aux = f.read()
    keys: set[str] = set()
    # bibtex writes \citation{key1,key2,...} for each \cite{...} in the source
    for match in re.finditer(r"\\citation\{([^}]+)\}", aux):
        for key in match.group(1).split(","):
            key = key.strip()
            if key and key != "*":
                keys.add(key)
    return keys


def _split_bib_entries(bib_text: str) -> list[tuple[str, str, str]]:
    """Split a .bib file into (entry_type, citation_key, raw_block) tuples.

    Walks the file tracking brace depth to reliably capture each @type{…} block
    (nested braces in titles etc. break naive regexes).
    """
    entries: list[tuple[str, str, str]] = []
    i, n = 0, len(bib_text)
    while i < n:
        at = bib_text.find("@", i)
        if at < 0:
            break
        open_brace = bib_text.find("{", at)
        if open_brace < 0:
            break
        entry_type = bib_text[at + 1 : open_brace].strip().lower()
        # Find the matching closing brace for this entry
        depth = 1
        j = open_brace + 1
        while j < n and depth > 0:
            c = bib_text[j]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            j += 1
        if depth != 0:
            break  # unbalanced — give up
        block = bib_text[at:j]
        # For @string/@preamble/@comment, key is empty — we keep the whole block as-is
        if entry_type in ("string", "preamble", "comment"):
            entries.append((entry_type, "", block))
        else:
            body = bib_text[open_brace + 1 : j - 1]
            comma = body.find(",")
            key = body[:comma].strip() if comma >= 0 else body.strip()
            entries.append((entry_type, key, block))
        i = j
    return entries


def prune_bibliography(aux_path: str, src_bib: str, dst_bib: str) -> tuple[int, int]:
    """Copy only the .bib entries actually cited in the compiled paper.

    Returns (kept, total). If the .aux file is missing or has no \\citation
    markers (e.g. the paper wasn't compiled yet, or cites nothing), falls back
    to copying the full bib so nothing is silently dropped.
    """
    with open(src_bib, encoding="utf-8", errors="replace") as f:
        bib_text = f.read()
    entries = _split_bib_entries(bib_text)
    total = sum(1 for e in entries if e[0] not in ("string", "preamble", "comment"))

    cited = _cited_keys_from_aux(aux_path)
    if not cited:
        # Safe fallback: keep everything rather than publish an empty bib
        shutil.copy2(src_bib, dst_bib)
        return (total, total)

    kept_blocks: list[str] = []
    kept = 0
    for entry_type, key, block in entries:
        if entry_type in ("string", "preamble", "comment"):
            kept_blocks.append(block)
        elif key in cited:
            kept_blocks.append(block)
            kept += 1

    with open(dst_bib, "w", encoding="utf-8") as f:
        f.write("\n\n".join(kept_blocks) + "\n")
    return (kept, total)


def find_classification(project_dir: str) -> str:
    """Find and read the primary category from classification.json."""
    # Search all iterations for classification.json, take the latest
    pattern = os.path.join(project_dir, "Iteration*", "input_files", "classification.json")
    files = sorted(glob.glob(pattern))
    if not files:
        return ""
    with open(files[-1]) as f:
        data = json.load(f)
    primary = data.get("primary_category", "")
    secondary = data.get("secondary_categories", [])
    parts = [primary] + secondary
    return "; ".join(parts) if parts else ""


def build(project_dir: str, repo_url: str, author: str):
    template_path = os.path.join(os.path.dirname(__file__), "page_template.html")
    paper_tex_path = os.path.join(project_dir, "paper.tex")
    paper_pdf_path = os.path.join(project_dir, "paper.pdf")
    presentation_path = os.path.join(project_dir, "presentation.mp3")
    docs_dir = os.path.join(project_dir, "docs")

    if not os.path.exists(paper_tex_path):
        print(f"Error: paper.tex not found in {project_dir}", file=sys.stderr)
        sys.exit(1)

    if not os.path.exists(template_path):
        print(f"Error: page_template.html not found at {template_path}", file=sys.stderr)
        sys.exit(1)

    # Read and parse paper.tex
    with open(paper_tex_path) as f:
        tex = f.read()

    title = extract_title(tex)
    abstract = extract_abstract(tex)
    primary_category = find_classification(project_dir)

    # AOE = UTC-12
    aoe = timezone(timedelta(hours=-12))
    now = datetime.now(aoe)
    date = now.strftime("%Y-%m-%d")
    time = now.strftime("%H:%M:%S") + " AOE"

    # Create docs/ and copy assets
    os.makedirs(docs_dir, exist_ok=True)

    if os.path.exists(paper_pdf_path):
        shutil.copy2(paper_pdf_path, docs_dir)
    if os.path.exists(presentation_path):
        shutil.copy2(presentation_path, docs_dir)

    # Copy bibliography for citation tracking, pruned to entries actually
    # cited in the compiled paper (so arxiv-browse doesn't ingest unused refs).
    bib_path = os.path.join(project_dir, "bibliography.bib")
    aux_path = os.path.join(project_dir, "paper.aux")
    if os.path.exists(bib_path):
        dst_bib = os.path.join(docs_dir, "bibliography.bib")
        kept, total = prune_bibliography(aux_path, bib_path, dst_bib)
        print(f"  Bibliography: kept {kept}/{total} entries actually cited")

    # Read template and replace placeholders
    with open(template_path) as f:
        html = f.read()

    html = html.replace("{{TITLE}}", title)
    html = html.replace("{{AUTHOR}}", author)
    html = html.replace("{{DATE}}", date)
    html = html.replace("{{TIME}}", time)
    html = html.replace("{{PRIMARY_CATEGORY}}", primary_category)
    html = html.replace("{{GITHUB_URL}}", repo_url)
    html = html.replace("{{ABSTRACT}}", abstract)

    # Write index.html
    index_path = os.path.join(docs_dir, "index.html")
    with open(index_path, "w") as f:
        f.write(html)

    print(f"Built GitHub Pages site in {docs_dir}")
    print(f"  Title: {title}")
    print(f"  Author: {author}")
    print(f"  Category: {primary_category}")
    print(f"  Files: {os.listdir(docs_dir)}")

    # Validate
    errors = validate_page(docs_dir)
    if errors:
        print(f"\n  WARNINGS:")
        for e in errors:
            print(f"    - {e}")


REQUIRED_FIELDS = {
    "{{TITLE}}": "title",
    "{{AUTHOR}}": "author",
    "{{DATE}}": "date",
    "{{TIME}}": "time",
    "{{ABSTRACT}}": "abstract",
    "{{PRIMARY_CATEGORY}}": "classification",
    "{{GITHUB_URL}}": "GitHub URL",
}


def validate_page(docs_dir: str) -> list[str]:
    """Check that the generated page has all required fields populated."""
    errors = []
    index_path = os.path.join(docs_dir, "index.html")

    if not os.path.exists(index_path):
        return ["index.html not found"]

    with open(index_path) as f:
        html = f.read()

    # Check no unreplaced placeholders remain
    for placeholder, name in REQUIRED_FIELDS.items():
        if placeholder in html:
            errors.append(f"{name} not set (placeholder {placeholder} still in HTML)")

    # Check required assets
    if not os.path.exists(os.path.join(docs_dir, "paper.pdf")):
        errors.append("paper.pdf missing from docs/")

    # Check content is not empty
    for field, label in [("Author: </span>", "author is empty"),
                         ("<p></p>", "abstract is empty"),
                         ("Subject: </span>", "classification is empty")]:
        if field in html:
            errors.append(label)

    return errors


def main():
    parser = argparse.ArgumentParser(description="Build GitHub Pages site for a Denario project")
    parser.add_argument("project_dir", help="Path to the project directory")
    parser.add_argument("--repo-url", required=True, help="GitHub repo URL")
    parser.add_argument("--author", default=os.environ.get("SCIENTIST_NAME", "denario"),
                        help="Author name (default: $SCIENTIST_NAME)")
    parser.add_argument("--validate", action="store_true",
                        help="Only validate an existing docs/ page, don't build")
    args = parser.parse_args()

    if args.validate:
        docs_dir = os.path.join(args.project_dir, "docs")
        errors = validate_page(docs_dir)
        if errors:
            print("Validation FAILED:")
            for e in errors:
                print(f"  - {e}")
            sys.exit(1)
        else:
            print("Validation OK")
            sys.exit(0)

    build(args.project_dir, args.repo_url, args.author)


if __name__ == "__main__":
    main()
