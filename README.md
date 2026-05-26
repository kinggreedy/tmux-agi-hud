# Tmux AGI-CLI Resource Quota Monitor

A lightweight tmux status monitor for AI CLI tools: Antigravity (AGY), Gemini CLI (GEM), and Codex CLI (CDX) quota tracking - inspired by RPG-style HP bars, because these things drain faster than stamina in a boss fight.

## Features

* **Adaptive Polling**
  API refresh intervals adapt dynamically based on quota level and reset proximity, from 1m to 1h.

* **Visual Progress Bars**
  5-segment color-coded bars representing quota health (Green / Orange / Red).

* **0% Recovery Mode**
  Empty quotas switch to grey recovery bars that refill as reset time approaches.

* **Session-Aware UI**
  The status line automatically changes based on the active tmux session name (`agy`, `gemini`, `codex`).

* **Independent API Scheduling**
  AGY, GEM, and CDX refresh independently to avoid unnecessary polling.

* **Robust Daemon + Watchdog**
  Background worker with timestamp-based stale-data cleanup.

## File Structure

* `tmux_status.py` — Main daemon and status renderer.
* `groups.json` — Model grouping and display configuration.
* `resource_watchdog.sh` — Clears stale tmux variables if the daemon stops updating.
* `tools\debug_status.py` — Debug utility for inspecting AGY responses.
* `tools\test_colors.py` — Verifies TrueColor terminal rendering.

## Setup

### 1. Configure Model Groups

Edit `groups.json` to define display groups such as:

```json
{
  "FLASH": [...],
  "PRO": [...]
}
```

Optional:

```json
"show_reload_timer": true
```

## Tmux Integration

Add to `~/.tmux.conf`:

```tmux
# Background quota daemon
run-shell -b 'python3 ~/tmux-agi-hud/tmux_status.py --tmux --daemon'

# Watchdog cleanup
run-shell -b 'while true; do ~/tmux-agi-hud/resource_watchdog.sh; sleep 60; done'

# Session-aware status display
set -g status-right "#{@resource_status}#{?#{==:#S,agy}, #{@resource_status_AGY},}#{?#{==:#S,gemini}, #{@resource_status_GEM},}#{?#{==:#S,codex}, #{@resource_status_CDX},}"

set -g status-interval 5
```

## Usage

Session names determine which quota group is shown:

| Session  | Status       |
| -------- | ------------ |
| `agy`    | AGY quota    |
| `gemini` | Gemini quota |
| `codex`  | Codex quota  |

Show all statuses manually:

```bash
python3 tmux_status.py
```

Force a specific provider:

```bash
python3 tmux_status.py --filter=AGY
```

## Reloading

After modifying the Python worker:

```bash
pkill -f tmux_status.py
tmux source-file ~/.tmux.conf
```

## Troubleshooting

| Indicator      | Meaning                                 |
| -------------- | --------------------------------------- |
| `U!`           | Unknown model or group inconsistency    |
| `OFF`          | API/service unavailable                 |
| `ERR ...`      | Worker exception                        |
| Missing status | Watchdog likely cleared stale variables |

Verify terminal TrueColor support:

```bash
python3 test_colors.py
```

## Note

- The daemon refresh loop and API polling are intentionally decoupled. Status rendering may update frequently without triggering additional API requests.

## Limitations

- Claude support is planned later. I do not currently have Claude access, but PRs are welcome.
- A proper PID/lockfile system should eventually be added to prevent duplicate daemon workers after repeated tmux reloads.
- Assumes tmux with TrueColor support (`tmux-256color` recommended).
- Some local API endpoints used by AGY are unofficial/internal and may change over time.
