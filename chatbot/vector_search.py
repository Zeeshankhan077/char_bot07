import os
import logging
import gc  # Garbage collection
import time

# Configure logging
logger = logging.getLogger(__name__)

EMBEDDING_PATH = os.path.join(os.path.dirname(__file__), 'embeddings/index.faiss')
METADATA_PATH = os.path.join(os.path.dirname(__file__), 'embeddings/metadata.pkl')

# Initialize variables
model = None
metadata = None
index = None
vector_search_enabled = True
_is_initialized = False
_last_used = 0  # Timestamp when the model was last used

def _lazy_load():
    """Lazy load the model and embeddings only when needed"""
    global model, metadata, index, vector_search_enabled, _is_initialized, _last_used

    # If already initialized and used recently, just update the timestamp
    if _is_initialized and model is not None:
        _last_used = time.time()
        return

    # If we're reinitializing after unloading, force garbage collection first
    if _is_initialized and model is None:
        gc.collect()

    try:
        # Import heavy modules only when needed
        import faiss
        import pickle
        import numpy as np
        from sentence_transformers import SentenceTransformer

        # Load the model with minimal memory footprint
        logger.info("Loading sentence transformer model...")
        model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")

        # Check if embedding files exist
        if os.path.exists(METADATA_PATH) and os.path.exists(EMBEDDING_PATH):
            # Load metadata
            with open(METADATA_PATH, "rb") as f:
                metadata = pickle.load(f)

            # Load FAISS index
            index = faiss.read_index(EMBEDDING_PATH)

            logger.info("Vector search initialized successfully")
        else:
            logger.warning(f"Embedding files not found at {EMBEDDING_PATH} or {METADATA_PATH}")
            vector_search_enabled = False
    except Exception as e:
        logger.error(f"Error initializing vector search: {str(e)}")
        vector_search_enabled = False

    _is_initialized = True
    _last_used = time.time()

def _unload_model():
    """Unload the model to free up memory"""
    global model, index, _last_used

    # Only unload if it's been more than 5 minutes since last use
    if model is not None and time.time() - _last_used > 300:  # 5 minutes
        logger.info("Unloading vector search model to free memory...")
        model = None
        index = None
        gc.collect()  # Force garbage collection

def retrieve_context(user_input, k=5):
    """Retrieve context based on user input using vector search."""
    # Check if ENABLE_VECTOR_SEARCH is set to False in environment variables
    if os.environ.get("ENABLE_VECTOR_SEARCH", "True").lower() != "true":
        logger.info("Vector search is disabled by environment variable")
        return ["Vector search is disabled."]

    # Lazy load the model and embeddings
    try:
        _lazy_load()

        # Check if vector search is enabled and properly initialized
        if not vector_search_enabled or model is None or index is None or metadata is None:
            logger.warning("Vector search is disabled or not properly initialized")
            return ["Vector search is currently unavailable."]

        # Import necessary modules here to avoid loading them at module level
        import numpy as np

        # Encode the user input
        embedding = model.encode([user_input])

        # Search for similar vectors
        distances, indices = index.search(np.array(embedding).astype("float32"), k)

        # Get results
        results = [metadata[i] for i in indices[0]]

        # Schedule unloading of model after use
        _last_used = time.time()

        return results
    except Exception as e:
        logger.error(f"Error in vector search: {str(e)}")
        return ["Error retrieving context information."]
