"""LLM provider interface.

Deliberately thin. The investigation layer must not care which model answers, because the model
is the least trustworthy component in the system: it proposes, the deterministic layer decides,
and the validator gates what reaches a report (G8, D5).

`FakeProvider` is not a mock for convenience -- it lets the injection and validator tests run
with no network, no key and no cost, and it makes "what happens when the model misbehaves" a
testable scenario rather than a hope.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Protocol


class LLMError(RuntimeError):
    pass


def _retry_delay_from(message: str) -> float | None:
    """Pull the server's suggested wait out of a 429 body, e.g. "Please retry in 32.2s"."""
    import re
    match = re.search(r"retry in ([0-9.]+)s", message)
    if match:
        try:
            return min(float(match.group(1)) + 1.0, 90.0)
        except ValueError:
            return None
    return None


@dataclass
class LLMResponse:
    text: str
    model: str
    latency_ms: float
    prompt_chars: int
    finish_reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"model": self.model, "latency_ms": round(self.latency_ms, 1),
                "prompt_chars": self.prompt_chars, "finish_reason": self.finish_reason}

    def parse_json(self) -> Any:
        """Parse a JSON response, tolerating the code fences models add unbidden."""
        text = self.text.strip()
        if text.startswith("```"):
            lines = [l for l in text.splitlines() if not l.strip().startswith("```")]
            text = "\n".join(lines).strip()
        start = min((i for i in (text.find("{"), text.find("[")) if i != -1), default=-1)
        if start == -1:
            raise LLMError(f"no JSON found in model output: {self.text[:200]!r}")
        end = max(text.rfind("}"), text.rfind("]"))
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError as exc:
            raise LLMError(f"model output is not valid JSON: {exc}; got {text[:200]!r}") from exc


class LLMProvider(Protocol):
    name: str
    model: str

    def complete(self, prompt: str, *, system: str | None = None,
                 max_output_tokens: int = 2048) -> LLMResponse:
        ...


@dataclass
class FakeProvider:
    """Returns scripted responses. Used by tests, and by the demo's offline fallback."""

    responses: list[str] = field(default_factory=list)
    name: str = "fake"
    model: str = "fake-deterministic"
    calls: list[str] = field(default_factory=list)

    def complete(self, prompt: str, *, system: str | None = None,
                 max_output_tokens: int = 2048) -> LLMResponse:
        self.calls.append(prompt)
        if not self.responses:
            raise LLMError("FakeProvider has no scripted responses left")
        text = self.responses.pop(0)
        return LLMResponse(text=text, model=self.model, latency_ms=0.0,
                           prompt_chars=len(prompt), finish_reason="stop")


class RateLimited(LLMError):
    """The provider refused for quota reasons. Distinct from a model error on purpose."""


@dataclass
class GeminiProvider:
    """Google AI Studio. The model id is configuration, never a constant in code.

    A timeout is mandatory: a hung call during a live demo is worse than a failed one, because
    the audience watches a spinner instead of an answer.

    **Rate limiting is built in, not left to callers.** The free tier allows 5 requests per
    minute; a 25-case benchmark run needs 25-50 calls, so an unpaced loop exhausts the quota in
    seconds and every later case fails. Measured 2026-10-29: an unpaced run produced 21 of 25
    cases blocked by 429 (RISKS.md S22).
    """

    api_key: str
    model: str
    timeout_s: float = 45.0
    name: str = "gemini"
    # 5 requests/minute on the free tier -> one call every 12.5s, with a little headroom.
    min_interval_s: float = 13.0
    max_retries: int = 3
    _last_call_at: float = field(default=0.0, repr=False)

    def __post_init__(self) -> None:
        if not self.api_key:
            raise LLMError("no API key. Set GOOGLE_API_KEY in .env (G2: never hardcode it).")
        try:
            from google import genai
        except ImportError as exc:  # pragma: no cover - environment problem, not logic
            raise LLMError("google-genai is not installed: pip install google-genai") from exc
        self._genai = genai
        self._client = genai.Client(api_key=self.api_key)

    def _wait_for_slot(self) -> None:
        """Space calls out so the per-minute quota is respected by construction."""
        if self.min_interval_s <= 0:
            return
        elapsed = time.monotonic() - self._last_call_at
        if self._last_call_at and elapsed < self.min_interval_s:
            time.sleep(self.min_interval_s - elapsed)
        self._last_call_at = time.monotonic()

    def complete(self, prompt: str, *, system: str | None = None,
                 max_output_tokens: int = 8192, json_output: bool = True) -> LLMResponse:
        from google.genai import types
        config_kwargs: dict[str, Any] = dict(
            max_output_tokens=max_output_tokens,
            # Temperature 0: an investigation that changes its mind between runs cannot be
            # reviewed or benchmarked.
            temperature=0.0,
            system_instruction=system,
            http_options=types.HttpOptions(timeout=int(self.timeout_s * 1000)),
        )
        # Ask for JSON natively rather than hoping the model complies. Without this, a reply that
        # begins correctly and is then cut off by the token budget is unparseable, which is how
        # the first live call failed.
        if json_output:
            config_kwargs["response_mime_type"] = "application/json"
        config = types.GenerateContentConfig(**config_kwargs)
        response = None
        start = time.perf_counter()
        for attempt in range(self.max_retries + 1):
            self._wait_for_slot()
            try:
                response = self._client.models.generate_content(
                    model=self.model, contents=prompt, config=config)
                break
            except Exception as exc:  # noqa: BLE001 - surface the real reason
                text = str(exc)
                transient = "429" in text or "RESOURCE_EXHAUSTED" in text \
                    or "503" in text or "UNAVAILABLE" in text
                if not transient or attempt == self.max_retries:
                    kind = RateLimited if ("429" in text or "RESOURCE_EXHAUSTED" in text) else LLMError
                    raise kind(
                        f"{self.model} call failed after {attempt + 1} attempt(s): "
                        f"{type(exc).__name__}: {text[:300]}") from exc
                # Honour the server's own retry hint when it gives one.
                delay = _retry_delay_from(text) or (2.0 ** attempt) * 15.0
                time.sleep(delay)
        latency = (time.perf_counter() - start) * 1000
        text = response.text or ""
        finish = None
        try:
            finish = str(response.candidates[0].finish_reason)
        except Exception:  # noqa: BLE001
            pass
        if not text.strip():
            raise LLMError(f"{self.model} returned empty output (finish_reason={finish})")
        # A truncated reply is a configuration problem, not a model error, so say which.
        if finish and "MAX_TOKENS" in str(finish).upper():
            raise LLMError(
                f"{self.model} hit the output limit of {max_output_tokens} tokens and the reply "
                f"is truncated (finish_reason={finish}). Raise max_output_tokens.")
        return LLMResponse(text=text, model=self.model, latency_ms=latency,
                           prompt_chars=len(prompt), finish_reason=finish)


@dataclass
class OpenAIProvider:
    """OpenAI. Same contract as GeminiProvider, so the investigation layer is unchanged (D5).

    Paid keys have far higher rate limits than Gemini's free tier, so `min_interval_s` defaults
    to 0. Set it if a particular key turns out to be rate-limited.
    """

    api_key: str
    model: str
    timeout_s: float = 45.0
    name: str = "openai"
    min_interval_s: float = 0.0
    max_retries: int = 3
    _last_call_at: float = field(default=0.0, repr=False)

    def __post_init__(self) -> None:
        if not self.api_key:
            raise LLMError("no API key. Set OPENAI_API_KEY in .env (G2: never hardcode it).")
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - environment problem
            raise LLMError("openai is not installed: pip install openai") from exc
        self._client = OpenAI(api_key=self.api_key, timeout=self.timeout_s)

    def _wait_for_slot(self) -> None:
        if self.min_interval_s <= 0:
            return
        elapsed = time.monotonic() - self._last_call_at
        if self._last_call_at and elapsed < self.min_interval_s:
            time.sleep(self.min_interval_s - elapsed)
        self._last_call_at = time.monotonic()

    def complete(self, prompt: str, *, system: str | None = None,
                 max_output_tokens: int = 8192, json_output: bool = True) -> LLMResponse:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        start = time.perf_counter()
        response = None
        send_temperature = True
        for attempt in range(self.max_retries + 1):
            self._wait_for_slot()
            try:
                kwargs: dict[str, Any] = {"model": self.model, "messages": messages,
                                          "max_completion_tokens": max_output_tokens}
                if send_temperature:
                    # Temperature 0: a report that changes between runs cannot be reviewed.
                    kwargs["temperature"] = 0.0
                if json_output:
                    # Ask for JSON natively rather than hoping, as with Gemini (D36).
                    kwargs["response_format"] = {"type": "json_object"}
                response = self._client.chat.completions.create(**kwargs)
                break
            except Exception as exc:  # noqa: BLE001 - surface the real reason
                text = str(exc)
                # Reasoning models fix temperature at 1 and reject any other value. Retry once
                # without it rather than failing on a parameter we do not need.
                if send_temperature and "temperature" in text.lower():
                    send_temperature = False
                    continue
                transient = any(code in text for code in ("429", "500", "502", "503", "504")) \
                    or "rate limit" in text.lower() or "overloaded" in text.lower()
                if not transient or attempt == self.max_retries:
                    kind = RateLimited if ("429" in text or "rate limit" in text.lower()) \
                        else LLMError
                    raise kind(f"{self.model} call failed after {attempt + 1} attempt(s): "
                               f"{type(exc).__name__}: {text[:300]}") from exc
                delay = _retry_delay_from(text) or (2.0 ** attempt) * 5.0
                time.sleep(delay)

        latency = (time.perf_counter() - start) * 1000
        if response is None:  # pragma: no cover - defensive
            raise LLMError(f"{self.model} produced no response")
        choice = response.choices[0]
        text = choice.message.content or ""
        finish = choice.finish_reason
        if finish == "length":
            raise LLMError(
                f"{self.model} hit the output limit of {max_output_tokens} tokens and the reply "
                "is truncated. Raise max_output_tokens.")
        if not text.strip():
            raise LLMError(f"{self.model} returned empty output (finish_reason={finish})")
        return LLMResponse(text=text, model=self.model, latency_ms=latency,
                           prompt_chars=len(prompt), finish_reason=finish)


def provider_from_config(cfg: Any) -> LLMProvider:
    """Build the configured provider. Adding one must not touch the investigation layer."""
    name = (cfg.llm_provider or "gemini").lower()
    if name == "gemini":
        return GeminiProvider(api_key=cfg.llm_api_key or "", model=cfg.llm_model)
    if name == "openai":
        return OpenAIProvider(api_key=cfg.llm_api_key or "", model=cfg.llm_model)
    if name == "fake":
        return FakeProvider()
    raise LLMError(f"unknown LLM_PROVIDER {name!r}. Supported: gemini, openai, fake.")
