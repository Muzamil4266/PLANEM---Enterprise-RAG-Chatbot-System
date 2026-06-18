import sys
sys.path.insert(0, r'C:\Users\khano\AppData\Roaming\Python\Python311\site-packages')

import os
import customtkinter as ctk
from tkinter import filedialog, messagebox
import threading
import re
import time
from datetime import timedelta
import shutil
import json
import traceback
import sqlite3
from datetime import datetime

# ============ GLOBAL EXCEPTION HANDLER ============

def global_exception_handler(exc_type, exc_value, exc_traceback):
    """Global exception handler to catch unexpected crashes"""
    error_text = "".join(
        traceback.format_exception(exc_type, exc_value, exc_traceback)
    )
    try:
        if 'app' in globals():
            app.gui_error(error_text)
        else:
            print(error_text)
    except:
        print(error_text)

sys.excepthook = global_exception_handler

# Configure CustomTkinter
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ============ CHAT HISTORY DATABASE ============

class ChatHistory:
    def __init__(self, db_path):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                question TEXT,
                answer TEXT,
                sources TEXT,
                confidence REAL,
                model TEXT
            )
        ''')
        conn.commit()
        conn.close()
    
    def add_entry(self, question, answer, sources, confidence, model):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO chat_history (timestamp, question, answer, sources, confidence, model)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (datetime.now().isoformat(), question, answer, json.dumps(sources), confidence, model))
        conn.commit()
        conn.close()
    
    def get_history(self, limit=50):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT timestamp, question, answer, sources, confidence, model
            FROM chat_history
            ORDER BY id DESC
            LIMIT ?
        ''', (limit,))
        rows = cursor.fetchall()
        conn.close()
        return rows
    
    def clear_history(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM chat_history')
        conn.commit()
        conn.close()

# ============ PART 1: INDEXING WITH GUI PROGRESS ============

def index_documents(gui_callback=None, settings=None):
    """Build database from PDFs with GUI progress display"""
    from sentence_transformers import SentenceTransformer
    import chromadb
    import PyPDF2
    import pdfplumber

    base_dir = r"C:\Shoby deathless laptop folder\RAG chatbots with python verification"
    model_path = os.path.join(base_dir, "models", "all-MiniLM-L6-v2")
    chroma_path = os.path.join(base_dir, "chroma_db")
    pdf_dir = os.path.join(base_dir, "test_data")
    
    if settings is None:
        settings = {
            "chunk_size": 800,
            "chunk_overlap": 150
        }
    
    chunk_size = settings.get("chunk_size", 800)
    chunk_overlap = settings.get("chunk_overlap", 150)

    def log(msg):
        if gui_callback:
            gui_callback(msg)
        else:
            print(msg)

    def update_progress(value):
        if gui_callback:
            gui_callback(None, value)

    log("=" * 70)
    log("�PLANEM AI - DOCUMENT INDEXING SYSTEM")
    log("=" * 70)
    log("")
    log("⏳ STEP 1: Loading embedding model...")
    start_time = time.time()
    embedder = SentenceTransformer(model_path)
    log(f"   ✓ Model loaded in {time.time()-start_time:.1f} seconds")
    log("")

    log("⏳ STEP 2: Connecting to Chroma database...")
    client = chromadb.PersistentClient(path=chroma_path)

    indexed_sources = set()
    try:
        collection = client.get_collection("documents")
        existing = collection.get()
        for meta in existing["metadatas"]:
            if meta and "source" in meta:
                indexed_sources.add(meta["source"])
        log(f"   ✓ Using existing collection with {len(indexed_sources)} indexed sources")
    except:
        # Create collection with cosine similarity space
        collection = client.create_collection(
            name="documents", 
            metadata={"hnsw:space": "cosine"}
        )
        log(f"   ✓ Created new collection with cosine similarity")
    log("")

    def extract_text(pdf_path, total_pages_ref):
        """Extract text with page-by-page progress"""
        text = ""

        try:
            with pdfplumber.open(pdf_path) as pdf:
                total_pages_ref[0] = len(pdf.pages)
                for i, page in enumerate(pdf.pages):
                    t = page.extract_text()
                    if t:
                        text += f"\n--- Page {i+1} ---\n" + t + "\n"
                    if (i + 1) % 50 == 0 or i == 0:
                        log(f"   📄 Extracting: Page {i+1} / {total_pages_ref[0]}")
                log("")
        except Exception as e:
            log(f"   ⚠ pdfplumber failed: {e}")
            try:
                with open(pdf_path, 'rb') as f:
                    reader = PyPDF2.PdfReader(f)
                    total_pages_ref[0] = len(reader.pages)
                    for i, page in enumerate(reader.pages):
                        page_text = page.extract_text()
                        if page_text:
                            text += f"\n--- Page {i+1} ---\n" + page_text + "\n"
                        if (i + 1) % 50 == 0 or i == 0:
                            log(f"   📄 Extracting: Page {i+1} / {total_pages_ref[0]}")
                    log("")
            except Exception as e2:
                log(f"   ✗ PyPDF2 also failed: {e2}")

        return text

    def chunk_text(text, size=800, overlap=150):
        """Split text into chunks with precise page info - removes duplicates"""
        lines = text.split('\n')
        chunks = []
        current = []
        last_seen_page = "1"
        length = 0
        seen_chunks = set()
        
        for line in lines:
            if "--- Page " in line:
                match = re.search(r"Page\s+(\d+)", line)
                if match:
                    last_seen_page = match.group(1)
                continue
            
            # Tie the specific line to the page it was found on
            current.append((line, last_seen_page))
            length += len(line) + 1
            
            if length >= size:
                chunk_text = "\n".join([l[0] for l in current])
                # Extract unique pages present in this specific chunk
                pages_in_chunk = set([l[1] for l in current])
                chunk_hash = hash(chunk_text[:100])
                
                if chunk_hash not in seen_chunks:
                    seen_chunks.add(chunk_hash)
                    chunks.append((
                        chunk_text,
                        ",".join(sorted(pages_in_chunk, key=lambda x: int(x) if x.isdigit() else 0))
                    ))
                
                if overlap > 0:
                    keep_lines = []
                    keep_length = 0
                    for item in reversed(current):
                        if keep_length + len(item[0]) + 1 <= overlap:
                            keep_lines.insert(0, item)
                            keep_length += len(item[0]) + 1
                        else:
                            break
                    current = keep_lines
                    length = keep_length
                else:
                    current = []
                    length = 0
        
        if current:
            chunk_text = "\n".join([l[0] for l in current])
            pages_in_chunk = set([l[1] for l in current])
            chunk_hash = hash(chunk_text[:100])
            if chunk_hash not in seen_chunks:
                chunks.append((
                    chunk_text,
                    ",".join(sorted(pages_in_chunk, key=lambda x: int(x) if x.isdigit() else 0))
                ))
        
        return chunks

    log("⏳ STEP 3: Scanning for PDF files...")
    all_pdfs = [f for f in os.listdir(pdf_dir) if f.lower().endswith('.pdf')]
    pdfs = [f for f in all_pdfs if f not in indexed_sources]
    
    log(f"   ✓ Already Indexed: {len(indexed_sources)} document(s)")
    log(f"   ✓ New PDFs Found: {len(pdfs)} document(s)")
    log("")

    if not pdfs:
        log("   ℹ No new PDFs to index. All documents are up to date.")
        log("=" * 70)
        return True, []

    total_chunks_all = 0
    total_stored_all = 0
    all_pdf_info = []

    for pdf_index, pdf in enumerate(pdfs, 1):
        path = os.path.join(pdf_dir, pdf)
        log(f"📄 PROCESSING PDF {pdf_index}/{len(pdfs)}: {pdf}")
        log("-" * 70)

        log("   ⏳ Extracting text...")
        extract_start = time.time()
        total_pages_ref = [0]
        text = extract_text(path, total_pages_ref)
        total_pages = total_pages_ref[0]
        extract_time = time.time() - extract_start

        log(f"   ✓ Extracted {len(text):,} characters from {total_pages} pages")
        log(f"   ✓ Extraction time: {extract_time:.1f} seconds")
        log("")

        if len(text) == 0:
            log("   ✗ No text extracted. Skipping this PDF.")
            continue

        log("   ⏳ Creating chunks (with duplicate removal)...")
        chunk_start = time.time()
        chunks = chunk_text(text, chunk_size, chunk_overlap)
        chunk_time = time.time() - chunk_start
        total_chunks = len(chunks)

        log(f"   ✓ Created {total_chunks:,} unique chunks")
        log(f"   ✓ Chunking time: {chunk_time:.1f} seconds")
        log("")

        if not chunks:
            log("   ✗ No chunks created. Skipping.")
            continue

        log("   ⏳ Creating embeddings...")
        embed_start = time.time()
        texts = [c[0] for c in chunks]

        batch_size = 100
        embeddings = []
        for i in range(0, len(texts), batch_size):
            end = min(i + batch_size, len(texts))
            batch_embeddings = embedder.encode(texts[i:end]).tolist()
            embeddings.extend(batch_embeddings)
            progress_pct = (end / len(texts))
            log(f"   🔢 Embeddings: {end}/{len(texts)} ({progress_pct*100:.1f}%)")
            update_progress(progress_pct)
        log("")

        embed_time = time.time() - embed_start
        log(f"   ✓ Embeddings created in {embed_time:.1f} seconds")
        log("")

        log("   ⏳ Storing in database...")
        store_start = time.time()

        ids = [f"{pdf}_chunk_{i}" for i in range(len(chunks))]
        metas = [{
            "source": pdf,
            "page": chunks[i][1]
        } for i in range(len(chunks))]

        total_batches = (len(chunks) + batch_size - 1) // batch_size
        stored_count = 0

        for batch_idx, i in enumerate(range(0, len(chunks), batch_size)):
            end = min(i + batch_size, len(chunks))
            collection.add(
                ids=ids[i:end],
                embeddings=embeddings[i:end],
                documents=texts[i:end],
                metadatas=metas[i:end]
            )
            stored_count += (end - i)

            elapsed = time.time() - store_start
            pct = (stored_count / total_chunks)

            if stored_count > 0 and elapsed > 0:
                rate = stored_count / elapsed
                remaining_chunks = total_chunks - stored_count
                eta_seconds = remaining_chunks / rate if rate > 0 else 0
                eta_str = str(timedelta(seconds=int(eta_seconds)))
            else:
                eta_str = "Calculating..."

            log(f"   📦 Stored: {stored_count:,} / {total_chunks:,} chunks ({pct*100:.1f}%)")
            log(f"   📊 Batch: {batch_idx + 1} / {total_batches}")
            log(f"   ⏱️  ETA: {eta_str}")
            log(f"   ⚡ Rate: {rate:.1f} chunks/second")
            log("-" * 50)
            update_progress(pct)

        store_time = time.time() - store_start
        total_chunks_all += total_chunks
        total_stored_all += stored_count

        all_pdf_info.append({
            "name": pdf,
            "pages": total_pages,
            "chunks": total_chunks
        })

        log(f"   ✓ Stored {stored_count:,} chunks in {store_time:.1f} seconds")
        log(f"   ✓ PDF complete!")
        log("")

    total_in_db = collection.count()
    total_time = time.time() - start_time

    log("=" * 70)
    log("✅ INDEXING COMPLETE")
    log("=" * 70)
    log(f"   📚 Total PDFs processed: {len(pdfs)}")
    log(f"   📄 Total chunks created: {total_chunks_all:,}")
    log(f"   📦 Total chunks stored: {total_stored_all:,}")
    log(f"   🗄️  Database total: {total_in_db:,} documents")
    log(f"   ⏱️  Total time: {str(timedelta(seconds=int(total_time)))}")
    log(f"   ⚡ Average rate: {total_stored_all/total_time:.1f} chunks/second")
    log("=" * 70)
    log("")

    return True, all_pdf_info

# ============ PART 2: MODERN GUI ============

class ChatbotGUI:
    def __init__(self, root, pdf_info=None):
        self.root = root
        self.pdf_info = pdf_info or []
        self.BASE_DIR = r"C:\Shoby deathless laptop folder\RAG chatbots with python verification"
        self.is_indexing = False
        self.stop_generation = False
        self.models_loaded = False
        self.search_only = False
        
        # Chat history
        self.history_db = ChatHistory(os.path.join(self.BASE_DIR, "chat_history.db"))
        
        # Load settings
        self.settings_file = os.path.join(self.BASE_DIR, "settings.json")
        self.settings = self.load_settings()
        
        # Apply theme from settings
        theme = self.settings.get("theme", "Dark")
        ctk.set_appearance_mode(theme.lower())
        
        # Apply accent color
        accent = self.settings.get("accent_color", "Blue")
        self.apply_accent_color(accent)
        
        # Configure root
        self.root.title("📚 Document AI - RAG Chatbot")
        self.root.geometry("1200x1100")
        
        # Create GUI immediately
        self.create_widgets()
        self.refresh_document_list()
        
        self.gui_event("�PLANEM AI - RAG Chatbot Started")
        self.gui_event("=" * 50)
        self.gui_event("Loading models in background...")
        
        # Load models in background
        self.update_system_status("Embedding Model: Loading...", "warning")
        threading.Thread(target=self.load_models, daemon=True).start()
        
        self.start_status_updates()

    def apply_accent_color(self, accent_name):
        """Apply accent color to the application"""
        accent_map = {
            "Blue": "blue",
            "Green": "green",
            "Orange": "orange",
            "Purple": "purple",
            "Red": "red"
        }
        color = accent_map.get(accent_name, "blue")
        try:
            ctk.set_default_color_theme(color)
        except:
            pass

    def start_status_updates(self):
        """Start periodic system status updates"""
        def update_status():
            while True:
                time.sleep(5)
                self.root.after(0, self.update_system_status_display)
        threading.Thread(target=update_status, daemon=True).start()

    def update_system_status_display(self):
        """Update the system status display"""
        if hasattr(self, 'system_status_label'):
            status_text = "🟢 SYSTEM STATUS\n\n"
            
            if hasattr(self, 'embedder'):
                status_text += "Embedding Model: ✅ Ready\n"
            else:
                status_text += "Embedding Model: ⏳ Loading...\n"
            
            if hasattr(self, 'collection'):
                try:
                    count = self.collection.count()
                    status_text += f"Chroma: ✅ Ready ({count} docs)\n"
                except:
                    status_text += "Chroma: ⚠️ Connected\n"
            else:
                status_text += "Chroma: ⏳ Loading...\n"
            
            try:
                import ollama
                ollama.list()
                status_text += f"Ollama: ✅ Ready\n"
            except:
                status_text += "Ollama: ⏳ Checking...\n"
            
            doc_count = self.status_vars["documents"].get()
            status_text += f"Documents: {doc_count}\n"
            
            chunk_count = self.status_vars["chunks"].get()
            status_text += f"Chunks: {chunk_count}\n"
            
            status_text += f"Model: {self.settings.get('model', 'tinyllama')}\n"
            status_text += f"Search Only: {'✅' if self.search_only else '❌'}\n"
            status_text += f"Answer Style: {self.settings.get('answer_style', 'Short')}"
            
            self.system_status_label.configure(text=status_text)

    def load_settings(self):
        """Load settings from JSON file"""
        default_settings = {
            "chunk_size": 800,
            "chunk_overlap": 150,
            "top_k": 10,
            "max_context_chunks": 3,
            "similarity_threshold": 0.50,  # Increased from 0.30 for cosine similarity
            "temperature": 0.2,
            "model": "tinyllama",
            "search_only": False,
            "theme": "Dark",
            "accent_color": "Blue",
            "answer_style": "Short",
            "max_sentences": 3
        }
        
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r') as f:
                    saved = json.load(f)
                    for key in default_settings:
                        if key not in saved:
                            saved[key] = default_settings[key]
                    return saved
        except Exception as e:
            print(f"Error loading settings: {e}")
        
        return default_settings

    def save_settings_to_file(self):
        """Save settings to JSON file"""
        try:
            with open(self.settings_file, 'w') as f:
                json.dump(self.settings, f, indent=2)
        except Exception as e:
            print(f"Error saving settings: {e}")

    def gui_log(self, msg, progress=None):
        """Log message to processing window"""
        if msg:
            self.processing_box.insert("end", msg + "\n")
            self.processing_box.see("end")
            self.root.update()
        
        if progress is not None:
            self.index_progress.set(progress)
            self.root.update()

    def gui_event(self, msg):
        """Log system event"""
        timestamp = time.strftime("%H:%M:%S")
        self.system_box.insert("end", f"[{timestamp}] {msg}\n")
        self.system_box.see("end")
        self.root.update()

    def gui_error(self, msg):
        """Log error to error console"""
        timestamp = time.strftime("%H:%M:%S")
        self.error_box.insert("end", f"[{timestamp}] ERROR: {msg}\n")
        self.error_box.see("end")
        self.root.update()

    def update_system_status(self, status, level="info"):
        """Update system status label with color coding"""
        colors = {
            "info": "#8b949e",
            "warning": "#d29922",
            "error": "#f85149",
            "success": "#3fb950"
        }
        if hasattr(self, 'system_status_label'):
            self.system_status_label.configure(text=status, text_color=colors.get(level, "#8b949e"))

    def load_models(self):
        from sentence_transformers import SentenceTransformer
        import chromadb
        import ollama

        try:
            self.gui_event("Loading embedding model...")
            self.update_system_status("Embedding Model: Loading...", "warning")
            self.embedder = SentenceTransformer(os.path.join(self.BASE_DIR, "models", "all-MiniLM-L6-v2"))
            self.gui_event("✓ Embedding model ready")
            self.update_system_status("Embedding Model: ✅ Ready", "success")

            self.gui_event("Connecting to Chroma database...")
            client = chromadb.PersistentClient(path=os.path.join(self.BASE_DIR, "chroma_db"))
            
            try:
                self.collection = client.get_collection("documents")
                self.gui_event("✓ Database connected")
            except Exception as e:
                self.gui_event(f"Collection missing: {e}")
                self.gui_event("Creating new collection with cosine similarity...")
                # Create collection with cosine similarity space
                self.collection = client.create_collection(
                    name="documents", 
                    metadata={"hnsw:space": "cosine"}
                )
                self.gui_event("✓ New collection created with cosine similarity")

            self.gui_event("Checking Ollama...")
            try:
                ollama.list()
                self.gui_event("✓ Ollama ready")
            except Exception as e:
                self.gui_event(f"⚠ Ollama error: {e}")
                self.gui_error(f"Ollama connection failed: {e}")
            
            count = self.collection.count()
            if count == 0:
                self.gui_event("ℹ️ No documents indexed yet.")
                self.gui_event("   Upload PDFs and click 'UPDATE INDEXES' to get started.")
            else:
                self.gui_event(f"✓ Database has {count} documents")
            
            self.models_loaded = True
            self.update_system_status("✅ All systems ready", "success")
            self.status_label.configure(text="Ready", text_color="#8b949e")
            self.refresh_document_list()
            self.update_status_cards()
            
        except Exception as e:
            self.gui_error(f"Error loading models: {str(e)}")
            self.update_system_status("❌ Error loading models", "error")
            self.status_label.configure(text="Error loading models", text_color="#f85149")
            messagebox.showerror("Model Error", f"Failed to load models:\n{str(e)}")

    def create_widgets(self):
        # Main scrollable frame
        self.main_frame = ctk.CTkScrollableFrame(
            self.root,
            fg_color="transparent"
        )
        self.main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # ===== STATUS LABEL =====
        self.status_label = ctk.CTkLabel(
            self.main_frame,
            text="Starting...",
            font=("Segoe UI", 12, "bold")
        )
        self.status_label.pack(anchor="w", pady=(0, 10))

        # ===== SYSTEM STATUS =====
        status_frame = ctk.CTkFrame(self.main_frame)
        status_frame.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            status_frame,
            text="🟢 SYSTEM STATUS",
            font=("Segoe UI", 14, "bold"),
            text_color="#3fb950"
        ).pack(anchor="w", padx=15, pady=(10, 5))

        self.system_status_label = ctk.CTkLabel(
            status_frame,
            text="Loading...",
            font=("Consolas", 11),
            justify="left"
        )
        self.system_status_label.pack(anchor="w", padx=15, pady=(0, 10))

        # ===== STATUS CARDS =====
        cards_frame = ctk.CTkFrame(self.main_frame)
        cards_frame.pack(fill="x", pady=(0, 10))

        self.status_vars = {
            "documents": ctk.StringVar(value="0"),
            "chunks": ctk.StringVar(value="0"),
            "database": ctk.StringVar(value="0"),
            "last_updated": ctk.StringVar(value="Never")
        }

        status_grid = ctk.CTkFrame(cards_frame)
        status_grid.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(
            status_grid,
            text="📄 Documents",
            font=("Segoe UI", 10)
        ).grid(row=0, column=0, padx=10, pady=5, sticky="w")
        
        ctk.CTkLabel(
            status_grid,
            textvariable=self.status_vars["documents"],
            font=("Segoe UI", 16, "bold")
        ).grid(row=1, column=0, padx=10, pady=5, sticky="w")

        ctk.CTkLabel(
            status_grid,
            text="🧩 Chunks",
            font=("Segoe UI", 10)
        ).grid(row=0, column=1, padx=10, pady=5, sticky="w")
        
        ctk.CTkLabel(
            status_grid,
            textvariable=self.status_vars["chunks"],
            font=("Segoe UI", 16, "bold")
        ).grid(row=1, column=1, padx=10, pady=5, sticky="w")

        ctk.CTkLabel(
            status_grid,
            text="💾 Database",
            font=("Segoe UI", 10)
        ).grid(row=0, column=2, padx=10, pady=5, sticky="w")
        
        ctk.CTkLabel(
            status_grid,
            textvariable=self.status_vars["database"],
            font=("Segoe UI", 16, "bold")
        ).grid(row=1, column=2, padx=10, pady=5, sticky="w")

        ctk.CTkLabel(
            status_grid,
            text="⏱ Last Updated",
            font=("Segoe UI", 10)
        ).grid(row=0, column=3, padx=10, pady=5, sticky="w")
        
        ctk.CTkLabel(
            status_grid,
            textvariable=self.status_vars["last_updated"],
            font=("Segoe UI", 12)
        ).grid(row=1, column=3, padx=10, pady=5, sticky="w")

        # ===== QUESTION MOUTH (with vertical resize handle) =====
        q_frame = ctk.CTkFrame(self.main_frame)
        q_frame.pack(fill="x", pady=(0, 10))

        # Resize handle for Question section
        q_resize = ctk.CTkFrame(q_frame, height=5, fg_color="#30363d", cursor="sb_v_double_arrow")
        q_resize.pack(fill="x", padx=0, pady=0)
        
        # Bind resize events
        q_resize.bind("<Button-1>", lambda e: self.start_resize(e, q_frame, "question"))
        q_resize.bind("<B1-Motion>", lambda e: self.do_resize(e, q_frame, "question"))

        q_header = ctk.CTkFrame(q_frame, fg_color="transparent")
        q_header.pack(fill="x", padx=15, pady=(10, 5))

        ctk.CTkLabel(
            q_header,
            text="🗣️ QUESTION",
            font=("Segoe UI", 14, "bold"),
            text_color="#3fb950"
        ).pack(side="left")

        self.search_only_toggle = ctk.CTkButton(
            q_header,
            text="🔍 SEARCH ONLY",
            command=self.toggle_search_only,
            fg_color="#1f6feb",
            hover_color="#1a5fc7",
            width=120
        )
        self.search_only_toggle.pack(side="right", padx=5)

        self.stop_button = ctk.CTkButton(
            q_header,
            text="🛑 STOP",
            command=self.stop_generation_handler,
            fg_color="#da3633",
            hover_color="#b02b2b",
            width=80,
            state="disabled"
        )
        self.stop_button.pack(side="right", padx=5)

        self.question_entry = ctk.CTkEntry(
            q_frame,
            placeholder_text="Ask a question about your documents...",
            height=45
        )
        self.question_entry.pack(fill="x", padx=15, pady=(0, 10))
        self.question_entry.bind("<Return>", lambda e: self.ask())

        self.ask_button = ctk.CTkButton(
            q_frame,
            text="🔍 ASK",
            command=self.ask,
            height=40,
            fg_color="#238636",
            hover_color="#2ea043"
        )
        self.ask_button.pack(padx=15, pady=(0, 10))

        # ===== ANSWER MOUTH (with vertical resize handle) =====
        a_frame = ctk.CTkFrame(self.main_frame)
        a_frame.pack(fill="both", expand=True, pady=(0, 10))

        a_resize = ctk.CTkFrame(a_frame, height=5, fg_color="#30363d", cursor="sb_v_double_arrow")
        a_resize.pack(fill="x", padx=0, pady=0)
        a_resize.bind("<Button-1>", lambda e: self.start_resize(e, a_frame, "answer"))
        a_resize.bind("<B1-Motion>", lambda e: self.do_resize(e, a_frame, "answer"))

        a_header = ctk.CTkFrame(a_frame, fg_color="transparent")
        a_header.pack(fill="x", padx=15, pady=(10, 5))

        ctk.CTkLabel(
            a_header,
            text="🤖 ANSWER",
            font=("Segoe UI", 14, "bold"),
            text_color="#a371f7"
        ).pack(side="left")

        ctk.CTkButton(
            a_header,
            text="📄 Export Chat",
            command=self.export_chat,
            fg_color="#1f6feb",
            hover_color="#1a5fc7",
            width=120
        ).pack(side="right", padx=5)

        ctk.CTkButton(
            a_header,
            text="📜 History",
            command=self.show_history,
            fg_color="#d29922",
            hover_color="#b0881a",
            width=100
        ).pack(side="right", padx=5)

        self.answer_box = ctk.CTkTextbox(
            a_frame,
            height=200,
            font=("Consolas", 11)
        )
        self.answer_box.pack(fill="both", expand=True, padx=15, pady=(0, 10))

        # ===== CONFIDENCE BAR =====
        conf_frame = ctk.CTkFrame(self.main_frame)
        conf_frame.pack(fill="x", pady=(0, 10))

        conf_header = ctk.CTkFrame(conf_frame, fg_color="transparent")
        conf_header.pack(fill="x", padx=15, pady=(5, 0))

        ctk.CTkLabel(
            conf_header,
            text="📊 Retrieval Confidence",
            font=("Segoe UI", 12)
        ).pack(side="left")

        self.confidence_label = ctk.CTkLabel(
            conf_header,
            text="--%",
            font=("Segoe UI", 12, "bold")
        )
        self.confidence_label.pack(side="right")

        self.confidence_bar = ctk.CTkProgressBar(
            conf_frame,
            height=15,
            progress_color="#30363d"
        )
        self.confidence_bar.pack(fill="x", padx=15, pady=(5, 10))
        self.confidence_bar.set(0)

        # ===== SOURCE VERIFICATION (with vertical resize handle) =====
        p_frame = ctk.CTkFrame(self.main_frame)
        p_frame.pack(fill="x", pady=(0, 10))

        p_resize = ctk.CTkFrame(p_frame, height=5, fg_color="#30363d", cursor="sb_v_double_arrow")
        p_resize.pack(fill="x", padx=0, pady=0)
        p_resize.bind("<Button-1>", lambda e: self.start_resize(e, p_frame, "source"))
        p_resize.bind("<B1-Motion>", lambda e: self.do_resize(e, p_frame, "source"))

        ctk.CTkLabel(
            p_frame,
            text="📄 SOURCE VERIFICATION & EVIDENCE",
            font=("Segoe UI", 14, "bold"),
            text_color="#d29922"
        ).pack(anchor="w", padx=15, pady=(10, 5))

        self.pages_box = ctk.CTkTextbox(
            p_frame,
            height=150,
            font=("Consolas", 10)
        )
        self.pages_box.pack(fill="x", padx=15, pady=(0, 10))

        # ===== SETTINGS MOUTH (with vertical resize handle) =====
        settings_frame = ctk.CTkFrame(self.main_frame)
        settings_frame.pack(fill="x", pady=(0, 10))

        settings_resize = ctk.CTkFrame(settings_frame, height=5, fg_color="#30363d", cursor="sb_v_double_arrow")
        settings_resize.pack(fill="x", padx=0, pady=0)
        settings_resize.bind("<Button-1>", lambda e: self.start_resize(e, settings_frame, "settings"))
        settings_resize.bind("<B1-Motion>", lambda e: self.do_resize(e, settings_frame, "settings"))

        ctk.CTkLabel(
            settings_frame,
            text="⚙ SETTINGS",
            font=("Segoe UI", 14, "bold"),
            text_color="#f0883e"
        ).pack(anchor="w", padx=15, pady=(10, 5))

        settings_grid = ctk.CTkFrame(settings_frame, fg_color="transparent")
        settings_grid.pack(fill="x", padx=15, pady=5)

        # Row 0: Chunk settings
        ctk.CTkLabel(
            settings_grid,
            text="Chunk Size:"
        ).grid(row=0, column=0, padx=5, pady=5, sticky="w")

        self.chunk_size_entry = ctk.CTkEntry(settings_grid, width=100)
        self.chunk_size_entry.insert(0, str(self.settings.get("chunk_size", 800)))
        self.chunk_size_entry.grid(row=1, column=0, padx=5, pady=5)

        ctk.CTkLabel(
            settings_grid,
            text="Chunk Overlap:"
        ).grid(row=0, column=1, padx=5, pady=5, sticky="w")

        self.chunk_overlap_entry = ctk.CTkEntry(settings_grid, width=100)
        self.chunk_overlap_entry.insert(0, str(self.settings.get("chunk_overlap", 150)))
        self.chunk_overlap_entry.grid(row=1, column=1, padx=5, pady=5)

        ctk.CTkLabel(
            settings_grid,
            text="Top K:"
        ).grid(row=0, column=2, padx=5, pady=5, sticky="w")

        self.topk_entry = ctk.CTkEntry(settings_grid, width=100)
        self.topk_entry.insert(0, str(self.settings.get("top_k", 10)))
        self.topk_entry.grid(row=1, column=2, padx=5, pady=5)

        ctk.CTkLabel(
            settings_grid,
            text="Max Context Chunks:"
        ).grid(row=0, column=3, padx=5, pady=5, sticky="w")

        self.context_chunks_entry = ctk.CTkEntry(settings_grid, width=100)
        self.context_chunks_entry.insert(0, str(self.settings.get("max_context_chunks", 3)))
        self.context_chunks_entry.grid(row=1, column=3, padx=5, pady=5)

        # Row 2: Threshold and Temperature
        ctk.CTkLabel(
            settings_grid,
            text="Similarity Threshold:"
        ).grid(row=2, column=0, padx=5, pady=5, sticky="w")

        self.threshold_slider = ctk.CTkSlider(
            settings_grid,
            from_=0,
            to=1,
            width=100
        )
        self.threshold_slider.set(self.settings.get("similarity_threshold", 0.50))
        self.threshold_slider.grid(row=3, column=0, padx=5, pady=5)

        ctk.CTkLabel(
            settings_grid,
            text="Temperature:"
        ).grid(row=2, column=1, padx=5, pady=5, sticky="w")

        self.temp_slider = ctk.CTkSlider(
            settings_grid,
            from_=0,
            to=1,
            width=100
        )
        self.temp_slider.set(self.settings.get("temperature", 0.2))
        self.temp_slider.grid(row=3, column=1, padx=5, pady=5)

        ctk.CTkLabel(
            settings_grid,
            text="Answer Style:"
        ).grid(row=2, column=2, padx=5, pady=5, sticky="w")

        self.answer_style_menu = ctk.CTkOptionMenu(
            settings_grid,
            values=["Short", "Medium", "Detailed"],
            width=100
        )
        self.answer_style_menu.set(self.settings.get("answer_style", "Short"))
        self.answer_style_menu.grid(row=3, column=2, padx=5, pady=5)

        ctk.CTkLabel(
            settings_grid,
            text="Max Sentences:"
        ).grid(row=2, column=3, padx=5, pady=5, sticky="w")

        self.max_sentences_entry = ctk.CTkEntry(settings_grid, width=100)
        self.max_sentences_entry.insert(0, str(self.settings.get("max_sentences", 3)))
        self.max_sentences_entry.grid(row=3, column=3, padx=5, pady=5)

        # Row 4: Model and Theme
        ctk.CTkLabel(
            settings_grid,
            text="LLM Model:"
        ).grid(row=4, column=0, padx=5, pady=5, sticky="w")

        self.model_menu = ctk.CTkOptionMenu(
            settings_grid,
            values=["tinyllama", "phi3", "gemma", "qwen2.5"],
            width=120
        )
        self.model_menu.set(self.settings.get("model", "tinyllama"))
        self.model_menu.grid(row=5, column=0, padx=5, pady=5)

        ctk.CTkLabel(
            settings_grid,
            text="Theme:"
        ).grid(row=4, column=1, padx=5, pady=5, sticky="w")

        self.theme_menu = ctk.CTkOptionMenu(
            settings_grid,
            values=["Dark", "Light", "System"],
            width=100
        )
        self.theme_menu.set(self.settings.get("theme", "Dark"))
        self.theme_menu.grid(row=5, column=1, padx=5, pady=5)

        ctk.CTkLabel(
            settings_grid,
            text="Accent Color:"
        ).grid(row=4, column=2, padx=5, pady=5, sticky="w")

        self.accent_menu = ctk.CTkOptionMenu(
            settings_grid,
            values=["Blue", "Green", "Orange", "Purple", "Red"],
            width=100
        )
        self.accent_menu.set(self.settings.get("accent_color", "Blue"))
        self.accent_menu.grid(row=5, column=2, padx=5, pady=5)

        # Row 6: Save and Rebuild buttons
        settings_btn_frame = ctk.CTkFrame(settings_grid, fg_color="transparent")
        settings_btn_frame.grid(row=6, column=0, columnspan=4, pady=10)

        ctk.CTkButton(
            settings_btn_frame,
            text="💾 Save Settings",
            command=self.save_settings,
            fg_color="#1f6feb",
            hover_color="#1a5fc7",
            width=120
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            settings_btn_frame,
            text="🔥 Rebuild Database",
            command=self.rebuild_database,
            fg_color="#da3633",
            hover_color="#b02b2b",
            width=150
        ).pack(side="left", padx=5)

        # ===== DOCUMENT MANAGER (with vertical resize handle) =====
        doc_frame = ctk.CTkFrame(self.main_frame)
        doc_frame.pack(fill="x", pady=(0, 10))

        doc_resize = ctk.CTkFrame(doc_frame, height=5, fg_color="#30363d", cursor="sb_v_double_arrow")
        doc_resize.pack(fill="x", padx=0, pady=0)
        doc_resize.bind("<Button-1>", lambda e: self.start_resize(e, doc_frame, "doc"))
        doc_resize.bind("<B1-Motion>", lambda e: self.do_resize(e, doc_frame, "doc"))

        ctk.CTkLabel(
            doc_frame,
            text="📚 DOCUMENT MANAGER",
            font=("Segoe UI", 14, "bold"),
            text_color="#58a6ff"
        ).pack(anchor="w", padx=15, pady=(10, 5))

        self.doc_box = ctk.CTkTextbox(
            doc_frame,
            height=150,
            font=("Consolas", 11)
        )
        self.doc_box.pack(fill="x", padx=15, pady=(0, 10))

        doc_btn_frame = ctk.CTkFrame(doc_frame, fg_color="transparent")
        doc_btn_frame.pack(fill="x", padx=15, pady=(0, 10))

        ctk.CTkButton(
            doc_btn_frame,
            text="🗑 DELETE DOCUMENT",
            command=self.delete_document,
            fg_color="#da3633",
            hover_color="#b02b2b"
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            doc_btn_frame,
            text="🔄 REFRESH LIST",
            command=self.refresh_document_list,
            fg_color="#1f6feb",
            hover_color="#1a5fc7"
        ).pack(side="left", padx=5)

        # ===== DOCUMENT INGESTION (with vertical resize handle) =====
        upload_frame = ctk.CTkFrame(self.main_frame)
        upload_frame.pack(fill="x", pady=(0, 10))

        upload_resize = ctk.CTkFrame(upload_frame, height=5, fg_color="#30363d", cursor="sb_v_double_arrow")
        upload_resize.pack(fill="x", padx=0, pady=0)
        upload_resize.bind("<Button-1>", lambda e: self.start_resize(e, upload_frame, "upload"))
        upload_resize.bind("<B1-Motion>", lambda e: self.do_resize(e, upload_frame, "upload"))

        ctk.CTkLabel(
            upload_frame,
            text="📥 DOCUMENT INGESTION",
            font=("Segoe UI", 14, "bold"),
            text_color="#3fb950"
        ).pack(anchor="w", padx=15, pady=(10, 5))

        upload_btn_frame = ctk.CTkFrame(upload_frame, fg_color="transparent")
        upload_btn_frame.pack(fill="x", padx=15, pady=(0, 10))

        ctk.CTkButton(
            upload_btn_frame,
            text="➕ ADD PDF",
            command=self.upload_pdf,
            fg_color="#238636",
            hover_color="#2ea043"
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            upload_btn_frame,
            text="🔄 UPDATE INDEXES",
            command=self.update_indexes,
            fg_color="#1f6feb",
            hover_color="#1a5fc7"
        ).pack(side="left", padx=5)

        # ===== PROCESSING MOUTH (with vertical resize handle) =====
        self.processing_frame = ctk.CTkFrame(self.main_frame)
        self.processing_frame.pack(fill="x", pady=(0, 10))

        processing_resize = ctk.CTkFrame(self.processing_frame, height=5, fg_color="#30363d", cursor="sb_v_double_arrow")
        processing_resize.pack(fill="x", padx=0, pady=0)
        processing_resize.bind("<Button-1>", lambda e: self.start_resize(e, self.processing_frame, "processing"))
        processing_resize.bind("<B1-Motion>", lambda e: self.do_resize(e, self.processing_frame, "processing"))

        ctk.CTkLabel(
            self.processing_frame,
            text="⚙ PROCESSING LOG",
            font=("Segoe UI", 14, "bold"),
            text_color="#f0883e"
        ).pack(anchor="w", padx=15, pady=(10, 5))

        self.processing_box = ctk.CTkTextbox(
            self.processing_frame,
            height=150,
            font=("Consolas", 10)
        )
        self.processing_box.pack(fill="both", expand=True, padx=15, pady=(0, 5))

        self.index_progress = ctk.CTkProgressBar(
            self.processing_frame,
            height=20
        )
        self.index_progress.pack(fill="x", padx=15, pady=(0, 10))
        self.index_progress.set(0)

        # ===== SYSTEM EVENTS (with vertical resize handle) =====
        system_frame = ctk.CTkFrame(self.main_frame)
        system_frame.pack(fill="x", pady=(0, 10))

        system_resize = ctk.CTkFrame(system_frame, height=5, fg_color="#30363d", cursor="sb_v_double_arrow")
        system_resize.pack(fill="x", padx=0, pady=0)
        system_resize.bind("<Button-1>", lambda e: self.start_resize(e, system_frame, "system"))
        system_resize.bind("<B1-Motion>", lambda e: self.do_resize(e, system_frame, "system"))

        ctk.CTkLabel(
            system_frame,
            text="📋 SYSTEM EVENTS",
            font=("Segoe UI", 14, "bold"),
            text_color="#58a6ff"
        ).pack(anchor="w", padx=15, pady=(10, 5))

        self.system_box = ctk.CTkTextbox(
            system_frame,
            height=100,
            font=("Consolas", 10)
        )
        self.system_box.pack(fill="x", padx=15, pady=(0, 10))

        # ===== ERROR CONSOLE (with vertical resize handle) =====
        self.error_frame = ctk.CTkFrame(self.main_frame)
        self.error_frame.pack(fill="x", pady=(0, 10))

        error_resize = ctk.CTkFrame(self.error_frame, height=5, fg_color="#30363d", cursor="sb_v_double_arrow")
        error_resize.pack(fill="x", padx=0, pady=0)
        error_resize.bind("<Button-1>", lambda e: self.start_resize(e, self.error_frame, "error"))
        error_resize.bind("<B1-Motion>", lambda e: self.do_resize(e, self.error_frame, "error"))

        ctk.CTkLabel(
            self.error_frame,
            text="🚨 ERROR CONSOLE",
            font=("Segoe UI", 14, "bold"),
            text_color="#f85149"
        ).pack(anchor="w", padx=15, pady=(10, 5))

        self.error_box = ctk.CTkTextbox(
            self.error_frame,
            height=80,
            font=("Consolas", 10)
        )
        self.error_box.pack(fill="x", padx=15, pady=(0, 10))

        # Footer
        footer = ctk.CTkLabel(
            self.main_frame,
            text="⚠️ This AI assistant provides information from your documents. Always verify important information.",
            font=("Segoe UI", 10),
            text_color="#f85149"
        )
        footer.pack(pady=(10, 5))

        self.gui_event("🚀 Application started successfully")
        self.update_system_status("🔄 Initializing...", "info")

        # Store frame heights for resize
        self.frame_heights = {}

    def start_resize(self, event, frame, name):
        """Start vertical resize operation"""
        self.resize_frame = frame
        self.resize_name = name
        self.resize_start_y = event.y_root
        self.resize_start_height = frame.winfo_height()

    def do_resize(self, event, frame, name):
        """Perform vertical resize operation"""
        if hasattr(self, 'resize_frame') and self.resize_frame == frame:
            delta_y = event.y_root - self.resize_start_y
            new_height = max(50, self.resize_start_height + delta_y)
            frame.configure(height=new_height)
            # Also resize the textbox inside
            for child in frame.winfo_children():
                if isinstance(child, ctk.CTkTextbox):
                    child.configure(height=new_height - 80)

    def toggle_search_only(self):
        """Toggle search-only mode"""
        self.search_only = not self.search_only
        if self.search_only:
            self.search_only_toggle.configure(
                text="🔍 SEARCH ONLY ✅",
                fg_color="#238636",
                hover_color="#2ea043"
            )
            self.gui_event("🔍 Search Only mode enabled - skipping LLM generation")
        else:
            self.search_only_toggle.configure(
                text="🔍 SEARCH ONLY",
                fg_color="#1f6feb",
                hover_color="#1a5fc7"
            )
            self.gui_event("🔍 Search Only mode disabled - LLM generation enabled")
        self.settings["search_only"] = self.search_only
        self.save_settings_to_file()

    def export_chat(self):
        """Export chat history to file"""
        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if not file_path:
            return
        
        try:
            history = self.history_db.get_history(limit=100)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write("=" * 70 + "\n")
                f.write("�PLANEM AI - CHAT HISTORY EXPORT\n")
                f.write("=" * 70 + "\n\n")
                
                for entry in history:
                    timestamp, question, answer, sources, confidence, model = entry
                    f.write(f"📅 {timestamp}\n")
                    f.write(f"❓ Question: {question}\n")
                    f.write(f"🤖 Answer: {answer}\n")
                    f.write(f"📊 Confidence: {confidence:.1f}%\n")
                    f.write(f"🧠 Model: {model}\n")
                    if sources:
                        try:
                            sources_list = json.loads(sources)
                            f.write(f"📚 Sources: {', '.join(sources_list[:5])}\n")
                        except:
                            pass
                    f.write("-" * 50 + "\n\n")
            
            messagebox.showinfo("Export Complete", f"Chat history exported to:\n{file_path}")
        except Exception as e:
            self.gui_error(f"Export error: {e}")
            messagebox.showerror("Error", f"Failed to export chat:\n{str(e)}")

    def show_history(self):
        """Show chat history in a popup window"""
        history = self.history_db.get_history(limit=20)
        
        if not history:
            messagebox.showinfo("Chat History", "No chat history found.")
            return
        
        history_window = ctk.CTkToplevel(self.root)
        history_window.title("📜 Chat History")
        history_window.geometry("800x600")
        
        textbox = ctk.CTkTextbox(history_window, font=("Consolas", 10))
        textbox.pack(fill="both", expand=True, padx=10, pady=10)
        
        for entry in history:
            timestamp, question, answer, sources, confidence, model = entry
            textbox.insert("end", f"📅 {timestamp}\n")
            textbox.insert("end", f"❓ {question}\n")
            textbox.insert("end", f"🤖 {answer[:200]}...\n")
            textbox.insert("end", f"📊 Confidence: {confidence:.1f}%\n")
            textbox.insert("end", "-" * 50 + "\n\n")
        
        textbox.configure(state="disabled")

    def update_status_cards(self):
        """Update status cards with current database info"""
        try:
            if not hasattr(self, 'collection'):
                return
            
            count = self.collection.count()
            self.status_vars["database"].set(f"{count:,}")
            
            results = self.collection.get(include=["metadatas"], limit=1000)
            sources = set()
            for meta in results['metadatas']:
                if meta and 'source' in meta:
                    sources.add(meta['source'])
            self.status_vars["documents"].set(str(len(sources)))
            
            self.status_vars["chunks"].set(f"{count:,}")
            
            from datetime import datetime
            self.status_vars["last_updated"].set(datetime.now().strftime("%H:%M:%S"))
        except Exception as e:
            self.gui_error(f"Error updating status cards: {e}")

    def get_indexed_sources(self):
        """Get set of sources already indexed in Chroma"""
        indexed = set()
        try:
            if not hasattr(self, 'collection'):
                return indexed
            data = self.collection.get(include=["metadatas"], limit=1000)
            for meta in data["metadatas"]:
                if meta and "source" in meta:
                    indexed.add(meta["source"])
        except Exception as e:
            self.gui_error(f"Error getting indexed sources: {e}")
        return indexed

    def refresh_document_list(self):
        """Refresh document list with indexing status"""
        if not hasattr(self, 'doc_box'):
            return
            
        self.doc_box.delete("0.0", "end")
        
        pdf_dir = os.path.join(self.BASE_DIR, "test_data")
        indexed_sources = self.get_indexed_sources()
        
        if not os.path.exists(pdf_dir):
            os.makedirs(pdf_dir)
            self.doc_box.insert("end", "No PDF documents found.\n")
            return
        
        pdfs = [f for f in os.listdir(pdf_dir) if f.lower().endswith('.pdf')]
        
        if not pdfs:
            self.doc_box.insert("end", "No PDF documents found.\n")
            return
        
        for f in pdfs:
            if f in indexed_sources:
                self.doc_box.insert("end", f"✓ {f}  [INDEXED]\n", "indexed")
            else:
                self.doc_box.insert("end", f"✗ {f}  [NOT INDEXED]\n", "not_indexed")
        
        self.doc_box.tag_config("indexed", foreground="#3fb950")
        self.doc_box.tag_config("not_indexed", foreground="#f85149")
        
        self.update_status_cards()

    def upload_pdf(self):
        """Upload a new PDF file"""
        file = filedialog.askopenfilename(
            filetypes=[("PDF Files", "*.pdf")]
        )
        
        if not file:
            return
        
        target_dir = os.path.join(self.BASE_DIR, "test_data")
        os.makedirs(target_dir, exist_ok=True)
        
        filename = os.path.basename(file)
        target_path = os.path.join(target_dir, filename)
        
        shutil.copy(file, target_path)
        self.refresh_document_list()
        self.gui_event(f"📄 PDF uploaded: {filename}")
        
        messagebox.showinfo(
            "Added",
            f"PDF copied successfully: {filename}\nClick 'UPDATE INDEXES' to index it."
        )

    def delete_document(self):
        """Delete document from filesystem and Chroma"""
        try:
            selected = self.doc_box.get("sel.first", "sel.last")
        except:
            messagebox.showwarning("No Selection", "Please select a document to delete.")
            return
        
        if not selected:
            messagebox.showwarning("No Selection", "Please select a document to delete.")
            return
        
        if "✓ " in selected or "✗ " in selected:
            parts = selected.split("  [")
            filename = parts[0].replace("✓ ", "").replace("✗ ", "").strip()
        else:
            filename = selected.strip()
        
        if not filename or not filename.endswith('.pdf'):
            messagebox.showwarning("Invalid Selection", "Please select a valid document.")
            return
        
        if not messagebox.askyesno("Confirm Delete", f"Delete {filename}?"):
            return
        
        pdf_dir = os.path.join(self.BASE_DIR, "test_data")
        file_path = os.path.join(pdf_dir, filename)
        
        if os.path.exists(file_path):
            os.remove(file_path)
        
        try:
            if hasattr(self, 'collection'):
                results = self.collection.get(where={"source": filename})
                if results["ids"]:
                    self.collection.delete(ids=results["ids"])
                    self.gui_event(f"🗑️ Deleted from database: {filename}")
        except Exception as e:
            self.gui_error(f"Error deleting from Chroma: {e}")
        
        self.refresh_document_list()
        self.update_status_cards()
        messagebox.showinfo("Deleted", f"{filename} deleted successfully.")

    def update_indexes(self):
        """Update indexes for new documents only"""
        if self.is_indexing:
            return
        
        if not self.models_loaded:
            messagebox.showinfo("Loading", "Models are still loading. Please wait.")
            return
        
        self.is_indexing = True
        self.ask_button.configure(state="disabled")
        self.status_label.configure(text="Indexing in progress...")
        self.processing_box.delete("0.0", "end")
        self.index_progress.set(0)
        self.gui_event("🔄 Starting indexing process...")
        
        self._read_settings_from_gui()
        threading.Thread(target=self.reindex_documents, daemon=True).start()

    def _read_settings_from_gui(self):
        """Read settings from GUI widgets"""
        try:
            self.settings["chunk_size"] = int(self.chunk_size_entry.get())
            self.settings["chunk_overlap"] = int(self.chunk_overlap_entry.get())
            self.settings["top_k"] = int(self.topk_entry.get())
            self.settings["max_context_chunks"] = int(self.context_chunks_entry.get())
            self.settings["similarity_threshold"] = float(self.threshold_slider.get())
            self.settings["temperature"] = float(self.temp_slider.get())
            self.settings["model"] = self.model_menu.get()
            self.settings["answer_style"] = self.answer_style_menu.get()
            self.settings["theme"] = self.theme_menu.get()
            self.settings["accent_color"] = self.accent_menu.get()
            self.settings["max_sentences"] = int(self.max_sentences_entry.get())
        except Exception as e:
            self.gui_error(f"Error reading settings: {e}")

    def reindex_documents(self):
        """Reindex documents in background"""
        try:
            def callback(msg=None, progress=None):
                if msg:
                    self.root.after(0, lambda: self.gui_log(msg))
                if progress is not None:
                    self.root.after(0, lambda: self.gui_log(None, progress))
            
            success, new_pdf_info = index_documents(callback, self.settings)
            
            self.root.after(
                0,
                lambda: self._reindex_complete(success, new_pdf_info)
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.gui_error(f"Indexing error: {str(e)}")
            self.root.after(
                0,
                lambda: self._reindex_error(str(e))
            )

    def _reindex_complete(self, success, new_pdf_info):
        """Handle reindex completion"""
        self.is_indexing = False
        self.refresh_document_list()
        self.update_status_cards()
        self.ask_button.configure(state="normal")
        self.index_progress.set(1)
        
        if success:
            if new_pdf_info:
                count = len(new_pdf_info)
                self.gui_log(f"\n✅ Index updated successfully! {count} new document(s) indexed.")
                self.gui_event(f"✅ Indexing complete: {count} new documents indexed")
                messagebox.showinfo("Done", f"Index updated successfully!\n{count} new document(s) indexed.")
            else:
                self.gui_log("\n✅ All documents are already indexed.")
                self.gui_event("✅ No new documents to index")
                messagebox.showinfo("Done", "All documents are already indexed.\nNo new documents to process.")
        else:
            self.gui_log("\n❌ Indexing failed.")
            self.gui_error("Indexing failed")
            messagebox.showerror("Error", "Indexing failed. Check the error console for details.")
        
        self.status_label.configure(text="Ready")

    def _reindex_error(self, error):
        """Handle reindex error"""
        self.is_indexing = False
        self.ask_button.configure(state="normal")
        self.status_label.configure(text="Error occurred")
        self.gui_error(f"Indexing error: {error}")
        messagebox.showerror("Error", f"Indexing failed:\n{error}")

    def rebuild_database(self):
        """Rebuild the entire database from scratch"""
        if not self.models_loaded:
            messagebox.showinfo("Loading", "Models are still loading. Please wait.")
            return
            
        if not messagebox.askyesno("Rebuild Database", 
            "This will delete ALL existing data and rebuild the database from all PDFs.\n\nContinue?"):
            return
        
        if self.is_indexing:
            return
        
        chroma_path = os.path.join(self.BASE_DIR, "chroma_db")
        try:
            if os.path.exists(chroma_path):
                shutil.rmtree(chroma_path)
                self.gui_event("🗑️ Deleted existing database")
                self.gui_log("🗑️ Deleted existing database")
        except Exception as e:
            self.gui_error(f"Failed to delete database: {e}")
            messagebox.showerror("Error", f"Failed to delete database:\n{str(e)}")
            return
        
        try:
            import chromadb
            client = chromadb.PersistentClient(path=os.path.join(self.BASE_DIR, "chroma_db"))
            # Create collection with cosine similarity space
            self.collection = client.create_collection(
                name="documents", 
                metadata={"hnsw:space": "cosine"}
            )
            self.gui_event("✓ New database created with cosine similarity")
            self.gui_log("✓ New database created with cosine similarity")
        except Exception as e:
            self.gui_error(f"Failed to create database: {e}")
            messagebox.showerror("Error", f"Failed to create database:\n{str(e)}")
            return
        
        self.is_indexing = True
        self.ask_button.configure(state="disabled")
        self.status_label.configure(text="Rebuilding database...")
        self.processing_box.delete("0.0", "end")
        self.index_progress.set(0)
        self.gui_event("🔄 Rebuilding database from all PDFs...")
        
        self._read_settings_from_gui()
        threading.Thread(target=self.rebuild_database_thread, daemon=True).start()

    def rebuild_database_thread(self):
        """Rebuild database in background thread"""
        try:
            def callback(msg=None, progress=None):
                if msg:
                    self.root.after(0, lambda: self.gui_log(msg))
                if progress is not None:
                    self.root.after(0, lambda: self.gui_log(None, progress))
            
            success, new_pdf_info = index_documents(callback, self.settings)
            
            self.root.after(
                0,
                lambda: self._reindex_complete(success, new_pdf_info)
            )
        except Exception as e:
            self.gui_error(f"Rebuild error: {str(e)}")
            self.root.after(
                0,
                lambda: self._reindex_error(str(e))
            )

    def save_settings(self):
        """Save settings from GUI to settings object and file"""
        try:
            self.settings["chunk_size"] = int(self.chunk_size_entry.get())
            self.settings["chunk_overlap"] = int(self.chunk_overlap_entry.get())
            self.settings["top_k"] = int(self.topk_entry.get())
            self.settings["max_context_chunks"] = int(self.context_chunks_entry.get())
            self.settings["similarity_threshold"] = float(self.threshold_slider.get())
            self.settings["temperature"] = float(self.temp_slider.get())
            self.settings["model"] = self.model_menu.get()
            self.settings["answer_style"] = self.answer_style_menu.get()
            self.settings["theme"] = self.theme_menu.get()
            self.settings["accent_color"] = self.accent_menu.get()
            self.settings["max_sentences"] = int(self.max_sentences_entry.get())
            
            # Apply theme
            theme = self.settings["theme"].lower()
            ctk.set_appearance_mode(theme)
            
            # Apply accent color
            self.apply_accent_color(self.settings["accent_color"])
            
            self.save_settings_to_file()
            self.gui_event("💾 Settings saved")
            messagebox.showinfo("Saved", "Settings saved successfully!")
        except ValueError as e:
            self.gui_error(f"Invalid setting value: {e}")
            messagebox.showerror("Error", f"Invalid setting value:\n{str(e)}")

    def stop_generation_handler(self):
        """Handle stop button click"""
        self.stop_generation = True
        self.stop_button.configure(state="disabled")
        self.gui_event("🛑 Generation stopped by user")

    def calculate_confidence(self, answer, source_chunks, similarities):
        """
        Calculate comprehensive confidence score using Python analysis.
        
        Args:
            answer: The generated answer string
            source_chunks: List of retrieved text chunks
            similarities: List of similarity scores for each chunk
        
        Returns:
            dict: Various confidence scores and analysis
        """
        # Retrieval Score - average similarity
        retrieval_score = sum(similarities) / len(similarities) if similarities else 0
        
        # Best Chunk Score - highest similarity
        best_chunk_score = max(similarities) if similarities else 0
        
        # Coverage Score - how much of the answer is covered by source chunks
        answer_words = set(answer.lower().split())
        chunk_words = set()
        for chunk in source_chunks:
            chunk_words.update(chunk.lower().split())
        
        overlap = answer_words & chunk_words
        coverage_score = len(overlap) / max(len(answer_words), 1)
        
        # Evidence Score - how many chunks were retrieved (capped at 5)
        evidence_score = min(len(source_chunks) / 5, 1.0)
        
        # Final combined score
        final_score = (
            retrieval_score * 0.40 +
            best_chunk_score * 0.20 +
            coverage_score * 0.25 +
            evidence_score * 0.15
        ) * 100
        
        return {
            "retrieval": retrieval_score,
            "best_chunk": best_chunk_score,
            "coverage": coverage_score,
            "evidence": evidence_score,
            "final": final_score
        }

    def update_confidence_meter(self, confidence):
        """Update visual confidence meter"""
        self.confidence_bar.set(confidence / 100)
        self.confidence_label.configure(text=f"{confidence:.1f}%")
        
        if confidence >= 80:
            self.confidence_bar.configure(progress_color="#238636")
            status = "🟢 Strong Evidence"
            color = "#238636"
        elif confidence >= 60:
            self.confidence_bar.configure(progress_color="#d29922")
            status = "🟡 Moderate Evidence"
            color = "#d29922"
        else:
            self.confidence_bar.configure(progress_color="#f85149")
            status = "🔴 Weak Evidence"
            color = "#f85149"
        
        self.status_label.configure(text=status, text_color=color)

    def ask(self):
        q = self.question_entry.get().strip()
        if not q:
            messagebox.showwarning("Empty Question", "Please enter a question!")
            return
        
        if not self.models_loaded:
            messagebox.showwarning("Loading", "Models are still loading. Please wait.")
            return
        
        if not hasattr(self, 'embedder'):
            messagebox.showwarning("Loading", "Models are still loading. Please wait.")
            return
        
        self.stop_generation = False
        self.ask_button.configure(state="disabled", text="⏳ THINKING...")
        self.stop_button.configure(state="normal")
        self.status_label.configure(text="Searching documents...", text_color="#58a6ff")
        threading.Thread(target=self.process, args=(q,), daemon=True).start()

    def process(self, question):
        import ollama

        try:
            start_time = time.time()
            
            if self.stop_generation:
                return
            
            question_embedding = self.embedder.encode([question]).tolist()
            
            if self.stop_generation:
                return
            
            results = self.collection.query(
                query_embeddings=question_embedding,
                n_results=self.settings.get("top_k", 10),
                include=["documents", "metadatas", "distances"]
            )
            
            source_chunks = results['documents'][0]
            metadatas = results['metadatas'][0]
            distances = results['distances'][0]
            
            # Convert Cosine Distance to Cosine Similarity (1.0 is a perfect match)
            similarities = [1.0 - d for d in distances]
            
            # Apply similarity threshold
            threshold = self.settings.get("similarity_threshold", 0.50)
            filtered_chunks = []
            filtered_metas = []
            filtered_sims = []
            
            for chunk, meta, sim in zip(source_chunks, metadatas, similarities):
                if sim >= threshold:
                    filtered_chunks.append(chunk)
                    filtered_metas.append(meta)
                    filtered_sims.append(sim)
            
            if self.stop_generation:
                return
            
            # Get answer style instruction
            style = self.settings.get("answer_style", "Short")
            max_sentences = self.settings.get("max_sentences", 3)
            
            if style == "Short":
                instruction = f"Answer in maximum {max_sentences} sentences. Be very concise."
            elif style == "Medium":
                instruction = f"Answer in maximum {max_sentences + 2} sentences. Provide moderate detail."
            else:
                instruction = "Answer in detail. Provide comprehensive information from the document."
            
            # SEARCH ONLY MODE
            if self.search_only:
                answer = "🔍 SEARCH ONLY MODE - Retrieved chunks:\n\n"
                for i, chunk in enumerate(filtered_chunks[:5], 1):
                    page_info = ""
                    if i - 1 < len(filtered_metas) and 'page' in filtered_metas[i-1]:
                        page_info = f" [Page {filtered_metas[i-1]['page']}]"
                    answer += f"[{i}]{page_info}\n{chunk[:300]}...\n\n"
                answer += f"\n📊 Retrieved {len(filtered_chunks)} relevant chunks"
                
                # Calculate confidence using Python
                scores = self.calculate_confidence(answer, filtered_chunks, filtered_sims)
                confidence = scores["final"]
                
                # Build diagnostics
                diagnostics = self._build_diagnostics(scores, filtered_chunks, source_chunks, filtered_sims)
                
                pages = []
                pdf_sources = []
                for meta in filtered_metas:
                    if 'page' in meta and meta['page']:
                        pages.append(meta['page'])
                    if 'source' in meta and meta['source']:
                        pdf_sources.append(meta['source'])
                
                elapsed = time.time() - start_time
                self.root.after(0, lambda: self.update_gui(
                    answer, confidence, pages, pdf_sources, filtered_chunks[:5], elapsed, diagnostics
                ))
                return
            
            # Prepare context with page citations
            max_chunks = self.settings.get("max_context_chunks", 3)
            context_chunks = filtered_chunks[:max_chunks]
            
            # Build context with page citations
            context_with_pages = ""
            for i, chunk in enumerate(context_chunks):
                page = filtered_metas[i]['page'] if i < len(filtered_metas) and 'page' in filtered_metas[i] else "Unknown"
                context_with_pages += f"\n--- Chunk {i+1} [Page {page}] ---\n{chunk}\n"
            
            prompt = f"""

You are an expert reading assistant. You must answer the user's question based strictly and ONLY on the provided context. 

If the answer cannot be found in the context, you must state: "The provided document does not contain this information." Do not make up facts or use outside knowledge.

{instruction}

Context (with page numbers):
{context_with_pages}

Question: {question}

Answer:"""         
            if self.stop_generation:
                return
            
            model = self.settings.get("model", "tinyllama")
            temperature = self.settings.get("temperature", 0.2)
            
            response = ollama.chat(
                model=model,
                options={"temperature": temperature},
                messages=[{'role': 'user', 'content': prompt}]
            )
            answer = response['message']['content'].strip()
            
            if self.stop_generation:
                return
            
            # Calculate confidence using Python
            scores = self.calculate_confidence(answer, filtered_chunks, filtered_sims)
            confidence = scores["final"]
            
            # Build diagnostics
            diagnostics = self._build_diagnostics(scores, filtered_chunks, source_chunks, filtered_sims)
            
            pages = []
            pdf_sources = []
            for meta in filtered_metas:
                if 'page' in meta and meta['page']:
                    pages.append(meta['page'])
                if 'source' in meta and meta['source']:
                    pdf_sources.append(meta['source'])
            
            elapsed = time.time() - start_time
            
            # Save to history
            self.history_db.add_entry(
                question, answer, 
                pdf_sources[:5], 
                confidence, 
                model
            )
            
            self.root.after(0, lambda: self.update_gui(
                answer, confidence, pages, pdf_sources, context_chunks, elapsed, diagnostics
            ))
            
        except Exception as e:
            self.gui_error(f"Processing error: {str(e)}")
            self.root.after(0, lambda: self.show_error(str(e)))

    def _build_diagnostics(self, scores, filtered_chunks, source_chunks, filtered_sims):
        """Build diagnostics string from confidence scores"""
        confidence = scores["final"]
        
        if confidence >= 80:
            level = "🟢 Strong"
        elif confidence >= 60:
            level = "🟡 Moderate"
        else:
            level = "🔴 Weak"
        
        diagnostics = f"""
CONFIDENCE ANALYSIS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Retrieval:      {scores['retrieval']:.2f}
Best Chunk:     {scores['best_chunk']:.2f}
Coverage:       {scores['coverage']:.2f}
Evidence:       {scores['evidence']:.2f}
Final Score:    {scores['final']:.1f}%

Assessment:     {level}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Retrieved:      {len(source_chunks)} chunks
Filtered:       {len(filtered_chunks)} chunks
Used:           {min(len(filtered_chunks), self.settings.get('max_context_chunks', 3))} chunks
Best Similarity: {max(filtered_sims):.2f} if filtered_sims else 0.00
"""
        return diagnostics

    def update_gui(self, answer, confidence, pages, pdf_sources, chunks, elapsed, diagnostics=""):
        self.answer_box.delete("0.0", "end")
        self.answer_box.insert("0.0", answer)
        
        self.update_confidence_meter(confidence)
        
        self.pages_box.delete("0.0", "end")
        
        if diagnostics:
            self.pages_box.insert("end", diagnostics + "\n")
        
        self.pages_box.insert("end", "📚 SOURCE EVIDENCE\n")
        self.pages_box.insert("end", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n")
        
        if pdf_sources:
            unique_pdfs = list(dict.fromkeys(pdf_sources))
            self.pages_box.insert("end", f"📄 Documents: {', '.join(unique_pdfs[:3])}\n\n")
        
        if pages:
            unique_pages = list(dict.fromkeys(pages))
            self.pages_box.insert("end", f"📑 Pages: {', '.join(unique_pages[:5])}\n\n")
        
        self.pages_box.insert("end", "📝 EVIDENCE TEXT PREVIEWS (with pages):\n")
        self.pages_box.insert("end", "──────────────────────────────────\n")
        
        for i, chunk in enumerate(chunks[:5], 1):
            page_info = ""
            if hasattr(self, 'filtered_metas') and i - 1 < len(self.filtered_metas):
                meta = self.filtered_metas[i-1]
                if 'page' in meta and meta['page']:
                    page_info = f" [Page {meta['page']}]"
            
            preview = chunk.replace("--- Page ", "📄 ").replace(" ---", "")
            preview = preview[:250] + "..." if len(preview) > 250 else preview
            self.pages_box.insert("end", f"\n[{i}]{page_info}\n{preview}\n")
        
        self.pages_box.insert("end", f"\n⏱ Response Time: {elapsed:.1f} seconds")
        
        self.ask_button.configure(state="normal", text="🔍 ASK")
        self.stop_button.configure(state="disabled")
        self.status_label.configure(text="Ready")

    def show_error(self, error):
        self.gui_error(error)
        messagebox.showerror("Error", f"Something went wrong:\n{error}")
        self.ask_button.configure(state="normal", text="🔍 ASK")
        self.stop_button.configure(state="disabled")
        self.status_label.configure(text="Error occurred", text_color="#f85149")

# ============ MAIN ============

if __name__ == "__main__":
    base_dir = r"C:\Shoby deathless laptop folder\RAG chatbots with python verification"
    chroma_path = os.path.join(base_dir, "chroma_db")
    
    print("=" * 70)
    print("🚀 LAUNCHIPLANEMI AI CHATBOT")
    print("=" * 70)
    print("GUI opens immediately - models load in background...")
    
    root = ctk.CTk()
    app = ChatbotGUI(root)
    
    globals()['app'] = app
    
    root.mainloop()
