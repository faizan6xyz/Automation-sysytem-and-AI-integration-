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
            if paragraph:
                all_chunks.append(paragraph)
print(f"Total chunks: {len(all_chunks)}")
model = SentenceTransformer("BAAI/bge-base-en-v1.5")
embeddings = model.encode(all_chunks, convert_to_numpy=True)
print("Embedding shape:", embeddings.shape)
index = faiss.read_index("rag_index.faiss")
all_chunks = np.load("chunks.npy", allow_pickle=True)
from rank_bm25 import BM25Okapi
tokenized_chunks = [chunk.lower().split() for chunk in all_chunks]
bm25 = BM25Okapi(tokenized_chunks)
print("BM25 index created.")
def retrieve(query, k=1):
    query_embedding = model.encode("Represent this sentence for searching relevant passages: " + query, convert_to_numpy=True)
    query_embedding = np.array([query_embedding], dtype=np.float32)
    faiss.normalize_L2(query_embedding)
    dense_scores, dense_indices = index.search(query_embedding, k=len(all_chunks))
    dense_scores = dense_scores[0]
    dense_indices = dense_indices[0]
    tokenized_query = query.lower().split()
    bm25_scores = bm25.get_scores(tokenized_query)
    aligned_dense_scores = np.zeros(len(all_chunks))
    for score, idx in zip(dense_scores, dense_indices):
        aligned_dense_scores[idx] = score
    dense_scores_norm = (aligned_dense_scores - aligned_dense_scores.min()) / \
                        (aligned_dense_scores.max() - aligned_dense_scores.min() + 1e-8)
    bm25_scores_norm = (bm25_scores - bm25_scores.min()) / (bm25_scores.max() - bm25_scores.min() + 1e-8)
    final_scores = (0.7 * dense_scores_norm + 0.3 * bm25_scores_norm)
    top_indices = np.argsort(final_scores)[::-1][:k]
    return [(all_chunks[idx], final_scores[idx]) for idx in top_indices]
if __name__ == "__main__":
    while True:
        query = input("Enter your query (or 'exit' to quit): ")
        if query.lower() == "exit":
            break
        print("\nRetrieving relevant chunks...\n")
        retrieve(query)