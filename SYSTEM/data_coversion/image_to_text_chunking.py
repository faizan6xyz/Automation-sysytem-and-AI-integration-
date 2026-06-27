import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from vison_model_Qwen3b import describe_image
result , source = describe_image("h.png")
print(result)
from Rag_create import build_index_from_text
saving = build_index_from_text(result , source_name= source)