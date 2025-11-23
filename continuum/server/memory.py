import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
from typing import List, Dict, Any
import os

class Memory:
    def __init__(self, persist_directory: str = "chroma_db"):
        self.client = chromadb.Client(Settings(
            persist_directory=persist_directory,
            is_persistent=True
        ))
        self.collection = self.client.get_or_create_collection(name="continuum")
        # Load a lightweight model for local embeddings
        self.model = SentenceTransformer('all-MiniLM-L6-v2')

    def add(self, id: str, text: str, metadata: Dict[str, Any]):
        """Add a text item to the vector store."""
        embedding = self.model.encode(text).tolist()
        self.collection.add(
            documents=[text],
            embeddings=[embedding],
            metadatas=[metadata],
            ids=[id]
        )

    def search(self, query: str, limit: int = 5, filters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """Search for relevant context items."""
        query_embedding = self.model.encode(query).tolist()
        
        # ChromaDB expects None for no filters, not {}
        where_clause = filters if filters else None
        
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=limit,
            where=where_clause
        )
        
        # Format results
        formatted_results = []
        if results['ids']:
            for i in range(len(results['ids'][0])):
                formatted_results.append({
                    "id": results['ids'][0][i],
                    "content": results['documents'][0][i],
                    "metadata": results['metadatas'][0][i],
                    "distance": results['distances'][0][i] if results['distances'] else None
                })
                
        return formatted_results

# Singleton instance
memory_store = Memory()
