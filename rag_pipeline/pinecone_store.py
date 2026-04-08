import os
from pinecone import Pinecone, ServerlessSpec
from dotenv import load_dotenv

load_dotenv()

class PineconeStore:
    def __init__(self, index_name=None):
        api_key = os.getenv("PINECONE_API_KEY")
        env = os.getenv("PINECONE_ENV", "us-east-1")
        self.index_name = index_name or os.getenv("PINECONE_INDEX_NAME", "devops")

        # Init client
        self.pc = Pinecone(api_key=api_key)

        # Create index if it doesn’t exist
        if self.index_name not in [i["name"] for i in self.pc.list_indexes()]:
            self.pc.create_index(
                name=self.index_name,
                dimension=1536,  # for text-embedding-3-small
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region=env.split("-")[0])
            )

        self.index = self.pc.Index(self.index_name)

    def upsert(self, embeddings, chunks):
        vectors = [
            (f"chunk-{i}", emb, {"text": chunk})
            for i, (emb, chunk) in enumerate(zip(embeddings, chunks))
        ]
        self.index.upsert(vectors=vectors)
        print(f"✅ Upserted {len(vectors)} chunks into Pinecone index {self.index_name}")

    def query(self, query_embedding, top_k=5):
        results = self.index.query(vector=query_embedding, top_k=top_k, include_metadata=True)
        return [match["metadata"]["text"] for match in results["matches"]]
