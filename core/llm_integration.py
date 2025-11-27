"""
LLM Integration - Unified interface for Anthropic, OpenAI, and other LLMs
Provides async handlers for RAG and collaboration systems
"""

import os
import logging
from typing import List, Dict, Any, Optional, AsyncIterator
from dataclasses import dataclass
from enum import Enum
import asyncio

logger = logging.getLogger(__name__)


class LLMProvider(Enum):
    """Supported LLM providers"""
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GROQ = "groq"
    GEMINI = "gemini"


@dataclass
class LLMConfig:
    """Configuration for LLM"""
    provider: LLMProvider
    model: str
    api_key: Optional[str] = None
    max_tokens: int = 4096
    temperature: float = 0.7
    top_p: float = 1.0
    stream: bool = True


@dataclass
class LLMResponse:
    """Response from LLM"""
    content: str
    model: str
    provider: str
    tokens_used: int
    finish_reason: str
    metadata: Dict[str, Any]


class LLMIntegration:
    """
    Unified LLM integration for multiple providers

    Features:
    - Support for Anthropic Claude, OpenAI GPT, Groq, Gemini
    - Async/await for all operations
    - Streaming support
    - Automatic retries
    - Token usage tracking
    - Fallback to alternative providers
    """

    def __init__(
        self,
        config: Optional[LLMConfig] = None,
        fallback_providers: Optional[List[LLMProvider]] = None
    ):
        """
        Initialize LLM Integration

        Args:
            config: Primary LLM configuration
            fallback_providers: List of fallback providers if primary fails
        """
        self.config = config or self._default_config()
        self.fallback_providers = fallback_providers or []

        # Initialize clients
        self.clients = {}
        self._initialize_clients()

    def _default_config(self) -> LLMConfig:
        """Get default configuration"""
        # Try to detect available API keys
        if os.getenv('ANTHROPIC_API_KEY'):
            return LLMConfig(
                provider=LLMProvider.ANTHROPIC,
                model="claude-sonnet-4-5-20250929",
                api_key=os.getenv('ANTHROPIC_API_KEY')
            )
        elif os.getenv('OPENAI_API_KEY'):
            return LLMConfig(
                provider=LLMProvider.OPENAI,
                model="gpt-4-turbo-preview",
                api_key=os.getenv('OPENAI_API_KEY')
            )
        else:
            logger.warning("No API keys found in environment")
            return LLMConfig(
                provider=LLMProvider.ANTHROPIC,
                model="claude-sonnet-4-5-20250929"
            )

    def _initialize_clients(self):
        """Initialize LLM clients"""
        # Anthropic
        if self.config.provider == LLMProvider.ANTHROPIC or \
           LLMProvider.ANTHROPIC in self.fallback_providers:
            try:
                from anthropic import AsyncAnthropic
                api_key = self.config.api_key if self.config.provider == LLMProvider.ANTHROPIC \
                    else os.getenv('ANTHROPIC_API_KEY')
                if api_key:
                    self.clients[LLMProvider.ANTHROPIC] = AsyncAnthropic(api_key=api_key)
                    logger.info("✓ Anthropic client initialized")
            except ImportError:
                logger.warning("Anthropic package not available")

        # OpenAI
        if self.config.provider == LLMProvider.OPENAI or \
           LLMProvider.OPENAI in self.fallback_providers:
            try:
                from openai import AsyncOpenAI
                api_key = self.config.api_key if self.config.provider == LLMProvider.OPENAI \
                    else os.getenv('OPENAI_API_KEY')
                if api_key:
                    self.clients[LLMProvider.OPENAI] = AsyncOpenAI(api_key=api_key)
                    logger.info("✓ OpenAI client initialized")
            except ImportError:
                logger.warning("OpenAI package not available")

        # Groq
        if self.config.provider == LLMProvider.GROQ or \
           LLMProvider.GROQ in self.fallback_providers:
            try:
                from groq import AsyncGroq
                api_key = self.config.api_key if self.config.provider == LLMProvider.GROQ \
                    else os.getenv('GROQ_API_KEY')
                if api_key:
                    self.clients[LLMProvider.GROQ] = AsyncGroq(api_key=api_key)
                    logger.info("✓ Groq client initialized")
            except ImportError:
                logger.warning("Groq package not available")

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_retries: int = 3
    ) -> LLMResponse:
        """
        Generate response from LLM

        Args:
            prompt: User prompt
            system_prompt: System prompt
            max_retries: Maximum retry attempts

        Returns:
            LLMResponse
        """
        providers_to_try = [self.config.provider] + self.fallback_providers
        last_error = None

        for provider in providers_to_try:
            if provider not in self.clients:
                continue

            for attempt in range(max_retries):
                try:
                    if provider == LLMProvider.ANTHROPIC:
                        return await self._generate_anthropic(prompt, system_prompt)
                    elif provider == LLMProvider.OPENAI:
                        return await self._generate_openai(prompt, system_prompt)
                    elif provider == LLMProvider.GROQ:
                        return await self._generate_groq(prompt, system_prompt)
                except Exception as e:
                    last_error = e
                    logger.warning(f"Attempt {attempt+1}/{max_retries} failed for {provider.value}: {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2 ** attempt)  # Exponential backoff

        raise Exception(f"All providers failed. Last error: {last_error}")

    async def _generate_anthropic(
        self,
        prompt: str,
        system_prompt: Optional[str] = None
    ) -> LLMResponse:
        """Generate response from Anthropic Claude"""
        client = self.clients[LLMProvider.ANTHROPIC]

        messages = [{"role": "user", "content": prompt}]

        response = await client.messages.create(
            model=self.config.model,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
            system=system_prompt or "",
            messages=messages
        )

        return LLMResponse(
            content=response.content[0].text,
            model=response.model,
            provider="anthropic",
            tokens_used=response.usage.input_tokens + response.usage.output_tokens,
            finish_reason=response.stop_reason,
            metadata={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens
            }
        )

    async def _generate_openai(
        self,
        prompt: str,
        system_prompt: Optional[str] = None
    ) -> LLMResponse:
        """Generate response from OpenAI"""
        client = self.clients[LLMProvider.OPENAI]

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = await client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature
        )

        return LLMResponse(
            content=response.choices[0].message.content,
            model=response.model,
            provider="openai",
            tokens_used=response.usage.total_tokens,
            finish_reason=response.choices[0].finish_reason,
            metadata={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens
            }
        )

    async def _generate_groq(
        self,
        prompt: str,
        system_prompt: Optional[str] = None
    ) -> LLMResponse:
        """Generate response from Groq"""
        client = self.clients[LLMProvider.GROQ]

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = await client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature
        )

        return LLMResponse(
            content=response.choices[0].message.content,
            model=response.model,
            provider="groq",
            tokens_used=response.usage.total_tokens,
            finish_reason=response.choices[0].finish_reason,
            metadata={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens
            }
        )

    async def stream_generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None
    ) -> AsyncIterator[str]:
        """
        Stream response from LLM

        Args:
            prompt: User prompt
            system_prompt: System prompt

        Yields:
            Text chunks
        """
        if self.config.provider == LLMProvider.ANTHROPIC:
            async for chunk in self._stream_anthropic(prompt, system_prompt):
                yield chunk
        elif self.config.provider == LLMProvider.OPENAI:
            async for chunk in self._stream_openai(prompt, system_prompt):
                yield chunk

    async def _stream_anthropic(
        self,
        prompt: str,
        system_prompt: Optional[str] = None
    ) -> AsyncIterator[str]:
        """Stream from Anthropic"""
        client = self.clients[LLMProvider.ANTHROPIC]
        messages = [{"role": "user", "content": prompt}]

        async with client.messages.stream(
            model=self.config.model,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
            system=system_prompt or "",
            messages=messages
        ) as stream:
            async for text in stream.text_stream:
                yield text

    async def _stream_openai(
        self,
        prompt: str,
        system_prompt: Optional[str] = None
    ) -> AsyncIterator[str]:
        """Stream from OpenAI"""
        client = self.clients[LLMProvider.OPENAI]

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        stream = await client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
            stream=True
        )

        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def get_status(self) -> Dict[str, Any]:
        """Get status of LLM integration"""
        return {
            "provider": self.config.provider.value,
            "model": self.config.model,
            "available_providers": [p.value for p in self.clients.keys()],
            "fallback_providers": [p.value for p in self.fallback_providers],
            "streaming_enabled": self.config.stream
        }


# Global LLM instance (singleton)
_llm_instance: Optional[LLMIntegration] = None


def get_llm(
    config: Optional[LLMConfig] = None,
    force_reload: bool = False
) -> LLMIntegration:
    """
    Get global LLM instance (singleton)

    Args:
        config: Configuration (uses default if None)
        force_reload: Force reload of instance

    Returns:
        LLMIntegration instance
    """
    global _llm_instance

    if _llm_instance is None or force_reload:
        _llm_instance = LLMIntegration(config)

    return _llm_instance


# Convenience async handler for RAG and collaboration
async def llm_handler(
    prompt: str,
    persona_key: Optional[str] = None,
    system_prompt: Optional[str] = None
) -> str:
    """
    Convenience async handler for LLM calls

    Args:
        prompt: User prompt
        persona_key: Optional persona key (will use persona's system prompt)
        system_prompt: Optional custom system prompt

    Returns:
        Response text
    """
    llm = get_llm()

    # Get persona system prompt if persona_key provided
    if persona_key and not system_prompt:
        from core.personas_extended import get_persona
        persona = get_persona(persona_key)
        if persona:
            system_prompt = persona['system_prompt']

    response = await llm.generate(prompt, system_prompt)
    return response.content


if __name__ == "__main__":
    # Test LLM integration
    logging.basicConfig(level=logging.INFO)

    print("\n" + "="*60)
    print("Testing LLM Integration")
    print("="*60 + "\n")

    # Create LLM instance
    llm = get_llm()

    status = llm.get_status()
    print("LLM Status:")
    for key, value in status.items():
        print(f"  {key}: {value}")

    # Test generation (will only work if API keys are set)
    if llm.clients:
        print("\n" + "-"*60)
        print("Testing Generation")
        print("-"*60 + "\n")

        async def test_generation():
            try:
                response = await llm.generate(
                    prompt="What is the capital of France?",
                    system_prompt="You are a helpful assistant. Be concise."
                )

                print(f"✓ Response generated")
                print(f"  Model: {response.model}")
                print(f"  Provider: {response.provider}")
                print(f"  Tokens: {response.tokens_used}")
                print(f"  Content: {response.content[:200]}...")

            except Exception as e:
                print(f"✗ Generation failed: {e}")

        asyncio.run(test_generation())
    else:
        print("\n⚠️  No LLM providers available")
        print("Set API keys in environment:")
        print("  export ANTHROPIC_API_KEY=your_key")
        print("  export OPENAI_API_KEY=your_key")
