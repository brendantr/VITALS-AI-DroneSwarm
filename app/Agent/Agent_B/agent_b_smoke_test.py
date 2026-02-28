from sentence_transformers import SentenceTransformer
import chromadb

EMBED_MODEL = "BAAI/bge-small-en-v1.5"
COLLECTION = "vitals_mission"
CHROMA_PATH = "./chroma_data"

def main():
    print("[*] Loading embedding model...")
    model = SentenceTransformer(EMBED_MODEL)

    # persistent chroma client
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    col = client.get_or_create_collection(COLLECTION)

    fact_text = "Person detected near debris field in sector B4, confidence 0.91, UAV_2."
    print("[*] Encoding and storing one fact...")
    emb = model.encode(fact_text, normalize_embeddings=True).tolist()

    # Optional: avoid duplicate-id crash if you rerun
    try:
        col.add(
            documents=[fact_text],
            embeddings=[emb],
            metadatas=[{"sector": "B4", "object": "person"}],
            ids=["obs_001"],
        )
    except Exception as e:
        print(f"[!] add skipped (likely duplicate id): {e}")

    query = "Recent human detections near sector B4?"
    print("[*] Querying back with:", query)
    q_emb = model.encode(query, normalize_embeddings=True).tolist()

    res = col.query(query_embeddings=[q_emb], n_results=3)
    print("[*] Results:", res["documents"], res["metadatas"])

if __name__ == "__main__":
    main()

