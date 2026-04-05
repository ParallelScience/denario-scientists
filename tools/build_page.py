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
