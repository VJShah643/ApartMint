"""
RAG System for Advisor Mode
Loads knowledge base markdown files, creates embeddings, and enables semantic search.
"""

import os
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
from typing import List, Dict, Tuple
import re


class KnowledgeBase:
    """
    RAG system for Uppsala housing advisor mode.
    Loads markdown files, chunks them, creates embeddings, and retrieves relevant context.
    """
    
    def __init__(self, knowledge_base_dir: str = "knowledge_base"):
        """
        Initialize the RAG system.
        
        Args:
            knowledge_base_dir: Directory containing knowledge base markdown files
        """
        self.knowledge_base_dir = knowledge_base_dir
        
        # Initialize embedding model
        print("Loading embedding model...")
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        
        # Initialize ChromaDB
        print("Initializing ChromaDB...")
        self.chroma_client = chromadb.Client(Settings(
            anonymized_telemetry=False,
            is_persistent=False  # In-memory for faster access
        ))
        
        # Create or get collection
        self.collection = self.chroma_client.create_collection(
            name="uppsala_housing_knowledge",
            metadata={"description": "Uppsala housing rental knowledge base"}
        )
        
        # Load and index knowledge base
        self._load_knowledge_base()
        
    def _load_knowledge_base(self):
        """Load all markdown files and create embeddings."""
        print("Loading knowledge base files...")
        
        markdown_files = [
            "bostad_process.md",
            "heimstaden_process.md",
            "queue_strategies.md",
            "student_housing.md",
            "budget_planning.md",
            "area_comparisons.md",
            "application_tips.md"
        ]
        
        all_chunks = []
        all_metadatas = []
        all_ids = []
        
        chunk_id = 0
        
        for filename in markdown_files:
            filepath = os.path.join(self.knowledge_base_dir, filename)
            
            if not os.path.exists(filepath):
                print(f"Warning: {filepath} not found, skipping...")
                continue
                
            print(f"Processing {filename}...")
            
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Chunk the content
            chunks = self._chunk_markdown(content, filename)
            
            for chunk_text, section_title in chunks:
                all_chunks.append(chunk_text)
                all_metadatas.append({
                    "source_file": filename,
                    "section": section_title
                })
                all_ids.append(f"chunk_{chunk_id}")
                chunk_id += 1
        
        print(f"Created {len(all_chunks)} chunks from {len(markdown_files)} files")
        
        # Create embeddings and add to ChromaDB
        print("Creating embeddings (this may take a minute)...")
        embeddings = self.embedding_model.encode(all_chunks, show_progress_bar=True)
        
        print("Adding to ChromaDB...")
        self.collection.add(
            embeddings=embeddings.tolist(),
            documents=all_chunks,
            metadatas=all_metadatas,
            ids=all_ids
        )
        
        print(f"✅ Knowledge base loaded! {len(all_chunks)} chunks indexed.")
    
    def _chunk_markdown(self, content: str, filename: str) -> List[Tuple[str, str]]:
        """
        Chunk markdown content by sections (headers).
        
        Args:
            content: Markdown file content
            filename: Source filename
            
        Returns:
            List of (chunk_text, section_title) tuples
        """
        chunks = []
        
        # Split by headers (## or ###)
        sections = re.split(r'\n(#{2,3}\s+.+?)\n', content)
        
        # sections[0] is content before first header (often file title)
        # sections[1] is first header, sections[2] is content after first header, etc.
        
        current_section = "Introduction"
        
        for i, section in enumerate(sections):
            if section.startswith('##'):
                # This is a header
                current_section = section.strip('#').strip()
            elif section.strip():
                # This is content
                # Split into smaller chunks if too large (max 500 words per chunk)
                words = section.split()
                
                if len(words) > 500:
                    # Split into multiple chunks
                    for j in range(0, len(words), 400):
                        chunk_words = words[j:j+500]
                        chunk_text = ' '.join(chunk_words)
                        
                        if chunk_text.strip():
                            chunks.append((
                                f"# {current_section}\n\n{chunk_text}",
                                current_section
                            ))
                else:
                    # Keep as single chunk
                    chunks.append((
                        f"# {current_section}\n\n{section}",
                        current_section
                    ))
        
        return chunks
    
    def retrieve(self, query: str, n_results: int = 5) -> List[Dict]:
        """
        Retrieve most relevant chunks for a query.
        
        Args:
            query: User's question
            n_results: Number of chunks to retrieve
            
        Returns:
            List of dicts with 'text', 'source_file', 'section', 'relevance_score'
        """
        # Create query embedding
        query_embedding = self.embedding_model.encode([query])[0]
        
        # Search in ChromaDB
        results = self.collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=n_results
        )
        
        # Format results
        retrieved_chunks = []
        
        for i in range(len(results['documents'][0])):
            retrieved_chunks.append({
                'text': results['documents'][0][i],
                'source_file': results['metadatas'][0][i]['source_file'],
                'section': results['metadatas'][0][i]['section'],
                'distance': results['distances'][0][i] if 'distances' in results else None
            })
        
        return retrieved_chunks
    
    def retrieve_formatted(self, query: str, n_results: int = 5) -> str:
        """
        Retrieve relevant chunks and format them for LLM prompt.
        
        Args:
            query: User's question
            n_results: Number of chunks to retrieve
            
        Returns:
            Formatted context string for LLM
        """
        chunks = self.retrieve(query, n_results)
        
        if not chunks:
            return "No relevant information found in knowledge base."
        
        formatted = "# Relevant Information from Knowledge Base\n\n"
        
        for i, chunk in enumerate(chunks, 1):
            formatted += f"## Source {i}: {chunk['section']} (from {chunk['source_file']})\n\n"
            formatted += chunk['text']
            formatted += "\n\n---\n\n"
        
        return formatted


# Global instance (initialized once when module is imported)
_kb_instance = None


def get_knowledge_base() -> KnowledgeBase:
    """
    Get or create the global knowledge base instance.
    This ensures we only load the knowledge base once.
    """
    global _kb_instance
    
    if _kb_instance is None:
        print("Initializing knowledge base for first time...")
        _kb_instance = KnowledgeBase()
    
    return _kb_instance


if __name__ == "__main__":
    # Test the RAG system
    print("Testing RAG system...\n")
    
    kb = KnowledgeBase()
    
    test_queries = [
        "How do I register for Bostad Uppsala?",
        "What is the Flogsta scream?",
        "How much should I budget for electricity?",
        "What are queue days and how do they work?",
        "Which neighborhoods are cheapest in Uppsala?"
    ]
    
    for query in test_queries:
        print(f"\n{'='*80}")
        print(f"Query: {query}")
        print('='*80)
        
        results = kb.retrieve(query, n_results=3)
        
        for i, result in enumerate(results, 1):
            print(f"\nResult {i}:")
            print(f"  Source: {result['source_file']} - {result['section']}")
            print(f"  Text preview: {result['text'][:200]}...")
