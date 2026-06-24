import torch
from transformers import AutoProcessor, AutoModel
from PIL import Image
import os
_model_cache = {}
def _get_vision_model(model_name="openai/clip-vit-base-patch32"):
    """Load and cache vision model to avoid repeated loading"""
    if model_name not in _model_cache:
        print(f"Loading model: {model_name}...")
        processor = AutoProcessor.from_pretrained(model_name)
        model = AutoModel.from_pretrained(model_name)
        model.eval()  # Set to evaluation mode
        _model_cache[model_name] = (processor, model)
        print("Model loaded successfully!")
    return _model_cache[model_name]
def run_vision_encoder(name, folder_path="SYSTEM/Data", model_name="openai/clip-vit-base-patch32"):
    file_path = os.path.join(folder_path, name)
    # Validate file exists
    if not os.path.exists(file_path):
        print(f"Error: {file_path} not found")
        return None
    # Validate file is an image
    valid_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp'}
    if not any(file_path.lower().endswith(ext) for ext in valid_extensions):
        print(f"Warning: {name} may not be a valid image file")
    try:
        # Load cached model
        processor, model = _get_vision_model(model_name)
        # Load and preprocess image
        image = Image.open(file_path).convert("RGB")
        inputs = processor(images=image, return_tensors="pt")
        # Generate embedding
        with torch.no_grad():
            outputs = model.get_image_features(**inputs)
        image_embedding = outputs.image_embeds
        print(f"[{name}] Embedding shape: {image_embedding.shape}")
        print(f"[{name}] Embedding norm: {torch.norm(image_embedding).item():.4f}")
        return image_embedding
    except Exception as e:
        print(f"Error processing {name}: {str(e)}")
        return None
def run_vision_encoder_batch(image_names, folder_path="SYSTEM/Data", **kwargs):
    results = {}
    for name in image_names:
        embedding = run_vision_encoder(name, folder_path, **kwargs)
        if embedding is not None:
            results[name] = embedding
    print(f"\nSuccessfully processed {len(results)}/{len(image_names)} images")
    return results
def compute_similarity(embedding1, embedding2):
    if embedding1 is None or embedding2 is None:
        return None
    # Normalize embeddings
    emb1_norm = embedding1 / embedding1.norm(dim=-1, keepdim=True)
    emb2_norm = embedding2 / embedding2.norm(dim=-1, keepdim=True)
    # Cosine similarity
    similarity = torch.mm(emb1_norm, emb2_norm.T).item()
    return similarity


if __name__ == "__main__":
    # Single image
    embedding = run_vision_encoder("n.png")
    # Batch processing (model loads only once)
    images = ["img1.jpg", "img2.png", "img3.jpeg"]
    embeddings = run_vision_encoder_batch(images)
    # Compare two images
    emb1 = run_vision_encoder("image1.jpg")
    emb2 = run_vision_encoder("image2.jpg")
    sim = compute_similarity(emb1, emb2)
    print(f"Similarity: {sim:.4f}")