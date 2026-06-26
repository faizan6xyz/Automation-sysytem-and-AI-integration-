import torch
from PIL import Image
import numpy as np
import os

def image_to_tensor(name, folder_path="SYSTEM/Data", target_size=(336, 336), 
                    normalize=True, mean=(0.48145466, 0.4578275, 0.40821073), 
                    std=(0.26862954, 0.26130258, 0.27577711)):
    file_path = os.path.join(folder_path, name)
    if not os.path.exists(file_path):
        print(f"Error: {file_path} not found")
        return None
    try:
        # 1. Load the image using Pillow
        img = Image.open(file_path).convert("RGB")
        # 2. Resize the image (Vision encoders usually require fixed sizes)
        img = img.resize(target_size, Image.Resampling.LANCZOS)
        # 3. Convert to NumPy array (Height, Width, Channels)
        img_array = np.array(img)
        # 4. Normalize pixel values
        if normalize:
            # Convert from 0-255 to 0.0-1.0
            img_normalized = img_array.astype(np.float32) / 255.0
            # Apply standard normalization (ImageNet/CLIP stats)
            mean_array = np.array(mean, dtype=np.float32).reshape(1, 1, 3)
            std_array = np.array(std, dtype=np.float32).reshape(1, 1, 3)
            img_normalized = (img_normalized - mean_array) / std_array
        else:
            # Just scale to 0-1
            img_normalized = img_array.astype(np.float32) / 255.0
        # 5. Reorder dimensions from (H, W, C) to (C, H, W) , PyTorch expects channels first: [3, H, W]
        img_tensor = torch.from_numpy(img_normalized).permute(2, 0, 1)
        # 6. Add a "batch" dimension , Models expect [Batch_Size, Channels, Height, Width] -> [1, 3, H, W]
        img_tensor = img_tensor.unsqueeze(0)
        return img_tensor
    except Exception as e:
        print(f"Error processing {name}: {str(e)}")
        return None
def images_to_tensor_batch(image_names, folder_path="SYSTEM/Data", **kwargs):
    tensors = []
    valid_names = []    
    for name in image_names:
        tensor = image_to_tensor(name, folder_path, **kwargs)
        if tensor is not None:
            tensors.append(tensor)
            valid_names.append(name)
    if not tensors:
        print("No valid images processed")
        return None
    # Stack into a single batch tensor [N, C, H, W]
    batch_tensor = torch.cat(tensors, dim=0)
    print(f"Created batch tensor with shape: {batch_tensor.shape}")
    return batch_tensor, valid_names
def tensor_to_image(tensor, output_path=None):
    if tensor is None:
        return None    
    # Remove batch dimension if present
    if tensor.dim() == 4:
        tensor = tensor.squeeze(0)
    # Move from CPU/GPU and convert to numpy
    img_array = tensor.permute(1, 2, 0).cpu().numpy()
    # Denormalize if needed (assuming standard normalization was applied)
    if img_array.min() < 0 or img_array.max() > 1:
        mean = np.array([0.48145466, 0.4578275, 0.40821073])
        std = np.array([0.26862954, 0.26130258, 0.27577711])
        img_array = img_array * std + mean
    # Clip and scale to 0-255
    img_array = np.clip(img_array, 0, 1) * 255
    img_array = img_array.astype(np.uint8)
    img = Image.fromarray(img_array)
    if output_path:
        img.save(output_path)
        print(f"Saved image to {output_path}")
    return img
if __name__ == "__main__":
    # Single image
    tensor = image_to_tensor("screenshot.png")
    if tensor is not None:
        print(f"Tensor Shape: {tensor.shape}")
        print(f"Tensor dtype: {tensor.dtype}")
        print(f"Tensor range: [{tensor.min():.4f}, {tensor.max():.4f}]")
    
    # Batch processing
    images = ["img1.jpg", "img2.png", "img3.jpeg"]
    batch_tensor, valid = images_to_tensor_batch(images)
    
    # Test round-trip conversion
    img = tensor_to_image(tensor, "output_test.png")