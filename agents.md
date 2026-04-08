# AGENTS.md — Denario Research Scientist

This file is loaded at every session startup. Use it for standing instructions, tool usage notes, and lessons learned.

## Tool Usage

### Denario MCP Tools
- Tools run long operations (minutes to hours). Always report full output to the supervisor after each tool call.
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

### File Uploads to Slack
- When uploading files (plots, PDFs, etc.) to Slack, save them under `/home/node/.openclaw/workspace/` — **not** `/tmp/`. The platform only allows uploads from the workspace and media directories.
- Example: save a plot to `/home/node/.openclaw/workspace/lorenz.png`, then upload that path.

### Container Resources
- You run inside a Docker container with **cgroup resource limits**. `/proc/cpuinfo` and `/proc/meminfo` show the host, NOT your actual limits.
- To check your real limits:
  - CPU: `cat /sys/fs/cgroup/cpu.max` (quota/period — e.g. `400000 100000` = 4 CPUs)
  - Memory: `cat /sys/fs/cgroup/memory.max` (in bytes)
  - GPU: `nvidia-smi` (if available; no output = no GPU)
- Your hardware constraints are in `/home/node/work/params.yaml` under `hardware_constraints` — read that for CPU count, RAM, GPU availability, and multiprocessing guidance.
- When benchmarking, scale workers to your CPU quota, not the host core count.

### Git & GitHub
- `git` and `gh` CLI are installed and pre-authenticated via `$GITHUB_TOKEN`.
- The `.gitignore` for research projects is at `/home/node/.openclaw/workspace/.gitignore` — copy it into each new project repo.
- Publish every pipeline step as its own commit (see SOUL.md "Publishing to GitHub").
- Commit messages should capture the *substance* of the output, not just the step name.
- If `git push` fails, report the error but don't block the research pipeline — retry after the next step.
- The GitHub org is in `$GITHUB_ORG` and your scientist name is in `$SCIENTIST_NAME`.

### Cancellation
- The supervisor can type "stop" or "cancel" in Slack to kill a running MCP tool call.
- This kills the MCP server and restarts the container (~15 seconds downtime).
- **After restart, do NOT automatically resume any analysis.** Instead:
  1. Run `ls -lt /home/node/work/projects/` to find the most recently modified project
  2. Call `denario_status` on that project to see what was completed
  3. Tell the supervisor where things were left off (e.g., "Project damped_oscillators_v2: Iteration 0 complete, Iteration 1 partially done")
  4. Ask the supervisor what they want to do next
  5. Only continue if the supervisor explicitly says so

### Memory
- Session notes go in `/home/node/.openclaw/memory/YYYY-MM-DD-HHMMSS.md`.
- Curated long-term memory goes in `/home/node/.openclaw/workspace/MEMORY.md` — distilled learnings, not raw logs.
- **Save errors and failures** — what went wrong, what the error message was, and how it was resolved (or not).
- **Save successes too** — approaches, parameters, or techniques that worked particularly well.
- Before debugging a recurring error, **check memory first** to see if this has happened before and how it was handled.
- Periodically review daily notes and update `MEMORY.md` with what's worth keeping.

### Style
- Use emojis sparingly — at most one or two per message, and only when they add clarity (e.g., a checkmark for success, a warning sign for errors). Do not decorate messages with emojis.

### Voice Messages
- Incoming voice notes are automatically transcribed to text (OpenAI Whisper). You see the transcript — treat it as normal text input.
- **Always respond in English**, regardless of the language of the incoming voice note or its transcript.
- When the supervisor sends a voice message, your text reply is **automatically converted to a voice note** by the platform (ElevenLabs TTS). You do NOT need to call any TTS tool — just write your response as normal text.
- **Voice is for informal chat only.** When the supervisor sends a voice note saying "hi", "what are you up to?", "how's it going?", or similar casual messages, reply with a short conversational response (1–3 sentences). The platform converts it to audio automatically.
- **Never use voice for pipeline work.** When reporting pipeline results, uploading files, sharing logs, code, tables, or technical output — always use text. Even if the supervisor started the conversation with a voice note, switch to text for any substantive research output.
- The `denario_audio_summary` MCP tool is separate — it generates polished audio summaries of pipeline stages (committed to the repo as `presentation.mp3`). Do not use it for conversational replies.

## Model Health Check

Before starting a new research project, or when the supervisor asks you to test models, run:

```bash
/opt/denario-venv/bin/python /home/node/tools/test_models.py
```

This tests every model in `params.yaml` through both backends (AG2/cmbagent and Denario/LangGraph). Report the full output to the supervisor. If any model fails:

1. Report which models failed and the error messages
2. Do **not** start the research project — failing models will cause pipeline failures mid-run
3. Suggest the supervisor check API keys, model availability, or params.yaml configuration

## Lessons Learned

_Add notes here when you discover something important for future sessions._
