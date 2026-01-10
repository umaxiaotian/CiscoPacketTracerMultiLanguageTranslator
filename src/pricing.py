from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class PricingConfig:
    """料金概算用の単価（USD / 1M tokens）を保持します。"""

    input_per_1m: float
    output_per_1m: float


@dataclass
class UsageTotals:
    """トークン使用量の累計を保持します。"""

    input_tokens: int = 0
    output_tokens: int = 0

    def add(self, input_tokens: int, output_tokens: int) -> None:
        """累計にトークン数を加算します。

        Args:
            input_tokens: 入力トークン数。
            output_tokens: 出力トークン数。
        """
        self.input_tokens += int(input_tokens or 0)
        self.output_tokens += int(output_tokens or 0)


def load_pricing_config() -> PricingConfig:
    """dotenv から料金単価を読み込みます。

    未指定の場合はデフォルト値を利用します（必要に応じて .env で上書き可能）。

    Returns:
        PricingConfig: 単価設定。
    """
    return PricingConfig(
        input_per_1m=float(os.getenv("PRICE_INPUT_PER_1M", "1.75")),
        output_per_1m=float(os.getenv("PRICE_OUTPUT_PER_1M", "14.00")),
    )


def estimate_cost_usd(usage: UsageTotals, pricing: PricingConfig) -> float:
    """トークン使用量から料金概算（USD）を算出します。

    Args:
        usage: 使用トークン累計。
        pricing: 単価設定（USD / 1M tokens）。

    Returns:
        float: 概算料金（USD）。
    """
    return (
        (usage.input_tokens / 1_000_000.0) * pricing.input_per_1m
        + (usage.output_tokens / 1_000_000.0) * pricing.output_per_1m
    )
