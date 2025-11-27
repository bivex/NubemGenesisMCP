"""
RAG-Enhanced Response System
Complete RAG pipeline: context retrieval, persona memory, and enhanced responses
"""

import logging
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass
import time

from core.vector_database import get_vector_database
from core.embeddings_generator import get_embeddings_generator
from core.persona_memory import get_persona_memory
from core.context_manager import ContextWindowManager, ContextStrategy
from core.streaming_handler import StreamingHandler
from core.personas_extended import get_persona
from core.llm_integration import llm_handler as default_llm_handler
from core.advanced_rag import get_hybrid_search

logger = logging.getLogger(__name__)


@dataclass
class RAGContext:
    """Retrieved context for RAG"""
    documents: List[str]
    sources: List[Dict[str, Any]]
    relevance_scores: List[float]
    total_tokens: int


@dataclass
class EnhancedResponse:
    """Complete enhanced response with RAG"""
    response: str
    context_used: RAGContext
    persona_memories: List[Dict[str, Any]]
    tokens_used: int
    execution_time: float
    metadata: Dict[str, Any]


class RAGEnhancedResponseSystem:
    """
    Complete RAG system integrating all components

    Pipeline:
    1. Query analysis and embedding
    2. Context retrieval from vector DB
    3. Persona memory retrieval
    4. Context optimization
    5. Enhanced prompt generation
    6. Streaming response
    7. Memory storage
    """

    def __init__(
        self,
        persona_key: str,
        context_strategy: ContextStrategy = ContextStrategy.SLIDING_WINDOW,
        max_context_docs: int = 5,
        enable_streaming: bool = True,
        enable_memory: bool = True,
        use_advanced_rag: bool = False
    ):
        """
        Initialize RAG-Enhanced Response System

        Args:
            persona_key: Persona to use
            context_strategy: Strategy for context optimization
            max_context_docs: Maximum documents to retrieve
            enable_streaming: Enable response streaming
            enable_memory: Enable persona memory
            use_advanced_rag: Use advanced RAG with query expansion and re-ranking
        """
        self.persona_key = persona_key
        self.max_context_docs = max_context_docs
        self.enable_streaming = enable_streaming
        self.enable_memory = enable_memory
        self.use_advanced_rag = use_advanced_rag

        # Get persona
        self.persona = get_persona(persona_key)
        if not self.persona:
            raise ValueError(f"Persona {persona_key} not found")

        # Initialize components
        self.vector_db = get_vector_database()
        self.embeddings = get_embeddings_generator()
        self.context_manager = ContextWindowManager(strategy=context_strategy)

        # Advanced RAG system (optional)
        if use_advanced_rag:
            self.hybrid_search = get_hybrid_search(use_llm=True)
        else:
            self.hybrid_search = None

        if enable_streaming:
            self.streaming_handler = StreamingHandler(enable_metrics=True)
        else:
            self.streaming_handler = None

        if enable_memory:
            self.persona_memory = get_persona_memory(persona_key)
        else:
            self.persona_memory = None

        # Component availability
        self.vector_db_available = self.vector_db and self.vector_db.client is not None
        self.embeddings_available = self.embeddings is not None
        self.memory_available = self.persona_memory and self.persona_memory.enabled

        logger.info(f"RAG system initialized for {persona_key}")
        logger.info(f"  Vector DB: {self.vector_db_available}")
        logger.info(f"  Embeddings: {self.embeddings_available}")
        logger.info(f"  Memory: {self.memory_available}")

    async def retrieve_context(
        self,
        query: str,
        limit: int = None,
        score_threshold: float = 0.7
    ) -> RAGContext:
        """
        Retrieve relevant context from vector database

        Args:
            query: Query text
            limit: Maximum documents (uses max_context_docs if None)
            score_threshold: Minimum relevance score

        Returns:
            RAGContext with retrieved documents
        """
        if not self.vector_db_available or not self.embeddings_available:
            logger.warning("Vector DB or embeddings not available")
            return RAGContext(
                documents=[],
                sources=[],
                relevance_scores=[],
                total_tokens=0
            )

        try:
            # Use advanced RAG if enabled
            if self.use_advanced_rag and self.hybrid_search:
                logger.info("Using Advanced RAG (query expansion + re-ranking)")
                ranked_results = await self.hybrid_search.search(
                    query=query,
                    limit=limit or self.max_context_docs,
                    score_threshold=score_threshold
                )

                documents = [r.content for r in ranked_results]
                sources = [r.metadata for r in ranked_results]
                scores = [r.score for r in ranked_results]
            else:
                # Standard vector search
                logger.info("Using standard vector search")
                query_embedding = self.embeddings.generate(query).embedding

                # Search vector database
                results = self.vector_db.search(
                    query_embedding=query_embedding,
                    limit=limit or self.max_context_docs,
                    score_threshold=score_threshold
                )

                # Extract information
                documents = [r.content for r in results]
                sources = [r.metadata for r in results]
                scores = [r.score for r in results]

            # Count tokens
            total_tokens = sum(self.context_manager.count_tokens(doc) for doc in documents)

            logger.info(f"Retrieved {len(documents)} documents ({total_tokens} tokens)")

            return RAGContext(
                documents=documents,
                sources=sources,
                relevance_scores=scores,
                total_tokens=total_tokens
            )

        except Exception as e:
            logger.error(f"Error retrieving context: {e}")
            return RAGContext(documents=[], sources=[], relevance_scores=[], total_tokens=0)

    def retrieve_persona_memories(
        self,
        query: str,
        limit: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant memories from persona's long-term memory

        Args:
            query: Query text
            limit: Maximum memories

        Returns:
            List of memory dictionaries
        """
        if not self.memory_available:
            return []

        try:
            results = self.persona_memory.search_memories(
                query=query,
                limit=limit,
                score_threshold=0.75
            )

            memories = []
            for result in results:
                memories.append({
                    'content': result.entry.content,
                    'type': result.entry.memory_type,
                    'importance': result.entry.importance,
                    'relevance': result.relevance,
                    'score': result.score
                })

            logger.info(f"Retrieved {len(memories)} relevant memories")
            return memories

        except Exception as e:
            logger.error(f"Error retrieving memories: {e}")
            return []

    def build_enhanced_prompt(
        self,
        query: str,
        context: RAGContext,
        memories: List[Dict[str, Any]],
        include_persona_prompt: bool = True
    ) -> str:
        """
        Build enhanced prompt with context and memories

        Args:
            query: User query
            context: Retrieved context
            memories: Persona memories
            include_persona_prompt: Include persona system prompt

        Returns:
            Enhanced prompt string
        """
        prompt_parts = []

        # Persona system prompt
        if include_persona_prompt and self.persona:
            prompt_parts.append("ROLE AND EXPERTISE:")
            prompt_parts.append(self.persona['system_prompt'][:500] + "...")
            prompt_parts.append("")

        # Retrieved context
        if context.documents:
            prompt_parts.append("RELEVANT CONTEXT:")
            for i, (doc, score) in enumerate(zip(context.documents, context.relevance_scores), 1):
                prompt_parts.append(f"\n[Source {i}] (Relevance: {score:.2f})")
                prompt_parts.append(doc[:500] + "..." if len(doc) > 500 else doc)
            prompt_parts.append("")

        # Persona memories
        if memories:
            prompt_parts.append("RELEVANT PAST EXPERIENCE:")
            for memory in memories:
                prompt_parts.append(f"- [{memory['type']}] {memory['content'][:200]}...")
            prompt_parts.append("")

        # User query
        prompt_parts.append("USER QUERY:")
        prompt_parts.append(query)
        prompt_parts.append("")
        prompt_parts.append("Provide a comprehensive response using the context and your expertise.")

        return "\n".join(prompt_parts)

    async def generate_response(
        self,
        query: str,
        llm_handler: Optional[callable] = None,
        max_tokens: int = 2000
    ) -> EnhancedResponse:
        """
        Generate enhanced response with RAG pipeline

        Args:
            query: User query
            llm_handler: Async function to call LLM
            max_tokens: Maximum tokens for response

        Returns:
            EnhancedResponse with complete information
        """
        start_time = time.time()

        # 1. Retrieve context
        logger.info("Step 1: Retrieving context...")
        context = await self.retrieve_context(query)

        # 2. Retrieve memories
        logger.info("Step 2: Retrieving memories...")
        memories = self.retrieve_persona_memories(query)

        # 3. Build enhanced prompt
        logger.info("Step 3: Building enhanced prompt...")
        enhanced_prompt = self.build_enhanced_prompt(query, context, memories)

        # 4. Optimize context (ensure it fits)
        logger.info("Step 4: Optimizing context...")
        messages = [{"role": "user", "content": enhanced_prompt}]
        optimized_messages, stats = self.context_manager.optimize_context(
            messages,
            system_message=self.persona['system_prompt'] if self.persona else None,
            reserved_tokens=max_tokens
        )

        # 5. Generate response
        logger.info("Step 5: Generating response...")
        if llm_handler is None:
            llm_handler = default_llm_handler

        try:
            response_text = await llm_handler(
                prompt=optimized_messages[0]['content'],
                persona_key=self.persona_key
            )
        except Exception as e:
            logger.error(f"Error calling LLM: {e}")
            # Fallback to mock response
            response_text = f"[Error generating response: {e}]\n\n"
            response_text += f"Context used: {len(context.documents)} documents\n"
            response_text += f"Memories used: {len(memories)} memories\n"
            response_text += f"Persona: {self.persona_key}"

        # 6. Store in memory
        if self.memory_available:
            logger.info("Step 6: Storing interaction in memory...")
            self.persona_memory.add_memory(
                content=f"Query: {query[:100]}... Response: {response_text[:100]}...",
                memory_type='conversation',
                context={'query': query, 'context_docs': len(context.documents)},
                importance=0.6
            )

        # Create result
        execution_time = time.time() - start_time

        result = EnhancedResponse(
            response=response_text,
            context_used=context,
            persona_memories=[{'content': m['content'][:100]} for m in memories],
            tokens_used=stats.total_tokens + max_tokens,
            execution_time=execution_time,
            metadata={
                'persona': self.persona_key,
                'context_docs': len(context.documents),
                'memories_used': len(memories),
                'context_tokens': context.total_tokens,
                'utilization': f"{stats.utilization_percent:.1f}%"
            }
        )

        logger.info(f"RAG pipeline completed in {execution_time:.2f}s")
        return result

    def get_system_status(self) -> Dict[str, Any]:
        """Get status of RAG system components"""
        return {
            'persona_key': self.persona_key,
            'persona_loaded': self.persona is not None,
            'vector_db_available': self.vector_db_available,
            'embeddings_available': self.embeddings_available,
            'memory_available': self.memory_available,
            'streaming_enabled': self.enable_streaming,
            'context_strategy': self.context_manager.strategy.value,
            'max_context_docs': self.max_context_docs
        }


# Global RAG systems (one per persona)
_rag_systems: Dict[str, RAGEnhancedResponseSystem] = {}


def get_rag_system(persona_key: str) -> RAGEnhancedResponseSystem:
    """
    Get or create RAG system for a persona (singleton per persona)

    Args:
        persona_key: Persona key

    Returns:
        RAGEnhancedResponseSystem instance
    """
    global _rag_systems

    if persona_key not in _rag_systems:
        _rag_systems[persona_key] = RAGEnhancedResponseSystem(persona_key)

    return _rag_systems[persona_key]


if __name__ == "__main__":
    # Test RAG-enhanced response system
    logging.basicConfig(level=logging.INFO)

    print("\n" + "="*60)
    print("Testing RAG-Enhanced Response System")
    print("="*60 + "\n")

    # Create RAG system for a persona
    persona_key = "product-manager"
    rag = get_rag_system(persona_key)

    # Check status
    status = rag.get_system_status()
    print(f"RAG System Status for {persona_key}:")
    for key, value in status.items():
        print(f"  {key}: {value}")

    print("\n" + "-"*60)
    print("Testing RAG Pipeline")
    print("-"*60 + "\n")

    # Test query
    query = "How should I prioritize features for our mobile app?"

    async def test_rag():
        print(f"Query: {query}\n")

        # Generate enhanced response
        result = await rag.generate_response(query)

        print(f"✓ Response generated in {result.execution_time:.2f}s")
        print(f"\nMetadata:")
        for key, value in result.metadata.items():
            print(f"  {key}: {value}")

        print(f"\nResponse:")
        print(result.response)

        print(f"\nContext used: {len(result.context_used.documents)} documents")
        print(f"Memories used: {len(result.persona_memories)} memories")
        print(f"Tokens used: {result.tokens_used}")

    # Run test
    import asyncio
    asyncio.run(test_rag())
