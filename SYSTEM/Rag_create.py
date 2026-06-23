import os
os.environ["FASTEMBED_CACHE_PATH"] = r"C:\Users\faiza\fastembed_models"
import numpy as np
import faiss
from fastembed import TextEmbedding
from rank_bm25 import BM25Okapi
_model = TextEmbedding("BAAI/bge-base-en-v1.5")
def chunk_text(text, chunk_size=300, overlap=50):
    """Simple word-based chunking with overlap."""
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = start + chunk_size
        chunks.append(" ".join(words[start:end]))
        start += chunk_size - overlap
    return chunks
def build_index(file_name,
                folder_path="../Data",
                chunk_path="../",
                index_path="rag_index.faiss",
                chunks_path="chunks.npy"):
    file_path = os.path.join(folder_path, file_name)
    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read().strip()
    print(f"File loaded: {file_name}")
    new_chunks = chunk_text(text)
    print(f"Split into {len(new_chunks)} chunk(s)")
    full_index_path = os.path.join(chunk_path, index_path)
    full_chunks_path = os.path.join(chunk_path, chunks_path)
    new_embeddings = np.array(list(_model.embed(new_chunks)), dtype=np.float32)
    print("Embedding shape:", new_embeddings.shape)
    faiss.normalize_L2(new_embeddings)
    dimension = new_embeddings.shape[1]
    if os.path.exists(full_index_path):
        index = faiss.read_index(full_index_path)
        print(f"Loaded existing FAISS index ({index.ntotal} vectors)")
    else:
        index = faiss.IndexFlatIP(dimension)
        print("Created new FAISS index")
    existing_chunks = np.load(full_chunks_path, allow_pickle=True).tolist() \
                       if os.path.exists(full_chunks_path) else []
    index.add(new_embeddings)
    existing_chunks.extend(new_chunks)
    tmp_index_path = full_index_path + ".tmp"
    tmp_chunks_path = full_chunks_path + ".tmp"
    faiss.write_index(index, tmp_index_path)
    np.save(tmp_chunks_path, np.array(existing_chunks, dtype=object))
    os.replace(tmp_index_path, full_index_path)
    os.replace(tmp_chunks_path, full_chunks_path)
    print("Vectors stored:", index.ntotal)
    print(f"chunks.npy updated → {len(existing_chunks)} chunk(s) total")
    bm25 = BM25Okapi([chunk.lower().split() for chunk in existing_chunks])
    print("BM25 index rebuilt over all chunks.")
    return bm25
if __name__ == "__main__":
    build_index("my_document.txt")