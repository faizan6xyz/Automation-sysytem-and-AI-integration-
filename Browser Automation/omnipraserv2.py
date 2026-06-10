from ultralytics import YOLO
from huggingface_hub import hf_hub_download
from PIL import Image
import torch

# Download model from HuggingFace
model_path = hf_hub_download(
    repo_id="microsoft/OmniParser-v2.0",
    filename="icon_detect/model.pt",
    repo_type="model"
)

# Load YOLO model
model = YOLO(model_path)

# Run on your screenshot
image_path = r"dataset/001_www_youtube_com_watch_v_C_9Q1ocl_O4.png"
results = model(image_path)

img = Image.open(image_path)
IMG_W, IMG_H = img.size

print(f"Image size: {IMG_W}x{IMG_H}")
print(f"Detected {len(results[0].boxes)} elements\n")

# Print all detected elements with coordinates
for i, box in enumerate(results[0].boxes):
    confidence = box.conf.item()
    x1, y1, x2, y2 = box.xyxy[0].tolist()

    # Center coordinates
    cx = int((x1 + x2) / 2)
    cy = int((y1 + y2) / 2)

    print(f"Element {i+1}:")
    print(f"  Center:     ({cx}, {cy})")
    print(f"  Box:        ({int(x1)}, {int(y1)}) → ({int(x2)}, {int(y2)})")
    print(f"  Confidence: {confidence:.2f}")
    print()