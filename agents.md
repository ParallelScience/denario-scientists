# AGENTS.md — Denario Research Scientist

This file is loaded at every session startup. Use it for standing instructions, tool usage notes, and lessons learned.

## Tool Usage

### Denario MCP Tools
- Tools run long operations (minutes to hours). Always report full output to the user after each tool call.
- Use `denario_status` to check project state before deciding next steps.
- Use `denario_read_file` to read outputs — don't assume what they contain.

### Memory Search
- When a narrow memory search returns zero results, immediately retry with a broader query and lower `minScore` (e.g., 0.1) before concluding nothing was found.
- Embedding models can miss relevant results when the query wording doesn't closely match the stored text.

### Shell Execution
- You have full exec access (no approval needed).
- LaTeX is installed — you can compile `.tex` files directly with `pdflatex` or `latexmk`.
- Python is at `/opt/denario-venv/bin/python`.

## Lessons Learned

_Add notes here when you discover something important for future sessions._
