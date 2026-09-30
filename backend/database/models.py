import psycopg2
from psycopg2.extras import RealDictCursor, Json
import os
from dotenv import load_dotenv
from datetime import datetime
from werkzeug.utils import secure_filename
from flask import jsonify 
from utils.text_extractor import (
    extract_text_from_pdf,
    extract_text_from_docx,
    extract_text_from_txt,
    allowed_file
)
from utils.embeddings_generator import EmbeddingGenerator
import json

from utils.structural_chunking_embeddings import StructuralEmbeddingGenerator
load_dotenv()

class DatabaseManager:
    def __init__(self):
        self.config = {
            'host': os.getenv('HOST'),
            'user': os.getenv('USER'),
            'password': os.getenv('DB_PASSWORD'),
            'database': os.getenv('DATABASE'),
            'port': os.getenv('DB_PORT', 5432)
        }
    
    def get_connection(self):
        """Get PostgreSQL database connection"""
        return psycopg2.connect(**self.config)
    
    def store_page(self, website_id, url, title, content, metadata=None):
        """
        Store scraped page content
        
        Args:
            website_id: ID of the website
            url: Page URL
            title: Page title
            content: Page text content
            metadata: Optional dict with additional metadata (headers, meta tags, etc.)
        
        Returns:
            page_id: ID of the inserted page
        """
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            # Check if page already exists
            check_query = """
                SELECT id FROM website_pages
                WHERE website_id = %s AND url = %s
            """
            cursor.execute(check_query, (website_id, url))
            existing = cursor.fetchone()
            
            if existing:
                # Update existing page
                update_query = """
                    UPDATE website_pages
                    SET title = %s, content = %s, metadata = %s, 
                        updated_at = CURRENT_TIMESTAMP, status = 'active'
                    WHERE id = %s
                    RETURNING id
                """
                cursor.execute(update_query, (title, content, Json(metadata or {}), existing['id']))
                page_id = cursor.fetchone()['id']
                print(f" Updated page: {url}")
            else:
                # Insert new page
                insert_query = """
                    INSERT INTO website_pages (website_id, url, title, content, metadata, status)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                """
                cursor.execute(insert_query, (website_id, url, title, content, Json(metadata or {}), 'active'))
                page_id = cursor.fetchone()['id']
                print(f" Stored new page: {url}")
            
            conn.commit()
            return page_id
            
        except Exception as e:
            conn.rollback()
            print(f" Error storing page {url}: {e}")
            raise
        finally:
            cursor.close()
            conn.close()
    
    ## this function stores embeddings of scraped website pages
    def store_embedding(self, website_page_id=None, chunk_text=None, 
                       chunk_index=None, embedding_vector=None, token_count=None, 
                       tags=None, website_id=None, source=None,document_id = None):
        """
        Store text chunk embedding (for pages or documents)
        
        Args:
            page_id: ID of the page (optional, for scraped content)
            document_id: ID of the document (optional, for uploaded files)
            chunk_text: The text chunk (300-800 tokens)
            chunk_index: Order of chunk in the source
            embedding_vector: Embedding vector (dimension detected automatically)
            token_count: Number of tokens in chunk
            tags: List of tags for filtering
            website_id: Website ID (required)
            source: Source identifier (URL or filename)
        
        Returns:
            embedding_id: ID of the inserted embedding
        """
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            # Validate: ei page_id  must be provided
            if website_page_id is None:
                raise ValueError(" Page id must be provided")
            
           
            
            # Get source if not provided
            if not source:
                if website_page_id:
                    cursor.execute("SELECT url FROM website_pages WHERE id = %s", (website_page_id,))
                    page = cursor.fetchone()
                    source = page['url'] if page else None
                
            
            # Check if embedding already exists
            if website_page_id:
                check_query = """
                    SELECT id FROM website_embeddings 
                    WHERE website_page_id = %s AND chunk_index = %s
                """
                cursor.execute(check_query, (website_page_id, chunk_index))
            else:
                check_query = """
                    SELECT id FROM website_embeddings 
                    WHERE document_id = %s AND chunk_index = %s
                """
                cursor.execute(check_query, (document_id, chunk_index))
            
            existing = cursor.fetchone()
            
            # Convert embedding to PostgreSQL array format
            if hasattr(embedding_vector, 'tolist'):
                embedding_list = embedding_vector.tolist()
            else:
                embedding_list = embedding_vector
            
            embedding_str = '[' + ','.join(map(str, embedding_list)) + ']'
            
            if existing:
                # Update existing embedding
                update_query = """
                    UPDATE website_embeddings 
                    SET chunk_text = %s, embedding = %s::vector, 
                        source = %s, token_count = %s, tags = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    RETURNING id
                """
                cursor.execute(update_query, (
                    chunk_text, embedding_str, source, 
                    token_count, tags or [], existing['id']
                ))
                embedding_id = cursor.fetchone()['id']
            else:
                # Insert new embedding
                insert_query = """
                    INSERT INTO website_embeddings 
                    (website_id, website_page_id, chunk_text, chunk_index, 
                     embedding, source, token_count, tags)
                    VALUES (%s, %s, %s, %s, %s::vector, %s, %s, %s)
                    RETURNING id
                """
                cursor.execute(insert_query, (
                    website_id, website_page_id, chunk_text, chunk_index,
                    embedding_str, source, token_count, tags or []
                ))
                embedding_id = cursor.fetchone()['id']
            
            conn.commit()
            return embedding_id
            
        except Exception as e:
            conn.rollback()
            print(f"Error storing embedding: {e}")
            raise
        finally:
            cursor.close()
            conn.close()
    
    
   # function for storing and vectorizing the uploaded documents 
    def store_and_vectorize_document(self, file, website_id):

        conn = self.get_connection()
        cur = conn.cursor()

        UPLOAD_DIR = "uploads"
        os.makedirs(UPLOAD_DIR, exist_ok=True)

        if not file or not website_id:
            return jsonify({"error": "file and website_id are required"}), 400

        filename = secure_filename(file.filename)
        ext = os.path.splitext(filename)[1].lower()

        if not allowed_file(filename):
            return jsonify({"error": "Unsupported file type"}), 400

        file_path = os.path.join(UPLOAD_DIR, filename)
        file.save(file_path)

        document_id = None

        try:
            #  Insert Document
            
            cur.execute("""
                INSERT INTO documents (
                    website_id, file_name, file_extension,
                    file_size, file_path, status
                )
                VALUES (%s, %s, %s, %s, %s, 'processing')
                RETURNING id
            """, (
                website_id,
                filename,
                ext,
                os.path.getsize(file_path),
                file_path
            ))

            document_id = cur.fetchone()[0]
            conn.commit()

            ## Extract Pages
            

            if ext == ".pdf":
                pages = extract_text_from_pdf(file_path)  
                # MUST return list of dicts

            elif ext == ".docx":
                text = extract_text_from_docx(file_path)
                pages = [{"page_number": 1, "content": text}]

            else:
                text = extract_text_from_txt(file_path)
                pages = [{"page_number": 1, "content": text}]

            if not pages:
                raise ValueError("No content extracted from document")

            # Initialize Generator ONCE
            
            generator = EmbeddingGenerator()

            total_chunks = 0

            # Process Each Page
            

            for page in pages:

                content = page["content"]

                if not content.strip():
                    continue

                page_number = page["page_number"]

                # Insert page
                cur.execute("""
                    INSERT INTO document_pages (
                        document_id,
                        website_id,
                        page_number,
                        content
                    )
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                """, (
                    document_id,
                    website_id,
                    page_number,
                    content
                ))

                document_page_id = cur.fetchone()[0]

                # Chunk page
                
                chunks = generator.chunk_text(content)

                if not chunks:
                    continue

                texts = [c["chunk_text"] for c in chunks]

                ##Generate embeddings (BATCH)
                
                vectors = generator.generate_embeddings_batch(texts)

                # Store embeddings
               
                for chunk, vector in zip(chunks, vectors):

                    cur.execute("""
                        INSERT INTO document_embeddings (
                            website_id,
                            document_id,
                            document_page_id,
                            chunk_text,
                            chunk_index,
                            embedding,
                            token_count,
                            source
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        website_id,
                        document_id,
                        document_page_id,
                        chunk["chunk_text"],
                        chunk["chunk_index"],
                        vector.tolist(),
                        chunk["token_count"],
                        filename
                    ))

                total_chunks += len(chunks)

            ## Mark document complete
           
            cur.execute("""
                UPDATE documents
                SET status='completed',
                    processed_at=%s
                WHERE id=%s
            """, (datetime.utcnow(), document_id))

            conn.commit()

            return {
                "message": "Document processed successfully",
                "document_id": document_id,
                "pages_created": len(pages),
                "chunks_created": total_chunks
            }


        except Exception as e:

            conn.rollback()

            if document_id:
                cur.execute("""
                    UPDATE documents
                    SET status='failed',
                        error_message=%s
                    WHERE id=%s
                """, (str(e), document_id))
                conn.commit()

            return jsonify({"error": str(e)}), 500

        finally:
            cur.close()
            conn.close()


    def get_documents(self, website_id, status='completed'):
        """
        Get all documents for a website
        
        Args:
            website_id: Website ID
            status: Filter by status (default: 'completed')
        
        Returns:
            List of documents
        """
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            query = """
                SELECT id, file_name, file_extension, file_size, 
                       content, metadata, status, uploaded_at, processed_at
                FROM documents
                WHERE website_id = %s AND status = %s
                ORDER BY uploaded_at DESC
            """
            cursor.execute(query, (website_id, status))
            documents = cursor.fetchall()
            
            return [dict(doc) for doc in documents]
            
        finally:
            cursor.close()
            conn.close()
    
    def update_document_status(self, document_id, status, error_message=None):
        """
        Update document processing status
        
        Args:
            document_id: Document ID
            status: New status
            error_message: Error message if failed
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            query = """
                UPDATE documents 
                SET status = %s, 
                    error_message = %s,
                    processed_at = CASE WHEN %s IN ('completed', 'failed') 
                                   THEN CURRENT_TIMESTAMP ELSE processed_at END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """
            cursor.execute(query, (status, error_message, status, document_id))
            conn.commit()
            
            print(f" Updated document {document_id} status to: {status}")
            
        except Exception as e:
            conn.rollback()
            print(f" Error updating document status: {e}")
            raise
        finally:
            cursor.close()
            conn.close()
    
    def store_faq(self, website_id, question, answer, category=None, priority=0, embedding_vector=None):
        """
        Store FAQ with optional embedding
        
        Args:
            website_id: ID of the website
            question: FAQ question
            answer: FAQ answer
            category: Optional category
            priority: Priority level (higher = more important)
            embedding_vector: Optional embedding of the question for semantic search
        
        Returns:
            faq_id: ID of the inserted FAQ
        """
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            # Convert embedding to PostgreSQL array format if provided
            embedding_str = None
            if embedding_vector:
                embedding_str = '[' + ','.join(map(str, embedding_vector)) + ']'
            
            query = """
                INSERT INTO faqs 
                (website_id, question, answer, category, priority, is_active, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s::vector)
                RETURNING id
            """
            cursor.execute(query, (
                website_id, question, answer, category, 
                priority, True, embedding_str
            ))
            
            faq_id = cursor.fetchone()['id']
            conn.commit()
            
            print(f" Stored FAQ: {question[:50]}...")
            return faq_id
            
        except Exception as e:
            conn.rollback()
            print(f" Error storing FAQ: {e}")
            raise
        finally:
            cursor.close()
            conn.close()
    
    def update_website_status(self, website_id, status):
        """
        Update website scraping status
        
        Args:
            website_id: ID of the website
            status: New status (pending, scraping, active, failed, paused)
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            query = """
                UPDATE websites 
                SET status = %s, updated_at = CURRENT_TIMESTAMP 
                WHERE id = %s
            """
            cursor.execute(query, (status, website_id))
            conn.commit()
            
            print(f"Updated website {website_id} status to: {status}")
            
        except Exception as e:
            conn.rollback()
            print(f" Error updating website status: {e}")
            raise
        finally:
            cursor.close()
            conn.close()
    
    def update_last_scraped(self, website_id):
        """
        Update last_scraped_at timestamp for a website
        
        Args:
            website_id: ID of the website
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            query = """
                UPDATE websites 
                SET last_scraped_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """
            cursor.execute(query, (website_id,))
            conn.commit()
            
            print(f" Updated last_scraped_at for website {website_id}")
            
        except Exception as e:
            conn.rollback()
            print(f" Error updating last_scraped_at: {e}")
            raise
        finally:
            cursor.close()
            conn.close()
    
    def update_scraping_queue(self, website_id, status, error_message=None):
        """
        Update scraping queue status
        
        Args:
            website_id: ID of the website
            status: Queue status (pending, in_progress, completed, failed)
            error_message: Optional error message if failed
        """
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            # Find the most recent queue entry for this website
            select_query = """
                SELECT id FROM scraping_queue 
                WHERE website_id = %s 
                ORDER BY created_at DESC 
                LIMIT 1
            """
            cursor.execute(select_query, (website_id,))
            queue = cursor.fetchone()
            
            if queue:
                # Update existing queue entry
                update_query = """
                    UPDATE scraping_queue 
                    SET status = %s, error_message = %s,
                        started_at = CASE WHEN %s = 'in_progress' THEN CURRENT_TIMESTAMP ELSE started_at END,
                        completed_at = CASE WHEN %s IN ('completed', 'failed') THEN CURRENT_TIMESTAMP ELSE completed_at END
                    WHERE id = %s
                """
                cursor.execute(update_query, (status, error_message, status, status, queue['id']))
            else:
                # Create new queue entry
                insert_query = """
                    INSERT INTO scraping_queue (website_id, status, error_message)
                    VALUES (%s, %s, %s)
                """
                cursor.execute(insert_query, (website_id, status, error_message))
            
            conn.commit()
            print(f"🔄 Updated scraping queue for website {website_id}: {status}")
            
        except Exception as e:
            conn.rollback()
            print(f" Error updating scraping queue: {e}")
            raise
        finally:
            cursor.close()
            conn.close()
    
    def get_website_info(self, website_id):
        """
        Get website information
        
        Args:
            website_id: ID of the website
        
        Returns:
            dict with website info or None
        """
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            query = "SELECT * FROM websites WHERE id = %s"
            cursor.execute(query, (website_id,))
            website = cursor.fetchone()
            
            if website:
                return dict(website)
            return None
            
        finally:
            cursor.close()
            conn.close()
    
    def search_similar_embeddings(self, query_embedding, website_id, limit=5):
        """
        Search for similar embeddings using cosine similarity.
        website_id is REQUIRED.
        """

        if website_id is None:
            raise ValueError("website_id is required for embedding search.")

        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        try:
            # Ensure embedding is a list (important for psycopg + pgvector)
            query_embedding = list(query_embedding)

            query = """
            SELECT 
                e.chunk_text,
                e.source,
                e.tags,
                p.url,
                p.title,
                1 - (e.embedding <=> %s::vector) AS similarity
            FROM website_embeddings e
            JOIN website_pages p
                ON e.website_page_id = p.id
            WHERE p.website_id = %s
            AND p.status = 'active'
            ORDER BY e.embedding <=> %s::vector
            LIMIT %s;
            """

            cursor.execute(
                query,
                (query_embedding, website_id, query_embedding, limit)
            )

            results = cursor.fetchall()
            return [dict(row) for row in results]

        finally:
            cursor.close()


    def search_similar_document_embeddings(self, query_embedding, website_id, limit=5):
        """
        Search for similar embeddings in uploaded documents using cosine similarity.
        website_id is REQUIRED.
        Returns document chunk text, source file name, page number and similarity.
        """

        if website_id is None:
            raise ValueError("website_id is required for document embedding search.")

        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        try:
            # Ensure embedding is a list (important for psycopg + pgvector)
            query_embedding = list(query_embedding)

            query = """
            SELECT
                e.chunk_text,
                e.source,
                e.tags,
                d.file_name,
                dp.page_number,
                e.document_id,
                1 - (e.embedding <=> %s::vector) AS similarity
            FROM document_embeddings e
            JOIN document_pages dp
                ON e.document_page_id = dp.id
            JOIN documents d
                ON e.document_id = d.id
            WHERE e.website_id = %s
            ORDER BY e.embedding <=> %s::vector
            LIMIT %s;
            """

            cursor.execute(
                query,
                (query_embedding, website_id, query_embedding, limit)
            )

            results = cursor.fetchall()
            return [dict(row) for row in results]

        finally:
            cursor.close()


    def fetch_pages_by_website_id(self, website_id):
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        query = """
            SELECT id, url, title, content
            FROM website_pages
            WHERE website_id = %s
            AND status = 'active'
            ORDER BY scraped_at DESC
        """

        cursor.execute(query, (website_id,))
        rows = cursor.fetchall()

        cursor.close()
        conn.close()

        return [
            {
                "id": row["id"],
                "url": row["url"],
                "title": row["title"],
                "content": row["content"],
            }
            for row in rows
        ]
    

    def fetch_document_pages_by_website_id(self, website_id):
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        query = """
            SELECT id, document_id, website_id,page_number, content
            FROM document_pages
            WHERE website_id = %s
            ORDER BY created_at DESC
        """

        cursor.execute(query, (website_id,))
        rows = cursor.fetchall()

        cursor.close()
        conn.close()

        return [
            {
                "id": row["id"],
                "document_id": row["document_id"],
                "website_id": row["website_id"],
                "page_number": row["page_number"],
                "content": row["content"],
            }
            for row in rows
        ]
    

    ## function to get faqs by website-id
    
    def get_faqs_by_website_id(self, website_id, category=None, limit=50):
        """
        Retrieve FAQs for a specific website
        
        Args:
            website_id: ID of the website
            category: Optional category filter
            limit: Max FAQs to return
        
        Returns:
            List of FAQs
        """

        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        try:
            query = """
                SELECT
                    id,
                    question,
                    answer,
                    category,
                    priority,
                    created_at
                FROM faqs
                WHERE website_id = %s
                AND is_active = TRUE
            """

            params = [website_id]

            if category:
                query += " AND category = %s"
                params.append(category)

            query += """
                ORDER BY priority DESC, id DESC
                LIMIT %s
            """
            params.append(limit)

            cursor.execute(query, params)
            faqs = cursor.fetchall()

            print(f"Retrieved {len(faqs)} FAQs for website_id={website_id}")
            
            # Convert RealDictRow to regular dicts for JSON serialization
            return [dict(faq) for faq in faqs]  # Fixed: added dict() conversion

        except Exception as e:
            print(f"Error retrieving FAQs: {e}")
            raise

        finally:
            cursor.close()
            conn.close()

    

    ## method to get website by hash
    def get_website_by_hash(self, embed_hash):
        """
        Get website details by embed_hash
        """
        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, name, url, status, embed_hash, created_at
                    FROM websites
                    WHERE embed_hash = %s
                    """,
                    (embed_hash,)
                )
                result = cursor.fetchone()
                
                if result:
                    return {
                        'id': result[0],
                        'name': result[1],
                        'url': result[2],
                        'status': result[3],
                        'embed_hash': result[4],
                        'created_at': result[5],
                    }
                return None
        finally:
            cursor.close()
            conn.close()
            


    def create_and_store_json_object_embeddings(self, json_path: str, website_id: int, source: str = "json"):
        """
        Create ONE embedding per JSON object (1 object = 1 chunk = 1 embedding row)

        Example:
        [
        {"title": "About", "content": "Company info"},
        {"title": "Services", "content": "We provide AI"}
        ]

        → 2 embeddings stored (NOT further chunked)
        """

        if not os.path.exists(json_path):
            raise FileNotFoundError(f"JSON file not found: {json_path}")

        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        try:
            # Load JSON
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Ensure list of objects
            if isinstance(data, dict):
                data = [data]  # single object -> list

            if not isinstance(data, list):
                raise ValueError("JSON must be a list of objects or a single object")

            generator = StructuralEmbeddingGenerator()
            texts = []
            headings = []
            token_counts = []

            # -------- Convert each JSON object into ONE chunk --------
            for obj in data:
                if not isinstance(obj, dict):
                    continue

                # Use title/heading if available
                heading = obj.get("title") or obj.get("heading") or obj.get("name") or "json_object"

                # Convert full JSON object to clean text
                # (Better for semantic search than embedding only one field)
                text_parts = []
                for key, value in obj.items():
                    if value is None:
                        continue
                    text_parts.append(f"{key}: {value}")

                chunk_text = "\n".join(text_parts).strip()

                if not chunk_text:
                    continue

                texts.append(chunk_text)
                headings.append(str(heading))
                token_counts.append(len(chunk_text.split()))  # rough token estimate

            if not texts:
                raise ValueError("No valid JSON objects found to embed")

            # -------- Batch embedding (FAST & GPU/CPU efficient) --------
            vectors = generator.generate_embeddings_batch(texts)

            # -------- Store embeddings (1 row per JSON object) --------
            insert_query = """
                INSERT INTO embeddings (
                    website_id,
                    heading,
                    chunk_text,
                    embedding,
                    token_count,
                    source
                )
                VALUES (%s, %s, %s, %s::vector, %s, %s)
            """

            stored_count = 0

            for text, vector, heading, token_count in zip(texts, vectors, headings, token_counts):
                embedding_list = vector.tolist() if hasattr(vector, "tolist") else vector
                embedding_str = "[" + ",".join(map(str, embedding_list)) + "]"

                cursor.execute(insert_query, (
                    website_id,
                    heading,
                    text,
                    embedding_str,
                    token_count,
                    source
                ))

                stored_count += 1

            conn.commit()

            return {
                "status": "success",
                "json_objects_processed": len(texts),
                "embeddings_stored": stored_count,
                "file": os.path.basename(json_path)
            }

        except Exception as e:
            conn.rollback()
            print(f"Error storing JSON object embeddings: {e}")
            raise

        finally:
            cursor.close()
            conn.close()

    def store_embedding_row(self, website_id, heading, chunk_text, embedding_vector, token_count=None, source=None):
        """
        Store a single embedding row into the `embeddings` table.

        Args:
            website_id: website id
            heading: short heading/title for the chunk
            chunk_text: chunk text
            embedding_vector: list or numpy array of floats
            token_count: optional token count
            source: optional source identifier

        Returns:
            inserted row id
        """
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        try:
            # Convert embedding to list
            if hasattr(embedding_vector, 'tolist'):
                embedding_list = embedding_vector.tolist()
            else:
                embedding_list = embedding_vector

            embedding_str = '[' + ','.join(map(str, embedding_list)) + ']'

            insert_query = """
                INSERT INTO embeddings (
                    website_id, heading, chunk_text, embedding, token_count, source
                )
                VALUES (%s, %s, %s, %s::vector, %s, %s)
                RETURNING id
            """

            cursor.execute(insert_query, (
                website_id, heading, chunk_text, embedding_str, token_count, source
            ))

            row_id = cursor.fetchone()['id']
            conn.commit()
            return row_id

        except Exception as e:
            conn.rollback()
            print(f"Error storing generic embedding row: {e}")
            raise
        finally:
            cursor.close()
            conn.close()

    def search_similar_embeddings_epay(self, query_embedding, website_id, limit=5):
        """
        Search the generic `embeddings` table using pgvector similarity.

        Returns rows with heading, chunk_text, source and similarity score.
        """
        if website_id is None:
            raise ValueError("website_id is required for embedding search.")

        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        try:
            query_embedding = list(query_embedding)

            query = """
            SELECT
                id,
                heading,
                sub_heading,
                chunk_text,
                meta_data,
                token_count,
                created_at,
                1 - (embedding <=> %s::vector) AS similarity
            FROM epay_embeddings
            WHERE website_id = %s
            ORDER BY embedding <=> %s::vector
            LIMIT %s;
            """

            cursor.execute(query, (query_embedding, website_id, query_embedding, limit))
            results = cursor.fetchall()
            return [dict(row) for row in results]

        finally:
            cursor.close()
            conn.close()


    def close_all_connections(self):
            """Close all database connections """
            if self.conn and not self.conn.closed:
                self.conn.close()