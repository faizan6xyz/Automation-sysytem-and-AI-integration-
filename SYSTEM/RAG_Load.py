import os
import re
import numpy as np
import faiss
from fastembed import TextEmbedding
from rank_bm25 import BM25Okapi
CHUNK_PATH = "SYSTEM/RAG_data"
INDEX_PATH = os.path.join(CHUNK_PATH, "rag_index.faiss")
CHUNKS_PATH = os.path.join(CHUNK_PATH, "chunks.npy")
META_PATH = os.path.join(CHUNK_PATH, "metadata.npy")
model = TextEmbedding("BAAI/bge-base-en-v1.5")
index = faiss.read_index(INDEX_PATH)
all_chunks = np.load(CHUNKS_PATH, allow_pickle=True).tolist()
print(f"Loaded {len(all_chunks)} chunks from chunks.npy")
if os.path.exists(META_PATH):
    all_metadata = np.load(META_PATH, allow_pickle=True).tolist()
else:
    all_metadata = [{"source": "unknown", "chunk_id": i} for i in range(len(all_chunks))]
if index.ntotal != len(all_chunks):
    raise ValueError(
        f"Mismatch between FAISS index ({index.ntotal} vectors) and "
        f"chunks.npy ({len(all_chunks)} chunks). Rebuild the index."
    )
if len(all_metadata) != len(all_chunks):
    print(
        f"Warning: metadata count ({len(all_metadata)}) != chunk count "
        f"({len(all_chunks)}). Falling back to placeholder metadata."
    )
    all_metadata = [{"source": "unknown", "chunk_id": i} for i in range(len(all_chunks))]
def tokenize(text: str):
    return re.findall(r"\w+", text.lower())
tokenized_chunks = [tokenize(chunk) for chunk in all_chunks]
bm25 = BM25Okapi(tokenized_chunks)
print("BM25 index created.")
def embed_text(text: str) -> np.ndarray:
    return np.array(list(model.embed([text])), dtype=np.float32)
def retrieve(query: str, k: int = 5, rrf_k: int = 60):
    n = len(all_chunks)
    query_embedding = embed_text(query)
    faiss.normalize_L2(query_embedding)
    dense_scores, dense_indices = index.search(query_embedding, k=n)
    dense_indices = dense_indices[0]  # ranked order, best first
    tokenized_query = tokenize(query)
    bm25_scores = bm25.get_scores(tokenized_query)
    bm25_ranked_indices = np.argsort(bm25_scores)[::-1]  # ranked order, best first
    rrf_scores = np.zeros(n)
    for rank, idx in enumerate(dense_indices):
        rrf_scores[idx] += 1.0 / (rrf_k + rank + 1)
    for rank, idx in enumerate(bm25_ranked_indices):
        rrf_scores[idx] += 1.0 / (rrf_k + rank + 1)
    top_indices = np.argsort(rrf_scores)[::-1][:k]
    results = [
        {
            "text": all_chunks[idx],
            "score": float(rrf_scores[idx]),
            "source": all_metadata[idx].get("source", "unknown"),
            "chunk_id": all_metadata[idx].get("chunk_id", idx),
        }
        for idx in top_indices
    ]
    return results
if __name__ == "__main__":
    query = "your test query here"
    results = retrieve(query, k=5)
    for r in results:
        print(f"[{r['score']:.4f}] ({r['source']} #{r['chunk_id']}) {r['text'][:120]}...")