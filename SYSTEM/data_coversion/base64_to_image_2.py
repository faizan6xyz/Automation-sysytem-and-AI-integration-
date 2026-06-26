import base64
from PIL import Image
import io
def base64_to_pil_image(base64_string):
    try:
        # Remove header if present (e.g., "data:image/png;base64,")
        if "," in base64_string:
            base64_string = base64_string.split(",")[1]
        # Decode and create a BytesIO object
        image_data = base64.b64decode(base64_string)
        image = Image.open(io.BytesIO(image_data))
        return image
    except Exception as e:
        print(f" Error: {e}")
        return None
    
# Use this if you want to open, resize, or modify the image immediately after converting.
# Use this if you are feeding this image into your Qwen-VL model or need to resize/crop it before saving.
