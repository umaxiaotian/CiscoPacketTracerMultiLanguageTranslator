from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Tuple
import xml.etree.ElementTree as ET

from dotenv import load_dotenv

from aoai_async_client import make_async_client, translate_one_async
from pricing import UsageTotals, estimate_cost_usd, load_pricing_config
from progress import ProgressReporter
from qph_export import extract_phrases_from_ts, build_qph_xml, write_qph
from ptl_export import export_ptl_from_ts

# ローカル実行用（GitHub Actions では secrets/env が優先される）
load_dotenv()

FAILED_LOG_PATH = Path("translate_failed.jsonl")


@dataclass(frozen=True)
class TsItem:
    """TS ファイル内の翻訳単位（message）を保持します。"""

    context_name: str
    source_text: str
    message_elem: ET.Element
    translation_elem: ET.Element


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


def _text(elem: Optional[ET.Element]) -> str:
    """XML要素のテキストを安全に取得します。

    Args:
        elem: XML要素。

    Returns:
        str: テキスト（無い場合は空文字）。
    """
    if elem is None:
        return ""
    return (elem.text or "").strip()


def _ensure_translation_elem(message_elem: ET.Element) -> ET.Element:
    """message 要素配下に translation が無ければ作成します。

    Args:
        message_elem: <message> 要素。

    Returns:
        ET.Element: <translation> 要素。
    """
    tr = message_elem.find("translation")
    if tr is None:
        tr = ET.SubElement(message_elem, "translation")
    return tr


def _should_translate(translation_elem: ET.Element) -> bool:
    """翻訳対象か判定します。

    ルール:
    - translation が空 → 翻訳対象
    - translation type="unfinished" → 翻訳対象
    - それ以外 → 既に翻訳済みとして対象外

    Args:
        translation_elem: <translation> 要素。

    Returns:
        bool: 翻訳対象なら True。
    """
    if translation_elem.get("type") == "unfinished":
        return True
    return _text(translation_elem) == ""


def _iter_ts_items(ts_root: ET.Element) -> Iterable[TsItem]:
    """TS の全メッセージを走査します。

    Args:
        ts_root: <TS> ルート。

    Yields:
        TsItem: message 単位の情報。
    """
    for ctx in ts_root.findall("context"):
        ctx_name = _text(ctx.find("name"))
        for msg in ctx.findall("message"):
            src = _text(msg.find("source"))
            if not src:
                continue
            tr = _ensure_translation_elem(msg)
            yield TsItem(
                context_name=ctx_name,
                source_text=src,
                message_elem=msg,
                translation_elem=tr,
            )


def _count_candidates(ts_root: ET.Element) -> int:
    """翻訳候補数（source が存在する message 数）を数えます。

    Args:
        ts_root: <TS> ルート。

    Returns:
        int: 件数。
    """
    count = 0
    for _ in _iter_ts_items(ts_root):
        count += 1
    return count


def _ensure_extra_po_headers(ts_root: ET.Element, language: str) -> None:
    """Qt Linguist の <extra-po-header> を設定します（存在しなければ追加）。

    Args:
        ts_root: <TS> ルート。
        language: 言語（例: ja_JP）。

    Returns:
        None
    """
    # 既にあれば何もしない。無いなら最低限を追加。
    existing = ts_root.findall("extra-po-header")
    if existing:
        return

    # 形式は TS によって揺れますが、Qt Linguist は extra-po-header を複数持てます。
    # ここでは最小限（Language）のみ入れます。
    h = ET.SubElement(ts_root, "extra-po-header")
    h.text = f"Language: {language}"


def _write_failed_log(record: dict) -> None:
    """失敗ログ（jsonl）に追記します。

    Args:
        record: JSON 化可能な辞書。

    Returns:
        None
    """
    with FAILED_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _export_phrasebook(ts_root: ET.Element, out_path: str, translator_name: str) -> int:
    """TS からフレーズブック（QPH）を出力します。

    Args:
        ts_root: TS ルート要素。
        out_path: 出力パス（.qph など）。
        translator_name: 翻訳者名。

    Returns:
        int: 出力したエントリ数。
    """
    phrases = extract_phrases_from_ts(ts_root)
    qph_tree = build_qph_xml(phrases, translator_name=translator_name)
    write_qph(qph_tree, out_path, include_doctype=True)
    return len(phrases)


async def _run(args: argparse.Namespace) -> int:
    # TS 読み込み
    tree = ET.parse(args.input)
    root = tree.getroot()
    if root.tag != "TS":
        raise SystemExit("Not a Qt Linguist TS file (root is not <TS>).")

    # TS 属性整備
    root.set("language", args.language)
    _ensure_extra_po_headers(root, args.language)

    total_candidates = _count_candidates(root)

    # 翻訳対象収集
    targets: list[TsItem] = []
    already_done = 0
    for item in _iter_ts_items(root):
        if _should_translate(item.translation_elem):
            targets.append(item)
        else:
            already_done += 1

    # export-only：翻訳せず辞書/ptlだけ出す
    if args.export_only:
        wrote_any = False

        if args.phrasebook_out:
            n = _export_phrasebook(root, args.phrasebook_out, args.translator)
            print(f"Phrasebook written: {args.phrasebook_out} (entries={n})")
            wrote_any = True

        if args.ptl_out:
            # TS -> QM -> PTL (binary)
            ptl_path = export_ptl_from_ts(args.input, args.ptl_out, lrelease_path=args.lrelease_path)
            print(f"PTL written: {ptl_path}")
            wrote_any = True

        if not wrote_any:
            print("Nothing to export. Provide --phrasebook-out and/or --ptl-out.")
            return 1

        return 0

    # AOAI env（翻訳をする場合のみ必須）
    endpoint = _load_env_required("AZURE_OPENAI_ENDPOINT")
    api_key = _load_env_required("AZURE_OPENAI_API_KEY")
    deployment = _load_env_required("AZURE_OPENAI_DEPLOYMENT")

    pricing = load_pricing_config()
    client = make_async_client(endpoint=endpoint, api_key=api_key)

    # 失敗ログリセット
    if args.reset_failed_log and FAILED_LOG_PATH.exists():
        FAILED_LOG_PATH.unlink()

    reporter = ProgressReporter(total=total_candidates, every=args.progress_every)
    usage = UsageTotals()

    sem = asyncio.Semaphore(args.concurrency)
    lock = asyncio.Lock()

    translated_count = 0
    failed_count = 0
    skipped_count = already_done  # 既に翻訳済み/対象外

    start_time = time.time()

    output_path = args.output or args.input.replace(".ts", f".{args.language}.ts")
    partial_path = Path(output_path).with_suffix(Path(output_path).suffix + ".partial")

    target_language = f"{args.target_name} ({args.language})"

    async def worker(index: int, item: TsItem) -> None:
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
                item.translation_elem.text = result.text
                item.translation_elem.attrib.pop("type", None)
                usage.add(result.input_tokens, result.output_tokens)
                translated_count += 1

                if args.show:
                    print("-" * 80)
                    print(f"[{translated_count}] context={item.context_name}")
                    print(f"SRC: {item.source_text}")
                    print(f"TRG: {result.text}")
            else:
                # content_filter 等：未翻訳で残す
                item.translation_elem.attrib["type"] = "unfinished"
                failed_count += 1

                _write_failed_log(
                    {
                        "index": index,
                        "context": item.context_name,
                        "source": item.source_text,
                        "error_code": result.error_code,
                    }
                )

            # 進捗：処理済み（成功+失敗）を進捗カウントにする
            reporter.maybe_print(translated_count + failed_count, skipped_count)

            # 途中保存
            processed = translated_count + failed_count
            if args.save_every > 0 and processed % args.save_every == 0:
                try:
                    tree.write(str(partial_path), encoding="utf-8", xml_declaration=True)
                    elapsed = time.time() - start_time
                    print(f"[checkpoint] wrote {partial_path} (processed={processed}, elapsed={elapsed:.1f}s)")
                except Exception as exc:
                    print(f"[checkpoint] failed to write partial: {exc}")

    tasks = [asyncio.create_task(worker(i, item)) for i, item in enumerate(targets, start=1)]
    await asyncio.gather(*tasks)

    # 最終保存
    tree.write(output_path, encoding="utf-8", xml_declaration=True)

    # 任意：phrasebook 出力
    if args.phrasebook_out:
        n = _export_phrasebook(root, args.phrasebook_out, args.translator)
        print(f"Phrasebook written: {args.phrasebook_out} (entries={n})")

    # 任意：ptl 出力（TS->QM->PTL）
    if args.ptl_out:
        ptl_path = export_ptl_from_ts(output_path, args.ptl_out, lrelease_path=args.lrelease_path)
        print(f"PTL written: {ptl_path}")

    # サマリ
    cost = estimate_cost_usd(usage, pricing)
    elapsed_total = time.time() - start_time

    print("\n" + "=" * 80)
    print("DONE")
    print(f"Output TS: {output_path}")
    if args.phrasebook_out:
        print(f"Output QPH: {args.phrasebook_out}")
    if args.ptl_out:
        print(f"Output PTL: {args.ptl_out}")
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

    # 出力（任意）
    parser.add_argument(
        "--phrasebook-out",
        default=None,
        help="Output Qt phrasebook (.qph).",
    )
    parser.add_argument(
        "--ptl-out",
        default=None,
        help="Output .ptl (binary). Generated via lrelease (TS->QM->PTL rename).",
    )
    parser.add_argument(
        "--lrelease-path",
        default=None,
        help="Path to lrelease executable. If omitted, uses QT_LRELEASE_PATH or PATH.",
    )
    parser.add_argument(
        "--translator",
        default="YUMA OBATA",
        help='Translator name used in phrasebook metadata (default: "YUMA OBATA").',
    )

    # 翻訳せずに “出力だけ” 欲しい場合
    parser.add_argument(
        "--export-only",
        action="store_true",
        help="Do not call AOAI; only export phrasebook/PTL from the input TS.",
    )

    args = parser.parse_args()
    return asyncio.run(_run(args))
