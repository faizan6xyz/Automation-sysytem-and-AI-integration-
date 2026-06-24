import torch
from PIL import Image
import numpy as np
def image_to_tensor(image_path, target_size=(336, 336)):
    # 1. Load the image using Pillow
    img = Image.open(image_path).convert("RGB")
    # 2. Resize the image (Vision encoders usually require fixed sizes like 336x336)
    img = img.resize(target_size, Image.Resampling.LANCZOS)
    # 3. Convert to NumPy array (Height, Width, Channels)
    img_array = np.array(img)
    # 4. Normalize pixel values from 0-255 to 0.0-1.0 , Most vision models expect floats between 0 and 1
    img_normalized = img_array.astype(np.float32) / 255.0
    # 5. Reorder dimensions from (H, W, C) to (C, H, W) , PyTorch expects channels first: [3, 336, 336]
    img_tensor = torch.from_numpy(img_normalized).permute(2, 0, 1)
    # 6. Add a "batch" dimension ,  Models expect [Batch_Size, Channels, Height, Width] -> [1, 3, 336, 336]
    img_tensor = img_tensor.unsqueeze(0)
    return img_tensor
tensor = image_to_tensor("screenshot.png")
print(f"Tensor Shape: {tensor.shape}") 
