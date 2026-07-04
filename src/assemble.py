"""Stage 6 — assemble frames + audio into the deliverable MP4 with ffmpeg."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUDIO_DIR = ROOT / "assets" / "audio"


def _ambient_bed():
    for ext in ("mp3", "wav", "m4a", "ogg"):
        clips = sorted(AUDIO_DIR.glob(f"*.{ext}"))
        if clips:
            return clips[0]
    return None


def assemble(frames_dir, audio_path, out_path, fps=30, frame_ext="png",
             ambient=False, ambient_db=-22, silent_duration=None):
    """Mux frames (+ optional voiceover, + optional ducked ambient bed).

    silent_duration: set when there is no voiceover (--no-voice fixture runs);
    produces a silent MP4 of that length.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-framerate", str(fps),
           "-i", str(Path(frames_dir) / f"f%06d.{frame_ext}")]

    bed = _ambient_bed() if ambient else None
    if audio_path and bed:
        cmd += ["-i", str(audio_path), "-stream_loop", "-1", "-i", str(bed),
                "-filter_complex",
                f"[2:a]volume={ambient_db}dB[bed];[1:a][bed]amix=inputs=2:duration=first[a]",
                "-map", "0:v", "-map", "[a]"]
    elif audio_path:
        cmd += ["-i", str(audio_path)]
    elif silent_duration:
        cmd += ["-f", "lavfi", "-t", f"{silent_duration:.3f}",
                "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]

    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "21",
            "-preset", "medium", "-c:a", "aac", "-b:a", "160k",
            "-shortest", "-movflags", "+faststart", str(out_path)]
    subprocess.run(cmd, check=True, capture_output=True)
    return str(out_path)


def write_caption_file(caption_text, out_path):
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(caption_text + "\n")
    return str(out_path)
