from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from pathlib import Path
import xml.etree.ElementTree as ET
from aoai_async_client import make_async_client, translate_one_async
from pricing import UsageTotals, estimate_cost_usd, load_pricing_config
from progress import ProgressReporter
from ts_file import (
    TsMessage,
    count_candidates,
    ensure_extra_po_headers,
    get_or_create_translation_elem,
    iter_messages,
    should_translate,
)

from dotenv import load_dotenv

load_dotenv()


FAILED_LOG_PATH = Path("translate_failed.jsonl")


def _load_env_required(name: str) -> str:
    """環境変数を必須として取得します。

    Args:
        name: 環境変数名。

    Returns:
        str: 値。

    Raises:
        SystemExit: 未設定の場合。
    """
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"Missing env var: {name}")
    return value


def _write_failed_log(record: dict) -> None:
    """失敗ログ（jsonl）に追記します。

    Args:
        record: JSON 化可能な辞書。
    """
    with FAILED_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


async def _run(args: argparse.Namespace) -> int:
    endpoint = _load_env_required("AZURE_OPENAI_ENDPOINT")
    api_key = _load_env_required("AZURE_OPENAI_API_KEY")
    deployment = _load_env_required("AZURE_OPENAI_DEPLOYMENT")

    pricing = load_pricing_config()
    client = make_async_client(endpoint=endpoint, api_key=api_key)

    tree = ET.parse(args.input)
    root = tree.getroot()
    if root.tag != "TS":
        raise SystemExit("Not a Qt Linguist TS file (root is not <TS>).")

    root.set("language", args.language)
    ensure_extra_po_headers(root, args.language)

    target_language = f"{args.target_name} ({args.language})"

    total_candidates = count_candidates(root)

    # 翻訳対象を収集（翻訳が必要なものだけ）
    targets: list[tuple[TsMessage, ET.Element]] = []
    already_skipped = 0

    for item in iter_messages(root):
        translation_elem = get_or_create_translation_elem(item.message_elem)
        if not should_translate(translation_elem):
            already_skipped += 1
            continue
        targets.append((item, translation_elem))

    # 失敗ログは今回実行分を分けたいなら毎回消す
    if args.reset_failed_log and FAILED_LOG_PATH.exists():
        FAILED_LOG_PATH.unlink()

    reporter = ProgressReporter(total=total_candidates, every=args.progress_every)
    usage = UsageTotals()

    sem = asyncio.Semaphore(args.concurrency)
    lock = asyncio.Lock()

    translated_count = 0
    failed_count = 0
    skipped_count = already_skipped

    start_time = time.time()

    # 途中保存のパス
    partial_path = Path(args.output or args.input.replace(".ts", f".{args.language}.ts"))
    partial_path = partial_path.with_suffix(partial_path.suffix + ".partial")

    async def worker(index: int, item: TsMessage, translation_elem: ET.Element) -> None:
        nonlocal translated_count, failed_count, skipped_count

        async with sem:
            result = await translate_one_async(
                client=client,
                deployment=deployment,
                source_text=item.source_text,
                context_name=item.context_name,
                target_language=target_language,
                max_retries=args.max_retries,
                timeout_sec=args.timeout_sec,
            )

        async with lock:
            if result.ok:
                translation_elem.text = result.text
                translation_elem.attrib.pop("type", None)
                usage.add(result.input_tokens, result.output_tokens)
                translated_count += 1
            else:
                # content_filter など：未翻訳として残す
                translation_elem.attrib["type"] = "unfinished"
                failed_count += 1

                _write_failed_log(
                    {
                        "index": index,
                        "context": item.context_name,
                        "source": item.source_text,
                        "error_code": result.error_code,
                    }
                )

            # ログ表示（随時）
            if args.show and result.ok:
                print("-" * 80)
                print(f"[{translated_count}] context={item.context_name}")
                print(f"SRC: {item.source_text}")
                print(f"TRG: {result.text}")

            # 進捗表示
            reporter.maybe_print(translated_count + failed_count, skipped_count)

            # 途中保存（N件ごと）
            processed = translated_count + failed_count
            if args.save_every > 0 and processed % args.save_every == 0:
                try:
                    tree.write(str(partial_path), encoding="utf-8", xml_declaration=True)
                    elapsed = time.time() - start_time
                    print(f"[checkpoint] wrote {partial_path} (processed={processed}, elapsed={elapsed:.1f}s)")
                except Exception as exc:
                    print(f"[checkpoint] failed to write partial: {exc}")

    tasks = [
        asyncio.create_task(worker(i, item, translation_elem))
        for i, (item, translation_elem) in enumerate(targets, start=1)
    ]

    await asyncio.gather(*tasks)

    output_path = args.output or args.input.replace(".ts", f".{args.language}.ts")
    tree.write(output_path, encoding="utf-8", xml_declaration=True)

    cost = estimate_cost_usd(usage, pricing)

    elapsed_total = time.time() - start_time
    print("\n" + "=" * 80)
    print("DONE")
    print(f"Output: {output_path}")
    print(f"Candidates: {total_candidates}")
    print(f"Translated: {translated_count}")
    print(f"Failed (content_filter etc.): {failed_count}  -> {FAILED_LOG_PATH}")
    print(f"Skipped (already translated / not needed): {skipped_count}")
    print(f"Elapsed: {elapsed_total:.1f}s")
    print(f"Tokens: input={usage.input_tokens}, output={usage.output_tokens}")
    print(
        f"Cost estimate (USD): {cost:.6f}  "
        f"(input ${pricing.input_per_1m}/1M, output ${pricing.output_per_1m}/1M)"
    )
    print("=" * 80)

    return 0


def main() -> int:
    """CLI エントリポイントです。

    Returns:
        int: 正常終了は 0。
    """
    parser = argparse.ArgumentParser(description="Translate Qt Linguist .ts using Azure OpenAI (async parallel).")
    parser.add_argument("input", help="Input .ts file path")
    parser.add_argument("-o", "--output", default=None, help="Output .ts file path")
    parser.add_argument("--language", default="ja_JP", help="TS language attribute (e.g., ja_JP)")
    parser.add_argument("--target-name", default="Japanese", help='Target language display name (e.g., "Japanese")')

    # 並列・表示
    parser.add_argument("--concurrency", type=int, default=10, help="Number of concurrent requests")
    parser.add_argument("--progress-every", type=int, default=50, help="Print progress every N processed items")
    parser.add_argument("--show", action="store_true", help="Print each translation (only successful ones)")

    # リトライ・タイムアウト・途中保存
    parser.add_argument("--max-retries", type=int, default=6, help="Max retries for transient failures")
    parser.add_argument("--timeout-sec", type=float, default=60.0, help="Per-request timeout seconds")
    parser.add_argument("--save-every", type=int, default=200, help="Write partial output every N processed items")

    # ログ
    parser.add_argument("--reset-failed-log", action="store_true", help="Remove translate_failed.jsonl before run")

    args = parser.parse_args()
    return asyncio.run(_run(args))
