"""
Flask Application with PostgreSQL and pgvector support
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from dotenv import load_dotenv
import sys
import json
from multiprocessing import Process
import re
from urllib.parse import urlparse
import hashlib
import time
import secrets
from threading import Thread
from datetime import datetime
from utils.faq_generator_using_groq import GroqFAQGenerator
from utils.structural_chunking_embeddings import StructuralEmbeddingGenerator
from utils.rag_query_engine_epay_balochistan import RAGQueryEngine

# Import embedding generator and database manager
from utils.embeddings_generator import EmbeddingGenerator
from database.models import DatabaseManager
import torch
import gc
from transformers import AutoModelForCausalLM, AutoTokenizer
import traceback


load_dotenv()

app = Flask(__name__)
CORS(app)


# --- MODEL LOADING (One-time) ---
# MODEL_PATH = r"D:\flask_chatbot_main_branch\backend\utils\merged-phi3"

# print("Initializing API... Loading model and tokenizer.")
# tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
# model = AutoModelForCausalLM.from_pretrained(
#     MODEL_PATH,
#     device_map="cpu",
#     torch_dtype=torch.float16,
#     trust_remote_code=False,       
#     attn_implementation="eager",   
#     low_cpu_mem_usage=True
# )

# # Fix padding token logic
# tokenizer.pad_token = tokenizer.eos_token
# model.config.pad_token_id = model.config.eos_token_id


def generate_embed_hash():
    """Generate a unique hash for embed code"""
    return hashlib.sha256(secrets.token_bytes(32)).hexdigest()

def is_valid_url(url):
    """
    Validate URL including localhost URLs
    """
    try:
        result = urlparse(url)
        
        # Check if it has scheme and netloc
        if not all([result.scheme, result.netloc]):
            return False
        
        # Allow http and https
        if result.scheme not in ['http', 'https']:
            return False
        
        # Allow localhost patterns
        localhost_patterns = [
            'localhost',
            '127.0.0.1',
            '0.0.0.0',
            '::1'
        ]
        
        hostname = result.hostname or ''
        
        # Check if it's localhost or a valid domain
        if any(pattern in hostname.lower() for pattern in localhost_patterns):
            return True
        
        # Check for valid domain pattern
        domain_pattern = r'^([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$'
        if re.match(domain_pattern, hostname):
            return True
        
        return False
        
    except:
        return False


# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Initialize embedding generator (lazy loading)
embedding_generator = None

def get_embedding_generator():
    """Lazy load the embedding generator"""
    global embedding_generator
    if embedding_generator is None:
        embedding_generator = EmbeddingGenerator()
    return embedding_generator

def get_db_connection():
    """Get PostgreSQL database connection"""
    return psycopg2.connect(
        host=os.getenv('HOST'),
        user=os.getenv('USER'),
        password=os.getenv('DB_PASSWORD'),
        database=os.getenv('DATABASE'),
        port=os.getenv('DB_PORT', 5432)
    )
# At module level — just declare it as None
rag_engine = None

def get_rag_engine():
    """Lazy-load the RAG engine on first use"""
    global rag_engine
    if rag_engine is None:
        rag_engine = RAGQueryEngine(
            embedding_model="intfloat/e5-large-v2",
            ollama_model="llama3:latest",
            ollama_base_url="http://localhost:11434/v1"
        )
    return rag_engine


## api endpoint to register a new website and start scraping

@app.route('/api/register', methods=['POST'])
def register_website():
    """Register a new website and start scraping"""
    data = request.json
    
    # Validate input
    if not data.get('name') or not data.get('url'):
        return jsonify({'error': 'Name and URL are required'}), 400
    
    # Validate URL
    if not is_valid_url(data['url']):
        return jsonify({'error': 'Invalid URL format'}), 400
    
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Generate unique embed hash
        embed_hash = generate_embed_hash()
        
        # Get max_pages from env or use provided value
        max_pages = int(os.getenv('MAX_PAGES_PER_WEBSITE'))
        print(f"maximum pages to scrape: {max_pages}")
        
        # Check status field and set scrape_permission accordingly
        # status can be 'yes', 'no', True, False, 1, 0
        status_value = data.get('status', 'yes')
        
        # Convert various status formats to boolean
        if isinstance(status_value, str):
            scrape_permission = status_value.lower() in ['yes', 'true', '1', 'active', 'enabled']
        elif isinstance(status_value, bool):
            scrape_permission = status_value
        elif isinstance(status_value, int):
            scrape_permission = bool(status_value)
        else:
            scrape_permission = True  # Default to True if unclear
        
        # Determine website status based on scrape permission
        website_status = 'scraping' if scrape_permission else 'paused'
        
        # Insert website
        query = """
            INSERT INTO websites (name, url, embed_hash, scrape_permission, status, max_pages)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, name, url, embed_hash, status, scrape_permission
        """
        
        cursor.execute(query, (
            data['name'],
            data['url'],
            embed_hash,
            scrape_permission,
            website_status,
            max_pages
        ))
        
        website = cursor.fetchone()
        website_id = website['id']
        
        # Create scraping queue entry only if scraping is enabled
        if scrape_permission:
            queue_query = """
                INSERT INTO scraping_queue (website_id, status, priority)
                VALUES (%s, %s, %s)
            """
            cursor.execute(queue_query, (website_id, 'pending', 0))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        # Generate embed code using hash instead of ID
        api_url = os.getenv('API_URL', 'http://localhost:5000')
        embed_code = f"""<script>
(function() {{
  var script = document.createElement('script');
  script.src = '{api_url}/chatbot.js';
  script.setAttribute('data-website-hash', '{embed_hash}');
  document.body.appendChild(script);
}})();
</script>"""
        
        # Start scraping in background process only if permission granted
        if scrape_permission:
            print(f" Starting scraping for website_id={website_id}, url={data['url']}")
            
            # Import here to avoid circular imports
            from scrapers.run_spider import run_spider
            
            # Use multiprocessing to avoid Twisted reactor issues
            p = Process(
                target=run_spider,
                args=(website_id, data['url'], max_pages),
                daemon=False
            )
            p.start()
            
            print(f" Scraping process started (PID: {p.pid})")
        else:
            print(f" Scraping disabled for website_id={website_id}, url={data['url']}")
        
        # Prepare success message
        message = 'Website registered successfully.'
        if scrape_permission:
            message += ' Scraping started in background.'
        else:
            message += ' Scraping is disabled for this website.'
        
        return jsonify({
            
            'name': data['name'],
            'url': data['url'],
            'embed_hash': embed_hash,
            'scrape_permission': scrape_permission,
            'status': website_status,
            'embed_code': embed_code,
            'message': message
        }), 201
        
    except psycopg2.Error as e:
        if conn:
            conn.rollback()
        print(f"Database error: {str(e)}")
        return jsonify({'error': f'Database error: {str(e)}'}), 500
    except Exception as e:
        if conn:
            conn.rollback()
        print(f" Error registering website: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        if conn:
            conn.close()


## api endpoint to get faqs for a website
@app.route('/api/faqs/', methods=['GET'])
def get_faqs():
    """Get all FAQs for a specific website"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        website_id = 1
        query = """
            SELECT id, question, answer, category, priority, is_active, created_at, updated_at
            FROM faqs 
            WHERE website_id = %s AND is_active = TRUE
            ORDER BY priority DESC, created_at DESC
        """
        cursor.execute(query, (website_id,))
        faqs = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        print(f" Fetched {len(faqs)} FAQs for website_id={website_id}")
        
        # Convert to list of dicts and handle datetime serialization
        result = []
        for faq in faqs:
            faq_dict = dict(faq)
            if faq_dict.get('created_at'):
                faq_dict['created_at'] = faq_dict['created_at'].isoformat()
            if faq_dict.get('updated_at'):
                faq_dict['updated_at'] = faq_dict['updated_at'].isoformat()
            result.append(faq_dict)
        
        return jsonify(result), 200
        
    except Exception as e:
        print(f" Error fetching FAQs: {e}")
        return jsonify({'error': str(e)}), 500


## endpoint to get website details using website_id

@app.route('/api/website/<int:website_id>', methods=['GET'])
def get_website(website_id):
    """Get details of a specific website"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        query = """
            SELECT 
                w.*,
                (SELECT COUNT(*) FROM faqs WHERE website_id = w.id AND is_active = TRUE) as faq_count,
                (SELECT COUNT(*) FROM pages WHERE website_id = w.id AND status = 'active') as page_count
            FROM websites w
            WHERE w.id = %s
        """
        cursor.execute(query, (website_id,))
        website = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        if not website:
            return jsonify({'error': 'Website not found'}), 404
        
        # Convert to dict and handle datetime serialization
        result = dict(website)
        if result.get('created_at'):
            result['created_at'] = result['created_at'].isoformat()
        if result.get('updated_at'):
            result['updated_at'] = result['updated_at'].isoformat()
        if result.get('last_scraped_at'):
            result['last_scraped_at'] = result['last_scraped_at'].isoformat()
        
        return jsonify(result), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


## endpoint to generate embeddings for all pages of a website using website_id
@app.route('/api/embeddings/generate/<int:website_id>', methods=['POST'])
def generate_embeddings_for_website(website_id):
    """
    Generate embeddings for all pages of a website
    
    Query params:
        - background: if true, run in background thread (default: false)
        - chunk_size: token chunk size (default: 500)
        - overlap: token overlap between chunks (default: 50)
    """
    try:
        # Get query parameters
        background = request.args.get('background', 'false').lower() == 'true'
        chunk_size = int(request.args.get('chunk_size', 500))
        overlap = int(request.args.get('overlap', 50))
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Check if website exists
        cursor.execute("SELECT id, name, url FROM websites WHERE id = %s", (website_id,))
        website = cursor.fetchone()
        
        if not website:
            cursor.close()
            conn.close()
            return jsonify({'error': 'Website not found'}), 404
        
        # Get all active pages for this website
        cursor.execute("""
            SELECT id, url, title, content 
            FROM pages 
            WHERE website_id = %s AND status = 'active'
            ORDER BY id
        """, (website_id,))
        
        pages = cursor.fetchall()
        cursor.close()
        conn.close()
        
        if not pages:
            return jsonify({
                'error': 'No pages found for this website',
                'website_id': website_id
            }), 404
        
        print(f"Found {len(pages)} pages for website {website_id}")
        
        if background:
            # Run in background thread
            thread = Thread(
                target=_generate_embeddings_task,
                args=(website_id, pages, chunk_size, overlap)
            )
            thread.daemon = True
            thread.start()
            
            return jsonify({
                'message': 'Embedding generation started in background',
                'website_id': website_id,
                'website_name': website['name'],
                'pages_count': len(pages),
                'status': 'processing'
            }), 202
        else:
            # Run synchronously
            result = _generate_embeddings_task(website_id, pages, chunk_size, overlap)
            return jsonify(result), 200
            
    except Exception as e:
        print(f" Error in generate_embeddings_for_website: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

def _generate_embeddings_task(website_id, website_pages, chunk_size, overlap):
    """
    Background task to generate embeddings
    """
    try:
        print(f"\n{'='*60}")
        print(f" Starting embedding generation for website {website_id}")
        print(f" Pages to process: {len(website_pages)}")
        print(f"{'='*60}\n")
        
        # Get embedding generator
        generator = get_embedding_generator()
        db = DatabaseManager()
        
        total_embeddings = 0
        processed_pages = 0
        errors = []
        
        for page in website_pages:
            try:
                website_page_id = page['id']
                content = page['content']
                title = page['title'] or ''
                source = page['url']
                
                print(f"\n Processing page {website_page_id}: {page['url']}")
                
                # Skip empty content
                if not content or not content.strip():
                    print(f"  Skipping page {website_page_id} - empty content")
                    continue
                
                # Generate embeddings for page
                embeddings_data = generator.process_content(
                    website_page_id=website_page_id,
                    content=content,
                    title=title,
                    chunk_size=chunk_size,
                    overlap=overlap,
                    website_id = website_id,
                    source = source
                )
                
                # Store embeddings in database
                for emb_data in embeddings_data:
                    db.store_embedding(
                        website_page_id=emb_data['website_page_id'],
                        chunk_text=emb_data['chunk_text'],
                        chunk_index=emb_data['chunk_index'],
                        embedding_vector=emb_data['embedding_vector'],
                        token_count=emb_data['token_count'],
                        tags=emb_data['tags'],
                        website_id = emb_data['website_id']
                    )
                
                total_embeddings += len(embeddings_data)
                processed_pages += 1
                
                print(f" Stored {len(embeddings_data)} embeddings for page {website_page_id}")
                
            except Exception as e:
                error_msg = f"Error processing page {page['id']}: {str(e)}"
                print(f" {error_msg}")
                errors.append(error_msg)
                continue
        
        print(f"\n{'='*60}")
        print(f" Embedding generation completed!")
        print(f" Pages processed: {processed_pages}/{len(website_pages)}")
        print(f" Total embeddings: {total_embeddings}")
        if errors:
            print(f"Errors: {len(errors)}")
        print(f"{'='*60}\n")
        
        return {
            'message': 'Embedding generation completed',
            'website_id': website_id,
            'pages_processed': processed_pages,
            'total_pages': len(website_pages),
            'total_embeddings': total_embeddings,
            'errors': errors if errors else None
        }
        
    except Exception as e:
        error_msg = f"Fatal error in embedding generation: {str(e)}"
        print(f" {error_msg}")
        import traceback
        traceback.print_exc()
        return {
            'error': error_msg,
            'website_id': website_id
        }



## api to generate faqs of website using embed-hash
## this api endpoint reads the JSON file, 
# generates FAQs using Groq LLMs and stores them in the database using the existing store_faq function.
#  It uses the embed hash to identify the website and associate the generated FAQs with it.

# --- Flask API Route Supporting File Upload ---

@app.route('/generate-faqs', methods=['POST'])
def generate_faqs():
    # 1. Check if the file is in the request
    
    
    
    if 'file' not in request.files:
        return jsonify({"error": "No file part in the request"}), 400
    
    file = request.files['file']
    db = DatabaseManager()
    
    website_id = 1 #hardcoded for testing, retrieve it using get_website_by_hash(website_hash) in production(function is defiend in models.py)

    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    if file and file.filename.endswith('.json'):
        try:
            # 3. Read the file content directly without saving it to disk
            modules_data = json.load(file)
            
            generator = GroqFAQGenerator()
            result = generator.generate_faqs_from_data(modules_data, website_id)
            
            return jsonify(result), 200
        except Exception as e:
            return jsonify({"error": f"Failed to process file: {str(e)}"}), 500
    
    return jsonify({"error": "Invalid file type. Please upload a .json file"}), 400




# ## api to get inference from finetuned model
# # --- INFERENCE LOGIC ---
# @app.route('/finetuned-model/chat', methods=['POST'])
# def chat():
#     data = request.json
#     user_prompt = data.get("prompt", "")
    
#     if not user_prompt:
#         return jsonify({"error": "No prompt provided"}), 400

#     try:
#         messages = [{"role": "user", "content": user_prompt}]
#         inputs = tokenizer.apply_chat_template(
#             messages,
#             add_generation_prompt=True,
#             return_tensors="pt",
#             return_dict=True
#         ).to("cpu")

#         with torch.no_grad():
#             outputs = model.generate(
#                 **inputs,
#                 max_new_tokens=150,  # Keep this low for 8GB RAM stability
#                 temperature=0.7,
#                 do_sample=True,
#                 pad_token_id=tokenizer.eos_token_id
#             )

#         # Decode and clean response
#         full_text = tokenizer.decode(outputs[0], skip_special_tokens=True)
#         response_text = full_text.split("assistant")[-1].strip()

#         # Cleanup memory
#         gc.collect()

#         return jsonify({"response": response_text})

#     except Exception as e:
#         return jsonify({"error": str(e)}), 500


## api to upload doc using embed-hash

@app.route("/api/documents/upload", methods=["POST"])
def upload_document():
    """
    Upload document -> chunk -> generate embeddings
    Uses embed_hash for authentication
    """
    try:
        file = request.files.get("file")
        # embed_hash = request.form.get("embed_hash")
        
        if not file:
            return jsonify({
                "success": False,
                "error": "file is required",
            }), 400
            
        # if not embed_hash:
        #     return jsonify({
        #         "success": False,
        #         "error": "embed_hash is required",
        #     }), 400
        
        db = DatabaseManager()
        
        # Verify website exists and get website_id
        # website = db.get_website_by_hash(embed_hash)
        # if not website:
        #     return jsonify({
        #         "success": False,
        #         "error": "Invalid embed hash. Website not found.",
        #     }), 404
        
        website_id = 1 #hardcoded for testing, replace with website['id'] in production
        
        # Store and vectorize document
        results = db.store_and_vectorize_document(file, website_id)
        
        return jsonify({
            "success": True,
            "website_id": website_id,
            "results": results,
        }), 200
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


## rag query endpoint using groq api

# @app.route("/api/user/query", methods=["POST"])
# def query_rag():
#     """
#     Main RAG query endpoint

#     Expected JSON:
#     {
#         "query": "What is your refund policy?",
#         "website_id": 1,
#         "top_k": 5,
#         "temperature": 0.7,
#         "max_tokens": 500
#     }
#     """
#     try:
#         data = request.get_json()

#         if not data or "query" not in data:
#             return jsonify({
#                 "status": "error",
#                 "message": "Missing 'query' in request body"
#             }), 400

#         user_query = data.get("query")
#         website_id = 2 #hardcoded for testing, replace with data.get("website_id") in production


#         # Load engine (lazy)
#         engine = load_engine()

#         # Run RAG pipeline
#         result = engine.query(
#             user_query=user_query,
#             website_id=website_id,
      
#         )
#         print(f"RAG Query Response: {result}")
#         return jsonify({
#             "status": "success",
#             "data": result
#         })

#     except Exception as e:
#         traceback.print_exc()
#         return jsonify({
#             "status": "error",
#             "message": str(e)
#         }), 500




UPLOAD_DIR = "uploads/json"
os.makedirs(UPLOAD_DIR, exist_ok=True)

## api to create embeddings from JSON file  
@app.route("/api/embeddings/json", methods=["POST"])
def create_json_embeddings():
    """
    API to create embeddings from JSON file
    Rule: 1 JSON object = 1 chunk = 1 embedding row
    """

    try:
        # website_id = request.form.get("website_id")
        website_id = 1 #hardcoded for testing, replace with request.form.get("website_id") in production

        if not website_id:
            return jsonify({"error": "website_id is required"}), 400

        # Accept file upload OR raw JSON
        file = request.files.get("file")
        json_data = request.json if request.is_json else None

        if not file and not json_data:
            return jsonify({"error": "Provide JSON file or JSON body"}), 400

        # Save uploaded file (if provided)
        if file:
            
            file_path = os.path.join(UPLOAD_DIR, file.filename)
            file.save(file_path)

            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = json_data

        # Convert single object → list
        if isinstance(data, dict):
            data = [data]

        if not isinstance(data, list):
            return jsonify({"error": "JSON must be a list of objects"}), 400

        db = DatabaseManager()
        generator = StructuralEmbeddingGenerator()

        texts = []
        headings = []
        token_counts = []

        # -------- 1 OBJECT = 1 CHUNK --------
        for obj in data:
            if not isinstance(obj, dict):
                continue

            heading = (
                obj.get("title")
                or obj.get("heading")
                or obj.get("name")
                or "json_object"
            )

            # Convert entire object into a single text chunk
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
            token_counts.append(len(chunk_text.split()))

        if not texts:
            return jsonify({"error": "No valid JSON objects to embed"}), 400

        # -------- Batch Embeddings (E5 1024 dim) --------
        vectors = generator.generate_embeddings_batch(texts)

        conn = db.get_connection()
        cursor = conn.cursor()

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

        stored = 0

        for text, vector, heading, token_count in zip(texts, vectors, headings, token_counts):
            embedding_list = vector.tolist() if hasattr(vector, "tolist") else vector
            embedding_str = "[" + ",".join(map(str, embedding_list)) + "]"

            cursor.execute(insert_query, (
                int(website_id),
                heading,
                text,
                embedding_str,
                token_count,
                "json_api"
            ))
            stored += 1

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            "status": "success",
            "objects_processed": len(texts),
            "embeddings_stored": stored,
            "embedding_dimension": 1024
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# @app.route('/chatbot.js', methods=['GET'])
# def chatbot_script():
#     """Serve the embeddable chatbot JavaScript"""
#     try:
#         with open('static/chatbot.js', 'r', encoding='utf-8') as f:
#             script = f.read()
#         return script, 200, {'Content-Type': 'application/javascript; charset=utf-8'}
#     except FileNotFoundError:
#         error_script = """
#         console.error('Chatbot script not found. Make sure static/chatbot.js exists.');
#         alert('Chatbot failed to load. Please contact support.');
#         """
#         return error_script, 404, {'Content-Type': 'application/javascript'}


## api endpoint for epay rag query using epay specific engine and embedding table


@app.route("/api/chat", methods=["POST"])
def rag_query():

    data = request.json

    if not data or "query" not in data:
        return jsonify({
            "status": "error",
            "message": "Query is required"
        }), 400

    user_query = data["query"]
    embed_hash = data["embed_hash"]
    db = DatabaseManager()

    website_id = db.get_website_by_hash(embed_hash)
    if not website_id:
        return jsonify({
            "status": "error",
            "message": "Invalid embed hash"
        }), 400

    top_k = data.get("top_k", 5)
    engine = get_rag_engine() ## lazy load the engine, it will initialize only on first request and reuse for subsequent requests, this is important to save time on loading the embedding model and ollama model for every request
    result = engine.query(
        user_query=user_query,
        website_id=website_id,
        top_k=top_k
    )
    
    print(f"RAG Query Response: {result['response']}")
    print(f"Generated response for query in {result['time_taken']} seconds")

    return jsonify(result["response"]), 200



@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT 1')
        cursor.close()
        conn.close()
        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'message': 'API is running'
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'database': 'disconnected',
            'error': str(e)
        }), 500



@app.route('/', methods=['GET'])
def index():
    """Root endpoint"""
    return jsonify({
        'name': 'Chatbot Scraper API with pgvector',
        'version': '1.0.0',
        'database': 'PostgreSQL with pgvector',
        'embedding_model': 'intfloat/e5-large-v2',
        'embedding_dimension': '1024',
        'embedding_library': 'sentence-transformers',
        'llm used': 'llama3',
        
        'endpoints': {
            'POST /api/register': 'Register a new website',
            'GET /api/website/<id>': 'Get website details',
            'GET /api/faqs/<website_id>': 'Get FAQs for a website',
            'POST /api/embeddings/generate/<website_id>': 'Generate embeddings for website pages',
            'POST /api/faqs/generate/<int:website_id>' : 'Generate FAQ for a website',
            'POST /api/chat' : 'Generate response for user query',
            'POST /api/documents/upload': 'Uploads documents associated with any website and converts them to vector embeddings ',
            'GET /health': 'Health check'
        }
    }), 200

if __name__ == '__main__':
    
    # Print startup info
    print("\n" + "="*50)
    print(" Chatbot Scraper API Starting...")
    print("="*50)
    print(f"Server: http://localhost:5000")
    print(f"API Docs: http://localhost:5000/")
    print(f"Health Check: http://localhost:5000/health")
    print(f"Database: PostgreSQL with pgvector")
    print("="*50 + "\n")
    
    app.run(debug=True, port=5000, threaded=True)