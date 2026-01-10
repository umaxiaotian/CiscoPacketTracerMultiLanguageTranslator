from __future__ import annotations

from typing import Tuple


def build_prompts(source_text: str, context_name: str, target_language: str) -> Tuple[str, str]:
    """SYSTEM/USER プロンプトを構築します。

    SYSTEM は役割と制約のみを担い、翻訳先言語は USER で指定します。
    （SYSTEM で言語を固定しない）

    Args:
        source_text: 翻訳元文字列。
        context_name: Qt の context 名。
        target_language: 翻訳先言語（例: Japanese (ja_JP)）。

    Returns:
        Tuple[str, str]: (system_prompt, user_prompt)
    """
    system_prompt = (
        "You are a professional software UI translator.\n"
        "Rules:\n"
        "- Preserve placeholders exactly (%1, %2, %s, {0}, ${var}).\n"
        "- Preserve XML/HTML tags.\n"
        "- Do not add explanations.\n"
        "- Output only the translated text."
    )

    user_prompt = (
        f"Target language: {target_language}\n"
        f"Qt context: {context_name}\n"
        f"Text: {source_text}"
    )
    return system_prompt, user_prompt
