from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class AzureOpenAIConfig:
    """Azure OpenAI の接続設定を保持します。"""

    endpoint: str
    api_key: str
    deployment: str


def load_azure_openai_config() -> AzureOpenAIConfig:
    """dotenv から Azure OpenAI 設定を読み込みます。

    Returns:
        AzureOpenAIConfig: 設定オブジェクト。

    Raises:
        SystemExit: 必須環境変数が不足している場合。
    """
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")

    missing = [
        key
        for key, value in {
            "AZURE_OPENAI_ENDPOINT": endpoint,
            "AZURE_OPENAI_API_KEY": api_key,
            "AZURE_OPENAI_DEPLOYMENT": deployment,
        }.items()
        if not value
    ]
    if missing:
        raise SystemExit("Missing env vars (.env expected): " + ", ".join(missing))

    return AzureOpenAIConfig(endpoint=endpoint, api_key=api_key, deployment=deployment)
