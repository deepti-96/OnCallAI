import os
from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings
from langchain_experimental.text_splitter import SemanticChunker

load_dotenv()

def chunk_text(text: str, chunk_size: int = 500):
    """
    Split text into semantic chunks using embeddings.
    :param text: Input text
    :param chunk_size: Approximate target size in tokens
    """
    # Use OpenAI embeddings (requires OPENAI_API_KEY in .env)
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

    # Initialize SemanticChunker
    splitter = SemanticChunker(
        embeddings,
        breakpoint_threshold_type="standard_deviation",  # options: "percentile", "standard_deviation"
        breakpoint_threshold_amount=1.0,                # lower = more splits
    )

    chunks = splitter.split_text(text)
    return chunks
