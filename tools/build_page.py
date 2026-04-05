#!/usr/bin/env python3
"""Build GitHub Pages site for a Denario research project.

Reads paper.tex from the project root to extract title and abstract,
copies assets into docs/, and generates index.html from the template.

Usage:
    python build_page.py <project_dir> --repo-url <url> [--author <name>]

Expects in <project_dir>:
    paper.tex, paper.pdf, presentation.mp3 (optional)
"""

import argparse
import os
import re
import shutil
import sys
from datetime import datetime


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
    date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Create docs/ and copy assets
    os.makedirs(docs_dir, exist_ok=True)

    if os.path.exists(paper_pdf_path):
        shutil.copy2(paper_pdf_path, docs_dir)
    shutil.copy2(paper_tex_path, docs_dir)
    if os.path.exists(presentation_path):
        shutil.copy2(presentation_path, docs_dir)

    # Read template and replace placeholders
    with open(template_path) as f:
        html = f.read()

    html = html.replace("{{TITLE}}", title)
    html = html.replace("{{AUTHOR}}", author)
    html = html.replace("{{DATE}}", date)
    html = html.replace("{{GITHUB_URL}}", repo_url)
    html = html.replace("{{ABSTRACT}}", abstract)
    html = html.replace("{{FIGURES}}", "")  # no figures on the page

    # Write index.html
    index_path = os.path.join(docs_dir, "index.html")
    with open(index_path, "w") as f:
        f.write(html)

    print(f"Built GitHub Pages site in {docs_dir}")
    print(f"  Title: {title}")
    print(f"  Author: {author}")
    print(f"  Files: {os.listdir(docs_dir)}")


def main():
    parser = argparse.ArgumentParser(description="Build GitHub Pages site for a Denario project")
    parser.add_argument("project_dir", help="Path to the project directory")
    parser.add_argument("--repo-url", required=True, help="GitHub repo URL")
    parser.add_argument("--author", default=os.environ.get("SCIENTIST_NAME", "denario"), help="Author name (default: $SCIENTIST_NAME)")
    args = parser.parse_args()
    build(args.project_dir, args.repo_url, args.author)


if __name__ == "__main__":
    main()
