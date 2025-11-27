"""
LLM Manager for handling multiple AI models
"""

import os
import asyncio
from typing import Dict, Any, List, Optional
import logging
from abc import ABC, abstractmethod

# Import LLM clients
try:
    from anthropic import Anthropic, AsyncAnthropic
except ImportError:
    Anthropic = AsyncAnthropic = None

try:
    from openai import OpenAI, AsyncOpenAI
except ImportError:
    OpenAI = AsyncOpenAI = None

try:
    import google.generativeai as genai
except ImportError:
    genai = None

logger = logging.getLogger(__name__)

class LLMClient(ABC):
    """Abstract base class for LLM clients"""
    
    @abstractmethod
    async def query(self, prompt: str, **kwargs) -> str:
        """Send query to LLM"""
        pass
    
    @abstractmethod
    def validate_connection(self) -> bool:
        """Validate API connection"""
        pass

class ClaudeClient(LLMClient):
    """Claude API client"""
    
    def __init__(self, api_key: str):
        if not Anthropic:
            raise ImportError("anthropic package not installed")
        
        self.client = AsyncAnthropic(api_key=api_key)
        self.model = "claude-3-opus-20240229"
    
    async def query(self, prompt: str, **kwargs) -> str:
        try:
            response = await self.client.messages.create(
                model=kwargs.get('model', self.model),
                max_tokens=kwargs.get('max_tokens', 4096),
                temperature=kwargs.get('temperature', 0.7),
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text
        except Exception as e:
            logger.error(f"Claude query failed: {e}")
            raise
    
    def validate_connection(self) -> bool:
        try:
            # Simple validation
            return self.client.api_key is not None
        except:
            return False

class OpenAIClient(LLMClient):
    """OpenAI API client"""
    
    def __init__(self, api_key: str):
        if not OpenAI:
            raise ImportError("openai package not installed")
        
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = "gpt-4-turbo-preview"
    
    async def query(self, prompt: str, **kwargs) -> str:
        try:
            response = await self.client.chat.completions.create(
                model=kwargs.get('model', self.model),
                messages=[{"role": "user", "content": prompt}],
                max_tokens=kwargs.get('max_tokens', 4096),
                temperature=kwargs.get('temperature', 0.7)
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"OpenAI query failed: {e}")
            raise
    
    def validate_connection(self) -> bool:
        try:
            return self.client.api_key is not None
        except:
            return False

class GeminiClient(LLMClient):
    """Google Gemini API client"""
    
    def __init__(self, api_key: str):
        if not genai:
            raise ImportError("google-generativeai package not installed")
        
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-1.5-pro')
    
    async def query(self, prompt: str, **kwargs) -> str:
        try:
            # Gemini is synchronous, wrap in executor
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                self.model.generate_content,
                prompt
            )
            return response.text
        except Exception as e:
            logger.error(f"Gemini query failed: {e}")
            raise
    
    def validate_connection(self) -> bool:
        try:
            return genai is not None
        except:
            return False

class LLMManager:
    """Manages multiple LLM clients"""
    
    def __init__(self, settings):
        self.settings = settings
        self.clients: Dict[str, LLMClient] = {}
        self.available_models: List[str] = []
        self.default_model = settings.default_model
        
    def initialize_clients(self):
        """Initialize all configured LLM clients"""
        
        # Claude
        if self.settings.claude_api_key:
            try:
                self.clients['claude'] = ClaudeClient(self.settings.claude_api_key)
                self.available_models.append('claude')
                logger.info("Claude client initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize Claude: {e}")
        
        # OpenAI
        if self.settings.openai_api_key:
            try:
                self.clients['gpt4'] = OpenAIClient(self.settings.openai_api_key)
                self.clients['openai'] = self.clients['gpt4']  # Alias
                self.available_models.extend(['gpt4', 'openai'])
                logger.info("OpenAI client initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize OpenAI: {e}")
        
        # Gemini
        if self.settings.google_api_key:
            try:
                self.clients['gemini'] = GeminiClient(self.settings.google_api_key)
                self.available_models.append('gemini')
                logger.info("Gemini client initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize Gemini: {e}")
        
        if not self.clients:
            logger.warning("No LLM clients initialized. Please configure API keys.")
    
    async def query(self, model: str, prompt: str, **kwargs) -> str:
        """Query a specific model"""
        if model not in self.clients:
            if self.default_model in self.clients:
                model = self.default_model
            else:
                raise ValueError(f"Model '{model}' not available. Available: {self.available_models}")
        
        client = self.clients[model]
        return await client.query(prompt, **kwargs)
    
    async def query_all(self, prompt: str, **kwargs) -> Dict[str, str]:
        """Query all available models"""
        tasks = []
        model_names = []
        
        for model_name, client in self.clients.items():
            tasks.append(client.query(prompt, **kwargs))
            model_names.append(model_name)
        
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        
        results = {}
        for model_name, response in zip(model_names, responses):
            if isinstance(response, Exception):
                results[model_name] = f"Error: {str(response)}"
            else:
                results[model_name] = response
        
        return results
    
    def get_connected_models(self) -> List[str]:
        """Get list of connected models"""
        return self.available_models
    
    def validate_all_connections(self) -> Dict[str, bool]:
        """Validate all client connections"""
        results = {}
        for model_name, client in self.clients.items():
            results[model_name] = client.validate_connection()
        return results
    
    def set_default_model(self, model: str):
        """Set the default model"""
        if model in self.clients:
            self.default_model = model
        else:
            raise ValueError(f"Model '{model}' not available")
    
    def cleanup(self):
        """Cleanup resources"""
        # Close any open connections if needed
        pass