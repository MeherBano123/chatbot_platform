-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Websites table
CREATE TABLE websites (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    url TEXT NOT NULL,
    embed_hash VARCHAR(64) UNIQUE NOT NULL,
    scrape_permission BOOLEAN DEFAULT TRUE,
    status VARCHAR(50) DEFAULT 'pending', -- pending, scraping, active, failed, paused
    last_scraped_at TIMESTAMP,
    scrape_frequency INTEGER DEFAULT 1, -- days between scrapes
    max_pages INTEGER DEFAULT 50,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(url, embed_hash)
);

-- Scraped pages table
CREATE TABLE website_pages (
    id SERIAL PRIMARY KEY,
    website_id INTEGER NOT NULL REFERENCES websites(id) ON DELETE CASCADE,
    url VARCHAR(2048) NOT NULL,
    title TEXT,
    content TEXT,
    metadata JSONB, -- store additional info like headers, meta tags, etc.
    status VARCHAR(50) DEFAULT 'active', -- active, deleted, error
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(website_id, url)
);


-- DOCUMENT UPLOADS TABLE FOR DOCUMENT INGESTION PIPELINE

CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    website_id INTEGER NOT NULL REFERENCES websites(id) ON DELETE CASCADE,

    -- File information
    file_name VARCHAR(255) NOT NULL,
    file_extension VARCHAR(10) NOT NULL,
    file_size BIGINT,
    file_path TEXT,

    -- Document-level metadata
    metadata JSONB,  -- author, page_count, created_date, etc.

    -- Processing status
    status VARCHAR(50) DEFAULT 'pending',
    error_message TEXT,

    -- Timestamps
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

--- documents_pages table for storing content of documents page vise
CREATE TABLE document_pages (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    website_id INTEGER NOT NULL REFERENCES websites(id) ON DELETE CASCADE,

    page_number INTEGER NOT NULL,
    content TEXT NOT NULL,

    -- Optional metadata
    token_count INTEGER,
    metadata JSONB,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (document_id, page_number)
);

-- Vector embeddings table for website_pages  (using pgvector)
-- Optimized chunk storage with metadata
CREATE TABLE website_embeddings (
    id SERIAL PRIMARY KEY,

    -- Foreign keys
    website_id INTEGER NOT NULL REFERENCES websites(id) ON DELETE CASCADE,
    website_page_id INTEGER NOT NULL REFERENCES website_pages(id) ON DELETE CASCADE,

    -- Chunk data
    chunk_text TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,

    -- might have to alter the embeddings dimensions if embeddings model is changed
    embedding vector(1024),

    -- Metadata
    source TEXT, -- URL or file name
    token_count INTEGER,
    tags TEXT[],

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        
    -- Prevent duplicate chunks per page
    UNIQUE (website_page_id, chunk_index)
    
   
);
-- Vector embeddings table for documents  (using pgvector)

CREATE TABLE document_embeddings (
    id SERIAL PRIMARY KEY,

    -- Foreign keys
    website_id INTEGER NOT NULL REFERENCES websites(id) ON DELETE CASCADE,
    
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE, --for uploaded documents
    document_page_id INTEGER NOT NULL REFERENCES document_pages(id) ON DELETE CASCADE,
   
    -- Chunk data
    chunk_text TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,

    -- might have to alter the embeddings dimensions if embeddings model is changed
    embedding vector(1024),

    -- Metadata
    source TEXT, -- URL or file name
    token_count INTEGER,
    tags TEXT[],

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    
    -- Prevent duplicate chunks per page
    UNIQUE (document_page_id, chunk_index)
    
   
);

-- FAQs table
CREATE TABLE faqs (
    id SERIAL PRIMARY KEY,
    website_id INTEGER NOT NULL REFERENCES websites(id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    category VARCHAR(100),
    priority INTEGER DEFAULT 0, -- higher priority FAQs shown first
    is_active BOOLEAN DEFAULT TRUE,

    -- might have to change the dimensions later, if embedding model is changed
    embedding vector(1024), -- embedding of the question for semantic search
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Scraping queue table (for managing scraping jobs)
CREATE TABLE scraping_queue (
    id SERIAL PRIMARY KEY,
    website_id INTEGER NOT NULL REFERENCES websites(id) ON DELETE CASCADE,
    status VARCHAR(50) DEFAULT 'pending', -- pending, in_progress, completed, failed
    priority INTEGER DEFAULT 0,
    error_message TEXT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE epay_embeddings (
    id SERIAL PRIMARY KEY,
    website_id INTEGER NOT NULL REFERENCES websites(id) ON DELETE CASCADE,
    heading TEXT,
    sub_heading TEXT,
    chunk_text TEXT NOT NULL,
    embedding VECTOR(1024),  -- E5 Large V2 = 1024 dim
    token_count INT,
    meta_data TEXT,
    source VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- ============================================================================
-- INDEXES
-- ============================================================================

-- Websites indexes
CREATE INDEX idx_websites_embed_hash ON websites(embed_hash);
CREATE INDEX idx_websites_status ON websites(status);

-- Website Pages indexes
CREATE INDEX idx_website_pages_website_id ON website_pages(website_id);
CREATE INDEX idx_website_pages_url ON website_pages(url);
CREATE INDEX idx_website_pages_status ON website_pages(status);

-- Documents indexes 
CREATE INDEX idx_documents_website_id ON documents(website_id);
CREATE INDEX idx_documents_status ON documents(status);
CREATE INDEX idx_documents_file_extension ON documents(file_extension);
CREATE INDEX idx_documents_uploaded_at ON documents(uploaded_at DESC);


-- Document Pages indexes
CREATE INDEX idx_doc_pages_website_id ON document_pages(website_id);
CREATE INDEX idx_doc_pages_document_id ON document_pages(document_id);


-- Website Embeddings indexes
CREATE INDEX idx_web_embed_website_id ON website_embeddings(website_id);
CREATE INDEX idx_web_embed_website_page_id ON website_embeddings(website_page_id);

-- Document Embeddings indexes
CREATE INDEX idx_doc_embed_website_id ON document_embeddings(website_id);
CREATE INDEX idx_doc_embed_document_id ON document_embeddings(document_id);
CREATE INDEX idx_doc_embed_doc_page_id ON document_embeddings(document_page_id);
 

-- Vector similarity search for website content
CREATE INDEX idx_web_embeddings_vector ON website_embeddings USING hnsw (embedding vector_cosine_ops);

-- Vector similarity search for website documents

CREATE INDEX idx_doc_embeddings_vector ON document_embeddings USING hnsw (embedding vector_cosine_ops);

-- FAQs indexes
CREATE INDEX idx_faqs_embedding ON faqs USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_faqs_website_id ON faqs(website_id);
CREATE INDEX idx_faqs_is_active ON faqs(is_active);

-- Scraping queue indexes
CREATE INDEX idx_scraping_queue_website_id ON scraping_queue(website_id);
CREATE INDEX idx_scraping_queue_status ON scraping_queue(status);

-- Embeddings table indexes (this table stores structured chunks of text with their embeddings for semantic search)
CREATE INDEX idx_embeddings_website_id ON epay_embeddings(website_id);

CREATE INDEX idx_embeddings_vector ON epay_embeddings USING hnsw (embedding vector_cosine_ops) ;