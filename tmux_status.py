import json
import os
import re
import urllib.request
import urllib.parse
import ssl
import sys
import socket
import glob
import time
import subprocess
from datetime import datetime, timezone

# Paths
workspace = os.path.dirname(os.path.abspath(__file__))
cli_root = os.path.expanduser("~/.gemini/antigravity-cli")
gemini_creds = os.path.expanduser("~/.gemini/oauth_creds.json")
agy_log_path = os.path.join(cli_root, "cli.log")
codex_sessions = os.path.expanduser("~/.codex/sessions")
groups_path = os.path.join(workspace, "groups.json")

ssl_context = ssl._create_unverified_context()

# Arguments
use_tmux = "--tmux" in sys.argv
is_daemon = "--daemon" in sys.argv
filter_arg = next((arg.split("=")[1] for arg in sys.argv if arg.startswith("--filter=")), None)

# Default window sizes in minutes for "0% recovery" bar
WINDOW_SIZES = {
    "AGY": 180,    # 3h
    "GEM": 1440,   # 24h
    "CDX_5H": 300, # 5h
    "CDX_WK": 10080 # 7d
}

# Caching state for Daemon mode
cache = {
    "agy_port": None,
    "agy_data": None,
    "agy_next": 0,
    "gemini_data": None,
    "gemini_next": 0,
    "gemini_mtime": 0,
    "codex_data": None,
    "codex_next": 0,
    "codex_file": None,
    "codex_file_next": 0,
    "groups_cfg": None,
    "groups_mtime": 0,
    "last_output": {},
    "min_pct": 100
}

def fmt(text, fg=None, bold=False):
    if not use_tmux:
        style = ""
        if bold: style += "\033[1m"
        if fg:
            r, g, b = int(fg[1:3], 16), int(fg[3:5], 16), int(fg[5:7], 16)
            style += f"\033[38;2;{r};{g};{b}m"
        return f"{style}{text}\033[0m" if style else text
    else:
        style_parts = []
        if fg: style_parts.append(f"fg={fg}")
        if bold: style_parts.append("bold")
        style = f"#[{','.join(style_parts)}]" if style_parts else ""
        return f"{style}{text}#[default]" if style else text

def format_duration(seconds):
    if seconds < 60: return "0:00"
    d = int(seconds // 86400)
    seconds %= 86400
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    if d > 0:
        return f"{d}::{h}:{m:02d}"
    return f"{h}:{m:02d}"

def format_reload_timer(seconds):
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 100:
        return f"{minutes}m"
    hours = minutes // 60
    if hours < 100:
        return f"{hours}h"
    days = hours // 24
    return f"{min(99, days)}d"

def get_adaptive_sleep(pct, remaining_secs):
    if pct == 0:
        if remaining_secs > 14400: return 3600 # > 4h -> 1h poll
        if remaining_secs > 7200: return 900   # > 2h -> 15m poll
        if remaining_secs > 1800: return 300   # > 30m -> 5m poll
        return 60                             # Min poll 1m
    if pct >= 40: return 300  # Healthy/Medium -> 5m poll
    if pct >= 20: return 120  # Low -> 2m poll
    return 60                 # Critical -> 1m poll

def generate_bar(pct, groups_cfg, time_remaining_secs=None, window_mins=None, length=5):
    colors = groups_cfg.get("colors", {})

    # Special case: 0% Recovery Bar (Grey, fills as time passes)
    if pct == 0 and time_remaining_secs is not None and window_mins is not None:
        window_secs = window_mins * 60
        time_passed = max(0, window_secs - time_remaining_secs)
        recovery_pct = (time_passed / window_secs) * 100
        filled = int(round(recovery_pct * length / 100))
        fg, bg = colors.get("recovery", ["#808080", "#303030"])
        return fmt("█" * filled, fg=fg) + fmt("█" * (length - filled), fg=bg)

    # Standard Quota Bar
    filled = int(round(pct * length / 100))
    if pct >= 80:
        fg, bg = colors.get("healthy", ["#00ff00", "#004c00"])
    elif pct >= 40:
        fg, bg = colors.get("medium", ["#ffb400", "#4c3600"])
    elif pct >= 20:
        fg, bg = colors.get("low", ["#ff7070", "#4c2121"])
    else:
        fg, bg = colors.get("critical", ["#ff3030", "#4c0e0e"])

    return fmt("█" * filled, fg=fg) + fmt("█" * (length - filled), fg=bg)

def get_agy_ports():
    if cache["agy_port"]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.1)
            if s.connect_ex(("127.0.0.1", cache["agy_port"])) == 0:
                return [cache["agy_port"]]
    ports = []
    try:
        cmd = "ss -tulpn | grep agy"
        res = os.popen(cmd).read()
        ports = [int(p) for p in re.findall(r"127\.0\.0\.1:(\d+)", res)]
    except: pass
    if not ports and os.path.exists(agy_log_path):
        try:
            with open(agy_log_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
            for line in reversed(lines):
                match = re.search(r"Language server listening on random port at (\d+)", line)
                if match: ports.append(int(match.group(1))); break
        except: pass
    return list(set(ports))

def fetch_agy_status():
    ports = get_agy_ports()
    for port in sorted(ports, reverse=True):
        url = f"https://127.0.0.1:{port}/exa.language_server_pb.LanguageServerService/GetUserStatus"
        headers = {'Content-Type': 'application/json', 'Connect-Protocol-Version': '1', 'X-Codeium-Csrf-Token': '00000000-0000-0000-0000-000000000000'}
        req = urllib.request.Request(url, data=b"{}", headers=headers, method='POST')
        try:
            with urllib.request.urlopen(req, context=ssl_context, timeout=1) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                cache["agy_port"] = port
                return data
        except: pass
    cache["agy_port"] = None
    return None

def fetch_gemini_quota():
    if not os.path.exists(gemini_creds): return None
    try:
        with open(gemini_creds, "r") as f: creds = json.load(f)
        expiry = creds.get("expiry_date", 0) / 1000.0
        if time.time() > expiry: return None
        token = creds.get("access_token")
        if not token: return None
        url = "https://cloudcode-pa.googleapis.com/v1internal:retrieveUserQuota"
        req_body = {"project": "workspace"}
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        req = urllib.request.Request(url, data=json.dumps(req_body).encode(), headers=headers)
        with urllib.request.urlopen(req, context=ssl_context, timeout=5) as resp:
            return json.loads(resp.read())
    except: return None

def fetch_codex_quota():
    now = time.time()
    latest_file = cache["codex_file"]
    if not latest_file or (now > cache["codex_file_next"]):
        try:
            files = glob.glob(os.path.join(codex_sessions, "**", "rollout-*.jsonl"), recursive=True)
            if files:
                latest_file = max(files, key=os.path.getmtime)
                cache["codex_file"] = latest_file
                cache["codex_file_next"] = now + 900
        except: pass

    if latest_file:
        try:
            with open(latest_file, "r", encoding="utf-8", errors="ignore") as f:
                for line in reversed(f.readlines()):
                    if "rate_limits" in line:
                        data = json.loads(line)
                        return data.get("payload", {}).get("rate_limits")
        except: pass
    return None

def load_groups():
    try:
        mtime = os.path.getmtime(groups_path)
        if mtime > cache["groups_mtime"]:
            with open(groups_path, "r") as f:
                cache["groups_cfg"] = json.load(f)
                cache["groups_mtime"] = mtime
    except:
        if not cache["groups_cfg"]: cache["groups_cfg"] = {}
    return cache["groups_cfg"]

def generate_output(groups_cfg):
    now = time.time()
    lines = {"AGY": None, "GEM": None, "CDX": None}
    all_pcts = []
    colors = groups_cfg.get("colors", {})

    # --- AGY SECTION ---
    if now > cache["agy_next"]:
        data = fetch_agy_status()
        if data:
            cache["agy_data"] = data
            u = data.get("userStatus", {})
            client_configs = u.get("cascadeModelConfigData", u.get("serverConfig", {})).get("clientModelConfigs", [])
            min_p, min_r = 100, 999999
            for cfg in client_configs:
                q = cfg.get("quotaInfo", {})
                fraction = q.get("remainingFraction")
                pct = int(fraction * 100) if fraction is not None else (0 if q.get("resetTime") else 100)
                min_p = min(min_p, pct)
                if q.get("resetTime"):
                    rem = (datetime.fromisoformat(q["resetTime"].replace("Z", "+00:00")) - datetime.now(timezone.utc)).total_seconds()
                    min_r = min(min_r, rem)
            cache["agy_next"] = now + get_adaptive_sleep(min_p, min_r)
        else: cache["agy_next"] = now + 60

    if cache["agy_data"]:
        status = cache["agy_data"]
        u = status.get("userStatus", {})
        credits = u.get("planStatus", {}).get("availablePromptCredits")
        model_data = {cfg.get("label"): cfg.get("quotaInfo", {}) for cfg in u.get("cascadeModelConfigData", u.get("serverConfig", {})).get("clientModelConfigs", []) if cfg.get("label")}
        agy_groups = groups_cfg.get("agy", {})
        known = set()
        for g in agy_groups.values(): known.update(g)
        unknown = any(m not in known for m in model_data.keys())
        has_inc = False
        results = []
        if credits is not None: results.append(fmt(f"◉:{credits}", fg=colors.get("coin", "#ffb400")))
        for g_name, g_models in agy_groups.items():
            present = [(m, model_data[m]) for m in g_models if m in model_data]
            if not present: continue
            stats = []
            for m, q in present:
                fraction = q.get("remainingFraction")
                pct = int(fraction * 100) if fraction is not None else (0 if q.get("resetTime") else 100)
                stats.append((pct, q.get("resetTime")))
            if len(set(stats)) > 1: has_inc = True
            avg_pct = stats[0][0]
            all_pcts.append(avg_pct)
            reset_txt, delta = "", None
            if avg_pct < 100:
                resets = [s[1] for s in stats if s[1]]
                if resets:
                    try:
                        rem = (datetime.fromisoformat(resets[0].replace("Z", "+00:00")) - datetime.now(timezone.utc)).total_seconds()
                        if rem > 0: reset_txt, delta = f" {format_duration(rem)}⌛", rem
                    except: pass
            bar = generate_bar(avg_pct, groups_cfg, delta, WINDOW_SIZES["AGY"])
            pct_label = f"{avg_pct}%" if avg_pct > 0 else "⚡"
            results.append(f"{g_name} {bar} {fmt(pct_label, bold=True)}{fmt(reset_txt, fg='#808080')}")
        u_tag = fmt(" U!", fg="#ff5050") if (unknown or has_inc) else ""
        reload_t = fmt(f" {format_reload_timer(cache['agy_next'] - now)}", fg="#ff3030") if groups_cfg.get("show_reload_timer", True) else ""
        lines["AGY"] = f"{' '.join(results)}{u_tag}{reload_t}".strip()
    else: lines["AGY"] = f"{fmt('OFF', fg='#808080')}"

    # --- GEMINI SECTION ---
    creds_mtime = 0
    try: creds_mtime = os.path.getmtime(gemini_creds)
    except: pass

    # If file changed, force a re-poll
    if creds_mtime > cache["gemini_mtime"]:
        cache["gemini_next"] = 0
        cache["gemini_mtime"] = creds_mtime

    if now > cache["gemini_next"]:
        data = fetch_gemini_quota()
        if data:
            cache["gemini_data"] = data
            buckets = data.get("buckets", [])
            min_p, min_r = 100, 999999
            for b in buckets:
                pct = int(b.get("remainingFraction", 1.0) * 100)
                min_p = min(min_p, pct)
                if b.get("resetTime"):
                    rem = (datetime.fromisoformat(b["resetTime"].replace("Z", "+00:00")) - datetime.now(timezone.utc)).total_seconds()
                    min_r = min(min_r, rem)
            cache["gemini_next"] = now + get_adaptive_sleep(min_p, min_r)
        else: cache["gemini_next"] = now + 300

    if cache["gemini_data"]:
        buckets = {b.get("modelId"): b for b in cache["gemini_data"]["buckets"] if b.get("modelId")}
        g_groups = groups_cfg.get("gemini", {})
        known = set()
        for g in g_groups.values(): known.update(g)
        unknown = any(bid not in known for bid in buckets.keys())
        has_inc = False
        results = []
        for g_name, g_ids in g_groups.items():
            present = [(bid, buckets[bid]) for bid in g_ids if bid in buckets]
            if not present: continue
            stats = []
            for bid, b in present:
                pct = int(b.get("remainingFraction", 1.0) * 100)
                stats.append((pct, b.get("resetTime")))
            if len(set(stats)) > 1: has_inc = True
            avg_pct = stats[0][0]
            all_pcts.append(avg_pct)
            reset_txt, delta = "", None
            if avg_pct < 100:
                resets = [s[1] for s in stats if s[1]]
                if resets:
                    try:
                        rem = (datetime.fromisoformat(resets[0].replace("Z", "+00:00")) - datetime.now(timezone.utc)).total_seconds()
                        if rem > 0: reset_txt, delta = f" {format_duration(rem)}⌛", rem
                    except: pass
            bar = generate_bar(avg_pct, groups_cfg, delta, WINDOW_SIZES["GEM"])
            pct_label = f"{avg_pct}%" if avg_pct > 0 else "⚡"
            results.append(f"{g_name} {bar} {fmt(pct_label, bold=True)}{fmt(reset_txt, fg='#808080')}")
        u_tag = fmt(" U!", fg="#ff5050") if (unknown or has_inc) else ""
        reload_t = fmt(f" {format_reload_timer(cache['gemini_next'] - now)}", fg="#ff3030") if groups_cfg.get("show_reload_timer", True) else ""
        lines["GEM"] = f"{' '.join(results)}{u_tag}{reload_t}".strip()
    else: lines["GEM"] = f"{fmt('OFF', fg='#808080')}"

    # --- CODEX SECTION ---
    if now > cache["codex_next"]:
        data = fetch_codex_quota()
        if data:
            cache["codex_data"] = data
            p = data.get("primary", {})
            left = 100 - p.get("used_percent", 0)
            res = p.get("resets_at", 0)
            cache["codex_next"] = now + get_adaptive_sleep(left, max(0, res - now))
        else: cache["codex_next"] = now + 300

    if cache["codex_data"]:
        c_quota = cache["codex_data"]
        results = []
        for key, label in [("primary", "5H"), ("secondary", "WK")]:
            lim = c_quota.get(key)
            if lim:
                left_pct = int(100 - lim.get("used_percent", 0))
                all_pcts.append(left_pct)
                reset_txt, delta = "", None
                resets_at = lim.get("resets_at")
                if resets_at and left_pct < 100:
                    delta = max(0, resets_at - now)
                    reset_txt = f" {format_duration(delta)}⌛"
                win = WINDOW_SIZES["CDX_5H"] if key == "primary" else WINDOW_SIZES["CDX_WK"]
                bar = generate_bar(left_pct, groups_cfg, delta, win)
                pct_label = f"{left_pct}%" if left_pct > 0 else "⚡"
                results.append(f"{label} {bar} {fmt(pct_label, bold=True)}{fmt(reset_txt, fg='#808080')}")
        reload_t = fmt(f" {format_reload_timer(cache['codex_next'] - now)}", fg="#ff3030") if groups_cfg.get("show_reload_timer", True) else ""
        lines["CDX"] = f"{' '.join(results)}{reload_t}"
    else: lines["CDX"] = f"{fmt('OFF', fg='#808080')}"

    if all_pcts: cache["min_pct"] = min(all_pcts)
    return lines

def update_tmux_vars(key, content):
    if cache["last_output"].get(key) == content: return
    now = str(int(time.time()))
    subprocess.run(["tmux", "set", "-gq", f"@resource_status_{key}", content], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["tmux", "set", "-gq", f"@resource_status_{key}_ts", now], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    cache["last_output"][key] = content

def main():
    groups_cfg = load_groups()
    selection = filter_arg
    if not selection:
        try:
            session_name = subprocess.check_output(["tmux", "display-message", "-p", "#S"], encoding="utf-8").strip().upper()
            if "AGY" in session_name: selection = "AGY"
            elif "GEMINI" in session_name or "GEM" in session_name: selection = "GEM"
            elif "CODEX" in session_name or "CDX" in session_name: selection = "CDX"
        except: pass

    if not is_daemon:
        lines = generate_output(groups_cfg)
        if selection and selection in lines: print(lines[selection])
        elif filter_arg: pass
        else: print("\n".join(filter(None, lines.values())))
    else:
        while True:
            try:
                groups_cfg = load_groups()
                lines = generate_output(groups_cfg)
                for key, content in lines.items():
                    if content: update_tmux_vars(key, content)
                ordered = [("1", lines["AGY"]), ("2", lines["GEM"]), ("3", lines["CDX"])]
                if selection and selection in lines:
                    update_tmux_vars("1", lines[selection])
                else:
                    for idx, content in ordered:
                        if content: update_tmux_vars(idx, content)
            except Exception as e:
                update_tmux_vars("ERR", f"ERR {e}")
            time.sleep(15)

if __name__ == "__main__":
    main()
