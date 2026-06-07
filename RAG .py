import os
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
folder_path = "Data"
all_chunks = []
for file in os.listdir(folder_path):
    if file.endswith(".txt"):
        with open(os.path.join(folder_path, file), "r", encoding="utf-8") as f:
            text = f.read()
        paragraphs = text.split("\n\n")
        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if paragraph:
                all_chunks.append(paragraph)
print("Total chunks:", len(all_chunks))
model = SentenceTransformer("BAAI/bge-base-en-v1.5")
embeddings = model.encode(all_chunks,convert_to_numpy=True)
print("Embedding shape:", embeddings.shape)
dimension = embeddings.shape[1]
index = faiss.IndexFlatL2(dimension)
index.add(np.array(embeddings, dtype=np.float32))
print("Vectors stored:", index.ntotal)
faiss.write_index(index, "rag_index.faiss") # Stores the vector embeddings
np.save("chunks.npy", np.array(all_chunks)) # Stores the original paragraph text corresponding to each vector 
print("FAISS index saved successfully.")