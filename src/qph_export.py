from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Iterable, Optional
import xml.etree.ElementTree as ET


@dataclass(frozen=True)
class Phrase:
    """フレーズブック用の 1 エントリです。"""

    source: str
    target: str
    definition: Optional[str] = None


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


def extract_phrases_from_ts(ts_root: ET.Element) -> list[Phrase]:
    """TS(XML)から翻訳済みフレーズを抽出します。

    方針:
    - <message><source> と <translation> が両方埋まっているものを抽出します
    - translation の type="unfinished" は除外します
    - 定義（definition）は context 名を入れます（Qt Linguist上で手掛かりになるため）

    Args:
        ts_root: TS のルート要素（<TS>）。

    Returns:
        list[Phrase]: 抽出したフレーズ一覧。
    """
    phrases: list[Phrase] = []
    for ctx in ts_root.findall("context"):
        ctx_name = _text(ctx.find("name"))
        for msg in ctx.findall("message"):
            src = _text(msg.find("source"))
            tr = msg.find("translation")
            if not src or tr is None:
                continue
            if tr.get("type") == "unfinished":
                continue
            trg = _text(tr)
            if not trg:
                continue
            phrases.append(Phrase(source=src, target=trg, definition=ctx_name or None))
    return phrases


def build_qph_xml(
    phrases: Iterable[Phrase],
    *,
    translator_name: str,
) -> ET.ElementTree:
    """Qt Phrase Book(QPH) の XML を構築します。

    NOTE:
    QPH は明確な公式スキーマが固定で公開されているわけではありませんが、
    Qt Linguist が扱う “<QPH> 配下に <phrase> を並べる” 形式が一般的です。:contentReference[oaicite:2]{index=2}

    Args:
        phrases: フレーズ一覧。
        translator_name: 翻訳者名（例: YUMA OBATA）。

    Returns:
        ElementTree: QPH 用 XML ツリー。
    """
    root = ET.Element("QPH")

    # 任意のメタ情報（互換性のため “必須” にはしない）
    meta = ET.SubElement(root, "meta")
    ET.SubElement(meta, "created").text = dt.datetime.now(dt.timezone.utc).isoformat()
    ET.SubElement(meta, "translator").text = translator_name

    for p in phrases:
        phrase = ET.SubElement(root, "phrase")
        ET.SubElement(phrase, "source").text = p.source
        ET.SubElement(phrase, "target").text = p.target
        if p.definition:
            ET.SubElement(phrase, "definition").text = p.definition

    return ET.ElementTree(root)


def write_qph(tree: ET.ElementTree, out_path: str, *, include_doctype: bool = True) -> None:
    """QPH XML をファイルに書き出します。

    Args:
        tree: QPH 用 XML ツリー。
        out_path: 出力パス（.qph または .ppl など）。
        include_doctype: 先頭に <!DOCTYPE QPH> を付与するか。

    Returns:
        None
    """
    xml_bytes = ET.tostring(tree.getroot(), encoding="utf-8")
    xml_decl = b'<?xml version="1.0" encoding="utf-8"?>\n'
    doctype = b"<!DOCTYPE QPH>\n" if include_doctype else b""
    with open(out_path, "wb") as f:
        f.write(xml_decl)
        f.write(doctype)
        f.write(xml_bytes)
        f.write(b"\n")

