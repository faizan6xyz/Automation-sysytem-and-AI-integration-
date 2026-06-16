import os
import numpy as np
import faiss
from fastembed import TextEmbedding
from rank_bm25 import BM25Okapi
model = TextEmbedding("BAAI/bge-base-en-v1.5")
index = faiss.read_index("rag_index.faiss")
all_chunks = np.load("chunks.npy", allow_pickle=True).tolist()
print(f"Loaded {len(all_chunks)} chunks from chunks.npy")
tokenized_chunks = [chunk.lower().split() for chunk in all_chunks]
bm25 = BM25Okapi(tokenized_chunks)
print("BM25 index created.")
def embed_text(text: str) -> np.ndarray:
    """Returns a (1, dim) float32 array."""
    return np.array(list(model.embed([text])), dtype=np.float32)
def retrieve(query: str, k: int = 1):
    query_embedding = embed_text(query)
    faiss.normalize_L2(query_embedding)
    dense_scores, dense_indices = index.search(query_embedding, k=len(all_chunks))
    dense_scores  = dense_scores[0]
    dense_indices = dense_indices[0]
    tokenized_query = query.lower().split()
    bm25_scores = bm25.get_scores(tokenized_query)
    aligned_dense_scores = np.zeros(len(all_chunks))
    for score, idx in zip(dense_scores, dense_indices):
        aligned_dense_scores[idx] = score
    def normalize(arr):
        min_val, max_val = arr.min(), arr.max()
        return (arr - min_val) / (max_val - min_val + 1e-8)
    dense_scores_norm = normalize(aligned_dense_scores)
    bm25_scores_norm  = normalize(bm25_scores)
    final_scores = 0.7 * dense_scores_norm + 0.3 * bm25_scores_norm
    top_indices  = np.argsort(final_scores)[::-1][:k]

    results = [(all_chunks[idx], final_scores[idx]) for idx in top_indices]
    return results
if __name__ == "__main__":
    while True:
        query = input("\nEnter your query (or 'exit' to quit): ")
        if query.lower() == "exit":
            break
        print("\nRetrieving relevant chunks...\n")
        results = retrieve(query, k=3)
        for i, (chunk, score) in enumerate(results, 1):
            print(f"[{i}] Score: {score:.4f}")
            print(f"     {chunk[:300]}...")   # print first 300 chars
            print()