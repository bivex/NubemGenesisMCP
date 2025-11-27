"""
Unified LLM Adapter - Sistema unificado para gestión de múltiples LLMs
Implementa fallback automático, consenso y optimizaciones
"""

import os
import asyncio
import json
import hashlib
import time
from typing import Dict, List, Optional, Any, Union, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from abc import ABC, abstractmethod
import logging
from enum import Enum
from functools import lru_cache
import numpy as np

# Import LLM libraries conditionally
try:
    import openai
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    import anthropic
    from anthropic import AsyncAnthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

try:
    from groq import AsyncGroq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

try:
    from together import AsyncTogether
    TOGETHER_AVAILABLE = True
except ImportError:
    TOGETHER_AVAILABLE = False

# Configure logging
logger = logging.getLogger(__name__)


class LLMProvider(Enum):
    """Supported LLM providers"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    GROQ = "groq"
    TOGETHER = "together"
    OLLAMA = "ollama"


@dataclass
class LLMConfig:
    """Configuration for LLM provider"""
    provider: LLMProvider
    api_key: Optional[str] = None
    model: str = ""
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout: int = 30
    retry_attempts: int = 3
    base_url: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)


@dataclass
class LLMResponse:
    """Standardized LLM response"""
    content: str
    provider: str
    model: str
    tokens_used: int = 0
    latency: float = 0.0
    cost: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers"""
    
    def __init__(self, config: LLMConfig):
        self.config = config
        self.client = None
        self.is_available = False
        self.initialize()
    
    @abstractmethod
    def initialize(self):
        """Initialize the provider client"""
        pass
    
    @abstractmethod
    async def query(self, prompt: str, **kwargs) -> LLMResponse:
        """Query the LLM provider"""
        pass
    
    @abstractmethod
    def estimate_cost(self, tokens: int) -> float:
        """Estimate cost for tokens"""
        pass
    
    def validate(self) -> bool:
        """Validate provider configuration"""
        return self.is_available and self.config.api_key is not None


class OpenAIProvider(BaseLLMProvider):
    """OpenAI API provider implementation"""
    
    def initialize(self):
        if OPENAI_AVAILABLE and self.config.api_key:
            self.client = AsyncOpenAI(
                api_key=self.config.api_key,
                base_url=self.config.base_url,
                timeout=self.config.timeout,
                max_retries=self.config.retry_attempts
            )
            self.is_available = True
            if not self.config.model:
                self.config.model = "gpt-4o-mini"
    
    async def query(self, prompt: str, **kwargs) -> LLMResponse:
        if not self.is_available:
            return LLMResponse(
                content="",
                provider="openai",
                model=self.config.model,
                error="OpenAI provider not available"
            )
        
        start_time = time.time()
        try:
            response = await self.client.chat.completions.create(
                model=kwargs.get('model', self.config.model),
                messages=[{"role": "user", "content": prompt}],
                max_tokens=kwargs.get('max_tokens', self.config.max_tokens),
                temperature=kwargs.get('temperature', self.config.temperature),
                stream=False
            )
            
            latency = time.time() - start_time
            tokens = response.usage.total_tokens if response.usage else 0
            
            return LLMResponse(
                content=response.choices[0].message.content,
                provider="openai",
                model=response.model,
                tokens_used=tokens,
                latency=latency,
                cost=self.estimate_cost(tokens),
                metadata={
                    "finish_reason": response.choices[0].finish_reason,
                    "usage": response.usage.model_dump() if response.usage else {}
                }
            )
        except Exception as e:
            logger.error(f"OpenAI query failed: {e}")
            return LLMResponse(
                content="",
                provider="openai",
                model=self.config.model,
                error=str(e),
                latency=time.time() - start_time
            )
    
    def estimate_cost(self, tokens: int) -> float:
        # Approximate costs per 1K tokens (varies by model)
        costs = {
            "gpt-4o": 0.015,
            "gpt-4o-mini": 0.0006,
            "gpt-4-turbo": 0.01,
            "gpt-3.5-turbo": 0.002
        }
        base_cost = costs.get(self.config.model, 0.002)
        return (tokens / 1000) * base_cost


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude API provider implementation"""
    
    def initialize(self):
        if ANTHROPIC_AVAILABLE and self.config.api_key:
            self.client = AsyncAnthropic(
                api_key=self.config.api_key,
                base_url=self.config.base_url,
                timeout=self.config.timeout,
                max_retries=self.config.retry_attempts
            )
            self.is_available = True
            if not self.config.model:
                self.config.model = "claude-3-haiku-20240307"
    
    async def query(self, prompt: str, **kwargs) -> LLMResponse:
        if not self.is_available:
            return LLMResponse(
                content="",
                provider="anthropic",
                model=self.config.model,
                error="Anthropic provider not available"
            )
        
        start_time = time.time()
        try:
            response = await self.client.messages.create(
                model=kwargs.get('model', self.config.model),
                messages=[{"role": "user", "content": prompt}],
                max_tokens=kwargs.get('max_tokens', self.config.max_tokens),
                temperature=kwargs.get('temperature', self.config.temperature)
            )
            
            latency = time.time() - start_time
            tokens = response.usage.input_tokens + response.usage.output_tokens
            
            return LLMResponse(
                content=response.content[0].text if response.content else "",
                provider="anthropic",
                model=response.model,
                tokens_used=tokens,
                latency=latency,
                cost=self.estimate_cost(tokens),
                metadata={
                    "stop_reason": response.stop_reason,
                    "usage": {
                        "input_tokens": response.usage.input_tokens,
                        "output_tokens": response.usage.output_tokens
                    }
                }
            )
        except Exception as e:
            logger.error(f"Anthropic query failed: {e}")
            return LLMResponse(
                content="",
                provider="anthropic",
                model=self.config.model,
                error=str(e),
                latency=time.time() - start_time
            )
    
    def estimate_cost(self, tokens: int) -> float:
        # Approximate costs per 1K tokens
        costs = {
            "claude-3-opus": 0.015,
            "claude-3-sonnet": 0.003,
            "claude-3-haiku": 0.00025
        }
        base_cost = costs.get(self.config.model.split('-20')[0], 0.003)
        return (tokens / 1000) * base_cost


class GeminiProvider(BaseLLMProvider):
    """Google Gemini API provider implementation"""
    
    def initialize(self):
        if GEMINI_AVAILABLE and self.config.api_key:
            genai.configure(api_key=self.config.api_key)
            self.is_available = True
            if not self.config.model:
                self.config.model = "gemini-1.5-flash"
    
    async def query(self, prompt: str, **kwargs) -> LLMResponse:
        if not self.is_available:
            return LLMResponse(
                content="",
                provider="gemini",
                model=self.config.model,
                error="Gemini provider not available"
            )
        
        start_time = time.time()
        try:
            model = genai.GenerativeModel(kwargs.get('model', self.config.model))
            
            generation_config = genai.GenerationConfig(
                max_output_tokens=kwargs.get('max_tokens', self.config.max_tokens),
                temperature=kwargs.get('temperature', self.config.temperature)
            )
            
            response = await asyncio.to_thread(
                model.generate_content,
                prompt,
                generation_config=generation_config
            )
            
            latency = time.time() - start_time
            
            return LLMResponse(
                content=response.text,
                provider="gemini",
                model=self.config.model,
                latency=latency,
                cost=self.estimate_cost(len(prompt) + len(response.text)),
                metadata={
                    "safety_ratings": [r.__dict__ for r in response.prompt_feedback.safety_ratings]
                    if hasattr(response, 'prompt_feedback') else []
                }
            )
        except Exception as e:
            logger.error(f"Gemini query failed: {e}")
            return LLMResponse(
                content="",
                provider="gemini",
                model=self.config.model,
                error=str(e),
                latency=time.time() - start_time
            )
    
    def estimate_cost(self, tokens: int) -> float:
        # Gemini pricing (approximate)
        return (tokens / 1000) * 0.0005  # Very competitive pricing


class GroqProvider(BaseLLMProvider):
    """Groq API provider implementation"""
    
    def initialize(self):
        if GROQ_AVAILABLE and self.config.api_key:
            self.client = AsyncGroq(api_key=self.config.api_key)
            self.is_available = True
            if not self.config.model:
                self.config.model = "mixtral-8x7b-32768"
    
    async def query(self, prompt: str, **kwargs) -> LLMResponse:
        if not self.is_available:
            return LLMResponse(
                content="",
                provider="groq",
                model=self.config.model,
                error="Groq provider not available"
            )
        
        start_time = time.time()
        try:
            response = await self.client.chat.completions.create(
                model=kwargs.get('model', self.config.model),
                messages=[{"role": "user", "content": prompt}],
                max_tokens=kwargs.get('max_tokens', self.config.max_tokens),
                temperature=kwargs.get('temperature', self.config.temperature)
            )
            
            latency = time.time() - start_time
            
            return LLMResponse(
                content=response.choices[0].message.content,
                provider="groq",
                model=response.model,
                latency=latency,
                cost=0,  # Groq is currently free
                metadata={"finish_reason": response.choices[0].finish_reason}
            )
        except Exception as e:
            logger.error(f"Groq query failed: {e}")
            return LLMResponse(
                content="",
                provider="groq",
                model=self.config.model,
                error=str(e),
                latency=time.time() - start_time
            )
    
    def estimate_cost(self, tokens: int) -> float:
        return 0  # Groq is currently free


class UnifiedLLMAdapter:
    """
    Unified adapter for all LLM providers with fallback, consensus, and optimization
    """
    
    def __init__(self, cache_manager=None, secrets_manager=None):
        self.providers: Dict[str, BaseLLMProvider] = {}
        self.fallback_chain = ['openai', 'anthropic', 'gemini', 'groq']
        self.cache_manager = cache_manager
        self.secrets_manager = secrets_manager
        self.metrics = {
            'total_queries': 0,
            'successful_queries': 0,
            'failed_queries': 0,
            'cache_hits': 0,
            'total_cost': 0.0,
            'total_latency': 0.0
        }
        self._initialize_providers()
    
    def _initialize_providers(self):
        """Initialize all available providers"""
        # Load API keys from environment or secrets manager
        api_keys = self._load_api_keys()
        
        # Initialize OpenAI
        if api_keys.get('openai'):
            self.providers['openai'] = OpenAIProvider(
                LLMConfig(
                    provider=LLMProvider.OPENAI,
                    api_key=api_keys['openai']
                )
            )
        
        # Initialize Anthropic
        if api_keys.get('anthropic'):
            self.providers['anthropic'] = AnthropicProvider(
                LLMConfig(
                    provider=LLMProvider.ANTHROPIC,
                    api_key=api_keys['anthropic']
                )
            )
        
        # Initialize Gemini
        if api_keys.get('gemini'):
            self.providers['gemini'] = GeminiProvider(
                LLMConfig(
                    provider=LLMProvider.GEMINI,
                    api_key=api_keys['gemini']
                )
            )
        
        # Initialize Groq
        if api_keys.get('groq'):
            self.providers['groq'] = GroqProvider(
                LLMConfig(
                    provider=LLMProvider.GROQ,
                    api_key=api_keys['groq']
                )
            )
        
        logger.info(f"Initialized {len(self.providers)} LLM providers: {list(self.providers.keys())}")
    
    def _load_api_keys(self) -> Dict[str, str]:
        """Load API keys from environment variables (secrets manager requires async)"""
        # Note: Secrets manager requires async initialization
        # For now, load from environment variables
        # TODO: Implement async initialization path
        return {
            'openai': os.getenv('OPENAI_API_KEY'),
            'anthropic': os.getenv('ANTHROPIC_API_KEY') or os.getenv('CLAUDE_API_KEY'),
            'gemini': os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY'),
            'groq': os.getenv('GROQ_API_KEY'),
            'together': os.getenv('TOGETHER_API_KEY')
        }
    
    def _get_cache_key(self, prompt: str, provider: str = None) -> str:
        """Generate cache key for prompt"""
        content = f"{provider or 'auto'}:{prompt}"
        return hashlib.sha256(content.encode()).hexdigest()
    
    async def query(
        self, 
        prompt: str, 
        provider: str = 'auto',
        use_cache: bool = True,
        **kwargs
    ) -> LLMResponse:
        """
        Query LLM with automatic provider selection and fallback
        
        Args:
            prompt: The query prompt
            provider: Provider name or 'auto' for automatic selection
            use_cache: Whether to use cache
            **kwargs: Additional parameters for the query
        
        Returns:
            LLMResponse with the result
        """
        self.metrics['total_queries'] += 1
        
        # Check cache first
        if use_cache and self.cache_manager:
            cache_key = self._get_cache_key(prompt, provider)
            cached_response = await self.cache_manager.get(cache_key)
            if cached_response:
                self.metrics['cache_hits'] += 1
                logger.debug(f"Cache hit for prompt: {prompt[:50]}...")
                return cached_response
        
        # Execute query
        if provider == 'auto':
            response = await self._query_with_fallback(prompt, **kwargs)
        elif provider in self.providers:
            response = await self.providers[provider].query(prompt, **kwargs)
        else:
            response = LLMResponse(
                content="",
                provider=provider,
                model="",
                error=f"Provider {provider} not available"
            )
        
        # Update metrics
        if response.error:
            self.metrics['failed_queries'] += 1
        else:
            self.metrics['successful_queries'] += 1
            self.metrics['total_cost'] += response.cost
            self.metrics['total_latency'] += response.latency
            
            # Cache successful response
            if use_cache and self.cache_manager and not response.error:
                cache_key = self._get_cache_key(prompt, provider)
                await self.cache_manager.set(cache_key, response, ttl=3600)
        
        return response
    
    async def _query_with_fallback(self, prompt: str, **kwargs) -> LLMResponse:
        """Query with automatic fallback through provider chain"""
        errors = []
        
        for provider_name in self.fallback_chain:
            if provider_name not in self.providers:
                continue
            
            provider = self.providers[provider_name]
            if not provider.validate():
                continue
            
            logger.debug(f"Trying provider: {provider_name}")
            response = await provider.query(prompt, **kwargs)
            
            if not response.error:
                logger.info(f"Successful query with {provider_name}")
                return response
            
            errors.append(f"{provider_name}: {response.error}")
            logger.warning(f"Provider {provider_name} failed: {response.error}")
        
        # All providers failed
        return LLMResponse(
            content="",
            provider="auto",
            model="",
            error=f"All providers failed. Errors: {'; '.join(errors)}"
        )
    
    async def consensus(
        self, 
        prompt: str,
        providers: Optional[List[str]] = None,
        threshold: float = 0.7,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Get consensus response from multiple LLMs
        
        Args:
            prompt: The query prompt
            providers: List of providers to use (None for top 3)
            threshold: Agreement threshold for consensus (0.0 to 1.0)
            **kwargs: Additional parameters
        
        Returns:
            Dictionary with consensus result and individual responses
        """
        # Select providers
        if providers is None:
            available = [p for p in self.fallback_chain[:3] if p in self.providers]
        else:
            available = [p for p in providers if p in self.providers]
        
        if len(available) < 2:
            return {
                'consensus': None,
                'error': 'Need at least 2 providers for consensus',
                'responses': []
            }
        
        # Query all providers in parallel
        tasks = [
            self.providers[p].query(prompt, **kwargs)
            for p in available
        ]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter successful responses
        valid_responses = [
            r for r in responses 
            if isinstance(r, LLMResponse) and not r.error
        ]
        
        if not valid_responses:
            return {
                'consensus': None,
                'error': 'No valid responses from providers',
                'responses': responses
            }
        
        # Calculate consensus
        consensus_result = self._calculate_consensus(valid_responses, threshold)
        
        return {
            'consensus': consensus_result['text'],
            'confidence': consensus_result['confidence'],
            'agreement': consensus_result['agreement'],
            'responses': valid_responses,
            'providers_used': [r.provider for r in valid_responses]
        }
    
    def _calculate_consensus(
        self, 
        responses: List[LLMResponse],
        threshold: float = 0.7
    ) -> Dict[str, Any]:
        """
        Calculate consensus from multiple responses
        
        Simple implementation - can be enhanced with:
        - Semantic similarity using embeddings
        - Weighted voting based on provider reliability
        - Fact extraction and comparison
        """
        if not responses:
            return {'text': '', 'confidence': 0.0, 'agreement': 0.0}
        
        if len(responses) == 1:
            return {
                'text': responses[0].content,
                'confidence': 1.0,
                'agreement': 1.0
            }
        
        # For now, use simple majority or return most detailed response
        # This is a simplified implementation
        contents = [r.content for r in responses]
        
        # Find longest response as a proxy for most detailed
        longest_response = max(contents, key=len)
        
        # Calculate simple agreement metric (can be improved)
        agreement_scores = []
        for i, content1 in enumerate(contents):
            for content2 in contents[i+1:]:
                # Simple character overlap ratio
                overlap = len(set(content1.split()) & set(content2.split()))
                total = len(set(content1.split()) | set(content2.split()))
                if total > 0:
                    agreement_scores.append(overlap / total)
        
        avg_agreement = np.mean(agreement_scores) if agreement_scores else 0.0
        
        return {
            'text': longest_response,
            'confidence': min(1.0, avg_agreement + 0.3),  # Boost confidence
            'agreement': avg_agreement
        }
    
    async def stream(
        self,
        prompt: str,
        provider: str = 'auto',
        callback: Optional[Callable] = None,
        **kwargs
    ):
        """
        Stream response from LLM (if supported by provider)
        
        Args:
            prompt: The query prompt
            provider: Provider to use
            callback: Async callback function for chunks
            **kwargs: Additional parameters
        """
        # This would require implementing streaming for each provider
        # For now, return regular response
        response = await self.query(prompt, provider, **kwargs)
        if callback:
            await callback(response.content)
        return response
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get adapter metrics"""
        return {
            **self.metrics,
            'avg_latency': self.metrics['total_latency'] / max(1, self.metrics['successful_queries']),
            'success_rate': self.metrics['successful_queries'] / max(1, self.metrics['total_queries']),
            'cache_hit_rate': self.metrics['cache_hits'] / max(1, self.metrics['total_queries']),
            'avg_cost_per_query': self.metrics['total_cost'] / max(1, self.metrics['successful_queries']),
            'available_providers': list(self.providers.keys())
        }
    
    def set_fallback_chain(self, chain: List[str]):
        """Update fallback chain order"""
        self.fallback_chain = [p for p in chain if p in self.providers]
        logger.info(f"Updated fallback chain: {self.fallback_chain}")
    
    async def health_check(self) -> Dict[str, bool]:
        """Check health of all providers"""
        health = {}
        for name, provider in self.providers.items():
            try:
                response = await provider.query("Hi", max_tokens=10)
                health[name] = not bool(response.error)
            except:
                health[name] = False
        return health