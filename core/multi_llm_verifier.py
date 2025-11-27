#!/usr/bin/env python3
"""
Multi-LLM Verification System for NubemSuperFClaude
Compares outputs from multiple LLMs and provides unified analysis
"""

import os
import sys
import json
import asyncio
import time
import logging
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime
import httpx
from colorama import init, Fore, Style
from pathlib import Path
import difflib

# Import cache manager
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from llm_cache_manager import LLMCacheManager

init(autoreset=True)

# Setup logging
log_dir = Path.home() / "NubemSuperFClaude" / "logs"
log_dir.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.DEBUG if os.environ.get('NUBEM_DEBUG') == 'true' else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_dir / 'multi_llm.log'),
        logging.StreamHandler() if os.environ.get('NUBEM_DEBUG') == 'true' else logging.NullHandler()
    ]
)
logger = logging.getLogger(__name__)

class MultiLLMVerifier:
    """Handles multi-model verification and comparison with caching and metrics"""
    
    def __init__(self):
        self.cache = LLMCacheManager()
        self.timeout = int(os.environ.get('NUBEM_LLM_TIMEOUT', 30))
        self.metrics = {
            'response_times': {},
            'token_counts': {},
            'costs': {},
            'errors': {}
        }
        self.models = {
            'claude': {
                'name': 'Claude 3.5 Sonnet (Anthropic)',
                'api_key_env': 'ANTHROPIC_API_KEY',
                'endpoint': 'https://api.anthropic.com/v1/messages',
                'model': 'claude-3-5-sonnet-20241022',
                'provider': 'anthropic'
            },
            'gemini': {
                'name': 'Gemini Pro (Google)',
                'api_key_env': 'GOOGLE_GEMINI_KEY',
                'endpoint': 'https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent',
                'model': 'gemini-pro',
                'provider': 'google'
            },
            'openai': {
                'name': 'GPT-4 (OpenAI)',
                'api_key_env': 'OPENAI_API_KEY',
                'endpoint': 'https://api.openai.com/v1/chat/completions',
                'model': 'gpt-4-turbo-preview',
                'provider': 'openai'
            },
            'llama': {
                'name': 'Llama 3.1 70B (Together)',
                'api_key_env': 'TOGETHER_API_KEY',
                'endpoint': 'https://api.together.xyz/v1/chat/completions',
                'model': 'meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo',
                'provider': 'together'
            },
            'mistral': {
                'name': 'Mistral Large',
                'api_key_env': 'MISTRAL_API_KEY',
                'endpoint': 'https://api.mistral.ai/v1/chat/completions',
                'model': 'mistral-large-latest',
                'provider': 'mistral'
            },
            'groq-llama': {
                'name': 'Llama 3.1 (Groq Fast)',
                'api_key_env': 'GROQ_API_KEY',
                'endpoint': 'https://api.groq.com/openai/v1/chat/completions',
                'model': 'llama-3.1-70b-versatile',
                'provider': 'groq'
            },
            'perplexity': {
                'name': 'Perplexity (with search)',
                'api_key_env': 'PERPLEXITY_API_KEY',
                'endpoint': 'https://api.perplexity.ai/chat/completions',
                'model': 'llama-3.1-sonar-large-128k-online',
                'provider': 'perplexity'
            }
        }
        
        self.default_combo = ['claude', 'gemini', 'openai']
        self.selected_models = []
        self.responses = {}
        
    def check_available_models(self) -> Dict[str, bool]:
        """Check which models have API keys configured"""
        available = {}
        for model_id, config in self.models.items():
            api_key = os.environ.get(config['api_key_env'], '')
            available[model_id] = bool(api_key)
        return available
    
    def display_model_selection(self) -> List[str]:
        """Interactive model selection interface"""
        available = self.check_available_models()
        
        print(f"\n{Fore.CYAN}═══════════════════════════════════════════════════════════{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}🤖 Selección de Modelos para Verificación{Style.RESET_ALL}")
        print(f"{Fore.CYAN}═══════════════════════════════════════════════════════════{Style.RESET_ALL}\n")
        
        # Show recommended combo
        print(f"{Fore.GREEN}Opción recomendada:{Style.RESET_ALL}")
        print(f"  0. {Fore.CYAN}Claude + Gemini + OpenAI{Style.RESET_ALL} (Combinación óptima)")
        print()
        
        # Show individual models
        print(f"{Fore.YELLOW}Modelos disponibles:{Style.RESET_ALL}")
        available_models = []
        for i, (model_id, config) in enumerate(self.models.items(), 1):
            status = "✅" if available[model_id] else "❌"
            if available[model_id]:
                available_models.append(model_id)
                print(f"  {i}. {status} {config['name']}")
            else:
                print(f"  {i}. {status} {config['name']} {Fore.RED}(No configurado){Style.RESET_ALL}")
        
        print(f"\n{Fore.YELLOW}Selecciona los modelos (separados por coma) o 0 para la opción recomendada:{Style.RESET_ALL}")
        print(f"Ejemplo: 1,2,3 o simplemente 0")
        
        try:
            selection = input(f"{Fore.GREEN}Tu selección: {Style.RESET_ALL}").strip()
            
            if selection == '0':
                # Check if default combo is available
                selected = []
                for model_id in self.default_combo:
                    if available[model_id]:
                        selected.append(model_id)
                if len(selected) < 2:
                    print(f"{Fore.YELLOW}⚠️  No hay suficientes modelos del combo default configurados{Style.RESET_ALL}")
                    return []
                return selected
            
            # Parse individual selections
            selected = []
            for num in selection.split(','):
                try:
                    idx = int(num.strip()) - 1
                    if 0 <= idx < len(self.models):
                        model_id = list(self.models.keys())[idx]
                        if available[model_id]:
                            selected.append(model_id)
                except:
                    continue
            
            return selected
            
        except (EOFError, KeyboardInterrupt):
            return []
    
    async def query_model(self, model_id: str, prompt: str) -> Tuple[str, str]:
        """Query a specific model with caching and metrics"""
        start_time = time.time()
        config = self.models[model_id]
        api_key = os.environ.get(config['api_key_env'], '')
        
        if not api_key:
            logger.warning(f"API key not configured for {config['name']}")
            return model_id, f"Error: API key not configured for {config['name']}"
        
        # Check cache first
        cached_response = self.cache.get(prompt, model_id)
        if cached_response:
            logger.info(f"Cache hit for {model_id}")
            self.metrics['response_times'][model_id] = 0.001  # Cached response is instant
            return model_id, cached_response.get('response', 'No response')
        
        try:
            logger.info(f"Querying {model_id} with timeout {self.timeout}s")
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                headers = {}
                json_data = {}
                
                # Configure request based on provider
                if config['provider'] == 'anthropic':
                    headers = {
                        'x-api-key': api_key,
                        'anthropic-version': '2023-06-01',
                        'content-type': 'application/json'
                    }
                    json_data = {
                        'model': config['model'],
                        'messages': [{'role': 'user', 'content': prompt}],
                        'max_tokens': 1000
                    }
                
                elif config['provider'] == 'google':
                    # Gemini uses API key in URL
                    endpoint = f"{config['endpoint']}?key={api_key}"
                    headers = {'Content-Type': 'application/json'}
                    json_data = {
                        'contents': [{'parts': [{'text': prompt}]}],
                        'generationConfig': {'maxOutputTokens': 1000}
                    }
                
                elif config['provider'] in ['openai', 'together', 'mistral', 'groq', 'perplexity']:
                    headers = {
                        'Authorization': f'Bearer {api_key}',
                        'Content-Type': 'application/json'
                    }
                    json_data = {
                        'model': config['model'],
                        'messages': [{'role': 'user', 'content': prompt}],
                        'max_tokens': 1000
                    }
                
                # Make request
                if config['provider'] == 'google':
                    response = await client.post(endpoint, headers=headers, json=json_data)
                else:
                    response = await client.post(config['endpoint'], headers=headers, json=json_data)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Extract content based on provider
                    if config['provider'] == 'anthropic':
                        content = data.get('content', [{}])[0].get('text', 'No response')
                    elif config['provider'] == 'google':
                        content = data.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', 'No response')
                    else:  # OpenAI format (most common)
                        content = data.get('choices', [{}])[0].get('message', {}).get('content', 'No response')
                    
                    # Calculate metrics
                    elapsed_time = time.time() - start_time
                    self.metrics['response_times'][model_id] = elapsed_time
                    
                    # Estimate tokens (rough approximation)
                    prompt_tokens = len(prompt.split()) * 1.3
                    response_tokens = len(content.split()) * 1.3
                    self.metrics['token_counts'][model_id] = {
                        'prompt': prompt_tokens,
                        'response': response_tokens,
                        'total': prompt_tokens + response_tokens
                    }
                    
                    # Cache the response
                    self.cache.set(prompt, model_id, content, {
                        'response_time': elapsed_time,
                        'tokens': prompt_tokens + response_tokens
                    })
                    
                    logger.info(f"{model_id} responded in {elapsed_time:.2f}s")
                    return model_id, content
                else:
                    logger.error(f"{model_id} returned HTTP {response.status_code}")
                    self.metrics['errors'][model_id] = f"HTTP {response.status_code}"
                    return model_id, f"Error: HTTP {response.status_code}"
                    
        except asyncio.TimeoutError:
            elapsed_time = time.time() - start_time
            logger.error(f"{model_id} timed out after {elapsed_time:.2f}s")
            self.metrics['errors'][model_id] = f"Timeout after {elapsed_time:.2f}s"
            return model_id, f"Error: Timeout after {self.timeout}s"
        except Exception as e:
            logger.error(f"{model_id} error: {str(e)}")
            self.metrics['errors'][model_id] = str(e)
            return model_id, f"Error: {str(e)}"
    
    async def get_all_responses(self, prompt: str, selected_models: List[str]) -> Dict[str, str]:
        """Get responses from all selected models concurrently"""
        print(f"\n{Fore.CYAN}🔄 Consultando modelos...{Style.RESET_ALL}")
        
        # Create tasks for all models
        tasks = []
        for model_id in selected_models:
            print(f"  • Consultando {self.models[model_id]['name']}...")
            tasks.append(self.query_model(model_id, prompt))
        
        # Wait for all responses
        results = await asyncio.gather(*tasks)
        
        # Store responses
        responses = {}
        for model_id, response in results:
            responses[model_id] = response
            
        return responses
    
    def display_responses(self, responses: Dict[str, str], prompt: str):
        """Display all model responses with metrics"""
        print(f"\n{Fore.CYAN}═══════════════════════════════════════════════════════════{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}📊 Respuestas de los Modelos{Style.RESET_ALL}")
        print(f"{Fore.CYAN}═══════════════════════════════════════════════════════════{Style.RESET_ALL}")
        
        print(f"\n{Fore.GREEN}Pregunta:{Style.RESET_ALL} {prompt[:100]}...")
        
        # Display metrics summary
        if self.metrics['response_times']:
            print(f"\n{Fore.MAGENTA}⏱️ Tiempos de respuesta:{Style.RESET_ALL}")
            for model_id, time_taken in self.metrics['response_times'].items():
                status = "🎯 (cached)" if time_taken < 0.01 else ""
                print(f"  • {model_id}: {time_taken:.2f}s {status}")
        
        for i, (model_id, response) in enumerate(responses.items(), 1):
            config = self.models.get(model_id, {'name': model_id})
            print(f"\n{Fore.YELLOW}{'─' * 60}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}{i}. {config['name']}{Style.RESET_ALL}")
            
            # Show token count if available
            if model_id in self.metrics.get('token_counts', {}):
                tokens = self.metrics['token_counts'][model_id]['total']
                print(f"{Fore.BLUE}📝 Tokens: ~{int(tokens)}{Style.RESET_ALL}")
            
            print(f"{Fore.YELLOW}{'─' * 60}{Style.RESET_ALL}")
            
            # Truncate long responses for display
            if response.startswith("Error:"):
                print(f"{Fore.RED}{response}{Style.RESET_ALL}")
            elif len(response) > 500:
                print(response[:500] + "...")
            else:
                print(response)
    
    def compare_responses(self, responses: Dict[str, str]) -> Dict[str, Any]:
        """Compare responses and find differences"""
        comparison = {
            'consensus': [],
            'differences': [],
            'unique_points': {},
            'similarity_matrix': {}
        }
        
        # Get non-error responses
        valid_responses = {k: v for k, v in responses.items() if not v.startswith("Error:")}
        
        if len(valid_responses) < 2:
            return comparison
        
        # Calculate similarity between responses
        response_list = list(valid_responses.items())
        for i, (model1, resp1) in enumerate(response_list):
            for j, (model2, resp2) in enumerate(response_list[i+1:], i+1):
                similarity = difflib.SequenceMatcher(None, resp1, resp2).ratio()
                key = f"{model1}-{model2}"
                comparison['similarity_matrix'][key] = round(similarity * 100, 2)
        
        # Find consensus (common phrases)
        all_responses = list(valid_responses.values())
        if all_responses:
            # Simple consensus: words that appear in all responses
            word_sets = [set(resp.lower().split()) for resp in all_responses]
            common_words = set.intersection(*word_sets) if word_sets else set()
            comparison['consensus'] = list(common_words)[:20]  # Top 20 common words
        
        return comparison
    
    def create_comparison_prompt(self, prompt: str, responses: Dict[str, str]) -> str:
        """Create a prompt for Claude to compare all responses"""
        comparison = f"""Analiza y compara las siguientes respuestas de diferentes modelos de IA a la pregunta:

PREGUNTA ORIGINAL: {prompt}

RESPUESTAS DE LOS MODELOS:
"""
        for model_id, response in responses.items():
            config = self.models[model_id]
            comparison += f"\n{'='*50}\n{config['name']}:\n{response}\n"
        
        comparison += """
Por favor proporciona:
1. Un análisis comparativo de las respuestas
2. Puntos en común entre todas las respuestas
3. Diferencias significativas
4. Cuál respuesta es más completa/precisa y por qué
5. Una síntesis unificada que combine lo mejor de todas las respuestas
"""
        return comparison
    
    async def compare_with_claude(self, prompt: str, responses: Dict[str, str]) -> str:
        """Use Claude to analyze and compare all responses"""
        print(f"\n{Fore.CYAN}🧠 Analizando respuestas con Claude...{Style.RESET_ALL}")
        
        comparison_prompt = self.create_comparison_prompt(prompt, responses)
        
        # Query Claude for analysis
        _, analysis = await self.query_model('claude', comparison_prompt)
        
        return analysis
    
    async def run_verification(self, prompt: str, selected_models: List[str]) -> Dict:
        """Run complete verification process"""
        # Get all responses
        responses = await self.get_all_responses(prompt, selected_models)
        
        # Display individual responses
        self.display_responses(responses, prompt)
        
        # Get Claude's analysis if multiple models
        if len(responses) > 1:
            analysis = await self.compare_with_claude(prompt, responses)
            
            print(f"\n{Fore.CYAN}═══════════════════════════════════════════════════════════{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}🎯 Análisis Comparativo de Claude{Style.RESET_ALL}")
            print(f"{Fore.CYAN}═══════════════════════════════════════════════════════════{Style.RESET_ALL}")
            print(f"\n{analysis}")
            
            return {
                'prompt': prompt,
                'responses': responses,
                'analysis': analysis,
                'timestamp': datetime.now().isoformat()
            }
        
        return {
            'prompt': prompt,
            'responses': responses,
            'timestamp': datetime.now().isoformat()
        }
    
    def save_verification(self, result: Dict, session_id: str):
        """Save verification results"""
        filename = f"verification_{session_id}.json"
        filepath = os.path.join(os.path.expanduser("~"), ".nubem_verifications", filename)
        
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        print(f"\n{Fore.GREEN}💾 Verificación guardada en: {filepath}{Style.RESET_ALL}")


def main():
    """Test the multi-LLM verifier"""
    verifier = MultiLLMVerifier()
    
    # Check available models
    available = verifier.check_available_models()
    print(f"Modelos disponibles: {sum(available.values())}/{len(available)}")
    
    # Select models
    selected = verifier.display_model_selection()
    
    if not selected:
        print(f"{Fore.RED}No se seleccionaron modelos{Style.RESET_ALL}")
        return
    
    print(f"\n{Fore.GREEN}Modelos seleccionados: {', '.join(selected)}{Style.RESET_ALL}")
    
    # Test query
    test_prompt = "Explica en 2 líneas qué es Python"
    
    # Run verification
    result = asyncio.run(verifier.run_verification(test_prompt, selected))
    
    # Save results
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    verifier.save_verification(result, session_id)


if __name__ == "__main__":
    main()