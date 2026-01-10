from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from typing import Optional

from openai import AsyncOpenAI, BadRequestError

from prompts import build_prompts


@dataclass(frozen=True)
class TranslateResult:
    """翻訳結果と使用トークンを保持します。"""

    ok: bool
    text: str
    input_tokens: int
    output_tokens: int
    error_code: str = ""
    error_message: str = ""


def make_async_client(endpoint: str, api_key: str) -> AsyncOpenAI:
    """Azure OpenAI 用の Async クライアントを生成します。

    Args:
        endpoint: Azure OpenAI のエンドポイント（https://...openai.azure.com）。
        api_key: API キー。

    Returns:
        AsyncOpenAI: 初期化済みクライアント。
    """
    base_url = endpoint.rstrip("/") + "/openai/v1/"
    return AsyncOpenAI(api_key=api_key, base_url=base_url)


def _extract_error_code_from_bad_request(exc: BadRequestError) -> str:
    """BadRequestError から Azure 形式の error.code を抽出します。

    Args:
        exc: BadRequestError。

    Returns:
        str: error.code（取得できない場合は空文字）。
    """
    try:
        data = exc.response.json()
        err = data.get("error") or {}
        return str(err.get("code") or "")
    except Exception:
        return ""


def _is_content_filter_error(exc: Exception) -> bool:
    """Azure OpenAI の content filter ブロックか判定します。

    Args:
        exc: 例外。

    Returns:
        bool: content_filter の場合 True。
    """
    if not isinstance(exc, BadRequestError):
        return False
    return _extract_error_code_from_bad_request(exc) == "content_filter"


async def translate_one_async(
    client: AsyncOpenAI,
    deployment: str,
    source_text: str,
    context_name: str,
    target_language: str,
    *,
    max_retries: int = 6,
    timeout_sec: float = 60.0,
) -> TranslateResult:
    """1メッセージを指定言語へ翻訳します（非同期）。

    方針:
    - content_filter の場合は例外にせず ok=False で返します（全体を止めないため）。
    - それ以外の一時的な失敗（429/5xx/ネットワーク等）は指数バックオフでリトライします。

    Args:
        client: AsyncOpenAI クライアント。
        deployment: Azure OpenAI のデプロイ名（例: gpt-4o-mini）。
        source_text: 翻訳元の文字列。
        context_name: Qt context 名。
        target_language: 翻訳先言語（例: Japanese (ja_JP)）。
        max_retries: 最大リトライ回数。
        timeout_sec: 1リクエストのタイムアウト秒。

    Returns:
        TranslateResult: 翻訳結果（ok=False の場合は text は空、error_code が入る）。
    """
    system_prompt, user_prompt = build_prompts(
        source_text=source_text,
        context_name=context_name,
        target_language=target_language,
    )

    last_exc: Optional[Exception] = None

    for attempt in range(max_retries + 1):
        try:
            resp = await asyncio.wait_for(
                client.responses.create(
                    model=deployment,  # Azure は deployment 名を model に渡す
                    input=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                ),
                timeout=timeout_sec,
            )

            text = (resp.output_text or "").strip()

            usage = getattr(resp, "usage", None)
            input_tokens = int(getattr(usage, "input_tokens", 0) or 0) if usage else 0
            output_tokens = int(getattr(usage, "output_tokens", 0) or 0) if usage else 0

            return TranslateResult(
                ok=True,
                text=text,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

        except Exception as exc:
            last_exc = exc

            # content_filter はスキップ（全体停止しない）
            if _is_content_filter_error(exc):
                return TranslateResult(
                    ok=False,
                    text="",
                    input_tokens=0,
                    output_tokens=0,
                    error_code="content_filter",
                    error_message=str(exc),
                )

            # 最終試行なら抜けて最後に例外
            if attempt >= max_retries:
                break

            # 指数バックオフ + ジッター（衝突回避）
            backoff = min(30.0, (2 ** attempt) * 0.5) + random.uniform(0, 0.25)
            await asyncio.sleep(backoff)

    raise last_exc if last_exc else RuntimeError("translate_one_async failed")
