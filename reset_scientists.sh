#!/usr/bin/env bash
# reset_scientists.sh
#
# Reset the `agent:main:main` session AND disable the heartbeat loop for
# every denario-* scientist. This is the session OpenClaw's heartbeat fires
# against every 30 min, so resetting + disabling stops the recurring bill
# entirely (not just until the next research run refills the transcript).
#
# What it does, per scientist:
#   1. Patches openclaw.json to set `agents.defaults.heartbeat.every = "0m"`
#      (the documented way to disable heartbeat — see openclaw/docs/gateway/
#      heartbeat.md: "use `0m` to disable")
#   2. Reads scientists/denario-N/config/agents/main/sessions/sessions.json
#      and looks up the `agent:main:main` entry to get its sessionId
#   3. Renames <sessionId>.jsonl -> <sessionId>.jsonl.reset.<UTC-timestamp>
#      (same convention OpenClaw already uses internally)
#   4. Removes the agent:main:main entry from sessions.json so OpenClaw
#      starts fresh on next turn
#   5. Restarts the container so the gateway reloads config + session state
#
# Usage:
#   ./reset_scientists.sh                 # reset + disable heartbeat on all
#   ./reset_scientists.sh 3 6             # only denario-3 and denario-6
#   ./reset_scientists.sh --dry-run       # show what would happen, do nothing
#   ./reset_scientists.sh --no-restart    # edit files but skip docker restart
#   ./reset_scientists.sh --no-disable    # reset session only, keep heartbeat
#   ./reset_scientists.sh --no-reset      # disable heartbeat only, keep session
#
# Re-enable heartbeat later by editing openclaw.json and setting
#   agents.defaults.heartbeat.every back to "30m" (or removing the key).
#
# Notes:
#   - Only `agent:main:main` is reset. Slack channel/thread sessions are
#     left alone; reset those from Slack itself if you want to clear them.
#   - Safe to run while containers are up; the restart is what takes effect,
#     and the .reset.<ts>.jsonl rename leaves an auditable trail.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

DRY_RUN=0
RESTART=1
DO_RESET=1
DO_DISABLE=1
TARGETS=()

for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
        --no-restart) RESTART=0 ;;
        --no-reset) DO_RESET=0 ;;
        --no-disable) DO_DISABLE=0 ;;
        -h|--help)
            sed -n '2,38p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        [0-9]*) TARGETS+=("$arg") ;;
        *) echo "unknown arg: $arg" >&2; exit 1 ;;
    esac
done

# Default: every denario-* directory under scientists/
if [ ${#TARGETS[@]} -eq 0 ]; then
    while IFS= read -r dir; do
        n="${dir##*denario-}"
        TARGETS+=("$n")
    done < <(find scientists -maxdepth 1 -type d -name 'denario-*' | sort -V)
fi

if [ ${#TARGETS[@]} -eq 0 ]; then
    echo "no scientists found under scientists/denario-*" >&2
    exit 1
fi

TS="$(date -u +%Y-%m-%dT%H-%M-%S.%3NZ)"
echo "reset timestamp: $TS"
[ "$DRY_RUN" = 1 ] && echo "(dry-run — no changes will be made)"
echo

reset_one() {
    local i="$1"
    local name="denario-$i"
    local cfg_dir="scientists/$name/config"
    local openclaw_json="$cfg_dir/openclaw.json"
    local sess_dir="$cfg_dir/agents/main/sessions"
    local sess_json="$sess_dir/sessions.json"

    if [ ! -d "$cfg_dir" ]; then
        printf "  %-12s skip: no config dir\n" "$name"
        return
    fi

    local actions=()

    # --- Step 1: disable heartbeat in openclaw.json ---
    if [ "$DO_DISABLE" = 1 ] && [ -f "$openclaw_json" ]; then
        local current
        current="$(python3 -c "
import json
try:
    d = json.load(open('$openclaw_json'))
    print(((d.get('agents') or {}).get('defaults') or {}).get('heartbeat', {}).get('every') or '')
except Exception:
    print('')
" 2>/dev/null)"

        if [ "$current" = "0m" ]; then
            actions+=("heartbeat already disabled")
        else
            actions+=("heartbeat.every: '${current:-unset}' -> '0m'")
            if [ "$DRY_RUN" = 0 ]; then
                python3 - "$openclaw_json" <<'PY'
import json, sys
p = sys.argv[1]
d = json.load(open(p))
agents = d.setdefault("agents", {})
defaults = agents.setdefault("defaults", {})
hb = defaults.setdefault("heartbeat", {})
hb["every"] = "0m"
json.dump(d, open(p, "w"), indent=2)
PY
            fi
        fi
    elif [ "$DO_DISABLE" = 1 ]; then
        actions+=("heartbeat: no openclaw.json to patch")
    fi

    # --- Step 2: reset agent:main:main session ---
    if [ "$DO_RESET" = 1 ] && [ -f "$sess_json" ]; then
        local sid
        sid="$(python3 -c "
import json
try:
    d = json.load(open('$sess_json'))
    print((d.get('agent:main:main') or {}).get('sessionId') or '')
except Exception:
    print('')
" 2>/dev/null)"

        if [ -z "$sid" ]; then
            actions+=("session: no agent:main:main entry")
        else
            local jsonl="$sess_dir/$sid.jsonl"
            if [ ! -f "$jsonl" ]; then
                actions+=("session: jsonl missing ($sid)")
            else
                local size_kb=$(( $(stat -c%s "$jsonl") / 1024 ))
                actions+=("reset session ${sid:0:8}… (${size_kb} KB)")
                if [ "$DRY_RUN" = 0 ]; then
                    mv "$jsonl" "${jsonl}.reset.${TS}"
                    python3 - "$sess_json" <<'PY'
import json, sys
p = sys.argv[1]
d = json.load(open(p))
d.pop("agent:main:main", None)
json.dump(d, open(p, "w"), indent=2)
PY
                fi
            fi
        fi
    fi

    # --- Step 3: restart container ---
    if [ "$DRY_RUN" = 0 ] && [ "$RESTART" = 1 ] && [ ${#actions[@]} -gt 0 ]; then
        if docker ps --format '{{.Names}}' | grep -qx "$name"; then
            docker restart "$name" >/dev/null
            actions+=("restarted")
        else
            actions+=("container not running — no restart")
        fi
    fi

    if [ ${#actions[@]} -eq 0 ]; then
        printf "  %-12s no-op\n" "$name"
    else
        printf "  %-12s %s\n" "$name" "${actions[0]}"
        for a in "${actions[@]:1}"; do
            printf "  %-12s %s\n" "" "$a"
        done
    fi
}

for i in "${TARGETS[@]}"; do
    reset_one "$i"
done

echo
echo "done."
