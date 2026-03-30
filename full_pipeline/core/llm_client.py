"""
core/llm_client.py [IMPROVED VERSION]
─────────────────────────────────────
Unified LLM client — supports Groq (free API) and Ollama (local).

IMPROVEMENTS:
  ✓ API key validation with helpful error messages
  ✓ Proper exception handling (raises instead of returning empty)
  ✓ Timeout protection for API calls
  ✓ Better retry logic with logging
  ✓ Specific exception types

Model assignments per agent (all free on Groq):
──────────────────────────────────────────────────────────────────
Agent 1 — Router      : llama-4-scout   (fallback only, embeddings first)
Agent 2 — Table       : llama-3.3-70b-versatile (best accuracy for table reading)
Agent 3 — Validator   : llama-3.1-8b-instant   (fast, rules-first)
Agent 4 — Definition  : llama-4-scout   (fast, simple text extraction)
Fallback              : llama-3.1-8b-instant (if Llama 4 unavailable)
──────────────────────────────────────────────────────────────────

Speed reference (Groq):
  llama-4-scout    : ~1,580 tokens/sec  → ~300ms per call
  llama-3.3-70b    : ~1,100 tokens/sec  → ~450ms per call
  llama-3.1-8b     :   ~681 tokens/sec  → ~750ms per call

Usage:
    export GROQ_API_KEY='gsk_...'

    # Per-agent clients (recommended):
    from core.llm_client import build_agent_clients
    clients = build_agent_clients(backend="groq")
    clients["agent1"].chat("...")
    clients["agent2"].chat("...")

    # Single client:
    from core.llm_client import LLMClient
    client = LLMClient(backend="groq", agent="agent2")
"""

import os
import re
import json
import time

# ── Model assignments per agent ───────────────────────────────────────────────
GROQ_AGENT_MODELS = {
    # Agent 1: Router 
    "agent1_router":     "meta-llama/llama-4-scout-17b-16e-instruct",

    # Agent 2: Table Specialist (Best reasoning available in your list)
    # Note: llama-3.3-70b is currently more stable for complex logic than scout
    "agent2_table":      "llama-3.3-70b-versatile",

    # Agent 3: Validator (Rules-based check)
    "agent3_validator":  "llama-3.1-8b-instant",

    # Agent 4: Definition (Reading comprehension)
    "agent4_definition": "meta-llama/llama-4-scout-17b-16e-instruct",

    # Fallback
    "fallback":          "llama-3.1-8b-instant",
}

# Ollama model for each agent (local, phi3.5 is the only one that fits 4GB)
OLLAMA_AGENT_MODELS = {
    "agent1_router":     "phi3.5:latest",
    "agent2_table":      "phi3.5:latest",
    "agent3_validator":  "phi3.5:latest",
    "agent4_definition": "phi3.5:latest",
    "fallback":          "phi3.5:latest",
}

OLLAMA_BASE_URL = "http://localhost:11435"

# ANSI colors for output
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
RESET  = "\033[0m"


# =============================================================================
# API KEY VALIDATION
# =============================================================================

def _validate_groq_api_key(api_key: str) -> None:
    """
    Validate GROQ API key format and presence.
    Raises RuntimeError with helpful message if invalid.
    """
    if not api_key or not api_key.strip():
        raise RuntimeError(
            f"\n{RED}{'='*70}\n"
            f"✗ GROQ_API_KEY environment variable not set.\n\n"
            f"Steps to fix:\n"
            f"  1. Get free API key at: https://console.groq.com\n"
            f"  2. In your terminal, run:\n"
            f"     export GROQ_API_KEY='gsk_...'\n"
            f"  3. Verify it's set:\n"
            f"     echo $GROQ_API_KEY\n"
            f"  4. Run the pipeline again\n"
            f"{'='*70}{RESET}\n"
        )
    
    api_key = api_key.strip()
    
    # Check format
    if not api_key.startswith("gsk_"):
        raise RuntimeError(
            f"{RED}✗ Invalid GROQ_API_KEY format.{RESET}\n"
            f"  Expected: starts with 'gsk_'\n"
            f"  Got: starts with '{api_key[:10]}...'\n"
            f"  Check your key at: https://console.groq.com/keys"
        )
    
    # Check length (typical Groq keys are ~45 chars)
    if len(api_key) < 20:
        raise RuntimeError(
            f"{RED}✗ GROQ_API_KEY appears too short ({len(api_key)} characters).{RESET}\n"
            f"  Check your key at: https://console.groq.com/keys"
        )


# =============================================================================
# LLM CLIENT
# =============================================================================

class LLMClient:
    """
    Single LLM client for one agent.
    Use build_agent_clients() to get all four at once.
    """

    def __init__(self, backend: str = "groq",
                 agent: str = "agent2_table",
                 model: str = None,
                 base_url: str = OLLAMA_BASE_URL,
                 timeout: int = 60,
                 max_retries: int = 3):
        """
        Args:
            backend : "groq" or "ollama"
            agent   : which agent this client is for
                      (determines default model)
            model   : override model (optional)
            base_url: Ollama base URL (ignored for Groq)
            timeout : timeout in seconds for API calls
            max_retries : maximum number of retry attempts
        """
        self.backend = backend.lower()
        self.agent   = agent
        self.timeout = timeout
        self.max_retries = max_retries

        if self.backend == "groq":
            try:
                from groq import Groq
            except ImportError:
                raise ImportError("Run: pip install groq")

            api_key = os.environ.get("GROQ_API_KEY", "").strip()
            _validate_groq_api_key(api_key)  # This will raise if invalid
            
            self.model  = model or GROQ_AGENT_MODELS.get(agent, GROQ_AGENT_MODELS["fallback"])
            self._groq  = Groq(api_key=api_key)

        elif self.backend == "ollama":
            import requests
            self.model    = model or OLLAMA_AGENT_MODELS.get(agent, "phi3.5:latest")
            self.base_url = base_url
            self._requests = requests

        else:
            raise ValueError(f"Unknown backend: {backend}. Use 'groq' or 'ollama'")

        print(f"  [llm] {agent:20s} → {self.model}  ({backend})  timeout={timeout}s")

    def chat(self, prompt: str, max_tokens: int = 2048,
             temperature: float = 0.0) -> str:
        """
        Send prompt to LLM and get response.
        
        Args:
            prompt: The user prompt
            max_tokens: Maximum tokens in response
            temperature: Temperature (0=deterministic, 1=creative)
        
        Returns:
            LLM response text
        
        Raises:
            TimeoutError: If API times out
            RuntimeError: If API fails after retries
        """
        if self.backend == "groq":
            return self._groq_chat(prompt, max_tokens, temperature)
        return self._ollama_chat(prompt, max_tokens, temperature)

    def chat_json(self, prompt: str, max_tokens: int = 2048) -> dict | list:
        """
        Send prompt and expect JSON response.
        Retries with stricter instruction if first attempt fails.
        
        Args:
            prompt: The user prompt
            max_tokens: Maximum tokens in response
        
        Returns:
            Parsed JSON (dict or list)
        
        Raises:
            ValueError: If response cannot be parsed as JSON after retries
        """
        # First attempt
        raw = self.chat(prompt, max_tokens)
        raw = re.sub(r"^```[a-z]*\n?", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\n?```$", "", raw).strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Try to extract JSON block from middle of prose response
            match = re.search(r"(\[.*?\]|\{.*?\})", raw, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass

            # Second attempt: explicitly tell the model to output ONLY JSON
            print(f"  [llm:{self.agent}] {YELLOW}⚠ JSON parse failed — retrying with strict prompt{RESET}")
            strict_prompt = (
                prompt
                + "\n\nCRITICAL: Your previous response was not valid JSON. "
                + "Output ONLY the raw JSON object or array. "
                + "No explanation, no markdown, no text before or after the JSON."
            )
            raw2 = self.chat(strict_prompt, max_tokens)
            raw2 = re.sub(r"^```[a-z]*\n?", "", raw2, flags=re.IGNORECASE)
            raw2 = re.sub(r"\n?```$", "", raw2).strip()
            try:
                return json.loads(raw2)
            except json.JSONDecodeError:
                match2 = re.search(r"(\[.*?\]|\{.*?\})", raw2, re.DOTALL)
                if match2:
                    try:
                        return json.loads(match2.group(1))
                    except json.JSONDecodeError:
                        pass
            
            # Both attempts failed — raise error instead of returning empty dict
            print(f"  [llm:{self.agent}] {RED}✗ JSON parsing FAILED after 2 retries{RESET}")
            print(f"     First 300 chars of response: {raw2[:300]}")
            raise ValueError(
                f"[{self.agent}] LLM response was not valid JSON after 2 attempts.\n"
                f"Raw response (first 300 chars): {raw2[:300]}\n\n"
                f"This usually means:\n"
                f"  1. The model didn't understand the JSON-only instruction\n"
                f"  2. The prompt is too long for the model\n"
                f"  3. The API is returning an error message instead\n"
                f"\nDebug steps:\n"
                f"  1. Check the raw response above\n"
                f"  2. Try a shorter prompt\n"
                f"  3. Try a different model"
            )

    def _groq_chat(self, prompt: str, max_tokens: int,
                   temperature: float) -> str:
        """
        Call Groq API with retry logic, timeout, and error handling.
        """
        for attempt in range(self.max_retries):
            try:
                resp = self._groq.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_tokens,
                    temperature=temperature,
                    timeout=self.timeout,  # Add timeout protection
                )
                return resp.choices[0].message.content.strip()

            except TimeoutError as e:
                print(f"  [llm:{self.agent}] {YELLOW}⏱ Timeout on attempt {attempt + 1}/{self.max_retries}{RESET}")
                if attempt == self.max_retries - 1:
                    raise TimeoutError(
                        f"[{self.agent}] Groq API timeout after {self.max_retries} attempts. "
                        f"Try increasing TIMEOUT_SECONDS in config."
                    )
                wait_time = 5 * (attempt + 1)
                print(f"  [llm:{self.agent}] Waiting {wait_time}s before retry...")
                time.sleep(wait_time)
                
            except Exception as e:
                msg = str(e).lower()
                print(f"  [llm:{self.agent}] Attempt {attempt + 1}/{self.max_retries}: {str(e)[:100]}")
                
                if "rate_limit" in msg:
                    wait = 30 * (attempt + 1)
                    print(f"  [llm:{self.agent}] {YELLOW}⚠ Rate limit — waiting {wait}s...{RESET}")
                    time.sleep(wait)
                    fallback = GROQ_AGENT_MODELS["fallback"]
                    if self.model != fallback:
                        print(f"  [llm:{self.agent}] Switching to fallback: {fallback}")
                        self.model = fallback
                        
                elif "model" in msg and ("not found" in msg or "unavailable" in msg):
                    fallback = GROQ_AGENT_MODELS["fallback"]
                    print(f"  [llm:{self.agent}] {YELLOW}⚠ Model {self.model} unavailable → {fallback}{RESET}")
                    self.model = fallback
                else:
                    raise

        raise RuntimeError(
            f"[{self.agent}] {RED}✗ Groq API failed after {self.max_retries} attempts{RESET}"
        )

    def _ollama_chat(self, prompt: str, max_tokens: int,
                     temperature: float) -> str:
        """
        Call Ollama API with error handling.
        """
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
                "num_ctx":     8192,
            }
        }
        try:
            resp = self._requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"].strip()

        except self._requests.exceptions.ConnectionError:
            raise RuntimeError(
                f"{RED}✗ Ollama not running at {self.base_url}.{RESET}\n"
                f"Run: OLLAMA_HOST=http://127.0.0.1:11435 ollama serve &"
            )
        except self._requests.exceptions.Timeout:
            raise TimeoutError(
                f"{RED}✗ Ollama API timeout at {self.base_url}.{RESET}\n"
                f"The model may be too slow for this prompt. Try reducing prompt size."
            )
        except Exception as e:
            raise RuntimeError(
                f"{RED}✗ Ollama API error:{RESET} {e}\n"
                f"Check that Ollama is running and the model is installed."
            )


# =============================================================================
# FACTORY — build all 4 clients at once
# =============================================================================

def build_agent_clients(backend: str = "groq",
                        base_url: str = OLLAMA_BASE_URL,
                        timeout: int = 60) -> dict[str, LLMClient]:
    """
    Build one LLMClient per agent, each with its optimal model.

    Args:
        backend: "groq" or "ollama"
        base_url: Ollama base URL (ignored for Groq)
        timeout: Timeout in seconds for API calls

    Returns:
        {
            "agent1": LLMClient for router (Scout / phi3.5)
            "agent2": LLMClient for table  (Maverick / phi3.5)
            "agent3": LLMClient for validator (Scout / phi3.5)
            "agent4": LLMClient for definition (Scout / phi3.5)
        }
    
    Raises:
        RuntimeError: If API key not set or backend unavailable
    """
    print(f"\n  Initialising LLM clients (backend={backend}, timeout={timeout}s):")
    return {
        "agent1": LLMClient(backend=backend, agent="agent1_router",     base_url=base_url, timeout=timeout),
        "agent2": LLMClient(backend=backend, agent="agent2_table",      base_url=base_url, timeout=timeout),
        "agent3": LLMClient(backend=backend, agent="agent3_validator",  base_url=base_url, timeout=timeout),
        "agent4": LLMClient(backend=backend, agent="agent4_definition", base_url=base_url, timeout=timeout),
    }


def model_summary(backend: str = "groq") -> None:
    """Print a summary of which model is assigned to each agent."""
    models = GROQ_AGENT_MODELS if backend == "groq" else OLLAMA_AGENT_MODELS
    print(f"\n  Model assignments ({backend}):")
    print(f"  {'─'*70}")
    for agent, model in models.items():
        if agent == "fallback":
            continue
        speed = {
            "meta-llama/llama-4-scout-17b-16e-instruct":      "~300ms/call",
            "llama-3.3-70b-versatile":                        "~450ms/call",
            "llama-3.1-8b-instant":                           "~750ms/call",
            "phi3.5:latest":                                  "~45s/call",
        }.get(model, "")
        print(f"  {agent:25s} {model:40s} {speed}")
    print(f"  {'─'*70}")
    print(f"  Fallback: {models['fallback']}")