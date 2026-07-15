#!/usr/bin/env python3
"""Shared multimodal model fallback for Huawei Cloud audit skills."""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests


CONFIG_ENV = "AUDIT_MODEL_CONFIG"
DEFAULT_CONFIG = Path(__file__).resolve().parent / "model_providers.json"


class ModelProviderError(RuntimeError):
    def __init__(
        self,
        message: str,
        retryable: bool = True,
        retry_after_seconds: float | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds
        self.status_code = status_code


@dataclass(frozen=True)
class ModelAttempt:
    provider: str
    model: str
    api_key_env: str


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    config_path = Path(path or os.environ.get(CONFIG_ENV) or DEFAULT_CONFIG)
    if not config_path.is_absolute():
        config_path = Path.cwd() / config_path
    with config_path.open("r", encoding="utf-8") as f:
        config = json.load(f)
    config["_config_path"] = str(config_path)
    return config


def configured_attempts(config: dict[str, Any]) -> list[ModelAttempt]:
    attempts: list[ModelAttempt] = []
    for entry in config.get("fallback_chain") or []:
        provider = str(entry.get("provider") or "").strip().lower()
        api_key_env = str(entry.get("api_key_env") or "").strip()
        for model in entry.get("models") or []:
            model_name = str(model).strip()
            if provider and model_name and api_key_env:
                attempts.append(ModelAttempt(provider=provider, model=model_name, api_key_env=api_key_env))
    if not attempts:
        raise ValueError("No model attempts configured in fallback_chain")
    return attempts


def extract_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("Model response did not contain a JSON object")
    return json.loads(stripped[start : end + 1])


def gemini_image_part(path: Path) -> dict[str, Any]:
    mime = mimetypes.guess_type(str(path))[0] or "image/png"
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return {"inline_data": {"mime_type": mime, "data": data}}


def retryable_status(status_code: int) -> bool:
    return status_code in {408, 409, 425, 429, 500, 502, 503, 504}


def parse_retry_after_seconds(response: requests.Response) -> float | None:
    header = response.headers.get("Retry-After")
    if header:
        try:
            return float(header)
        except ValueError:
            pass
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    details = payload.get("error", {}).get("details", []) if isinstance(payload, dict) else []
    for detail in details:
        retry_delay = detail.get("retryDelay") if isinstance(detail, dict) else None
        if isinstance(retry_delay, str):
            match = re.search(r"([\d.]+)s", retry_delay)
            if match:
                return float(match.group(1))
    match = re.search(r"retry in ([\d.]+)s", response.text, re.I)
    if match:
        return float(match.group(1))
    return None


def call_gemini(
    api_key: str,
    model: str,
    prompt: str,
    images: list[Path],
    timeout: int,
    temperature: float,
    max_output_tokens: int,
) -> dict[str, Any]:
    parts: list[dict[str, Any]] = [{"text": prompt}]
    for path in images:
        parts.append({"text": f"Screenshot: {path.name}"})
        parts.append(gemini_image_part(path))
    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"temperature": temperature, "maxOutputTokens": max_output_tokens},
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    try:
        response = requests.post(
            f"{url}?key={api_key}",
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise ModelProviderError(f"Gemini request failed for {model}: {exc}", retryable=True) from exc
    if response.status_code != 200:
        raise ModelProviderError(
            f"Gemini HTTP {response.status_code} for {model}: {response.text[:800]}",
            retryable=retryable_status(response.status_code),
            retry_after_seconds=parse_retry_after_seconds(response),
            status_code=response.status_code,
        )
    data = response.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    return extract_json(text)


def call_attempt(
    attempt: ModelAttempt,
    api_key: str,
    prompt: str,
    images: list[Path],
    timeout: int,
    temperature: float,
    max_output_tokens: int,
) -> dict[str, Any]:
    if attempt.provider == "gemini":
        return call_gemini(api_key, attempt.model, prompt, images, timeout, temperature, max_output_tokens)
    raise ModelProviderError(f"Unsupported provider: {attempt.provider}", retryable=False)


def call_model_with_fallback(
    prompt: str,
    images: list[Path],
    config_path: str | Path | None = None,
    timeout: int | None = None,
    retries_per_model: int | None = None,
    retry_sleep_seconds: float | None = None,
    model_switch_sleep_seconds: float | None = None,
    temperature: float | None = None,
    max_output_tokens: int | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    config = load_config(config_path)
    defaults = config.get("defaults") or {}
    timeout = int(timeout if timeout is not None else defaults.get("timeout_seconds", 120))
    retries_per_model = int(retries_per_model if retries_per_model is not None else defaults.get("retries_per_model", 2))
    retry_sleep_seconds = float(
        retry_sleep_seconds if retry_sleep_seconds is not None else defaults.get("retry_sleep_seconds", 30)
    )
    model_switch_sleep_seconds = float(
        model_switch_sleep_seconds
        if model_switch_sleep_seconds is not None
        else defaults.get("model_switch_sleep_seconds", 45)
    )
    temperature = float(temperature if temperature is not None else defaults.get("temperature", 0.2))
    max_output_tokens = int(max_output_tokens if max_output_tokens is not None else defaults.get("max_output_tokens", 8192))

    errors: list[str] = []
    attempts = configured_attempts(config)
    for index, attempt in enumerate(attempts):
        api_key = os.environ.get(attempt.api_key_env)
        label = f"{attempt.provider}:{attempt.model}"
        if not api_key:
            message = f"Skipping {label}: env {attempt.api_key_env} is not set"
            print(message, flush=True)
            errors.append(message)
            continue
        for retry_index in range(1, max(1, retries_per_model) + 1):
            print(f"Model analyze: provider={attempt.provider} model={attempt.model} attempt={retry_index}/{retries_per_model}", flush=True)
            try:
                result = call_attempt(attempt, api_key, prompt, images, timeout, temperature, max_output_tokens)
                metadata = {
                    "provider": attempt.provider,
                    "model": attempt.model,
                    "api_key_env": attempt.api_key_env,
                    "fallback_chain": [f"{item.provider}:{item.model}" for item in attempts],
                    "config_path": config.get("_config_path"),
                }
                return result, metadata
            except (ModelProviderError, ValueError, KeyError, IndexError, json.JSONDecodeError) as exc:
                retryable = getattr(exc, "retryable", True)
                status_code = getattr(exc, "status_code", None)
                message = str(exc)
                print(f"Model analyze failed: {message[:500]}", flush=True)
                errors.append(message)
                if not retryable:
                    break
                if status_code == 429:
                    print(f"Rate limited on {label}; switching to next configured model/provider.", flush=True)
                    break
                if retry_index < retries_per_model:
                    retry_after = getattr(exc, "retry_after_seconds", None)
                    sleep_for = retry_sleep_seconds * retry_index
                    if retry_after is not None:
                        sleep_for = max(sleep_for, retry_after + 3)
                    print(f"Sleeping {sleep_for:.1f}s before retrying {label}.", flush=True)
                    time.sleep(sleep_for)
        if index < len(attempts) - 1:
            time.sleep(max(0, model_switch_sleep_seconds))
    agent_fallback = config.get("agent_fallback") or {}
    note = agent_fallback.get("note") if agent_fallback.get("enabled") else None
    message = "All configured Gemini models failed"
    if note:
        message += f"; agent fallback required. {note}"
    raise RuntimeError(message + ":\n" + "\n".join(errors[-12:]))
