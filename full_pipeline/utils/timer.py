"""
utils/timer.py
──────────────
Tracks and displays time for each pipeline step.
"""

import time
from datetime import datetime

# ANSI colours
GREEN  = "\033[92m"
YELLOW = "\033[93m"
BLUE   = "\033[94m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"


class StepTimer:
    """Tracks timing for every step in the pipeline."""

    def __init__(self, pipeline_name: str = "Pipeline"):
        self.pipeline_name = pipeline_name
        self.steps         = []   # list of {name, start, end, duration}
        self.pipeline_start = time.time()
        print(f"\n{BOLD}{'═'*65}{RESET}")
        print(f"{BOLD}  {pipeline_name}{RESET}")
        print(f"{DIM}  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{RESET}")
        print(f"{BOLD}{'═'*65}{RESET}")

    def start(self, step_name: str, detail: str = "") -> float:
        """Mark the start of a step. Returns start time."""
        t = time.time()
        detail_str = f" {DIM}({detail}){RESET}" if detail else ""
        print(f"\n{CYAN}▶ {step_name}{RESET}{detail_str}")
        self.steps.append({"name": step_name, "start": t, "end": None, "duration": None})
        return t

    def end(self, summary: str = "") -> float:
        """Mark the end of the current step. Returns duration."""
        t        = time.time()
        step     = self.steps[-1]
        step["end"]      = t
        step["duration"] = t - step["start"]

        dur_str = f"{step['duration']:.2f}s"
        color   = GREEN if step["duration"] < 5 else YELLOW
        print(f"  {color}✓ Done in {dur_str}{RESET}" + (f"  {DIM}{summary}{RESET}" if summary else ""))
        return step["duration"]

    def summary(self):
        """Print full timing summary at end of pipeline."""
        total = time.time() - self.pipeline_start
        print(f"\n{BOLD}{'═'*65}{RESET}")
        print(f"{BOLD}  TIMING SUMMARY{RESET}")
        print(f"{BOLD}{'─'*65}{RESET}")

        for step in self.steps:
            dur  = step["duration"] or 0
            bar  = "█" * min(int(dur * 2), 40)
            color = GREEN if dur < 5 else YELLOW
            print(f"  {step['name']:40s} {color}{dur:6.2f}s  {bar}{RESET}")

        print(f"{BOLD}{'─'*65}{RESET}")
        print(f"  {'TOTAL':40s} {BOLD}{total:6.2f}s{RESET}")
        print(f"{BOLD}{'═'*65}{RESET}\n")
        return total


def fmt_time(seconds: float) -> str:
    """Format seconds into readable string."""
    if seconds < 1:
        return f"{seconds*1000:.0f}ms"
    elif seconds < 60:
        return f"{seconds:.2f}s"
    else:
        return f"{seconds/60:.1f}min"
