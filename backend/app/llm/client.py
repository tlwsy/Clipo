import json
import time

import httpx


class CompatibleClient:
    def complete(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        messages: list[dict],
        json_mode: bool = True,
        max_tokens: int = 2000,
    ) -> str:
        body = {"model": model, "messages": messages, "temperature": 0.2, "max_tokens": max_tokens}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        started = time.monotonic()
        with httpx.Client(timeout=45, trust_env=False, follow_redirects=False) as client:
            with client.stream(
                "POST",
                base_url.rstrip("/") + "/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json=body,
            ) as response:
                response.raise_for_status()
                data = bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > 1024 * 1024:
                        raise ValueError("Model response too large")
                    if time.monotonic() - started > 60:
                        raise ValueError("Model response deadline exceeded")

        return json.loads(data)["choices"][0]["message"]["content"]
