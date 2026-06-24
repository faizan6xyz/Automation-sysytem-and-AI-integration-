import base64
def imageconvert (name):
    with open("name", "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode("utf-8")
    return image_b64
