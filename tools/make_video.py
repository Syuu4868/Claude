#!/usr/bin/env python3
"""選んだ曲と背景画像から、作業用BGMの長尺動画とチャプター一覧を作る。

使い方:
    python3 tools/make_video.py 曲フォルダ 背景画像 -o out/rain_cafe.mp4
    python3 tools/make_video.py 曲フォルダ 背景画像 -o out/rain_cafe.mp4 --minutes 60 --shorts

曲はファイル名順に並ぶ（01_xxx.mp3 のように番号を付けると順番を決められる）。
--minutes を指定すると、その長さになるまで曲を繰り返す。
--shorts を付けると、YouTubeショート/TikTok用の縦型45秒動画も作る。
チャプター一覧は 出力名.chapters.txt に書き出すので、そのまま概要欄に貼れる。
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".flac", ".ogg"}


def duration_of(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    return float(out.strip())


def run(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit("ffmpegでエラーが出ました:\n" + result.stderr[-2000:])


def build_playlist(tracks, minutes, crossfade):
    """目標の長さに届くまで曲を並べ、(曲, 開始秒) の一覧を返す。"""
    durations = {t: duration_of(t) for t in tracks}
    playlist, position = [], 0.0
    target = minutes * 60 if minutes else None
    while True:
        for track in tracks:
            playlist.append((track, position))
            position += durations[track] - crossfade
            if target and position >= target:
                return playlist
        if not target:
            return playlist


def timestamp(seconds):
    seconds = int(seconds)
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def mix_audio(playlist, crossfade, out_path):
    inputs, filters = [], []
    for track, _ in playlist:
        inputs += ["-i", str(track)]
    if len(playlist) == 1:
        run(["ffmpeg", "-y", *inputs, "-c:a", "aac", "-b:a", "192k", str(out_path)])
        return
    prev = "[0:a]"
    for i in range(1, len(playlist)):
        label = f"[a{i}]"
        filters.append(f"{prev}[{i}:a]acrossfade=d={crossfade}:c1=tri:c2=tri{label}")
        prev = label
    # 曲が変わっても音量がばらつかないよう最後に整える
    filters.append(f"{prev}loudnorm=I=-14:TP=-1.5:LRA=11[out]")
    run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(filters),
         "-map", "[out]", "-c:a", "aac", "-b:a", "192k", str(out_path)])


def render_video(image, audio, out_path):
    scale = ("scale=1920:1080:force_original_aspect_ratio=increase,"
             "crop=1920:1080,format=yuv420p")
    run(["ffmpeg", "-y", "-loop", "1", "-framerate", "2", "-i", str(image), "-i", str(audio),
         "-vf", scale, "-c:v", "libx264", "-tune", "stillimage", "-preset", "medium",
         "-c:a", "copy", "-shortest", "-movflags", "+faststart", str(out_path)])


def render_short(image, track, out_path, start=30, length=45):
    scale = ("scale=1080:1920:force_original_aspect_ratio=increase,"
             "crop=1080:1920,format=yuv420p")
    fade = f"afade=t=in:d=1,afade=t=out:st={length - 2}:d=2"
    run(["ffmpeg", "-y", "-loop", "1", "-framerate", "30", "-i", str(image),
         "-ss", str(start), "-t", str(length), "-i", str(track),
         "-vf", scale, "-af", fade, "-c:v", "libx264", "-tune", "stillimage",
         "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(out_path)])


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("tracks", type=Path, help="曲を入れたフォルダ")
    parser.add_argument("image", type=Path, help="背景画像")
    parser.add_argument("-o", "--out", type=Path, required=True, help="出力するmp4")
    parser.add_argument("--minutes", type=float, help="この長さになるまで曲を繰り返す")
    parser.add_argument("--crossfade", type=float, default=3.0, help="曲のつなぎの秒数")
    parser.add_argument("--shorts", action="store_true", help="縦型45秒動画も作る")
    args = parser.parse_args()

    tracks = sorted(p for p in args.tracks.iterdir() if p.suffix.lower() in AUDIO_EXTS)
    if not tracks:
        sys.exit(f"{args.tracks} に音声ファイルがありません")
    args.out.parent.mkdir(parents=True, exist_ok=True)

    playlist = build_playlist(tracks, args.minutes, args.crossfade)
    with tempfile.TemporaryDirectory() as tmp:
        audio = Path(tmp) / "mix.m4a"
        print(f"{len(playlist)}曲をつないでいます...")
        mix_audio(playlist, args.crossfade, audio)
        print("動画を書き出しています...")
        render_video(args.image, audio, args.out)

    chapters = args.out.with_suffix(".chapters.txt")
    lines = [f"{timestamp(start)} {track.stem.lstrip('0123456789_- ')}" for track, start in playlist]
    chapters.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"完成: {args.out}\nチャプター: {chapters}")

    if args.shorts:
        short = args.out.with_name(args.out.stem + "_shorts.mp4")
        render_short(args.image, tracks[0], short)
        print(f"ショート: {short}")


if __name__ == "__main__":
    main()
