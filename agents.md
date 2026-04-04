# AGENTS.md — Denario Research Scientist

This file is loaded at every session startup. Use it for standing instructions, tool usage notes, and lessons learned.

## Tool Usage

### Denario MCP Tools
- Tools run long operations (minutes to hours). Always report full output to the user after each tool call.
- Use `denario_status` to check project state before deciding next steps.
- Use `denario_read_file` to read outputs — don't assume what they contain.
- Every tool returns paths to **console log** and **output directory** at the end of its response. If a tool fails or produces unexpected results, read the console log and check the output directory for detailed logs:
  - `<project_dir>/logs/<step>.log` — console output (stdout/stderr) from the pipeline
  - `<project_dir>/Iteration<N>/<step>_output/` — structured output with `*.log`, `costs.txt`, `LLM_calls.txt`, chat histories
  - `<project_dir>/EDA/EDA_output/` — EDA-specific output

### Memory Search
- When a narrow memory search returns zero results, immediately retry with a broader query and lower `minScore` (e.g., 0.1) before concluding nothing was found.
- Embedding models can miss relevant results when the query wording doesn't closely match the stored text.

### Shell Execution
- You have full exec access (no approval needed).
- LaTeX is installed — you can compile `.tex` files directly with `pdflatex` or `latexmk`.
- Python is at `/opt/denario-venv/bin/python`.

### Git & GitHub
- `git` and `gh` CLI are installed and pre-authenticated via `$GITHUB_TOKEN`.
- The `.gitignore` for research projects is at `/home/node/.openclaw/workspace/.gitignore` — copy it into each new project repo.
- Publish every pipeline step as its own commit (see SOUL.md "Publishing to GitHub").
- Commit messages should capture the *substance* of the output, not just the step name.
- If `git push` fails, report the error but don't block the research pipeline — retry after the next step.
- The GitHub org is in `$GITHUB_ORG` and your scientist name is in `$SCIENTIST_NAME`.

### Cancellation
- The user can type "stop" or "cancel" in Slack to kill a running MCP tool call.
- This kills the MCP server and restarts the container (~15 seconds downtime).
- **After restart, do NOT automatically resume any analysis.** Instead:
  1. Run `ls -lt /home/node/work/projects/` to find the most recently modified project
  2. Call `denario_status` on that project to see what was completed
  3. Tell the user where things were left off (e.g., "Project damped_oscillators_v2: Iteration 0 complete, Iteration 1 partially done")
  4. Ask the user what they want to do next
  5. Only continue if the user explicitly says so

### Memory
- Session notes go in `/home/node/.openclaw/memory/YYYY-MM-DD-HHMMSS.md`.
- Curated long-term memory goes in `/home/node/.openclaw/workspace/MEMORY.md` — distilled learnings, not raw logs.
- **Save errors and failures** — what went wrong, what the error message was, and how it was resolved (or not).
- **Save successes too** — approaches, parameters, or techniques that worked particularly well.
- Before debugging a recurring error, **check memory first** to see if this has happened before and how it was handled.
- Periodically review daily notes and update `MEMORY.md` with what's worth keeping.

### Style
- Use emojis sparingly — at most one or two per message, and only when they add clarity (e.g., a checkmark for success, a warning sign for errors). Do not decorate messages with emojis.

## Lessons Learned

_Add notes here when you discover something important for future sessions._
