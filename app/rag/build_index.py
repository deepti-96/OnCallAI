# Placeholder for building a vector index from app/rag/data/examples.jsonl
# In hackathon, you may directly load examples in analyst or wire Chroma here.
import json, os
DATA = 'app/rag/data/examples.jsonl'
if os.path.exists(DATA):
    print('Index build stub: loaded examples:', sum(1 for _ in open(DATA,'r',encoding='utf-8')))
else:
    print('No examples found:', DATA)
