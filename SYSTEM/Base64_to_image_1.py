import base64
def base64_to_image(base64_string, output_path="output_image.png"):
    try:
        # 1. Decode the base64 string to bytes , Note: If your string starts with "data:image/png;base64,", you need to remove that part first
        if "," in base64_string:
            base64_string = base64_string.split(",")[1]
        image_data = base64.b64decode(base64_string)
        # 2. Write the bytes to a file
        with open(output_path, "wb") as f:
            f.write(image_data)
        print(f" Image saved successfully to: {output_path}")
    except Exception as e:
        print(f" Error unable to covnert : {e}")
        
# This method writes the binary data directly to disk without loading it into memory as an image object first.
# Use this if you just want to save the file from your automation script.
