import cv2
import os
def extract_frames(name, data_dir="SYSTEM/Data", frames_per_second=1, quality=95):
    video_path = os.path.join(data_dir, name)
    if not os.path.exists(video_path):
        print(f"{video_path} not found")
        return None
    video_name = os.path.splitext(os.path.basename(video_path))[0]
    base_dir = os.path.dirname(video_path)
    out_dir = os.path.join(base_dir, video_name)
    os.makedirs(out_dir, exist_ok=True)
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps == 0:
        print(f"Warning: Could not determine FPS for {video_name}")
        cap.release()
        return None
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_interval = max(1, round(fps / frames_per_second))
    print(f"[{video_name}] FPS: {fps}, Total frames: {total_frames}, Extracting every {frame_interval} frames")
    frame_idx = 0
    saved_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % frame_interval == 0:
            out_path = os.path.join(out_dir, f"frame_{saved_idx:04d}.jpg")
            cv2.imwrite(out_path, frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
            saved_idx += 1
            # Progress tracking
            if saved_idx % 10 == 0:
                progress = (frame_idx / total_frames) * 100
                print(f"Progress: {progress:.1f}% ({saved_idx} frames saved)")
        frame_idx += 1
    cap.release()
    print(f"[{video_name}] Saved {saved_idx} frames to {out_dir}/")
    return out_dir
def extract_frames_batch(video_names, data_dir="SYSTEM/Data", **kwargs):
    results = {}
    for name in video_names:
        result = extract_frames(name, data_dir, **kwargs)
        results[name] = result
    return results


if __name__ == "__main__":
    # Single video
    extract_frames("x.mp4")
    # Or batch processing
    videos = ["video1.mp4", "video2.mp4", "video3.mp4"]
    extract_frames_batch(videos, frames_per_second=5)