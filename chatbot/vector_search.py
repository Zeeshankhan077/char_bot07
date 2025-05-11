import faiss
import pickle
import numpy as np
from sentence_transformers import SentenceTransformer
import os
import logging

# Configure logging
logger = logging.getLogger(__name__)

EMBEDDING_PATH = os.path.join(os.path.dirname(__file__), 'embeddings/index.faiss')
METADATA_PATH = os.path.join(os.path.dirname(__file__), 'embeddings/metadata.pkl')

# Initialize variables
model = None
metadata = None
index = None
vector_search_enabled = True

try:
    # Load the model
    model = SentenceTransformer("all-MiniLM-L6-v2")

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

def retrieve_context(user_input, k=5):
    """Retrieve context based on user input using vector search."""
    # Check if vector search is enabled and properly initialized
    if not vector_search_enabled or model is None or index is None or metadata is None:
        logger.warning("Vector search is disabled or not properly initialized")
        return ["Vector search is currently unavailable."]

    try:
        # Encode the user input
        embedding = model.encode([user_input])

        # Search for similar vectors
        distances, indices = index.search(np.array(embedding).astype("float32"), k)

        # Return the metadata for the found indices
        return [metadata[i] for i in indices[0]]
    except Exception as e:
        logger.error(f"Error in vector search: {str(e)}")
        return ["Error retrieving context information."]