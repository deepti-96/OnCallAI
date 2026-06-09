create extension if not exists vector with schema extensions;

create table if not exists rag_documents (
  id uuid primary key,
  title text not null,
  content text not null,
  doc_type text not null default 'knowledge',
  source text not null default 'seeded',
  metadata jsonb not null default '{}'::jsonb,
  embedding extensions.vector(768) not null,
  created_at timestamptz not null default now()
);

create index if not exists rag_documents_embedding_idx
  on rag_documents
  using ivfflat (embedding extensions.vector_cosine_ops)
  with (lists = 50);

create or replace function match_rag_documents(
  query_embedding extensions.vector(768),
  match_count integer default 3
)
returns table (
  id uuid,
  title text,
  content text,
  doc_type text,
  source text,
  metadata jsonb,
  similarity double precision
)
language sql
as $$
  select
    rag_documents.id,
    rag_documents.title,
    rag_documents.content,
    rag_documents.doc_type,
    rag_documents.source,
    rag_documents.metadata,
    1 - (rag_documents.embedding <=> query_embedding) as similarity
  from rag_documents
  order by rag_documents.embedding <=> query_embedding
  limit match_count;
$$;
