#!/usr/bin/env python3
"""Sunoで生成した曲を機械的にチェックし、明らかな失敗作を振り分ける。

使い方:
    python3 tools/check_tracks.py 曲フォルダ [--move]

--move を付けると、問題のある曲を 曲フォルダ/rejected/ へ移動する。
最終的に良い曲かどうかは耳で判断すること。ここでは無音・極端な音量・短すぎる曲だけを弾く。
"""
import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".flac", ".ogg"}

MIN_SECONDS = 90          # これより短い曲は除外
MAX_SILENCE_SECONDS = 3.0  # 曲の途中にこれ以上の無音があれば除外
SILENCE_DB = -45          # 無音とみなす音量
TOO_QUIET_DB = -30        # 平均音量がこれより小さければ除外


def probe_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    return float(out.strip())


def analyze(path):
    log = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
         "-af", f"silencedetect=noise={SILENCE_DB}dB:d={MAX_SILENCE_SECONDS},volumedetect",
         "-f", "null", "-"],
        capture_output=True, text=True,
    ).stderr
    mean = re.search(r"mean_volume: (-?[\d.]+) dB", log)
    peak = re.search(r"max_volume: (-?[\d.]+) dB", log)
    starts = [float(s) for s in re.findall(r"silence_start: (-?[\d.]+)", log)]
    return (float(mean.group(1)) if mean else None,
            float(peak.group(1)) if peak else None,
            starts)


def problems(path):
    found = []
    duration = probe_duration(path)
    mean, peak, silence_starts = analyze(path)
    if duration < MIN_SECONDS:
        found.append(f"短すぎる({duration:.0f}秒)")
    if mean is not None and mean < TOO_QUIET_DB:
        found.append(f"音が小さすぎる(平均{mean:.1f}dB)")
    # 曲の冒頭と最後の10秒の無音はフェードとして許す
    mid = [s for s in silence_starts if 2 < s < duration - 10]
    if mid:
        found.append(f"途中に無音あり({mid[0]:.0f}秒付近)")
    return duration, mean, peak, found


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--move", action="store_true", help="問題のある曲を rejected/ へ移動する")
    args = parser.parse_args()

    tracks = sorted(p for p in args.folder.iterdir() if p.suffix.lower() in AUDIO_EXTS)
    if not tracks:
        sys.exit(f"{args.folder} に音声ファイルがありません")

    rejected_dir = args.folder / "rejected"
    ok_count = 0
    for track in tracks:
        duration, mean, peak, found = problems(track)
        status = "NG " + " / ".join(found) if found else "OK"
        print(f"{track.name:40s} {duration/60:5.1f}分  平均{mean:6.1f}dB  {status}")
        if found and args.move:
            rejected_dir.mkdir(exist_ok=True)
            shutil.move(str(track), rejected_dir / track.name)
        ok_count += not found

    print(f"\n{len(tracks)}曲中 {ok_count}曲が機械チェックを通過しました。")


if __name__ == "__main__":
    main()
