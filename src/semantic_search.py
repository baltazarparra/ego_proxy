"""
Semantic search using sentence transformers for conversation retrieval.

Provides embedding generation and similarity search capabilities
for finding relevant past conversations.
"""

import logging
import numpy as np
import struct

logger = logging.getLogger(__name__)

# Global model instance (lazy loaded)
_model = None


def get_embedding_model():
    """
    Get or initialize the sentence transformer model.

    Returns:
        SentenceTransformer model instance
    """
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            logger.debug("Loading sentence-transformers model (all-MiniLM-L6-v2)...")
            _model = SentenceTransformer('all-MiniLM-L6-v2')
            logger.debug("Embedding model loaded successfully")
        except ImportError:
            logger.error("sentence-transformers not installed. Install with: pip install sentence-transformers")
            raise
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            raise
    return _model


def generate_embedding(text: str) -> np.ndarray:
    """
    Generate an embedding vector for the given text.

    Args:
        text: Text to embed

    Returns:
        Numpy array containing the embedding vector
    """
    model = get_embedding_model()
    
    try:
        # Generate embedding
        embedding = model.encode(text, convert_to_numpy=True)
        return embedding
    except Exception as e:
        logger.error(f"Error generating embedding: {e}")
        raise


def generate_embeddings_batch(texts: list[str]) -> list[np.ndarray]:
    """
    Generate embeddings for multiple texts efficiently.

    Args:
        texts: List of texts to embed

    Returns:
        List of numpy arrays containing embeddings
    """
    model = get_embedding_model()
    
    try:
        # Batch encoding is more efficient
        embeddings = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        return [emb for emb in embeddings]
    except Exception as e:
        logger.error(f"Error generating batch embeddings: {e}")
        raise


def embedding_to_bytes(embedding: np.ndarray) -> bytes:
    """
    Convert a numpy embedding array to bytes for database storage.

    Args:
        embedding: Numpy array embedding

    Returns:
        Bytes representation of the embedding
    """
    return embedding.tobytes()


def bytes_to_embedding(data: bytes) -> np.ndarray:
    """
    Convert bytes back to numpy embedding array.

    Args:
        data: Bytes representation of embedding

    Returns:
        Numpy array embedding
    """
    # Reconstruct the numpy array from bytes
    # all-MiniLM-L6-v2 produces 384-dimensional embeddings
    return np.frombuffer(data, dtype=np.float32)


def cosine_similarity(embedding1: np.ndarray, embedding2: np.ndarray) -> float:
    """
    Calculate cosine similarity between two embeddings.

    Args:
        embedding1: First embedding vector
        embedding2: Second embedding vector

    Returns:
        Cosine similarity score between 0 and 1
    """
    # Normalize vectors
    norm1 = np.linalg.norm(embedding1)
    norm2 = np.linalg.norm(embedding2)
    
    if norm1 == 0 or norm2 == 0:
        return 0.0
    
    # Calculate cosine similarity
    similarity = np.dot(embedding1, embedding2) / (norm1 * norm2)
    
    # Ensure result is between 0 and 1
    return float(max(0.0, min(1.0, (similarity + 1) / 2)))


def find_most_similar(
    query_embedding: np.ndarray,
    stored_embeddings: list[tuple[int, bytes]],
    top_k: int = 5,
    min_similarity: float = 0.3
) -> list[tuple[int, float]]:
    """
    Find the most similar stored embeddings to a query embedding.

    Args:
        query_embedding: The query embedding vector
        stored_embeddings: List of (conversation_id, embedding_bytes) tuples
        top_k: Number of top results to return
        min_similarity: Minimum similarity threshold (0-1)

    Returns:
        List of (conversation_id, similarity_score) tuples, sorted by similarity
    """
    if not stored_embeddings:
        return []
    
    similarities = []
    
    for conversation_id, embedding_bytes in stored_embeddings:
        try:
            # Convert bytes to numpy array
            stored_embedding = bytes_to_embedding(embedding_bytes)
            
            # Calculate similarity
            similarity = cosine_similarity(query_embedding, stored_embedding)
            
            # Only include if above threshold
            if similarity >= min_similarity:
                similarities.append((conversation_id, similarity))
        except Exception as e:
            logger.warning(f"Error processing embedding for conversation {conversation_id}: {e}")
            continue
    
    # Sort by similarity (descending) and return top k
    similarities.sort(key=lambda x: x[1], reverse=True)
    return similarities[:top_k]


def batch_cosine_similarity(query_embedding: np.ndarray, embeddings: np.ndarray) -> np.ndarray:
    """
    Calculate cosine similarity between a query and multiple embeddings efficiently.

    Args:
        query_embedding: Single query embedding (1D array)
        embeddings: Multiple embeddings (2D array, one embedding per row)

    Returns:
        Array of similarity scores
    """
    # Normalize query
    query_norm = query_embedding / (np.linalg.norm(query_embedding) + 1e-8)
    
    # Normalize all embeddings
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    embeddings_norm = embeddings / (norms + 1e-8)
    
    # Calculate cosine similarities
    similarities = np.dot(embeddings_norm, query_norm)
    
    # Scale from [-1, 1] to [0, 1]
    similarities = (similarities + 1) / 2
    
    return similarities


def search_conversations(
    query: str,
    stored_embeddings: list[tuple[int, bytes]],
    top_k: int = 5,
    min_similarity: float = 0.3
) -> list[tuple[int, float]]:
    """
    Search for conversations similar to a text query.

    Args:
        query: Text query to search for
        stored_embeddings: List of (conversation_id, embedding_bytes) from database
        top_k: Number of top results to return
        min_similarity: Minimum similarity threshold

    Returns:
        List of (conversation_id, similarity_score) tuples
    """
    # Generate embedding for the query
    query_embedding = generate_embedding(query)
    
    # Find most similar stored embeddings
    results = find_most_similar(
        query_embedding, 
        stored_embeddings, 
        top_k=top_k,
        min_similarity=min_similarity
    )
    
    logger.debug(f"Found {len(results)} similar conversations for query: {query[:50]}...")
    
    return results


class EmbeddingCache:
    """Simple in-memory cache for embeddings to avoid recomputation."""
    
    def __init__(self, max_size: int = 100):
        """
        Initialize the cache.

        Args:
            max_size: Maximum number of embeddings to cache
        """
        self.cache = {}
        self.max_size = max_size
        self.access_order = []
    
    def get(self, key: str) -> np.ndarray | None:
        """
        Get an embedding from cache.

        Args:
            key: Cache key (typically the text)

        Returns:
            Cached embedding or None if not found
        """
        if key in self.cache:
            # Update access order (move to end)
            self.access_order.remove(key)
            self.access_order.append(key)
            return self.cache[key]
        return None
    
    def put(self, key: str, embedding: np.ndarray):
        """
        Store an embedding in cache.

        Args:
            key: Cache key
            embedding: Embedding to cache
        """
        # If cache is full, remove least recently used
        if len(self.cache) >= self.max_size and key not in self.cache:
            lru_key = self.access_order.pop(0)
            del self.cache[lru_key]
        
        self.cache[key] = embedding
        
        if key not in self.access_order:
            self.access_order.append(key)
    
    def clear(self):
        """Clear the cache."""
        self.cache.clear()
        self.access_order.clear()


# Global embedding cache
_embedding_cache = EmbeddingCache(max_size=100)


def get_cached_embedding(text: str) -> np.ndarray:
    """
    Get embedding with caching support.

    Args:
        text: Text to embed

    Returns:
        Embedding vector
    """
    # Check cache first
    cached = _embedding_cache.get(text)
    if cached is not None:
        return cached
    
    # Generate and cache
    embedding = generate_embedding(text)
    _embedding_cache.put(text, embedding)
    
    return embedding

