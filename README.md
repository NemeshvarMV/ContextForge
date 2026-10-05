# ContextForge

ContextForge is an enterprise-focused, agentic Retrieval-Augmented Generation
(RAG) assistant for Kubernetes, Intel hardware, and enterprise networking
questions.

The current implementation covers the workflow from document ingestion through
the LLM gateway:

```text
Documents
   -> parsing and chunking
   -> embeddings
   -> Qdrant vector index
   -> LangGraph planner
   -> retrieval and semantic reranking
   -> LLM response generation through Portkey
   -> FastAPI API / Streamlit UI
```

## What has been implemented

### 1. Data ingestion

- Universal directory ingestion with source-type detection from subdirectories
  or an explicitly supplied source type.
- Supported document formats:
  - PDF
  - HTML and HTM
  - TXT
  - DOCX
  - PPTX
- Local text extraction:
  - `pypdf` for normal PDF extraction.
  - `pdfplumber` fallback for PDF pages that do not yield text with `pypdf`.
  - BeautifulSoup for HTML parsing.
  - Unstructured for Office documents.
  - Native UTF-8 text loading for plain-text files.
- Removal of HTML scripts, styles, metadata, and other non-readable content.
- Paragraph-oriented chunking with a configurable default maximum chunk size of
  1,500 characters.
- Processed chunks and metadata are saved locally under
  `processed_data/<source_type>/`.
- Empty, unsupported, and failed documents are skipped or logged with
  Logfire rather than being indexed as empty content.
- Optional `--wipe` ingestion mode to recreate the Qdrant collection before a
  fresh load.

### 2. Embeddings and vector storage

- Lazy embedding-model initialization so the model is loaded only when needed.
- Gemini embedding support using `gemini-embedding-2-preview` with 3,072
  dimensions.
- Automatic local fallback to
  `sentence-transformers/all-mpnet-base-v2` with 768 dimensions when Gemini
  cannot be reached.
- Batched document embedding with retry and exponential backoff for Gemini
  rate-limit and quota failures.
- Qdrant collection creation using the active embedding dimension and cosine
  distance.
- Each indexed point stores:
  - The chunk text.
  - Source filename.
  - Source type.
  - A generated point ID.
- Vector upsert into the configured `enterprise_rag` collection.

### 3. Agentic RAG workflow

- LangGraph workflow with explicit planner, retriever, and responder nodes.
- Conversation-aware planning:
  - Conversational or memory-only requests bypass retrieval.
  - Technical questions are converted into a refined search query.
- Technical retrieval flow:
  - Query embedding.
  - Qdrant similarity search for up to 15 candidate chunks.
  - FlashRank local cross-encoder reranking.
  - The top five reranked chunks are passed to the responder.
- Conversation memory through LangGraph `MemorySaver` and a caller-provided
  `thread_id`.
- Context-size protection before generation so the prompt is bounded for the
  configured model limits.
- Response metadata includes the question, answer, execution status, thought
  process, and retrieved sources.
- A `/graph` endpoint exposes a rendered view of the compiled LangGraph
  workflow.

### 4. Guardrails and request gating

- NeMo Guardrails is initialized at application startup.
- A guardrail gate runs before the RAG graph.
- Implemented rail behaviors include:
  - Off-topic request refusal.
  - Jailbreak and prompt-override refusal.
  - Consistent greetings.
  - Capability explanations.
  - Farewell responses.
- Guardrail-handled requests skip vector retrieval and return an explicit
  blocked/handled status.
- The guardrail rules constrain the assistant to Kubernetes, Intel hardware,
  and enterprise networking topics.

### 5. LLM gateway

- Portkey is integrated as the LLM gateway for generation.
- LangChain nodes use an OpenAI-compatible `ChatOpenAI` client pointed at the
  Portkey gateway, allowing the existing LangGraph nodes to use gateway-routed
  models.
- Native Portkey chat completion is used by the responder so gateway response
  headers can be inspected.
- Gateway configuration includes:
  - Model fallback targets.
  - Retry handling for HTTP 429 and 503 responses.
  - Response caching.
  - Feature and environment metadata.
- Portkey cache status is surfaced in the agent plan and API response when a
  cached response is served.
- Separate feature labels are supported for gateway calls, such as planner and
  RAG generation.

### 6. API, UI, and observability

- FastAPI service with:
  - `GET /` health-style availability response.
  - `GET /graph` workflow visualization.
  - `POST /query` for guarded, stateful agentic queries.
- Streamlit chat UI with:
  - Session-based conversation memory.
  - Clear-history and memory reset control.
  - Visible agent thought-process steps.
  - Retrieved-source inspection.
  - Response streaming effect.
  - Backend connection and error states.
- Logfire spans and structured events across ingestion, parsing, embedding,
  retrieval, reranking, guardrails, generation, API calls, and UI
  interactions.
- LangSmith/LangChain tracing configuration is supported through environment
  variables.

## Project structure

```text
app/
├── agents/                 # LangGraph state, graph, planner, retriever, responder
├── gateway/                # Portkey gateway client and cache-status handling
├── guardrails/             # NeMo Guardrails setup and Colang rules
├── ingestion/              # Loaders, chunking, and ingestion orchestration
├── services/retrieval/     # Embeddings, Qdrant search, and reranking
├── config.py               # Environment-backed application settings
└── main.py                 # FastAPI application
UI/app.py                   # Streamlit frontend
```

## Configuration

Create a `.env` file in the project root. At minimum, configure the credentials
and endpoints required by the services you use:

```dotenv
GEMINI_API_KEY=
QDRANT_CLUSTER_ENDPOINT=
QDRANT_API_KEY=
GROQ_API_KEY=
PORTKEY_API_KEY=
LOGFIRE_TOKEN=
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=
LANGSMITH_PROJECT=rag_scale_test
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
BACKEND_URL=http://localhost:8000
```

Do not commit `.env` or any API keys.

## Running the application

Install the project dependencies with Python 3.14 or newer:

```powershell
uv sync
```

Ingest documents from the default `DATA` directory:

```powershell
uv run python -m app.ingestion.processor DATA
```

Recreate the collection before ingesting:

```powershell
uv run python -m app.ingestion.processor DATA --wipe
```

Start the FastAPI backend:

```powershell
uv run uvicorn app.main:app --reload
```

Start the Streamlit frontend in a second terminal:

```powershell
uv run streamlit run UI/app.py
```

The UI sends requests to `BACKEND_URL`, which defaults to
`http://localhost:8000`.

## Future scope

### Evaluations

Formal evaluation and regression tracking are planned for a future scope. This
will include:

- A maintained golden question-and-answer dataset.
- Live pipeline evaluation against the running API.
- Answer relevancy, answer correctness, context precision, and context recall
  measurements.
- Tool/route correctness for conversational, retrieval, and guardrail paths.
- Guardrail precision, recall, accuracy, false-positive, and false-negative
  reporting.
- An evaluation dashboard and repeatable benchmark runs.

The current README describes the delivered ingestion-to-`llm-gateway`
implementation; evaluation results are intentionally not presented as
completed product capabilities.