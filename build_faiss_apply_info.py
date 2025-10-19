from sentence_transformers import SentenceTransformer
import faiss
import pickle
import os
import textwrap

DOCS_FOLDER = "docs"

# --- Simple chunking function ---
def chunk_text(text: str, chunk_size: int = 500, overlap: int = 100):
    text = text.replace("\n", " ").strip()
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk.strip())
        start += chunk_size - overlap
    return chunks

# --- Collect text chunks from your docs folder ---
data = []
for file in os.listdir(DOCS_FOLDER):
    if file.endswith(".txt"):
        path = os.path.join(DOCS_FOLDER, file)
        with open(path, "r", encoding="utf-8") as f:
            full_text = f.read().strip()
            source = "heimstaden" if "heim" in file.lower() else "bostad"
            chunks = chunk_text(full_text)
            for i, chunk in enumerate(chunks):
                data.append({
                    "source": source,
                    "chunk_id": i,
                    "text": chunk
                })


# Embed each chunk ---
model = SentenceTransformer("all-MiniLM-L6-v2")
texts = [d["text"] for d in data]
embeddings = model.encode(texts, convert_to_numpy=True)

# --- Step 3. Build FAISS index ---
dimension = embeddings.shape[1]
index = faiss.IndexFlatL2(dimension)
index.add(embeddings)

# Save FAISS index and metadata ---
faiss.write_index(index, "apply_info.index")
with open("apply_info_meta.pkl", "wb") as f:
    pickle.dump(data, f)

print(f"Built FAISS with {len(data)} chunks")
