from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional


def _which(cmd: str) -> Optional[str]:
    """PATH から実行ファイルを探索します。

    Args:
        cmd: コマンド名。

    Returns:
        Optional[str]: 見つかった実行ファイルパス。無ければ None。
    """
    return shutil.which(cmd)


def compile_qm_with_lrelease(
    ts_path: str,
    qm_path: str,
    *,
    lrelease_path: Optional[str] = None,
) -> None:
    """lrelease を使って TS から QM を生成します。

    Args:
        ts_path: 入力 .ts ファイルパス。
        qm_path: 出力 .qm ファイルパス。
        lrelease_path: lrelease 実行ファイルパス（未指定なら PATH から探索）。

    Returns:
        None

    Raises:
        RuntimeError: lrelease が見つからない、またはコンパイルに失敗した場合。
    """
    ts = Path(ts_path)
    qm = Path(qm_path)

    if not ts.exists():
        raise RuntimeError(f"TS file not found: {ts}")

    exe = (lrelease_path or os.getenv("QT_LRELEASE_PATH") or _which("lrelease") or _which("lrelease-qt5"))
    if not exe:
        raise RuntimeError(
            "lrelease not found. Install Qt Linguist tools (lrelease), "
            "or set QT_LRELEASE_PATH to the lrelease executable."
        )

    qm.parent.mkdir(parents=True, exist_ok=True)

    # lrelease input.ts -qm output.qm
    proc = subprocess.run(
        [exe, str(ts), "-qm", str(qm)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "lrelease failed.\n"
            f"cmd: {exe} {ts} -qm {qm}\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}\n"
        )


def export_ptl_from_ts(
    ts_path: str,
    ptl_path: str,
    *,
    lrelease_path: Optional[str] = None,
) -> str:
    """TS から PTL（=QM相当のバイナリ）を生成します。

    実装は「TS→QM を lrelease で作り、QM を PTL 拡張子で保存する」です。:contentReference[oaicite:2]{index=2}

    Args:
        ts_path: 入力 .ts パス。
        ptl_path: 出力 .ptl パス。
        lrelease_path: lrelease 実行ファイルパス（未指定なら PATH/ENV から探索）。

    Returns:
        str: 生成した ptl のパス。
    """
    ptl = Path(ptl_path)
    tmp_qm = ptl.with_suffix(".qm")

    compile_qm_with_lrelease(ts_path, str(tmp_qm), lrelease_path=lrelease_path)
    ptl.parent.mkdir(parents=True, exist_ok=True)

    # “中身は qm” を ptl として保存
    shutil.copyfile(str(tmp_qm), str(ptl))

    # tmp_qm を残したいなら消さない。デフォルトは掃除。
    try:
        tmp_qm.unlink(missing_ok=True)  # py3.8+ OK
    except Exception:
        pass

    return str(ptl)
