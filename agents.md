# AGENTS.md — Denario Research Scientist

This file is loaded at every session startup. Use it for standing instructions, tool usage notes, and lessons learned.

## Tool Usage

### Denario MCP Tools
- Pipeline stages run long operations (minutes to hours). The long stages (`eda`, `literature`, `results`, `evaluate`, `paper`, `publish`, `audio_summary`) must be run as **jobs** — `denario_job_start` → loop `denario_job_wait(job_id, 45)` → read the result file — never through their synchronous tools (see SOUL.md "Running a long stage as a job"). Short tools (`setup`, `idea`, `methods`, `classify`, `status`, `read_file`, `list_files`) stay synchronous. Always report full output to the supervisor after each stage.
- Job state lives on disk under `<project_dir>/.denario_jobs/<job_id>/` (`spec.json`, `status.json`, `result.json`, `job.log`). It survives MCP server and container restarts. Every `denario_job_*` tool returns a string starting with `ERROR:` on failure instead of raising.
- One active job per project. A second `denario_job_start` on a busy project returns the running job's status rather than starting another — that is not an error, wait on the job it reports.
- Use `denario_status` to check project state before deciding next steps.
- Use `denario_read_file` to read outputs — don't assume what they contain.
- Every tool returns paths to **console log** and **output directory** at the end of its response. If a tool fails or produces unexpected results, read the console log and check the output directory for detailed logs:
  - `<project_dir>/logs/<step>.log` — console output (stdout/stderr) from the pipeline
  - `<project_dir>/Iteration<N>/<step>_output/` — structured output with `*.log`, `costs.txt`, `LLM_calls.txt`, chat histories
  - `<project_dir>/EDA/EDA_output/` — EDA-specific output

### If the Denario tools are missing
- If no `denario_*` tools are in your tool list, or a Denario call fails with **"Connection closed"**, the Denario MCP server crashed at startup. That is an infrastructure failure, not a supervisor cancel — report it as such.
- Do **not** try to restart the gateway: `openclaw gateway restart` is disabled here and does nothing.
- Tools are bound when a **session** starts. Once the server is fixed (by you or the supervisor), ask the supervisor to type `/new` in Slack — a new session picks the tools up; a container restart alone does not.

### Memory Search
- When a narrow memory search returns zero results, immediately retry with a broader query and lower `minScore` (e.g., 0.1) before concluding nothing was found.
- Embedding models can miss relevant results when the query wording doesn't closely match the stored text.

### Shell Execution
- You have full exec access (no approval needed).
- LaTeX is installed — you can compile `.tex` files directly with `pdflatex` or `latexmk`.
- Python is at `/opt/denario-venv/bin/python`.

### Scientific APIs
- **Materials Project** is authenticated. `$MP_API_KEY` and `$MATERIALS_API_KEY` are both set to the same secret, so bare `MPRester()` works out of the box (`from mp_api.client import MPRester`). Do not ask the supervisor for a key.

### Sending Files to Slack
- When sharing files with the supervisor, attach them as **Slack file attachments** in your reply — do NOT paste file content as inline text.
- **Important — path sandbox:** OpenClaw's media upload only allows files under `/home/node/.openclaw/workspace/**`. Files under `/home/node/work/**` (the Denario project dirs) **cannot** be uploaded directly — the attempt will fail with "Local media path is not under an allowed directory" and surface a "Message failed" notification to Slack.
- **Always copy work-dir files into the workspace first**, then upload from the workspace path. Use a descriptive filename. Example:
  ```bash
  cp /home/node/work/projects/co2_capture_v1/Iteration5/input_files/results.md \
     /home/node/.openclaw/workspace/co2_capture_v1_iter5_results.md
  ```
  then call `message upload-file` with `filePath=/home/node/.openclaw/workspace/co2_capture_v1_iter5_results.md`.
- **All file types are supported**: `.md`, `.tex`, `.pdf`, `.png`, `.csv`, etc.
- After each pipeline step, copy the output file (e.g., `idea.md`, `methods.md`) from the project's `Iteration*/input_files/` directory into the workspace with a clear name like `<project>_iter<N>_<stage>.md`, then attach.
- For generated plots, same pattern: copy into the workspace with a descriptive filename, then attach.

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

### Cancellation (job-cancel protocol)
- The supervisor can type "stop", "cancel", "abort" or "kill" in Slack.
- **You handle it:** call `denario_job_cancel(job_id)` on your running job (`denario_job_list(project_dir)` if you need the id), then confirm to the supervisor what was cancelled (job id, stage, elapsed, last log line) and ask what to do next. The MCP server and the container keep running; nothing restarts.
- **Fallback (you are unresponsive):** an independent cancel watcher also sees the message. It kills the running job's process group directly (SIGTERM, SIGKILL after 10 s) — you will see the job as `cancelled`/`lost` on your next `denario_job_status`. Only when **no** job is running (a legacy synchronous tool call is blocking the server) does it kill the MCP server and restart the container (~15 seconds downtime).
- `denario_job_cancel` is idempotent — calling it on a finished or already-cancelled job just says so.
- **After a cancel, do NOT automatically resume or restart the stage.** Report where things stand and wait for the supervisor.

### Recovery after a container restart or `/new`
- Jobs survive MCP server restarts, container restarts and `/new` — the job process is separate and its state is on disk. **Do not assume a restart killed the work.**
- First call `denario_job_list(project_dir)` (with the project path — a freshly restarted server only knows the roots it has been told about; the no-argument form lists what it already knows). Listing indexes the jobs it shows, so `denario_job_status`/`denario_job_wait`/`denario_job_cancel` on those ids work afterwards; you can also pass `project_dir` to those three tools directly. A job that shows `running` is still running from before: **resume by waiting on it** (`denario_job_wait(job_id, 45)` loop) and report as usual when it finishes. **Never start a duplicate** — the server refuses anyway and returns the existing job's status.
- A job that shows `lost` died with the restart (no heartbeat, no result). Read its `job.log`, report it as an infrastructure failure, and ask before restarting the stage.
- Then, if nothing is running:
  1. Run `ls -lt /home/node/work/projects/` to find the most recently modified project
  2. Call `denario_status` on that project to see what was completed
  3. Tell the supervisor where things were left off (e.g., "Project damped_oscillators_v2: Iteration 0 complete, Iteration 1 results job lost at step 3/7")
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
