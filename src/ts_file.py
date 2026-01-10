from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Iterator, Optional, Tuple


TRANSLATOR_NAME = "YUMA OBATA"


def normalize_text(text: str) -> str:
    """テキストを正規化します。

    Args:
        text: 対象文字列。

    Returns:
        str: 正規化後文字列。
    """
    return re.sub(r"\s+", " ", (text or "")).strip()


def is_translatable(source_text: str) -> bool:
    """翻訳対象として有効か判定します。

    Args:
        source_text: source 要素の文字列。

    Returns:
        bool: 翻訳すべき内容がある場合 True。
    """
    return bool(normalize_text(source_text))


def should_translate(translation_elem: Optional[ET.Element]) -> bool:
    """translation 要素を翻訳すべきか判定します。

    Args:
        translation_elem: <translation> 要素。

    Returns:
        bool: 翻訳が必要なら True。
    """
    if translation_elem is None:
        return True
    text = normalize_text("".join(translation_elem.itertext()))
    if not text:
        return True
    return translation_elem.get("type") == "unfinished"


def ensure_extra_po_headers(root: ET.Element, language: Optional[str]) -> None:
    """extra-po-headers を追加/更新します（翻訳者名を入れる）。

    Args:
        root: <TS> ルート要素。
        language: 言語コード（例: ja_JP）。
    """
    header = None
    for child in root:
        if child.tag == "extra-po-headers":
            header = child
            break

    lines = [
        "Project-Id-Version: UNKNOWN",
        f"PO-Revision-Date: {time.strftime('%Y-%m-%d %H:%M%z')}",
        f"Last-Translator: {TRANSLATOR_NAME}",
        "Language-Team: UNKNOWN",
    ]
    if language:
        lines.append(f"Language: {language}")

    lines.extend(
        [
            "MIME-Version: 1.0",
            "Content-Type: text/plain; charset=UTF-8",
            "Content-Transfer-Encoding: 8bit",
        ]
    )

    value = "\\n".join(lines) + "\\n"

    if header is None:
        header = ET.Element("extra-po-headers")
        header.text = value
        root.insert(0, header)
    else:
        header.text = value


@dataclass
class TsMessage:
    """TS の message を扱うためのデータ構造。"""

    context_name: str
    message_elem: ET.Element
    source_text: str


def iter_messages(root: ET.Element) -> Iterator[TsMessage]:
    """TS 内の message を列挙します。

    Args:
        root: <TS> ルート要素。

    Yields:
        TsMessage: message 情報。
    """
    for context in root.findall("context"):
        context_name = context.findtext("name", "") or ""
        for msg in context.findall("message"):
            source_text = msg.findtext("source", "") or ""
            if not is_translatable(source_text):
                continue
            yield TsMessage(context_name=context_name, message_elem=msg, source_text=source_text)


def count_candidates(root: ET.Element) -> int:
    """翻訳候補数（source が非空な message 数）を数えます。

    Args:
        root: <TS> ルート要素。

    Returns:
        int: 候補数。
    """
    return sum(1 for _ in iter_messages(root))


def get_or_create_translation_elem(message_elem: ET.Element) -> ET.Element:
    """message から translation 要素を取得し、無ければ作成します。

    Args:
        message_elem: <message> 要素。

    Returns:
        ET.Element: <translation> 要素。
    """
    translation = message_elem.find("translation")
    if translation is None:
        translation = ET.SubElement(message_elem, "translation")
    return translation
