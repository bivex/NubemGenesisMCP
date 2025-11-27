#!/usr/bin/env python3
"""
Lightweight RAG System for NubemSuperFClaude
Works without heavy dependencies like sentence-transformers
"""

import os
import json
import hashlib
from typing import List, Dict, Optional, Any
from datetime import datetime
import sqlite3
from pathlib import Path

# Use simple TF-IDF for embeddings instead of transformers
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

from session_manager import SessionManager


class LightweightRAG:
    """Lightweight RAG without heavy dependencies"""
    
    def __init__(self):
        self.session_manager = SessionManager()
        self.vectorizer = TfidfVectorizer(max_features=1000, stop_words='english')
        self.vectors = None
        self.documents = []
        self.metadata = []
        
        # Cache directory
        self.cache_dir = Path.home() / ".nubem_rag_cache"
        self.cache_dir.mkdir(exist_ok=True)
        
        # Load or build index
        self._load_or_build_index()
    
    def _load_or_build_index(self):
        """Load existing index or build new one"""
        cache_file = self.cache_dir / "rag_index.json"
        
        if cache_file.exists():
            # Load from cache
            with open(cache_file, 'r') as f:
                cache_data = json.load(f)
                self.documents = cache_data.get('documents', [])
                self.metadata = cache_data.get('metadata', [])
        else:
            # Build new index
            self.rebuild_index()
    
    def rebuild_index(self):
        """Rebuild the search index from all sessions"""
        self.documents = []
        self.metadata = []
        
        # Get all sessions
        sessions = self.session_manager.get_recent_sessions(limit=100)
        
        for session in sessions:
            session_id = session['session_id']
            messages = self.session_manager.get_session_messages(session_id)
            
            for msg in messages:
                self.documents.append(msg['content'])
                self.metadata.append({
                    'session_id': session_id,
                    'role': msg['role'],
                    'timestamp': msg['timestamp']
                })
        
        # Fit vectorizer if we have documents
        if self.documents:
            self.vectors = self.vectorizer.fit_transform(self.documents)
            
            # Save to cache
            cache_file = self.cache_dir / "rag_index.json"
            with open(cache_file, 'w') as f:
                json.dump({
                    'documents': self.documents,
                    'metadata': self.metadata,
                    'timestamp': datetime.now().isoformat()
                }, f)
    
    def search(self, query: str, limit: int = 5, min_score: float = 0.1) -> List[Dict[str, Any]]:
        """Search for relevant content"""
        if not self.documents or self.vectors is None:
            return []
        
        # Vectorize query
        query_vector = self.vectorizer.transform([query])
        
        # Calculate similarities
        similarities = cosine_similarity(query_vector, self.vectors).flatten()
        
        # Get top results
        indices = np.argsort(similarities)[::-1][:limit * 2]
        
        results = []
        seen = set()
        
        for idx in indices:
            if similarities[idx] < min_score:
                break
            
            # Skip duplicates
            content_hash = hashlib.md5(self.documents[idx].encode()).hexdigest()[:8]
            if content_hash in seen:
                continue
            seen.add(content_hash)
            
            results.append({
                'content': self.documents[idx],
                'score': float(similarities[idx]),
                'metadata': self.metadata[idx]
            })
            
            if len(results) >= limit:
                break
        
        return results
    
    def find_similar_qa_pairs(self, query: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Find similar question-answer pairs"""
        results = self.search(query, limit=limit * 3)
        
        qa_pairs = []
        for result in results:
            if result['metadata']['role'] == 'user':
                # Find the answer
                session_id = result['metadata']['session_id']
                messages = self.session_manager.get_session_messages(session_id)
                
                for i, msg in enumerate(messages):
                    if msg['content'] == result['content'] and i + 1 < len(messages):
                        answer = messages[i + 1]
                        if answer['role'] == 'assistant':
                            qa_pairs.append({
                                'question': result['content'],
                                'answer': answer['content'],
                                'score': result['score'],
                                'session_id': session_id
                            })
                            break
        
        return qa_pairs[:limit]
    
    def get_context_for_prompt(self, query: str, max_chars: int = 2000) -> str:
        """Build context string for LLM prompt"""
        results = self.search(query, limit=5)
        qa_pairs = self.find_similar_qa_pairs(query, limit=2)
        
        context_parts = []
        
        # Add QA pairs
        if qa_pairs:
            context_parts.append("📚 CONOCIMIENTO RELEVANTE:")
            for qa in qa_pairs:
                context_parts.append(f"\nP: {qa['question'][:100]}...")
                context_parts.append(f"R: {qa['answer'][:200]}...")
        
        # Add relevant contexts
        if results:
            context_parts.append("\n🎯 CONTEXTO RELACIONADO:")
            for result in results[:3]:
                if result['score'] > 0.3:
                    role = "👤" if result['metadata']['role'] == 'user' else "🤖"
                    context_parts.append(f"\n{role} {result['content'][:150]}...")
        
        # Join and truncate
        full_context = "\n".join(context_parts)
        if len(full_context) > max_chars:
            full_context = full_context[:max_chars] + "\n..."
        
        return full_context


# Test the lightweight RAG
if __name__ == "__main__":
    import sys
    
    rag = LightweightRAG()
    
    if len(sys.argv) < 2:
        print("Lightweight RAG System")
        print("Commands:")
        print("  rebuild  - Rebuild index")
        print("  search   - Search for query")
        print("  qa       - Find Q&A pairs")
        sys.exit(0)
    
    command = sys.argv[1]
    
    if command == "rebuild":
        print("Rebuilding index...")
        rag.rebuild_index()
        print(f"✅ Indexed {len(rag.documents)} documents")
    
    elif command == "search":
        if len(sys.argv) < 3:
            print("Usage: rag_lite.py search <query>")
        else:
            query = " ".join(sys.argv[2:])
            results = rag.search(query)
            
            print(f"Found {len(results)} results for: {query}")
            for r in results:
                print(f"\nScore: {r['score']:.3f}")
                print(f"Content: {r['content'][:200]}...")
    
    elif command == "qa":
        if len(sys.argv) < 3:
            print("Usage: rag_lite.py qa <query>")
        else:
            query = " ".join(sys.argv[2:])
            qa_pairs = rag.find_similar_qa_pairs(query)
            
            print(f"Found {len(qa_pairs)} Q&A pairs for: {query}")
            for qa in qa_pairs:
                print(f"\nQ: {qa['question'][:100]}...")
                print(f"A: {qa['answer'][:200]}...")
                print(f"Score: {qa['score']:.3f}")