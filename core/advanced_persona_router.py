#!/usr/bin/env python3
"""
Advanced Persona Router - Enhanced routing with embeddings, RL, and ensemble methods
=====================================================================================

This module provides state-of-the-art persona routing capabilities:
- Semantic matching with embeddings (sentence-transformers)
- Reinforcement learning from user feedback
- Ensemble routing combining multiple strategies
- Performance metrics and A/B testing
- Historical learning and optimization

Author: NubemSuperFClaude Team
Date: 2025-10-12
"""

import asyncio
import logging
import numpy as np
from typing import Dict, Any, List, Optional, Tuple, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict
import json
from pathlib import Path
import hashlib

logger = logging.getLogger(__name__)

# ============================================================================
# Data Models
# ============================================================================

@dataclass
class RoutingContext:
    """Enhanced routing context with rich metadata"""
    task: str
    task_type: Optional[str] = None
    domains: Set[str] = field(default_factory=set)
    complexity_level: float = 0.5
    required_capabilities: Set[str] = field(default_factory=set)
    conversation_history: List[Dict] = field(default_factory=list)
    user_preferences: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    session_id: Optional[str] = None


@dataclass
class RoutingResult:
    """Comprehensive routing result with metadata"""
    primary_persona: str
    support_personas: List[str]
    confidence_score: float
    strategy_used: str
    routing_time_ms: float
    embedding_similarity: Optional[float] = None
    all_scores: Dict[str, float] = field(default_factory=dict)
    reasoning: str = ""
    ab_test_variant: Optional[str] = None


@dataclass
class FeedbackRecord:
    """User feedback for reinforcement learning"""
    routing_id: str
    persona_selected: str
    task_context: str
    user_rating: float  # 0.0-1.0
    success: bool
    latency_ms: float
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class RoutingMetrics:
    """Comprehensive routing metrics"""
    total_requests: int = 0
    successful_routings: int = 0
    average_confidence: float = 0.0
    average_latency_ms: float = 0.0
    strategy_usage: Dict[str, int] = field(default_factory=dict)
    persona_usage: Dict[str, int] = field(default_factory=dict)
    persona_success_rate: Dict[str, float] = field(default_factory=dict)
    average_user_rating: float = 0.0
    embedding_cache_hit_rate: float = 0.0


# ============================================================================
# 1. Semantic Embedding Matcher
# ============================================================================

class SemanticMatcher:
    """
    Semantic matching using sentence transformers embeddings
    Provides high-quality semantic similarity between tasks and personas
    """

    def __init__(self, model_name: str = 'all-MiniLM-L6-v2'):
        self.model_name = model_name
        self.model = None
        self.embedding_cache = {}
        self.cache_hits = 0
        self.cache_misses = 0
        self._initialize_model()

    def _initialize_model(self):
        """Initialize sentence transformer model"""
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(self.model_name)
            logger.info(f"Semantic matcher initialized with {self.model_name}")
        except Exception as e:
            logger.warning(f"Could not load sentence transformer: {e}")
            self.model = None

    def _get_cache_key(self, text: str) -> str:
        """Generate cache key for text"""
        return hashlib.md5(text.encode()).hexdigest()

    def get_embedding(self, text: str, use_cache: bool = True) -> np.ndarray:
        """
        Get embedding for text with caching

        Args:
            text: Input text
            use_cache: Whether to use cache

        Returns:
            Embedding vector as numpy array
        """
        cache_key = self._get_cache_key(text)

        if use_cache and cache_key in self.embedding_cache:
            self.cache_hits += 1
            return self.embedding_cache[cache_key]

        self.cache_misses += 1

        if self.model:
            try:
                embedding = self.model.encode(text, show_progress_bar=False)
                if use_cache:
                    self.embedding_cache[cache_key] = embedding
                return embedding
            except Exception as e:
                logger.error(f"Embedding generation failed: {e}")

        # Fallback: simple hash-based pseudo-embedding
        return self._fallback_embedding(text)

    def _fallback_embedding(self, text: str) -> np.ndarray:
        """Fallback deterministic pseudo-embedding"""
        import random
        text_hash = int(hashlib.md5(text.encode()).hexdigest(), 16)
        random.seed(text_hash)
        return np.array([random.gauss(0, 1) for _ in range(384)])

    def calculate_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate cosine similarity between two texts

        Args:
            text1: First text
            text2: Second text

        Returns:
            Similarity score (0.0-1.0)
        """
        emb1 = self.get_embedding(text1)
        emb2 = self.get_embedding(text2)

        # Cosine similarity
        similarity = np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2))

        # Normalize to 0-1 range
        return float((similarity + 1) / 2)

    def find_best_matches(self,
                         query: str,
                         candidates: Dict[str, str],
                         top_k: int = 5) -> List[Tuple[str, float]]:
        """
        Find best matching candidates for query

        Args:
            query: Query text
            candidates: Dict of {id: description}
            top_k: Number of top matches to return

        Returns:
            List of (candidate_id, similarity_score) sorted by score
        """
        query_emb = self.get_embedding(query)
        scores = []

        for candidate_id, candidate_text in candidates.items():
            candidate_emb = self.get_embedding(candidate_text)
            similarity = np.dot(query_emb, candidate_emb) / \
                        (np.linalg.norm(query_emb) * np.linalg.norm(candidate_emb))
            similarity = (similarity + 1) / 2  # Normalize to 0-1
            scores.append((candidate_id, float(similarity)))

        # Sort by similarity (descending)
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total = self.cache_hits + self.cache_misses
        hit_rate = self.cache_hits / total if total > 0 else 0.0
        return {
            'cache_size': len(self.embedding_cache),
            'cache_hits': self.cache_hits,
            'cache_misses': self.cache_misses,
            'hit_rate': hit_rate
        }


# ============================================================================
# 2. Reinforcement Learning Router
# ============================================================================

class RLPersonaRouter:
    """
    Reinforcement Learning based persona router
    Uses Q-learning to optimize persona selection based on user feedback
    """

    def __init__(self, learning_rate: float = 0.1,
                 discount_factor: float = 0.9,
                 exploration_rate: float = 0.1):
        self.learning_rate = learning_rate
        self.discount_factor = discount_factor
        self.exploration_rate = exploration_rate

        # Q-table: state -> persona -> Q-value
        self.q_table: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))

        # Experience replay buffer
        self.experience_buffer: List[FeedbackRecord] = []
        self.max_buffer_size = 10000

        # Statistics
        self.total_updates = 0
        self.average_reward = 0.0

    def _get_state_key(self, context: RoutingContext) -> str:
        """
        Convert routing context to state key
        Uses task_type, complexity, and domains
        """
        domains_str = ','.join(sorted(context.domains)) if context.domains else 'general'
        complexity_bucket = int(context.complexity_level * 10) / 10  # Round to 0.1
        return f"{context.task_type or 'general'}:{complexity_bucket}:{domains_str}"

    def select_persona(self,
                      context: RoutingContext,
                      available_personas: List[str],
                      exploit_only: bool = False) -> Tuple[str, float]:
        """
        Select persona using epsilon-greedy policy

        Args:
            context: Routing context
            available_personas: List of available persona IDs
            exploit_only: If True, always exploit (no exploration)

        Returns:
            (selected_persona, q_value)
        """
        state_key = self._get_state_key(context)

        # Exploration vs Exploitation
        if not exploit_only and np.random.random() < self.exploration_rate:
            # Explore: random selection
            persona = np.random.choice(available_personas)
            q_value = self.q_table[state_key][persona]
            return persona, q_value

        # Exploit: select best known persona
        best_persona = None
        best_q_value = float('-inf')

        for persona in available_personas:
            q_value = self.q_table[state_key][persona]
            if q_value > best_q_value:
                best_q_value = q_value
                best_persona = persona

        # If no persona has been tried, select first
        if best_persona is None:
            best_persona = available_personas[0]
            best_q_value = 0.0

        return best_persona, best_q_value

    def update_from_feedback(self, feedback: FeedbackRecord):
        """
        Update Q-values based on user feedback

        Args:
            feedback: Feedback record with rating and success
        """
        # Add to experience buffer
        self.experience_buffer.append(feedback)
        if len(self.experience_buffer) > self.max_buffer_size:
            self.experience_buffer.pop(0)

        # Calculate reward
        # Reward combines success (0/1), user rating (0-1), and latency penalty
        latency_penalty = min(feedback.latency_ms / 5000, 0.3)  # Max 0.3 penalty
        reward = (float(feedback.success) * 0.5 +
                 feedback.user_rating * 0.5 -
                 latency_penalty)

        # Extract state from context
        # Simplified: use task_context as state indicator
        state_key = feedback.task_context
        persona = feedback.persona_selected

        # Q-learning update: Q(s,a) = Q(s,a) + α * [R + γ * max(Q(s',a')) - Q(s,a)]
        # Simplified: no next state (episodic)
        current_q = self.q_table[state_key][persona]
        new_q = current_q + self.learning_rate * (reward - current_q)
        self.q_table[state_key][persona] = new_q

        # Update statistics
        self.total_updates += 1
        self.average_reward = (self.average_reward * (self.total_updates - 1) + reward) / self.total_updates

        logger.debug(f"RL Update: persona={persona}, reward={reward:.3f}, new_q={new_q:.3f}")

    def batch_update(self, batch_size: int = 32):
        """
        Perform batch update from experience buffer
        Useful for mini-batch training
        """
        if len(self.experience_buffer) < batch_size:
            return

        # Sample random batch
        batch_indices = np.random.choice(len(self.experience_buffer), batch_size, replace=False)
        batch = [self.experience_buffer[i] for i in batch_indices]

        for feedback in batch:
            self.update_from_feedback(feedback)

    def get_statistics(self) -> Dict[str, Any]:
        """Get RL statistics"""
        return {
            'total_updates': self.total_updates,
            'average_reward': self.average_reward,
            'q_table_size': len(self.q_table),
            'experience_buffer_size': len(self.experience_buffer),
            'exploration_rate': self.exploration_rate
        }

    def save_model(self, path: str):
        """Save Q-table and experience buffer to disk"""
        data = {
            'q_table': {k: dict(v) for k, v in self.q_table.items()},
            'experience_buffer': [
                {
                    'routing_id': fb.routing_id,
                    'persona_selected': fb.persona_selected,
                    'task_context': fb.task_context,
                    'user_rating': fb.user_rating,
                    'success': fb.success,
                    'latency_ms': fb.latency_ms,
                    'timestamp': fb.timestamp.isoformat()
                }
                for fb in self.experience_buffer
            ],
            'statistics': self.get_statistics()
        }

        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
        logger.info(f"RL model saved to {path}")

    def load_model(self, path: str):
        """Load Q-table and experience buffer from disk"""
        try:
            with open(path, 'r') as f:
                data = json.load(f)

            # Load Q-table
            self.q_table = defaultdict(lambda: defaultdict(float))
            for state, actions in data['q_table'].items():
                for action, q_value in actions.items():
                    self.q_table[state][action] = q_value

            # Load experience buffer
            self.experience_buffer = [
                FeedbackRecord(
                    routing_id=fb['routing_id'],
                    persona_selected=fb['persona_selected'],
                    task_context=fb['task_context'],
                    user_rating=fb['user_rating'],
                    success=fb['success'],
                    latency_ms=fb['latency_ms'],
                    timestamp=datetime.fromisoformat(fb['timestamp'])
                )
                for fb in data['experience_buffer']
            ]

            # Load statistics
            stats = data.get('statistics', {})
            self.total_updates = stats.get('total_updates', 0)
            self.average_reward = stats.get('average_reward', 0.0)

            logger.info(f"RL model loaded from {path}")
        except Exception as e:
            logger.warning(f"Could not load RL model: {e}")


# ============================================================================
# 3. Ensemble Router
# ============================================================================

class EnsembleRouter:
    """
    Ensemble routing combining multiple strategies
    Uses weighted voting to combine different routing approaches
    """

    def __init__(self):
        self.strategies: Dict[str, Tuple[Any, float]] = {}  # strategy_name -> (router, weight)
        self.strategy_performance: Dict[str, List[float]] = defaultdict(list)

    def add_strategy(self, name: str, router: Any, weight: float = 1.0):
        """
        Add a routing strategy to ensemble

        Args:
            name: Strategy name
            router: Router instance with select_persona method
            weight: Initial weight (will be adjusted based on performance)
        """
        self.strategies[name] = (router, weight)
        logger.info(f"Added ensemble strategy: {name} with weight {weight}")

    def select_persona(self,
                      context: RoutingContext,
                      available_personas: List[str],
                      method: str = 'weighted_voting') -> Tuple[str, Dict[str, Any]]:
        """
        Select persona using ensemble method

        Args:
            context: Routing context
            available_personas: Available personas
            method: Ensemble method ('weighted_voting', 'confidence_weighted', 'rank_fusion')

        Returns:
            (selected_persona, metadata)
        """
        if method == 'weighted_voting':
            return self._weighted_voting(context, available_personas)
        elif method == 'confidence_weighted':
            return self._confidence_weighted(context, available_personas)
        elif method == 'rank_fusion':
            return self._rank_fusion(context, available_personas)
        else:
            raise ValueError(f"Unknown ensemble method: {method}")

    def _weighted_voting(self, context: RoutingContext, available_personas: List[str]) -> Tuple[str, Dict]:
        """Weighted voting across strategies"""
        votes: Dict[str, float] = defaultdict(float)
        strategy_results = {}

        for strategy_name, (router, weight) in self.strategies.items():
            try:
                # Each strategy votes with its weight
                if hasattr(router, 'select_persona'):
                    persona, score = router.select_persona(context, available_personas)
                    votes[persona] += weight * (score if score > 0 else 0.5)
                    strategy_results[strategy_name] = {'persona': persona, 'score': score}
            except Exception as e:
                logger.warning(f"Strategy {strategy_name} failed: {e}")

        # Select persona with most votes
        if not votes:
            return available_personas[0], {'error': 'All strategies failed'}

        best_persona = max(votes.items(), key=lambda x: x[1])

        return best_persona[0], {
            'method': 'weighted_voting',
            'all_votes': dict(votes),
            'strategy_results': strategy_results,
            'winning_score': best_persona[1]
        }

    def _confidence_weighted(self, context: RoutingContext, available_personas: List[str]) -> Tuple[str, Dict]:
        """Weight votes by confidence scores"""
        weighted_scores: Dict[str, float] = defaultdict(float)
        total_confidence = 0.0
        strategy_results = {}

        for strategy_name, (router, base_weight) in self.strategies.items():
            try:
                if hasattr(router, 'select_persona'):
                    persona, score = router.select_persona(context, available_personas)
                    confidence = abs(score)  # Use absolute score as confidence
                    weighted_scores[persona] += base_weight * confidence
                    total_confidence += confidence
                    strategy_results[strategy_name] = {
                        'persona': persona,
                        'score': score,
                        'confidence': confidence
                    }
            except Exception as e:
                logger.warning(f"Strategy {strategy_name} failed: {e}")

        if not weighted_scores:
            return available_personas[0], {'error': 'All strategies failed'}

        # Normalize by total confidence
        if total_confidence > 0:
            weighted_scores = {k: v / total_confidence for k, v in weighted_scores.items()}

        best_persona = max(weighted_scores.items(), key=lambda x: x[1])

        return best_persona[0], {
            'method': 'confidence_weighted',
            'normalized_scores': dict(weighted_scores),
            'strategy_results': strategy_results,
            'total_confidence': total_confidence
        }

    def _rank_fusion(self, context: RoutingContext, available_personas: List[str]) -> Tuple[str, Dict]:
        """Reciprocal Rank Fusion (RRF)"""
        rrf_scores: Dict[str, float] = defaultdict(float)
        k = 60  # RRF constant
        strategy_rankings = {}

        for strategy_name, (router, weight) in self.strategies.items():
            try:
                # Get rankings from each strategy
                if hasattr(router, 'find_best_matches'):
                    # Semantic matcher
                    rankings = router.find_best_matches(
                        context.task,
                        {p: p for p in available_personas},
                        top_k=len(available_personas)
                    )
                elif hasattr(router, 'select_persona'):
                    # Other routers - create synthetic ranking
                    persona, score = router.select_persona(context, available_personas)
                    rankings = [(persona, score)]
                else:
                    continue

                # Apply RRF formula
                for rank, (persona, score) in enumerate(rankings):
                    rrf_scores[persona] += weight / (k + rank + 1)

                strategy_rankings[strategy_name] = rankings

            except Exception as e:
                logger.warning(f"Strategy {strategy_name} failed in rank fusion: {e}")

        if not rrf_scores:
            return available_personas[0], {'error': 'All strategies failed'}

        best_persona = max(rrf_scores.items(), key=lambda x: x[1])

        return best_persona[0], {
            'method': 'rank_fusion',
            'rrf_scores': dict(rrf_scores),
            'strategy_rankings': strategy_rankings,
            'k': k
        }

    def update_weights(self, strategy_name: str, performance_score: float):
        """
        Update strategy weights based on performance
        Uses exponential moving average
        """
        if strategy_name not in self.strategies:
            return

        # Record performance
        self.strategy_performance[strategy_name].append(performance_score)

        # Keep last 100 scores
        if len(self.strategy_performance[strategy_name]) > 100:
            self.strategy_performance[strategy_name].pop(0)

        # Calculate new weight based on recent performance
        recent_scores = self.strategy_performance[strategy_name][-10:]
        avg_performance = np.mean(recent_scores)

        # Update weight (exponential moving average)
        router, old_weight = self.strategies[strategy_name]
        new_weight = 0.7 * old_weight + 0.3 * avg_performance
        self.strategies[strategy_name] = (router, new_weight)

        logger.debug(f"Updated {strategy_name} weight: {old_weight:.3f} -> {new_weight:.3f}")

    def get_statistics(self) -> Dict[str, Any]:
        """Get ensemble statistics"""
        stats = {}
        for name, (_, weight) in self.strategies.items():
            perf = self.strategy_performance[name]
            stats[name] = {
                'weight': weight,
                'performance_samples': len(perf),
                'avg_performance': np.mean(perf) if perf else 0.0,
                'recent_performance': np.mean(perf[-10:]) if perf else 0.0
            }
        return stats


# ============================================================================
# To be continued in next message...
# ============================================================================
