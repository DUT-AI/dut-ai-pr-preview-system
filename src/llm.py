"""OpenAI-compatible chat completion via stdlib (no extra dependencies)."""
import json
import time
import urllib.error
import urllib.request


USER_AGENT = "dut-ai-pr-preview-system/1.4"


def _log(message: str) -> None:
    print(f"[llm] {message}", flush=True)


def chat(messages: list[dict], *, model: str, api_key: str, base_url: str,
         max_tokens: int = 49_152, retries: int = 3) -> str:
    """POST {base_url}/chat/completions. Retry up to `retries` times (timeout/429/5xx).

    Default max_tokens 49152, matching the verify agent: deepseek-v4-flash is a
    reasoning model that spends most of its budget on reasoning_content before
    emitting any real content, so the cap is mostly consumed before the answer
    starts. 4096 returned empty content; 16384 got a 120-file PR roughly 7.6K
    characters into its claims JSON and cut it mid-string.
    """
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        # llama.cpp forwards this to thinking-capable chat templates. The
        # review pipeline needs the requested JSON in `content`, not an empty
        # answer after the token budget is consumed by hidden reasoning.
        "chat_template_kwargs": {"enable_thinking": False},
    }).encode()

    last_err = None
    endpoint = f"{base_url.rstrip('/')}/chat/completions"
    for attempt in range(1, retries + 1):
        started = time.perf_counter()
        req = urllib.request.Request(
            endpoint,
            data=payload,
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {api_key}",
                     "User-Agent": USER_AGENT},
        )
        _log(
            "chat request start "
            f"attempt={attempt}/{retries} endpoint={endpoint} model={model} "
            f"max_tokens={max_tokens}"
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = resp.read().decode()
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                _log(
                    "chat request ok "
                        f"attempt={attempt}/{retries} status={getattr(resp, 'status', 200)} "
                    f"elapsed_ms={elapsed_ms} bytes={len(raw)}"
                )
                data = json.loads(raw)
                choice = data["choices"][0]
                content = choice["message"]["content"]
                if content is None:
                    raise RuntimeError("chat returned null content")
                # Truncation has to be named here. The caller only sees a
                # half-written document, and json.loads reports it as
                # "Unterminated string at line 146" — which reads like the model
                # returned garbage rather than like it ran out of room.
                if choice.get("finish_reason") == "length":
                    _log(
                        "chat response truncated "
                        f"attempt={attempt}/{retries} returned_chars={len(content)}"
                    )
                    raise RuntimeError(
                        f"chat truncated: hit max_tokens={max_tokens} before "
                        f"finishing (finish_reason=length, {len(content)} chars "
                        f"returned). Raise max_tokens or send less input.")
                return content
        except urllib.error.HTTPError as e:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            body = e.read().decode(errors="replace")[:300]
            retryable = e.code >= 500 or e.code == 429
            last_err = f"HTTP {e.code}: {body or e.reason or '<empty response>'}"
            _log(
                "chat request failed "
                f"attempt={attempt}/{retries} status={e.code} retryable={retryable} "
                f"elapsed_ms={elapsed_ms} body={body!r}"
            )
            if not retryable:
                raise RuntimeError(
                    f"chat failed (HTTP {e.code}): {body}"
                ) from e
            retry_after = e.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                _log(
                    "chat retry-after "
                    f"attempt={attempt}/{retries} seconds={min(int(retry_after), 30)}"
                )
                time.sleep(min(int(retry_after), 30))
                continue
        except urllib.error.URLError as e:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            last_err = f"{e.__class__.__name__}: {e.reason}"
            _log(
                "chat request error "
                f"attempt={attempt}/{retries} elapsed_ms={elapsed_ms} error={last_err}"
            )
        except KeyError as e:
            _log(f"chat malformed response missing key={e}")
            raise RuntimeError("chat returned malformed response: missing key "
                               f"{e}") from e
        except json.JSONDecodeError as e:
            _log(f"chat non-json response error={e}")
            raise RuntimeError(f"chat returned non-JSON response: {e}") from e
        time.sleep(2 * attempt)
    raise RuntimeError(f"chat failed after {retries} retries: {last_err}")
