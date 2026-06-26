from faster_whisper import WhisperModel
import os
# Model sizes: tiny, base, small, medium, large-v3
# On RTX 2050 (4GB VRAM), "small" or "medium" run comfortably with int8/float16
model = WhisperModel(
    "medium",
    device="cuda",          # use "cpu" if you hit VRAM issues
    compute_type="float16"  # use "int8" for even lower VRAM usage
)
def transcribe_audio(audio_path: str):
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found at '{audio_path}'. Check the path/filename.")
    segments, info = model.transcribe(
        audio_path,
        beam_size=5,
        language=None,        # None = auto-detect, or set "en", "hi", etc.
        vad_filter=True,       # filters out silence — big speed boost on real audio
        word_timestamps=False  # set True if you need word-level timing
    )
    print(f"Detected language: {info.language} (prob: {info.language_probability:.2f})")
    print(f"Audio duration: {info.duration:.2f}s\n")
    full_text = []
    for segment in segments:
        print(f"[{segment.start:.2f}s -> {segment.end:.2f}s] {segment.text}")
        full_text.append(segment.text)
    return " ".join(full_text).strip()
if __name__ == "__main__":
    transcript = transcribe_audio("input_audio.mp3")
    print(transcript)