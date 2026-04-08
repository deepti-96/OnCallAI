import os
from openai import OpenAI
import tiktoken
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def embed_chunks(chunks, model="text-embedding-3-small", max_tokens=7500):
    enc = tiktoken.encoding_for_model(model)
    embeddings = []
    safe_chunks = []

    for chunk in chunks:
        tokens = enc.encode(chunk)

        if len(tokens) > max_tokens:
            print(f"⚠️ Chunk too big ({len(tokens)} tokens) → splitting...")
            start = 0
            while start < len(tokens):
                sub_tokens = tokens[start:start + max_tokens]
                sub_text = enc.decode(sub_tokens)
                resp = client.embeddings.create(model=model, input=sub_text)
                embeddings.append(resp.data[0].embedding)
                safe_chunks.append(sub_text)
                start += max_tokens
        else:
            resp = client.embeddings.create(model=model, input=chunk)
            embeddings.append(resp.data[0].embedding)
            safe_chunks.append(chunk)

    return embeddings, safe_chunks
