# Tmux AGI-CLI Resource Quota Monitor

A lightweight, high-performance tmux status monitor for AI CLI tools: Antigravity (AGY), Gemini CLI (GEM), and Codex CLI (CDX). Inspired by RPG-style HP bars to help you track your "mana" across different models, because these things drain faster than stamina in a boss fight.

## Features

* **Adaptive Polling**
  API refresh intervals adapt dynamically based on quota level and reset proximity, from 1m to 1h.

* **RPG-Style Visual Bars with Minimalist Design**
  5-segment color-coded bars representing quota health (Green / Orange / Red).
  Empty quotas switch to a grey progress bar that fills up as the reset time approaches.
  Ultra-clean, space-efficient output with icons (`◉`, `⌛`, `↻`) and high-density data.

* **Session-Aware UI**
  Automatically displays only the relevant agent status based on the active tmux session name (`agy`, `gemini`, `codex`).

* **Robust Daemon + Watchdog**
  Background worker with timestamp-based stale-data cleanup via a watchdog script.

* **Independent API Scheduling**
  AGY, GEM, and CDX refresh independently to avoid unnecessary polling.

## File Structure

* `tmux_status.py` — Main daemon and status renderer.
* `groups.json` — Central configuration for model grouping, colors, and display toggles.
* `resource_watchdog.sh` — Clears stale tmux variables if the daemon stops.
* `tools/debug_status.py` — Utility for inspecting raw API quota responses from the CLI tools.
* `tools/test_colors.py` — Visual test suite to verify terminal color rendering and UI phases.

## Setup

### 1. Configure Model Groups

Edit `groups.json` to customize your theme or model groupings:

```json
{
  "colors": {
    "healthy": ["#00ff00", "#004c00"],
    ...
    "coin": "#ffb400"
  },
  "show_reload_timer": true,
  "session-name": {
    "GROUP-NAME": [
      model1, model2, ...
    ]
  }
}
```

### 2. Tmux Integration

Add the following to your `~/.tmux.conf`:

```tmux
# Start the background quota daemon
run-shell -b 'python3 ~/tmux-agi-hud/tmux_status.py --tmux --daemon'

# Start the watchdog cleanup
run-shell -b 'while true; do ~/tmux-agi-hud/resource_watchdog.sh; sleep 60; done'

# Session-aware status display
set -g status-right "#{@resource_status}#{?#{==:#S,agy}, #{@resource_status_AGY},}#{?#{==:#S,gemini}, #{@resource_status_GEM},}#{?#{==:#S,codex}, #{@resource_status_CDX},}"
set -g status-interval 5
```

## Usage

The system automatically detects your tmux session name to filter the display:

| Session Name Contains | Displayed Status |
| --------------------- | ---------------- |
| `AGY`                 | Antigravity      |
| `GEMINI` / `GEM`      | Gemini CLI       |
| `CODEX` / `CDX`       | Codex CLI        |

**Manual Commands:**
- Show all statuses: `python3 tmux_status.py`
- Force a specific agent: `python3 tmux_status.py --filter=GEM`

## Troubleshooting

| Indicator | Meaning                                 |
| --------- | --------------------------------------- |
| `⚡`      | Charging mode (Quota is 0%, bar filling) |
| `U!`      | Unknown model or internal inconsistency |
| `OFF`     | API/service unavailable                 |
| `ERR ...` | Background worker exception             |
| `0s-1h`   | (Red text) Time until next API poll     |

## Note

- The daemon refresh loop and API polling are intentionally decoupled. Status rendering may update frequently without triggering additional API requests.

## Limitations

- Claude support is planned later. I do not currently have Claude access, but PRs are welcome.
- A proper PID/lockfile system should eventually be added to prevent duplicate daemon workers after repeated tmux reloads.
- Assumes tmux with TrueColor support (`tmux-256color` recommended).
- Some local API endpoints are unofficial/internal and may change over time.
