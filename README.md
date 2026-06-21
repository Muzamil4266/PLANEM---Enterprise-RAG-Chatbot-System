
 
 # Screenshots

## Screenshot 1
![Screenshot 1](P%20(1).png)

## Screenshot 2
![Screenshot 2](P%20(2).png)

## Screenshot 3
![Screenshot 3](P%20(3).png)

## Screenshot 4
![Screenshot 4](P%20(4).png)

## Screenshot 5
![Screenshot 5](P5.png)
 
 
 
 📚 PLANEM AI - Document RAG Chatbot
Chat with your documents using AI. Get answers from your PDFs instantly.

🤔 What is PLANEM AI?
PLANEM AI is a desktop application that lets you talk to your documents. You upload PDFs, and the AI reads them, indexes them, and answers your questions based on what's inside.

Think of it like having a smart assistant that has read all your documents and can find any information you need in seconds. No more searching through hundreds of pages manually!

✨ What Can It Do?
📄 Read PDFs - Upload any PDF document. The app reads and understands everything inside.

🔍 Search Instantly - Ask questions in plain English and get answers from your documents.

🤖 AI-Powered - Uses advanced AI models to understand your questions and find the right answers.

📑 Show Sources - Every answer comes with page numbers and evidence so you can verify the information.

📊 Confidence Meter - See how confident the AI is about each answer. Green means strong evidence!

💾 Chat History - All your conversations are saved automatically. Review them anytime.

📤 Export Chat - Save your conversations as text files for sharing or record-keeping.

🎨 Beautiful Interface - Modern dark theme with easy-to-use controls.

⚙️ How It Works
Simple 3-Step Process
1️⃣ Upload Documents - Add your PDFs to the system.

2️⃣ Index Them - The AI reads and organizes all the information. This builds a searchable database.

3️⃣ Ask Questions - Type your question and get instant answers with source references.

Behind the Scenes
📝 Text Extraction - The app extracts text from your PDFs using pdfplumber and PyPDF2. It handles multiple page formats and extracts clean text.

🧩 Smart Chunking - Long documents are split into smaller pieces called "chunks." Each chunk keeps track of which page it came from. This makes searching fast and accurate.

🧠 AI Embeddings - Using the all-MiniLM-L6-v2 model, the app converts text into mathematical vectors that capture meaning. This helps find the most relevant information.

💾 Vector Database - ChromaDB stores all the text chunks and their embeddings. It allows lightning-fast similarity searches.

🔍 Semantic Search - When you ask a question, the app finds the chunks that are most similar in meaning, not just matching keywords.

🤖 Answer Generation - Using Ollama with models like tinyllama, phi3, or gemma, the app generates natural language answers based on the retrieved chunks.

🎯 Confidence Scoring - Five different metrics calculate how reliable the answer is:

Retrieval Score (how good were the search results)

Best Chunk Score (the most relevant piece found)

Coverage Score (how much of the answer is in the documents)

Evidence Score (how many sources support the answer)

Final Confidence (combined score shown as a percentage)

🚀 Applications
🎓 Students - Quickly find information in textbooks and lecture notes. No more endless page flipping!

🧑‍💼 Professionals - Search through reports, contracts, and business documents instantly.

📚 Researchers - Extract specific information from research papers and academic literature.

⚖️ Legal - Find relevant passages in legal documents and case files.

🏥 Medical - Search through medical records, research, and clinical documentation.

📰 Journalists - Find specific facts and quotes in large document collections.

🧠 Personal Knowledge - Build a searchable library of everything you've read.

🛠️ Installation & Setup
Step 1: Install Python
Make sure you have Python 3.8 or higher installed. Download from python.org if needed.

Step 2: Install Ollama
PLANEM AI uses Ollama for generating answers. Install it from ollama.ai.

Step 3: Download a Model
Open your terminal and run:

bash
ollama pull tinyllama
You can also use other models like phi3, gemma, or qwen2.5.

Step 4: Install Dependencies
bash
pip install customtkinter sentence-transformers chromadb PyPDF2 pdfplumber ollama
Step 5: Run the Application
bash
python PLANEM.py
💡 First-time Note: The app will download the embedding model (~90MB) on first run. This happens only once.

🎮 How to Use
📥 Add Documents
Click "➕ ADD PDF" to upload one or more PDFs. The files are copied to the app's document folder.

🔄 Update Indexes
Click "🔄 UPDATE INDEXES" to process all new PDFs. This extracts text, creates chunks, and builds the search database. Watch the progress bar and logs to see the process.

🔍 Ask Questions
Type your question in the "QUESTION" box and press Enter or click "🔍 ASK". The app will search all documents and provide an answer with source verification.

📊 Check Confidence
The confidence meter shows how reliable the answer is:

🟢 Green (80%+) = Strong evidence from documents

🟡 Yellow (60-80%) = Moderate evidence, some uncertainty

🔴 Red (below 60%) = Weak evidence, verify carefully

📑 View Sources
The "SOURCE VERIFICATION" section shows:

Page numbers where information was found

Preview of the text chunks used

Document names

Confidence analysis breakdown

📜 Chat History
Click "📜 History" to see all your previous questions and answers. Everything is saved automatically.

📤 Export Chat
Click "📄 Export Chat" to save your conversation as a text file.

🔍 Search Only Mode
Toggle "SEARCH ONLY" to see the retrieved chunks without generating an AI answer. Useful for debugging or when you want to see raw search results.

⚙️ Settings Explained
Chunk Size - How many words per chunk. Larger chunks capture more context but take more memory.

Chunk Overlap - Words shared between chunks to maintain context across boundaries.

Top K - How many chunks to retrieve initially. More chunks mean better coverage but slower.

Max Context Chunks - How many chunks to use for generating the answer.

Similarity Threshold - Minimum relevance score (0-1). Higher values mean stricter filtering.

Temperature - Controls AI creativity (0-1). Lower = more focused and factual.

Answer Style - Short, Medium, or Detailed. Controls answer length.

Max Sentences - Maximum sentences for Short/Medium answers.

LLM Model - Choose which AI model to use (tinyllama, phi3, gemma, qwen2.5).

Theme - Dark, Light, or System. Changes the app appearance.

Accent Color - Blue, Green, Orange, Purple, or Red. Customizes the theme.

🔧 Troubleshooting
❌ "Models are still loading" - Wait a few seconds after startup. The models load in the background.

❌ "No documents indexed" - You need to add PDFs and click "UPDATE INDEXES" first.

❌ "Collection missing" - Click "🔥 Rebuild Database" to recreate the database.

❌ "Ollama connection failed" - Make sure Ollama is installed and running. Check with ollama list.

❌ "No text extracted" - Some PDFs are scanned images. The app can't read them. Use OCR software first.

🐌 Slow performance - Use a smaller model like tinyllama. Reduce chunk size and top_k values.

🛠️ Technology Stack
GUI - CustomTkinter for modern dark-themed interface

AI Models - Sentence Transformers (all-MiniLM-L6-v2) for embeddings, Ollama for LLM generation

Database - ChromaDB for vector storage and similarity search

PDF Processing - pdfplumber and PyPDF2 for text extraction

Language - Python 3.8+

🎯 Project Structure
text
PLANEM AI/
├── PLANEM.py              # Main application
├── test_data/             # Your PDFs go here
├── chroma_db/             # Vector database (auto-created)
├── models/                # AI models (auto-downloaded)
├── settings.json          # Your preferences
└── chat_history.db        # All your conversations
📝 License
Open-source and free to use. Modify and share as you like.

🙏 Acknowledgments
Built with love using these amazing tools:

CustomTkinter for the beautiful interface

Sentence Transformers for understanding text

ChromaDB for fast searching

Ollama for AI generation

pdfplumber for reading PDFs

💬 Need Help?
Check the ERROR CONSOLE for detailed error messages

Look at the PROCESSING LOG to see what the app is doing

Try rebuilding the database if you have issues

Make sure your PDFs are text-based (not scanned)

🤖 Ask anything. Get answers from your documents.
