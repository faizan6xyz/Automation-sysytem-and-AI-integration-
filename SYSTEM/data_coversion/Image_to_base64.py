import base64
import os
def image_to_base64(name, folder_path="SYSTEM/Data"):
    file_path = os.path.join(folder_path, name)
    if not os.path.exists(file_path):
        print(f"Error: {file_path} not found")
        return None
    try:
        with open(file_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode("utf-8")
        return image_b64
    except Exception as e:
        print(f"Error converting {name} to base64: {str(e)}")
        return None
def image_to_base64_with_prefix(name, folder_path="SYSTEM/Data"):
    file_path = os.path.join(folder_path, name)
    if not os.path.exists(file_path):
        print(f"Error: {file_path} not found")
        return None
    try:
        # A MIME type (Multipurpose Internet Mail Extensions) is a standard way to identify the format and nature of a file on the internet
        ext = os.path.splitext(name)[1].lower()
        mime_types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.bmp': 'image/bmp',
            '.webp': 'image/webp',
            '.tiff': 'image/tiff'
        }
        mime_type = mime_types.get(ext, 'image/png')  # Default to PNG
        with open(file_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode("utf-8")
        data_uri = f"data:{mime_type};base64,{image_b64}"
        return data_uri
    except Exception as e:
        print(f"Error converting {name}: {str(e)}")
        return None
def base64_to_image(base64_string, output_path):
    try:
        # Handle data URI format (remove prefix if present)
        if ',' in base64_string:
            base64_string = base64_string.split(',')[1]
        # Decode and save
        image_data = base64.b64decode(base64_string)
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(image_data)
        print(f"Image saved to: {output_path}")
        return output_path
    except Exception as e:
        print(f"Error decoding base64: {str(e)}")
        return None
def get_base64_size_info(base64_string):
    if not base64_string:
        return None
    # Remove data URI prefix if present
    if ',' in base64_string:
        b64_data = base64_string.split(',')[1]
    else:
        b64_data = base64_string
    # Calculate sizes
    b64_size = len(b64_data)
    original_size = len(base64.b64decode(b64_data))
    overhead = ((b64_size - original_size) / original_size) * 100
    return {
        'base64_size_bytes': b64_size,
        'original_size_bytes': original_size,
        'overhead_percentage': round(overhead, 2),
        'base64_size_kb': round(b64_size / 1024, 2),
        'original_size_kb': round(original_size / 1024, 2)
    }
if __name__ == "__main__":
    # Basic conversion
    b64 = image_to_base64("screenshot.png")
    if b64:
        print(f"Base64 length: {len(b64)} characters")
        print(f"First 100 chars: {b64[:100]}...")
    # With data URI prefix (for APIs/HTML)
    data_uri = image_to_base64_with_prefix("image.jpg")
    # Round-trip test
    if b64:
        base64_to_image(b64, "SYSTEM/Data/decoded_test.png")
    # Size analysis
    if b64:
        info = get_base64_size_info(b64)
        for key, value in info.items():
            print(f"  {key}: {value}")