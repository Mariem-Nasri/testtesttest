"""
utils/display.py
────────────────
Formats and prints the output of each pipeline step.
"""

import json

GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
BLUE   = "\033[94m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"


def section(title: str):
    print(f"\n  {BOLD}{BLUE}── {title} {'─'*(50-len(title))}{RESET}")


def kv(label: str, value, indent: int = 4):
    """Print a key-value pair."""
    pad = " " * indent
    val_str = str(value) if not isinstance(value, (dict, list)) else json.dumps(value, indent=2)
    print(f"{pad}{DIM}{label:20s}{RESET} {val_str}")


def result_row(key_name: str, value, score: float, extra: str = ""):
    """Print one extraction result with colour-coded score."""
    if score is None:
        score = 0.0
    flag  = f"{GREEN}✓{RESET}" if score >= 0.8 else f"{YELLOW}~{RESET}" if score >= 0.6 else f"{RED}✗{RESET}"
    color = GREEN if score >= 0.8 else YELLOW if score >= 0.6 else RED
    print(f"  {flag}  {key_name[:45]:46s} "
          f"value={str(value)[:18]:19s} "
          f"{color}score={score:.2f}{RESET}"
          + (f"  {DIM}{extra}{RESET}" if extra else ""))


def index_stats(label: str, n_snippets: int, n_dims: int, build_time: float):
    print(f"  {GREEN}✓{RESET}  {label:35s} "
          f"{n_snippets:4d} snippets  "
          f"{n_dims}d embeddings  "
          f"{DIM}built in {build_time:.2f}s{RESET}")


def search_result(rank: int, snippet: str, score: float):
    color = GREEN if score >= 0.85 else YELLOW if score >= 0.65 else RED
    print(f"    [{rank}] {color}score={score:.3f}{RESET}  {snippet[:70]}")


def agent_header(agent_name: str, key_name: str):
    print(f"\n  {BOLD}[ {agent_name} ]{RESET}  {DIM}{key_name}{RESET}")


def step_output(label: str, content: str, max_len: int = 120):
    """Show a labelled output value, truncated if too long."""
    display = content[:max_len] + "..." if len(content) > max_len else content
    print(f"    {CYAN}{label:18s}{RESET} {display}")


def separator():
    print(f"  {DIM}{'─'*60}{RESET}")


def confidence_badge(score: float) -> str:
    if score >= 0.85:
        return f"{GREEN}HIGH{RESET}"
    elif score >= 0.65:
        return f"{YELLOW}MEDIUM{RESET}"
    else:
        return f"{RED}LOW{RESET}"


def needs_llm_badge(needs: bool) -> str:
    if needs:
        return f"{YELLOW}→ LLM needed{RESET}"
    return f"{GREEN}→ No LLM needed{RESET}"
