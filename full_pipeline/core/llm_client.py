"""
core/llm_client.py
───────────────────
Unified LLM client — supports Groq (free API) and Ollama (local/private).

For financial data security → use backend="ollama" with qwen2.5:7b
  Everything stays on your machine. No data sent to external APIs.

Agent model assignments:
────────────────────────────────────────────────────────────────────────────
Agent              Groq model                         Ollama model
─────────────────  ─────────────────────────────────  ──────────────────────
doc_map            llama-3.3-70b-versatile            qwen2.5:7b (loaded)
tables             llama-3.3-70b-versatile            qwen2.5:7b
rules              llama-3.3-70b-versatile            qwen2.5:7b
terms              llama-3.3-70b-versatile            qwen2.5:7b
description        meta-llama/llama-4-scout           qwen2.5:7b
validator          llama-3.1-8b-instant               qwen2.5:7b
────────────────────────────────────────────────────────────────────────────

Speed reference (Groq):
  llama-3.3-70b-versatile   : ~1,100 tok/s  → ~450ms/call
  llama-4-scout             : ~1,580 tok/s  → ~300ms/call
  llama-3.1-8b-instant      :   ~681 tok/s  → ~750ms/call (rules-first, rarely called)

Speed reference (Ollama / qwen2.5:7b on CPU):
  ~10-40 tok/s depending on hardware → 5–30s/call
  With GPU: ~100 tok/s → ~1–3s/call

Startup:
  # Start Ollama (first time only):
  ollama serve &
  ollama pull qwen2.5:7b-instruct-q4_K_M   (already downloaded on this machine)

  # Set API key for Groq:
  export GROQ_API_KEY='gsk_...'
"""

import os
import re
import json
import time

# ── Model assignments ─────────────────────────────────────────────────────────

GROQ_AGENT_MODELS = {
    # Phase 1 — Document Map: best reasoning for document structure
    "doc_map":     "llama-3.3-70b-versatile",

    # Tables Agent: best at reading structured table data
    "tables":      "llama-3.3-70b-versatile",

    # Rules Sub-Agent: needs to combine table + paragraph logic
    "rules":       "llama-3.3-70b-versatile",

    # Terms Agent (Doc-Type Sub-Agent): clause extraction
    "terms":       "llama-3.3-70b-versatile",

    # Description Agent: simple definition lookup — use fast model
    "description": "meta-llama/llama-4-scout-17b-16e-instruct",

    # Validator: fast rules-first, LLM rarely called
    "validator":   "llama-3.1-8b-instant",

    # Fallback for any missing agent key
    "fallback":    "llama-3.1-8b-instant",
}

# Local Ollama — qwen2.5:7b is already installed on this machine
# Best open model for structured document extraction at 7B parameters
OLLAMA_AGENT_MODELS = {
    "doc_map":     "qwen2.5:7b-instruct-q4_K_M",
    "tables":      "qwen2.5:7b-instruct-q4_K_M",
    "rules":       "qwen2.5:7b-instruct-q4_K_M",
    "terms":       "qwen2.5:7b-instruct-q4_K_M",
    "description": "qwen2.5:7b-instruct-q4_K_M",
    "validator":   "qwen2.5:7b-instruct-q4_K_M",
    "fallback":    "qwen2.5:7b-instruct-q4_K_M",
}

OLLAMA_BASE_URL = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")

# ── Colors ────────────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
RESET  = "\033[0m"


# =============================================================================
# API KEY VALIDATION
# =============================================================================

def _validate_groq_key(api_key: str) -> None:
    if not api_key or not api_key.strip():
        raise RuntimeError(
            f"\n{RED}{'='*60}\n"
            f"✗ GROQ_API_KEY not set.\n"
            f"  Get free key: https://console.groq.com\n"
            f"  Then: export GROQ_API_KEY='gsk_...'\n"
            f"{'='*60}{RESET}\n"
        )
    if not api_key.strip().startswith("gsk_"):
        raise RuntimeError(
            f"{RED}✗ Invalid GROQ_API_KEY format — should start with 'gsk_'{RESET}"
        )


# =============================================================================
# LLM CLIENT
# =============================================================================

class LLMClient:
    """
    LLM client for one agent. Use build_agent_clients() to get all at once.
    """

    def __init__(self, backend: str = "groq",
                 agent: str = "terms",
                 model: str = None,
                 base_url: str = None,
                 timeout: int = 120,
                 max_retries: int = 3):
        self.backend     = backend.lower()
        self.agent       = agent
        self.timeout     = timeout
        self.max_retries = max_retries

        _base_url = base_url or OLLAMA_BASE_URL

        if self.backend == "groq":
            try:
                from groq import Groq
            except ImportError:
                raise ImportError("Run: pip install groq")
            api_key     = os.environ.get("GROQ_API_KEY", "").strip()
            _validate_groq_key(api_key)
            self.model  = model or GROQ_AGENT_MODELS.get(agent, GROQ_AGENT_MODELS["fallback"])
            self._groq  = Groq(api_key=api_key)

        elif self.backend == "ollama":
            import requests
            self.model    = model or OLLAMA_AGENT_MODELS.get(agent, OLLAMA_AGENT_MODELS["fallback"])
            self.base_url = _base_url
            self._req     = requests

        else:
            raise ValueError(f"Unknown backend '{backend}'. Use 'groq' or 'ollama'.")

        print(f"  [llm] {agent:15s} → {self.model}  ({backend})")

    # ── Chat (plain text response) ─────────────────────────────────────────────

    def chat(self, prompt: str, max_tokens: int = 2048,
             temperature: float = 0.0) -> str:
        if self.backend == "groq":
            return self._groq_chat(prompt, max_tokens, temperature)
        return self._ollama_chat(prompt, max_tokens, temperature)

    # ── Chat JSON (expects JSON response) ─────────────────────────────────────

    def chat_json(self, prompt: str, max_tokens: int = 2048) -> dict | list:
        raw = self.chat(prompt, max_tokens)
        raw = re.sub(r"^```[a-z]*\n?", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\n?```$", "", raw).strip()

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            m = re.search(r"(\{.*?\}|\[.*?\])", raw, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(1))
                except json.JSONDecodeError:
                    pass

        # Retry with stricter instruction
        print(f"  [llm:{self.agent}] {YELLOW}⚠ JSON parse failed — retrying{RESET}")
        strict = (prompt + "\n\nIMPORTANT: Output ONLY raw JSON. "
                  "No markdown, no explanation, no text before/after the JSON object.")
        raw2 = self.chat(strict, max_tokens)
        raw2 = re.sub(r"^```[a-z]*\n?", "", raw2, flags=re.IGNORECASE)
        raw2 = re.sub(r"\n?```$", "", raw2).strip()
        try:
            return json.loads(raw2)
        except json.JSONDecodeError:
            m2 = re.search(r"(\{.*?\}|\[.*?\])", raw2, re.DOTALL)
            if m2:
                try:
                    return json.loads(m2.group(1))
                except json.JSONDecodeError:
                    pass

        raise ValueError(
            f"[{self.agent}] LLM did not return valid JSON after 2 attempts.\n"
            f"Response preview: {raw2[:200]}"
        )

    # ── Groq backend ──────────────────────────────────────────────────────────

    def _groq_chat(self, prompt: str, max_tokens: int, temperature: float) -> str:
        for attempt in range(self.max_retries):
            try:
                resp = self._groq.chat.completions.create(
                    model    = self.model,
                    messages = [{"role": "user", "content": prompt}],
                    max_tokens  = max_tokens,
                    temperature = temperature,
                    timeout     = self.timeout,
                )
                return resp.choices[0].message.content.strip()

            except Exception as e:
                msg = str(e).lower()
                print(f"  [llm:{self.agent}] attempt {attempt+1}: {str(e)[:80]}")

                if "rate_limit" in msg:
                    wait = 30 * (attempt + 1)
                    print(f"  [llm:{self.agent}] {YELLOW}Rate limit — waiting {wait}s{RESET}")
                    time.sleep(wait)
                    fallback = GROQ_AGENT_MODELS["fallback"]
                    if self.model != fallback:
                        self.model = fallback
                elif "model" in msg and ("not found" in msg or "unavailable" in msg):
                    self.model = GROQ_AGENT_MODELS["fallback"]
                elif attempt == self.max_retries - 1:
                    raise RuntimeError(f"[{self.agent}] Groq failed after {self.max_retries} attempts: {e}")
                else:
                    time.sleep(5 * (attempt + 1))

        raise RuntimeError(f"[{self.agent}] Groq: max retries exceeded")

    # ── Ollama backend ────────────────────────────────────────────────────────

    def _ollama_chat(self, prompt: str, max_tokens: int, temperature: float) -> str:
        payload = {
            "model":   self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream":  False,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
                "num_ctx":     8192,
            },
        }
        try:
            resp = self._req.post(
                f"{self.base_url}/api/chat",
                json    = payload,
                timeout = self.timeout,
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"].strip()

        except self._req.exceptions.ConnectionError:
            raise RuntimeError(
                f"{RED}✗ Ollama not running at {self.base_url}\n"
                f"  Start it: ollama serve{RESET}"
            )
        except self._req.exceptions.Timeout:
            raise TimeoutError(
                f"{RED}✗ Ollama timeout — model may be slow on CPU.\n"
                f"  Consider: OLLAMA_NUM_THREAD=4 ollama serve{RESET}"
            )
        except Exception as e:
            raise RuntimeError(f"{RED}✗ Ollama error: {e}{RESET}")


# =============================================================================
# FACTORY — build all agent clients at once
# =============================================================================

def build_agent_clients(backend: str = "groq",
                        base_url: str = None,
                        timeout: int = None) -> dict[str, LLMClient]:
    """
    Build one LLMClient per agent.

    Returns:
        {
            "doc_map"    : Phase 1 Document Map
            "tables"     : Tables Agent
            "rules"      : Rules Sub-Agent
            "terms"      : Terms Agent (Doc-Type Sub-Agent)
            "description": Description Agent
            "validator"  : Validator
            "keyword"    : None (keyword search needs no LLM)
        }
    """
    _url = base_url or OLLAMA_BASE_URL
    # Ollama runs 1 request at a time — with 6 workers queuing, each waits
    # up to 6×40s = 240s. Use 600s timeout so none time out on CPU.
    if timeout is None:
        timeout = 600 if backend == "ollama" else 120
    print(f"\n  Initialising LLM clients (backend={backend}, timeout={timeout}s):")

    agents_to_build = ["doc_map", "tables", "rules", "terms", "description", "validator"]
    clients = {}
    for agent_name in agents_to_build:
        clients[agent_name] = LLMClient(
            backend  = backend,
            agent    = agent_name,
            base_url = _url,
            timeout  = timeout,
        )

    clients["keyword"] = None   # keyword search needs no LLM
    return clients


def model_summary(backend: str = "groq") -> None:
    """Print model assignments."""
    models = GROQ_AGENT_MODELS if backend == "groq" else OLLAMA_AGENT_MODELS
    speeds = {
        "llama-3.3-70b-versatile":                    "~450ms/call",
        "meta-llama/llama-4-scout-17b-16e-instruct":  "~300ms/call",
        "llama-3.1-8b-instant":                       "~750ms/call",
        "qwen2.5:7b-instruct-q4_K_M":                 "~5-30s/call (CPU) / ~1-3s (GPU)",
    }
    print(f"\n  Model assignments ({backend}):")
    print(f"  {'─'*72}")
    for agent, model in models.items():
        if agent == "fallback":
            continue
        speed = speeds.get(model, "")
        print(f"  {agent:15s}  {model:45s}  {speed}")
    print(f"  {'─'*72}")
    if backend == "ollama":
        print(f"\n  {GREEN}▶ Local mode: all data stays on your machine (financial security){RESET}")
        print(f"    Model: {OLLAMA_AGENT_MODELS['tables']}")
        print(f"    Start: ollama serve")
