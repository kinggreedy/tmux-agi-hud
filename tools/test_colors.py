import sys

def fmt(text, r, g, b, bold=False):
    style = f"\033[38;2;{r};{g};{b}m"
    if bold: style = "\033[1m" + style
    return f"{style}{text}\033[0m"

def generate_bar(pct, time_remaining_secs=None, window_mins=None, length=5):
    if pct == 0 and time_remaining_secs is not None and window_mins is not None:
        window_secs = window_mins * 60
        time_passed = max(0, window_secs - time_remaining_secs)
        recovery_pct = (time_passed / window_secs) * 100
        filled = int(round(recovery_pct * length / 100))
        return fmt("█" * filled, 128, 128, 128) + fmt("█" * (length - filled), 48, 48, 48)

    filled = int(round(pct * length / 100))
    if pct >= 80:
        f, e = (0, 255, 0), (0, 76, 0)
    elif pct >= 40:
        f, e = (255, 180, 0), (76, 54, 0)
    elif pct >= 20:
        f, e = (255, 112, 112), (76, 33, 33)
    else:
        f, e = (255, 48, 48), (76, 14, 14)
    
    return fmt("█" * filled, *f) + fmt("█" * (length - filled), *e)

print(f"{fmt('--- STATUS BAR PHASE TEST ---', 255, 255, 255, bold=True)}\n")

phases = [
    ("HEALTHY (80%+)", 94, "12:30"),
    ("WARNING (40-80%)", 67, "5:15"),
    ("LOW (20-40%)", 31, "1:20"),
    ("CRITICAL (0-20%)", 12, "0:45"),
]

for name, pct, timer in phases:
    bar = generate_bar(pct)
    status = f"FLASH:{bar} {fmt(f'{pct}%', 255, 255, 255, bold=True)} · {fmt(timer, 128, 128, 128)}"
    print(f"{name.ljust(18)} : {status}")

# Recovery Tests
print(f"\n{fmt('--- 0% RECOVERY PROGRESSION (Grey Bar) ---', 255, 255, 255, bold=True)}")
win = 180 # 3h
recovery_steps = [
    ("Just hit 0%", 180, "3:00"), # 0% passed
    ("25% recovered", 135, "2:15"),
    ("50% recovered", 90, "1:30"),
    ("75% recovered", 45, "0:45"),
    ("Nearly reset", 2, "0:02")
]

for name, rem, timer in recovery_steps:
    bar = generate_bar(0, rem * 60, win)
    status = f"FLASH:{bar} {fmt('0%', 255, 255, 255, bold=True)} · {fmt(timer, 128, 128, 128)}"
    print(f"{name.ljust(18)} : {status}")

print(f"\n{fmt('--- ICON & CREDIT TEST ---', 255, 255, 255, bold=True)}")
coin = fmt("◉", 255, 180, 0)
credits = fmt("500", 255, 180, 0)
print(f"AGY Header Sample  : {fmt('AGY', 0, 200, 255, bold=True)}: {coin}:{credits}")
print(f"Long-term Reset    : {fmt('CDX', 255, 0, 255, bold=True)}: WK:{generate_bar(84)} {fmt('84%', 255, 255, 255, bold=True)} · {fmt('6::17:29', 128, 128, 128)}")
