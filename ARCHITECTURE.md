# Context Broker Architecture

## Executive Summary

Context Broker is a Model Context Protocol (MCP) server that provides semantic code search capabilities for AI assistants. It bridges the gap between natural language queries and code retrieval by using sentence transformers to understand code semantics.

**Key Architectural Decisions:**
- **Modular Design**: Separated into logical modules (config, utils, project, storage, indexer, server)
- **Dual Storage Modes**: Supports both global and in-project storage with automatic fallback
- **Intelligent Caching**: Multi-layer caching (memory + disk) with file modification tracking
- **Zero-Config Setup**: Auto-detects project roots using common markers

---

## System Context Diagram (C4 Level 1)

```mermaid
flowchart TB
    subgraph "AI Assistant Environment"
        AI["AI Assistant<br/>(Claude, Kimi, etc.)"]
        Client["MCP Client<br/>(Claude Desktop, Kimi CLI)"]
    end
    
    subgraph "Context Broker"
        MCP["MCP Server<br/>(FastMCP)"]
        Core["Core Engine"]
    end
    
    subgraph "External Resources"
        Codebase[(Target Codebase)]
        Storage[(Search Results Storage)]
        Model[(Sentence Transformer<br/>all-MiniLM-L6-v2)]
    end
    
    AI -->|"Natural Language Query"| Client
    Client -->|"MCP Protocol"| MCP
    MCP -->|"Search Request"| Core
    Core -->|"File Contents"| Codebase
    Core -->|"Embeddings"| Model
    Core -->|"Save/Load"| Storage
    MCP -->|"Results + Context"| Client
    Client -->|"Context"| AI
```

---

## Container Diagram (C4 Level 2)

```mermaid
flowchart TB
    subgraph "MCP Server Container"
        API["API Layer<br/>(FastMCP Tools & Resources)"]
        
        subgraph "Core Modules"
            Indexer["Indexer Module<br/>• File Scanning<br/>• Embedding Generation<br/>• Similarity Search"]
            Project["Project Module<br/>• Root Detection<br/>• Ignore Patterns"]
            Storage["Storage Module<br/>• JSON Persistence<br/>• Multi-mode Storage"]
            Utils["Utils Module<br/>• Token Counting<br/>• Logging"]
        end
        
        Config["Config Module<br/>• Environment Variables<br/>• Constants"]
    end
    
    subgraph "External Systems"
        Files[(File System)]
        Cache[(Cache Files)]
        Model[(ML Model)]
    end
    
    API -->|"search_codebase()"| Indexer
    API -->|"save/load"| Storage
    API -->|"auto-detect"| Project
    
    Indexer -->|"get files"| Project
    Indexer -->|"persist"| Storage
    Indexer -->|"encode"| Model
    
    Project -->|"scan"| Files
    Storage -->|"read/write"| Cache
    
    Config -->|"configure"| API
    Config -->|"configure"| Indexer
    Config -->|"configure"| Storage
```

---

## Component Diagram (C4 Level 3)

### Indexer Module

```mermaid
flowchart LR
    subgraph "Indexer Module"
        Entry["get_index_for_project()"]
        
        subgraph "Indexing Pipeline"
            Scan["File Scanner<br/>glob + ignore patterns"]
            Read["File Reader<br/>encoding handling"]
            Embed["Embedding Generator<br/>SentenceTransformer"]
            Store["Index Store<br/>in-memory cache"]
        end
        
        Search["search_codebase()"]
        
        subgraph "Search Pipeline"
            Cache["Query Cache<br/>mtime validation"]
            Encode["Query Encoder"]
            Similarity["Cosine Similarity<br/>sklearn"]
            Rank["Result Ranker<br/>top-k selection"]
        end
    end
    
    Entry --> Scan
    Scan --> Read
    Read --> Embed
    Embed --> Store
    
    Search --> Cache
    Cache -->|"cache miss"| Encode
    Encode --> Similarity
    Similarity --> Rank
    
    Store --> Search
```

### Storage Module

```mermaid
flowchart TD
    subgraph "Storage Module"
        API["Public API"]
        
        subgraph "Storage Strategy"
            Global["Global Storage<br/>~/.context-broker/"]
            Local["In-Project Storage<br/>{project}/.context-broker/"]
            Both["Both Mode<br/>local priority + fallback"]
        end
        
        Router["Storage Router<br/>mode-based dispatch"]
    end
    
    API --> Router
    
    Router -->|"mode=global"| Global
    Router -->|"mode=in-project"| Local
    Router -->|"mode=both"| Both
    
    Both -->|"write"| Local
    Both -->|"read: try local first"| Local
    Both -->|"fallback"| Global
```

---

## Data Flow Sequence Diagram

### Search Flow

```mermaid
sequenceDiagram
    participant AI as AI Assistant
    participant MCP as MCP Server
    participant Cache as Query Cache
    participant Index as File Index
    participant Model as ML Model
    
    AI->>MCP: search_codebase("auth middleware")
    
    alt Index not in memory
        MCP->>Index: get_index_for_project()
        Index->>Index: Scan files
        Index->>Index: Apply ignore patterns
        Index->>Model: encode(documents)
        Model-->>Index: embeddings
        Index->>Index: Store in _INDEXES
    end
    
    MCP->>Cache: Check query cache
    
    alt Cache hit and valid
        Cache-->>MCP: Return cached results
    else Cache miss or stale
        MCP->>Model: encode([query])
        Model-->>MCP: query_embedding
        MCP->>Index: cosine_similarity()
        Index-->>MCP: ranked results
        MCP->>Cache: Update cache with mtimes
    end
    
    MCP-->>AI: Return file contents + stats
```

### Save Results Flow

```mermaid
sequenceDiagram
    participant AI as AI Assistant
    participant MCP as MCP Server
    participant Search as Search Engine
    participant Storage as Storage Module
    participant Disk as File System
    
    AI->>MCP: save_search_results(query, filename)
    
    MCP->>Search: search_codebase(query)
    Search-->>MCP: results
    
    MCP->>MCP: Format JSON structure
    
    MCP->>Storage: save_json_data()
    
    alt Mode = global
        Storage->>Disk: Write to ~/.context-broker/
    else Mode = in-project
        Storage->>Disk: Write to {project}/.context-broker/
    else Mode = both
        Storage->>Disk: Write to local project
    end
    
    Storage-->>MCP: filepath
    MCP-->>AI: Success + filepath
```

---

## Entity Relationship Diagram

### Search Result Storage Schema

```mermaid
erDiagram
    SAVED_RESULT {
        string project "Project name"
        string project_root "Absolute path"
        string query "Original search query"
        string storage_mode "global|in-project|both"
        int top_k "Number of results requested"
        string timestamp "Save timestamp"
        int file_count "Number of files saved"
        object statistics "Token usage stats"
    }
    
    FILE_ENTRY {
        string path "Absolute file path"
        string content "File contents"
    }
    
    TOKEN_STATS {
        int total_tokens "Total project tokens"
        int context_tokens "Tokens in results"
        int saved_tokens "Tokens saved"
        float saved_percent "Percentage saved"
    }
    
    SAVED_RESULT ||--o{ FILE_ENTRY : contains
    SAVED_RESULT ||--|| TOKEN_STATS : includes
```

---

## Module Dependencies

```mermaid
flowchart TB
    subgraph "Application Layer"
        Main[main.py]
        Entry[context-broker.py]
    end
    
    subgraph "Interface Layer"
        Server[server.py<br/>MCP Tools & Resources]
    end
    
    subgraph "Domain Layer"
        Indexer[indexer.py<br/>Search & Embeddings]
        Storage[storage.py<br/>Persistence]
        Project[project.py<br/>Detection & Ignores]
    end
    
    subgraph "Infrastructure Layer"
        Utils[utils.py<br/>Logging & Tokens]
        Config[config.py<br/>Configuration]
    end
    
    Main --> Server
    Entry --> Server
    
    Server --> Indexer
    Server --> Storage
    Server --> Project
    Server --> Utils
    
    Indexer --> Project
    Indexer --> Utils
    Indexer --> Config
    
    Storage --> Utils
    Storage --> Config
    
    Project --> Utils
    Project --> Config
    
    Utils --> Config
```

---

## Cache Invalidation Strategy

```mermaid
flowchart TD
    A[New Search Request] --> B{Cache Hit?}
    B -->|No| C[Perform Search]
    B -->|Yes| D{Files Changed?}
    
    D -->|Check mtimes| E{Any mtime differs?}
    E -->|No| F[Return Cached Results]
    E -->|Yes| C
    
    C --> G[Generate Embeddings]
    G --> H[Rank Results]
    H --> I[Update Cache]
    I --> J[Return Results]
    
    F --> J
```

---

## Storage Mode Decision Matrix

| Mode | Write Location | Read Priority | Best For |
|------|---------------|---------------|----------|
| `global` | `~/.context-broker/` | Global only | CI/CD, centralized |
| `in-project` | `{project}/.context-broker/` | Local only | Team collaboration |
| `both` | Local project | Local → Global fallback | Daily development |

---

## Performance Characteristics

### Indexing Performance
- **First Search**: O(n) where n = number of files
- **Embedding Generation**: ~100-500ms per 100 files (CPU)
- **Memory Usage**: ~100MB base + ~1MB per 100 files

### Search Performance
- **Cache Hit**: <10ms
- **Cache Miss**: 50-200ms (similarity computation)
- **Token Counting**: ~1ms per KB of text

### Storage Performance
- **JSON Save**: ~10ms per file
- **JSON Load**: ~5ms per file
- **Cache Persistence**: ~50ms per 100 cache entries

---

## Security Considerations

1. **File Access**: Only reads files, never writes to source code
2. **Path Traversal**: All paths resolved using `Path.resolve()`
3. **Sensitive Data**: Respects `.gitignore` and `.dockerignore`
4. **Storage Isolation**: Project names used as directory boundaries
5. **No Code Execution**: Pure read-only analysis

---

## Extension Points

### Adding New File Types
```python
# In context_broker/config.py
SUPPORTED_EXTENSIONS.extend([
    "*.cpp", "*.hpp",  # C++
    "*.kt",            # Kotlin
    "*.swift",         # Swift
])
```

### Adding New Storage Backends
```python
# In context_broker/storage.py
class S3Storage:
    def save(self, key: str, data: dict) -> None: ...
    def load(self, key: str) -> dict: ...
```

### Custom Embedding Models
```python
# In context_broker/config.py
EMBEDDING_MODEL = "sentence-transformers/all-mpnet-base-v2"
```
