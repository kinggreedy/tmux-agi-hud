#!/usr/bin/env bash

# resource_watchdog.sh - Clears stale tmux status variables
# MAX_AGE: seconds before a variable is considered dead (180s = 3 mins)
MAX_AGE=180
now="$(date +%s)"

check_one() {
  local key="$1"
  local ts
  
  # Fetch timestamp from tmux global options
  ts="$(tmux show -gqv "@resource_status_${key}_ts")"

  # If no timestamp or invalid, clear the variable
  if [[ -z "$ts" || ! "$ts" =~ ^[0-9]+$ ]]; then
    # Only clear if the status isn't already empty (to avoid redundant calls)
    if [[ -n "$(tmux show -gqv "@resource_status_${key}")" ]]; then
        tmux set -gq "@resource_status_${key}" ""
    fi
    return
  fi

  # Check if timestamp is older than MAX_AGE
  if (( now - ts > MAX_AGE )); then
    tmux set -gq "@resource_status_${key}" ""
    tmux set -gq "@resource_status_${key}_ts" ""
  fi
}

# Check all possible keys
keys=("AGY" "GEM" "CDX" "1" "2" "3")

for k in "${keys[@]}"; do
  check_one "$k"
done
