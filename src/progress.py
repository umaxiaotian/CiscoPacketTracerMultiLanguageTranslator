from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class ProgressReporter:
    """進捗表示を担当します。"""

    total: int
    every: int = 10
    start_time: float = time.time()

    def maybe_print(self, translated: int, skipped: int) -> None:
        """必要なら進捗を表示します。

        Args:
            translated: 翻訳済み件数。
            skipped: スキップ件数。
        """
        if self.every <= 0:
            return
        if translated == 0:
            return
        if translated % self.every != 0 and translated != self.total:
            return

        pct = (translated / max(1, self.total)) * 100.0
        elapsed = time.time() - self.start_time
        print(
            f"[progress] {translated}/{self.total} ({pct:.1f}%) "
            f"translated | skipped={skipped} | elapsed={elapsed:.1f}s"
        )
