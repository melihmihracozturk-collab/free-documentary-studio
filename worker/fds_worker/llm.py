"""Ücretsiz LLM sağlayıcı zinciri: Gemini → Groq → OpenRouter.

- Yalnızca anahtarı tanımlı sağlayıcılar kullanılır; hiçbiri yoksa LLM gerektiren adımlar çalışmaz.
- Kota (429) veya hata olursa sıradaki model/sağlayıcıya geçilir.
- Yanıtlar veritabanında önbelleğe alınır: aynı istek iki kez gönderilmez.
- Her istek usage_metrics tablosuna yazılır (Dashboard kota uyarıları için).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Callable

import httpx

from . import http


RATE_LIMIT_WAIT = 45  # sn; Gemini ücretsiz katmanı dakika başı sınırlı


class LLMError(Exception):
    pass


class QuotaExhausted(LLMError):
    """Tüm sağlayıcılar kota/yoğunluk (429/503) nedeniyle yanıt vermedi. Adım ertelenmeli, başarısız sayılmamalı."""


@dataclass
class Provider:
    name: str
    model: str
    call: Callable[[str, str, float], str]


def _gemini(model: str):
    key = os.environ["GEMINI_API_KEY"]

    def call(system: str, prompt: str, temperature: float) -> str:
        try:
            r = http.request(
                "POST",
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            headers={"x-goog-api-key": key},
            json={
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": temperature, "responseMimeType": "application/json"},
                },
                timeout=240,
                retries=1,
            )
        except httpx.HTTPStatusError as e:
            # Gövdedeki kota adı (ör. ...PerDay...) teşhis için eklenir; anahtar başlıkta olduğundan mesajda yer almaz.
            body = e.response.text
            quota = re.findall(r'"quotaId":\s*"([^"]+)"', body) or re.findall(r'"message":\s*"([^"]{0,160})', body)
            raise httpx.HTTPStatusError(f"{e.response.status_code} {'; '.join(quota[:2])}", request=e.request,
                                        response=e.response) from None
        data = r.json()
        try:
            return "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError) as e:
            raise LLMError(f"Gemini boş yanıt: {json.dumps(data)[:300]}") from e

    return call


def _openai_compatible(base: str, key_env: str, model: str):
    key = os.environ[key_env]

    def call(system: str, prompt: str, temperature: float) -> str:
        r = http.request(
            "POST", f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": model, "temperature": temperature,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            },
            timeout=240, retries=1,
        )
        return r.json()["choices"][0]["message"]["content"]

    return call


def providers() -> list[Provider]:
    out: list[Provider] = []
    if os.environ.get("GEMINI_API_KEY"):
        for m in (os.environ.get("GEMINI_MODELS") or "gemini-3.8-flash,gemini-3.5-flash-lite").split(","):
            out.append(Provider("gemini", m.strip(), _gemini(m.strip())))
    if os.environ.get("GROQ_API_KEY"):
        m = (os.environ.get("GROQ_MODEL") or "openai/gpt-oss-120b")
        out.append(Provider("groq", m, _openai_compatible("https://api.groq.com/openai/v1", "GROQ_API_KEY", m)))
    if os.environ.get("OPENROUTER_API_KEY") and os.environ.get("OPENROUTER_MODEL"):
        m = os.environ["OPENROUTER_MODEL"]  # yalnızca ":free" ile biten modeller önerilir
        out.append(Provider("openrouter", m, _openai_compatible("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", m)))
    return out


def configured() -> bool:
    return bool(providers()) or os.environ.get("FDS_FAKE_LLM") == "1"


def parse_json(text: str) -> Any:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
        raise


# Testler bu kancayı değiştirir: (system, prompt) -> dict
fake_responder: Callable[[str, str], Any] | None = None


def complete_json(conn, system: str, prompt: str, *, task: str, temperature: float = 0.4,
                  use_cache: bool = True) -> Any:
    key = hashlib.sha256(json.dumps([system, prompt, temperature]).encode()).hexdigest()
    if use_cache and conn is not None:
        row = conn.execute("select response from llm_cache where key=%s", (key,)).fetchone()
        if row:
            return row["response"]

    if os.environ.get("FDS_FAKE_LLM") == "1":
        if fake_responder is None:
            raise LLMError("FDS_FAKE_LLM=1 ama sahte yanıtlayıcı tanımlı değil")
        result, prov = fake_responder(system, prompt), Provider("fake", "fake", lambda *a: "")
    else:
        errors: list[str] = []
        result, prov = None, None
        # Ücretsiz katman dakika başı sınırı (429) veya geçici yoğunluk (503): tüm zincir başarısızsa bekleyip tekrar dene.
        for round_ in range(3):
            transient = False
            for p in providers():
                try:
                    result = parse_json(p.call(system, prompt, temperature))
                    prov = p
                    break
                except (http.RateLimited, httpx.HTTPError, LLMError, json.JSONDecodeError, KeyError) as e:
                    msg = str(e)
                    code = getattr(getattr(e, "response", None), "status_code", None)
                    transient |= isinstance(e, http.RateLimited) or code in (429, 503) or " 429 " in msg or " 503 " in msg
                    errors.append(f"{p.name}/{p.model}: {type(e).__name__}: {msg.splitlines()[0][:160]}")
            if prov is not None or not transient or round_ == 2:
                break
            time.sleep(RATE_LIMIT_WAIT)
        if prov is None and transient:
            raise QuotaExhausted("LLM kotası dolu veya servis yoğun; adım ertelendi: " + " | ".join(errors[-2:]))
        if prov is None:
            if not errors:
                raise LLMError("Hiçbir LLM anahtarı tanımlı değil (GEMINI_API_KEY / GROQ_API_KEY / OPENROUTER_API_KEY)")
            raise LLMError("Tüm LLM sağlayıcıları başarısız: " + " | ".join(errors))

    if conn is not None:
        conn.execute(
            "insert into llm_cache (key, provider, model, response) values (%s,%s,%s,%s::jsonb) "
            "on conflict (key) do nothing", (key, prov.name, prov.model, json.dumps(result)))
        conn.execute("insert into usage_metrics (metric, value) values (%s, 1)", (f"llm:{prov.name}:{task}",))
    return result
