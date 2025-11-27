#!/usr/bin/env python3
"""
Intelligent RAG System for NubemSuperFClaude
Automatically searches and retrieves relevant context from vector database
"""

import os
import json
import asyncio
import hashlib
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime, timedelta
import numpy as np
from pathlib import Path
import logging

# Qdrant client
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, MatchValue,
    SearchParams, ScoredPoint
)

# Embeddings
from sentence_transformers import SentenceTransformer
import tiktoken

# Import session manager
from session_manager import SessionManager

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class IntelligentRAGSystem:
    """Advanced RAG system with automatic context retrieval"""
    
    def __init__(self, qdrant_host: str = "localhost", qdrant_port: int = 6333):
        """Initialize RAG system with Qdrant and embeddings"""
        
        # Qdrant client
        self.qdrant = QdrantClient(host=qdrant_host, port=qdrant_port)
        
        # Embedding model (multilingual)
        self.embedder = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
        self.embedding_dim = 384  # Dimension for MiniLM
        
        # Session manager
        self.session_manager = SessionManager()
        
        # Collections in Qdrant
        self.collections = {
            'messages': 'nubem_messages',          # Individual messages
            'sessions': 'nubem_sessions',          # Session summaries
            'knowledge': 'nubem_knowledge',        # Knowledge base
            'personas': 'nubem_personas',          # AI personas context
            'solutions': 'nubem_solutions'         # Problem-solution pairs
        }
        
        # Initialize collections
        self._init_collections()
        
        # Context window settings
        self.max_context_tokens = 4000
        self.tokenizer = tiktoken.get_encoding("cl100k_base")
        
        # Relevance thresholds
        self.relevance_thresholds = {
            'high': 0.85,
            'medium': 0.70,
            'low': 0.50
        }
    
    def _init_collections(self):
        """Initialize Qdrant collections if they don't exist"""
        for name, collection in self.collections.items():
            try:
                self.qdrant.get_collection(collection)
                logger.info(f"Collection {collection} exists")
            except:
                # Create collection
                self.qdrant.create_collection(
                    collection_name=collection,
                    vectors_config=VectorParams(
                        size=self.embedding_dim,
                        distance=Distance.COSINE
                    )
                )
                logger.info(f"Created collection {collection}")
    
    def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding using centralized manager"""
        from .embeddings.embedding_manager import get_embedding_manager
        manager = get_embedding_manager()
        return manager.generate(text)
    
    def _OLD_generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for text"""
        embedding = self.embedder.encode(text, normalize_embeddings=True)
        return embedding.tolist()
    
    async def index_session(self, session_id: str):
        """Index a complete session in vector database"""
        messages = self.session_manager.get_session_messages(session_id)
        
        if not messages:
            return
        
        points = []
        for i, msg in enumerate(messages):
            # Create unique ID
            point_id = hashlib.md5(
                f"{session_id}_{i}_{msg['timestamp']}".encode()
            ).hexdigest()[:16]
            
            # Generate embedding
            embedding = self.generate_embedding(msg['content'])
            
            # Create point
            point = PointStruct(
                id=point_id,
                vector=embedding,
                payload={
                    'session_id': session_id,
                    'message_index': i,
                    'role': msg['role'],
                    'content': msg['content'],
                    'timestamp': msg['timestamp'],
                    'model': msg.get('model', 'unknown'),
                    'tokens': msg.get('tokens', 0)
                }
            )
            points.append(point)
        
        # Batch upload to Qdrant
        if points:
            self.qdrant.upsert(
                collection_name=self.collections['messages'],
                points=points
            )
            logger.info(f"Indexed {len(points)} messages from session {session_id}")
    
    async def search_relevant_context(
        self, 
        query: str, 
        exclude_session: Optional[str] = None,
        limit: int = 10,
        min_score: float = 0.5
    ) -> List[Dict[str, Any]]:
        """
        Search for relevant context across all sessions
        
        Args:
            query: Current user query
            exclude_session: Session ID to exclude (current session)
            limit: Maximum number of results
            min_score: Minimum relevance score
        
        Returns:
            List of relevant contexts with metadata
        """
        
        # Generate query embedding
        query_embedding = self.generate_embedding(query)
        
        # Build filter
        filter_conditions = []
        if exclude_session:
            filter_conditions.append(
                FieldCondition(
                    key="session_id",
                    match=MatchValue(value=exclude_session),
                    inverse=True
                )
            )
        
        # Search in messages collection
        results = self.qdrant.search(
            collection_name=self.collections['messages'],
            query_vector=query_embedding,
            limit=limit * 2,  # Get more to filter
            filter=Filter(must=filter_conditions) if filter_conditions else None
        )
        
        # Process and rank results
        relevant_contexts = []
        seen_content = set()
        
        for point in results:
            if point.score < min_score:
                continue
            
            payload = point.payload
            content_hash = hashlib.md5(payload['content'].encode()).hexdigest()
            
            # Skip duplicates
            if content_hash in seen_content:
                continue
            seen_content.add(content_hash)
            
            # Add relevance level
            if point.score >= self.relevance_thresholds['high']:
                relevance = 'high'
            elif point.score >= self.relevance_thresholds['medium']:
                relevance = 'medium'
            else:
                relevance = 'low'
            
            relevant_contexts.append({
                'content': payload['content'],
                'role': payload['role'],
                'session_id': payload['session_id'],
                'timestamp': payload['timestamp'],
                'score': point.score,
                'relevance': relevance,
                'model': payload.get('model', 'unknown')
            })
            
            if len(relevant_contexts) >= limit:
                break
        
        return relevant_contexts
    
    async def find_similar_problems(
        self, 
        problem: str,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Find similar problems that were solved before"""
        
        # Search for similar user questions
        contexts = await self.search_relevant_context(
            query=problem,
            limit=limit * 3  # Get more to find Q&A pairs
        )
        
        # Find question-answer pairs
        solutions = []
        for ctx in contexts:
            if ctx['role'] == 'user':
                # Look for the assistant response
                session_messages = self.session_manager.get_session_messages(
                    ctx['session_id']
                )
                
                for i, msg in enumerate(session_messages):
                    if (msg['timestamp'] == ctx['timestamp'] and 
                        i + 1 < len(session_messages)):
                        # Found the question, get the answer
                        answer = session_messages[i + 1]
                        if answer['role'] == 'assistant':
                            solutions.append({
                                'question': ctx['content'],
                                'answer': answer['content'],
                                'session_id': ctx['session_id'],
                                'score': ctx['score'],
                                'timestamp': ctx['timestamp']
                            })
                            break
        
        return solutions[:limit]
    
    async def get_session_recommendations(
        self,
        current_query: str,
        current_session: str
    ) -> Dict[str, Any]:
        """Get intelligent recommendations based on current context"""
        
        recommendations = {
            'related_topics': [],
            'similar_sessions': [],
            'suggested_questions': [],
            'relevant_knowledge': [],
            'confidence_score': 0.0
        }
        
        # Find relevant contexts
        contexts = await self.search_relevant_context(
            query=current_query,
            exclude_session=current_session,
            limit=20
        )
        
        if not contexts:
            return recommendations
        
        # Calculate confidence score
        if contexts:
            avg_score = sum(c['score'] for c in contexts) / len(contexts)
            recommendations['confidence_score'] = avg_score
        
        # Group by session to find similar sessions
        session_scores = {}
        for ctx in contexts:
            session_id = ctx['session_id']
            if session_id not in session_scores:
                session_scores[session_id] = []
            session_scores[session_id].append(ctx['score'])
        
        # Calculate average score per session
        for session_id, scores in session_scores.items():
            avg_score = sum(scores) / len(scores)
            recommendations['similar_sessions'].append({
                'session_id': session_id,
                'relevance_score': avg_score,
                'matching_messages': len(scores)
            })
        
        # Sort by relevance
        recommendations['similar_sessions'].sort(
            key=lambda x: x['relevance_score'], 
            reverse=True
        )
        recommendations['similar_sessions'] = recommendations['similar_sessions'][:5]
        
        # Extract topics and knowledge
        for ctx in contexts[:10]:
            if ctx['relevance'] == 'high':
                recommendations['relevant_knowledge'].append({
                    'content': ctx['content'][:200] + '...' if len(ctx['content']) > 200 else ctx['content'],
                    'score': ctx['score'],
                    'from_session': ctx['session_id']
                })
        
        # Generate suggested questions based on patterns
        similar_problems = await self.find_similar_problems(current_query, limit=3)
        for problem in similar_problems:
            recommendations['suggested_questions'].append(
                problem['question'][:100] + '...' if len(problem['question']) > 100 else problem['question']
            )
        
        return recommendations
    
    async def build_context_for_llm(
        self,
        query: str,
        current_session: Optional[str] = None,
        max_tokens: int = 2000
    ) -> str:
        """
        Build optimized context for LLM with relevant information
        
        Returns formatted context string for injection into LLM prompt
        """
        
        # Get relevant contexts
        contexts = await self.search_relevant_context(
            query=query,
            exclude_session=current_session,
            limit=10
        )
        
        # Find similar problems with solutions
        solutions = await self.find_similar_problems(query, limit=3)
        
        # Build context string
        context_parts = []
        
        # Add similar solutions if found
        if solutions:
            context_parts.append("📚 CONOCIMIENTO RELEVANTE DE SESIONES ANTERIORES:")
            for i, sol in enumerate(solutions, 1):
                context_parts.append(f"\n{i}. Pregunta similar (relevancia: {sol['score']:.2f}):")
                context_parts.append(f"   P: {sol['question'][:150]}...")
                context_parts.append(f"   R: {sol['answer'][:300]}...")
        
        # Add highly relevant contexts
        high_relevance = [c for c in contexts if c['relevance'] == 'high']
        if high_relevance:
            context_parts.append("\n\n🎯 CONTEXTO ALTAMENTE RELEVANTE:")
            for ctx in high_relevance[:3]:
                role_emoji = "👤" if ctx['role'] == 'user' else "🤖"
                context_parts.append(f"\n{role_emoji} {ctx['content'][:200]}...")
        
        # Join and truncate to token limit
        full_context = "\n".join(context_parts)
        
        # Count tokens and truncate if needed
        tokens = self.tokenizer.encode(full_context)
        if len(tokens) > max_tokens:
            # Truncate to fit
            truncated_tokens = tokens[:max_tokens]
            full_context = self.tokenizer.decode(truncated_tokens)
            full_context += "\n... (contexto truncado)"
        
        return full_context
    
    async def auto_index_all_sessions(self):
        """Automatically index all existing sessions"""
        sessions = self.session_manager.get_recent_sessions(limit=100)
        
        logger.info(f"Indexing {len(sessions)} sessions...")
        for session in sessions:
            await self.index_session(session['session_id'])
        
        logger.info("Indexing complete")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about the vector database"""
        stats = {}
        
        for name, collection in self.collections.items():
            try:
                info = self.qdrant.get_collection(collection)
                stats[name] = {
                    'vectors_count': info.vectors_count,
                    'points_count': info.points_count,
                    'status': info.status
                }
            except:
                stats[name] = {'status': 'not_initialized'}
        
        return stats
    
    async def suggest_next_action(
        self,
        conversation_history: List[Dict[str, str]],
        current_session: str
    ) -> List[str]:
        """
        Suggest next actions based on conversation patterns
        
        Returns list of suggested next questions or actions
        """
        
        if not conversation_history:
            return []
        
        # Get last user message
        last_message = None
        for msg in reversed(conversation_history):
            if msg.get('role') == 'user':
                last_message = msg.get('content', '')
                break
        
        if not last_message:
            return []
        
        # Find similar conversation flows
        similar_contexts = await self.search_relevant_context(
            query=last_message,
            exclude_session=current_session,
            limit=20
        )
        
        # Extract what typically comes next
        suggestions = []
        for ctx in similar_contexts:
            if ctx['role'] == 'user' and ctx['score'] > 0.8:
                # Find next user message in that session
                session_messages = self.session_manager.get_session_messages(
                    ctx['session_id']
                )
                
                for i, msg in enumerate(session_messages):
                    if msg['content'] == ctx['content'] and i + 2 < len(session_messages):
                        next_user_msg = session_messages[i + 2]
                        if next_user_msg['role'] == 'user':
                            suggestions.append(next_user_msg['content'])
                            break
        
        # Deduplicate and return top suggestions
        seen = set()
        unique_suggestions = []
        for sugg in suggestions:
            sugg_lower = sugg.lower()[:50]
            if sugg_lower not in seen:
                seen.add(sugg_lower)
                unique_suggestions.append(sugg)
        
        return unique_suggestions[:5]


# CLI interface for testing
if __name__ == "__main__":
    import sys
    from colorama import init, Fore, Style
    
    init(autoreset=True)
    
    async def main():
        rag = IntelligentRAGSystem()
        
        if len(sys.argv) < 2:
            print(f"{Fore.CYAN}Intelligent RAG System for NubemSuperFClaude{Style.RESET_ALL}")
            print("\nCommands:")
            print("  index    - Index all sessions")
            print("  search   - Search relevant context")
            print("  similar  - Find similar problems")
            print("  stats    - Show statistics")
            print("  suggest  - Get suggestions for query")
            return
        
        command = sys.argv[1]
        
        if command == "index":
            print(f"{Fore.YELLOW}Indexing all sessions...{Style.RESET_ALL}")
            await rag.auto_index_all_sessions()
            print(f"{Fore.GREEN}✅ Indexing complete{Style.RESET_ALL}")
        
        elif command == "search":
            if len(sys.argv) < 3:
                print("Usage: intelligent_rag_system.py search <query>")
                return
            
            query = " ".join(sys.argv[2:])
            print(f"{Fore.CYAN}Searching for: {query}{Style.RESET_ALL}")
            
            contexts = await rag.search_relevant_context(query)
            
            if contexts:
                print(f"\n{Fore.GREEN}Found {len(contexts)} relevant contexts:{Style.RESET_ALL}")
                for ctx in contexts[:5]:
                    print(f"\n{Fore.YELLOW}Score: {ctx['score']:.3f} | {ctx['relevance'].upper()}{Style.RESET_ALL}")
                    print(f"Session: {ctx['session_id']}")
                    print(f"Content: {ctx['content'][:200]}...")
            else:
                print(f"{Fore.RED}No relevant contexts found{Style.RESET_ALL}")
        
        elif command == "similar":
            if len(sys.argv) < 3:
                print("Usage: intelligent_rag_system.py similar <problem>")
                return
            
            problem = " ".join(sys.argv[2:])
            print(f"{Fore.CYAN}Finding similar problems to: {problem}{Style.RESET_ALL}")
            
            solutions = await rag.find_similar_problems(problem)
            
            if solutions:
                print(f"\n{Fore.GREEN}Found {len(solutions)} similar problems:{Style.RESET_ALL}")
                for sol in solutions:
                    print(f"\n{Fore.YELLOW}Q:{Style.RESET_ALL} {sol['question'][:100]}...")
                    print(f"{Fore.GREEN}A:{Style.RESET_ALL} {sol['answer'][:200]}...")
                    print(f"{Fore.BLUE}Score: {sol['score']:.3f}{Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}No similar problems found{Style.RESET_ALL}")
        
        elif command == "stats":
            stats = rag.get_statistics()
            print(f"\n{Fore.CYAN}Vector Database Statistics:{Style.RESET_ALL}")
            for collection, info in stats.items():
                print(f"\n{Fore.YELLOW}{collection}:{Style.RESET_ALL}")
                for key, value in info.items():
                    print(f"  {key}: {value}")
        
        elif command == "suggest":
            if len(sys.argv) < 3:
                print("Usage: intelligent_rag_system.py suggest <query>")
                return
            
            query = " ".join(sys.argv[2:])
            context = await rag.build_context_for_llm(query)
            
            print(f"{Fore.CYAN}Context for LLM:{Style.RESET_ALL}")
            print(context)
            
            recommendations = await rag.get_session_recommendations(query, "test_session")
            print(f"\n{Fore.GREEN}Recommendations:{Style.RESET_ALL}")
            print(f"Confidence: {recommendations['confidence_score']:.2f}")
            print(f"Similar sessions: {len(recommendations['similar_sessions'])}")
            print(f"Relevant knowledge: {len(recommendations['relevant_knowledge'])}")
    
    asyncio.run(main())