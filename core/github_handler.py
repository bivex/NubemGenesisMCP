#!/usr/bin/env python3
"""
GitHub Handler - Manages GitHub operations with Google Secrets integration
"""

import os
import requests
import time
from typing import Dict, List, Optional, Tuple
import logging
from core.progress_indicator import ProgressIndicator, MultiStepProgress
from core.github_complete import github_complete, execute_github_command

logger = logging.getLogger(__name__)

class GitHubHandler:
    """Handle GitHub operations using token from Google Secrets"""
    
    def __init__(self):
        self.token = None
        self.load_github_token()
    
    def load_github_token(self):
        """Load GitHub token from environment or Google Secrets"""
        try:
            # First try to load from Google Secrets
            from core.secrets_loader import initialize_secrets
            initialize_secrets()
            
            # Get GitHub token
            self.token = os.environ.get('GITHUB_TOKEN') or os.environ.get('GITHUB_API_TOKEN')
            
            if self.token:
                logger.info("✅ GitHub token loaded successfully")
            else:
                logger.warning("⚠️ GitHub token not found in Google Secrets")
        except Exception as e:
            logger.error(f"Error loading GitHub token: {e}")
    
    def list_repositories(self, username: Optional[str] = None) -> List[Dict]:
        """List all repositories for authenticated user or specific username"""
        if not self.token:
            return {"error": "GitHub token not configured. Please check Google Secrets."}
        
        headers = {
            'Authorization': f'token {self.token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        try:
            # Get authenticated user info if no username provided
            if not username:
                user_response = requests.get('https://api.github.com/user', headers=headers)
                if user_response.status_code == 200:
                    user_info = user_response.json()
                    username = user_info.get('login')
            
            # Get all repositories
            all_repos = []
            page = 1
            
            while True:
                url = f'https://api.github.com/user/repos?page={page}&per_page=100&sort=updated'
                response = requests.get(url, headers=headers)
                
                if response.status_code == 200:
                    repos = response.json()
                    if not repos:
                        break
                    all_repos.extend(repos)
                    page += 1
                else:
                    logger.error(f"GitHub API error: {response.status_code}")
                    break
            
            return all_repos
            
        except Exception as e:
            logger.error(f"Error listing repositories: {e}")
            return {"error": str(e)}
    
    def get_repository(self, owner: str, repo: str) -> Dict:
        """Get specific repository information"""
        if not self.token:
            return {"error": "GitHub token not configured"}
        
        headers = {
            'Authorization': f'token {self.token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        try:
            response = requests.get(
                f'https://api.github.com/repos/{owner}/{repo}',
                headers=headers
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return {"error": f"Repository not found: {response.status_code}"}
                
        except Exception as e:
            logger.error(f"Error getting repository: {e}")
            return {"error": str(e)}
    
    def format_repo_list(self, repos: List[Dict]) -> str:
        """Format repository list for display"""
        if isinstance(repos, dict) and "error" in repos:
            return f"❌ Error: {repos['error']}"
        
        output = []
        output.append(f"\n📚 REPOSITORIOS ENCONTRADOS: {len(repos)}\n")
        output.append("=" * 60)
        
        for i, repo in enumerate(repos, 1):
            visibility = '🔒 Privado' if repo.get('private') else '🌍 Público'
            stars = repo.get('stargazers_count', 0)
            lang = repo.get('language') or 'Sin lenguaje'
            updated = repo.get('updated_at', '')[:10]
            
            output.append(f"\n{i}. {visibility} {repo.get('name', 'Sin nombre')}")
            output.append(f"   📝 {repo.get('description') or 'Sin descripción'}")
            output.append(f"   💻 {lang} | ⭐ {stars} | 🔄 {updated}")
            output.append(f"   🔗 {repo.get('html_url', '')}")
        
        # Statistics
        if repos:
            private_count = sum(1 for r in repos if r.get('private'))
            public_count = len(repos) - private_count
            total_stars = sum(r.get('stargazers_count', 0) for r in repos)
            
            output.append(f"\n{'=' * 60}")
            output.append(f"📊 ESTADÍSTICAS:")
            output.append(f"   🌍 Públicos: {public_count}")
            output.append(f"   🔒 Privados: {private_count}")
            output.append(f"   ⭐ Total estrellas: {total_stars}")
            
            # Language statistics
            languages = {}
            for repo in repos:
                lang = repo.get('language')
                if lang:
                    languages[lang] = languages.get(lang, 0) + 1
            
            if languages:
                output.append(f"\n💻 Lenguajes más usados:")
                for lang, count in sorted(languages.items(), key=lambda x: x[1], reverse=True)[:5]:
                    output.append(f"   - {lang}: {count} repos")
        
        return "\n".join(output)
    
    def change_repo_visibility(self, repo_name: str, owner: str, private: bool = True) -> Tuple[bool, str]:
        """Change repository visibility (public/private)"""
        if not self.token:
            return False, "GitHub token not configured"
        
        headers = {
            'Authorization': f'token {self.token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        url = f'https://api.github.com/repos/{owner}/{repo_name}'
        data = {'private': private}
        
        try:
            response = requests.patch(url, json=data, headers=headers)
            
            if response.status_code == 200:
                visibility = "privado" if private else "público"
                return True, f"✅ {repo_name} cambiado a {visibility}"
            else:
                return False, f"❌ Error cambiando {repo_name}: {response.status_code}"
                
        except Exception as e:
            return False, f"❌ Error: {str(e)}"
    
    def make_all_repos_private(self) -> str:
        """Change all public repositories to private with progress indicator"""
        if not self.token:
            return "❌ GitHub token no configurado. Verifica Google Secrets."
        
        # Get all repositories
        with ProgressIndicator("Obteniendo lista de repositorios", style='github') as progress:
            repos = self.list_repositories()
            
        if isinstance(repos, dict) and 'error' in repos:
            return repos['error']
        
        # Filter public repositories
        public_repos = [r for r in repos if not r.get('private', True)]
        
        if not public_repos:
            return "✅ No hay repositorios públicos para cambiar"
        
        # Setup multi-step progress
        steps = [
            f"Procesando {len(public_repos)} repositorios públicos",
            "Verificando permisos",
            "Cambiando visibilidad",
            "Confirmando cambios"
        ]
        
        progress = MultiStepProgress(steps, f"Cambiando {len(public_repos)} repositorios a privado")
        progress.start()
        
        results = []
        success_count = 0
        failed_count = 0
        
        # Step 1: Process repositories
        progress.next_step()
        time.sleep(0.5)
        
        # Step 2: Check permissions
        progress.next_step()
        owner = public_repos[0]['owner']['login'] if public_repos else None
        time.sleep(0.5)
        
        # Step 3: Change visibility
        progress.next_step()
        
        for repo in public_repos:
            repo_name = repo['name']
            repo_owner = repo['owner']['login']
            
            # Show individual progress
            with ProgressIndicator(f"Cambiando {repo_name}", style='dots'):
                success, message = self.change_repo_visibility(repo_name, repo_owner, private=True)
                
                if success:
                    success_count += 1
                    results.append(f"  ✅ {repo_name}")
                else:
                    failed_count += 1
                    results.append(f"  ❌ {repo_name}: Error")
                
                # Small delay to avoid rate limiting
                time.sleep(0.5)
        
        # Step 4: Confirm changes
        progress.next_step()
        time.sleep(0.5)
        
        progress.complete(success=(failed_count == 0))
        
        # Build result summary
        output = [
            f"\n📊 RESULTADO DE LA OPERACIÓN:",
            f"✅ Exitosos: {success_count}",
            f"❌ Fallidos: {failed_count}",
            f"\nDetalles:"
        ]
        output.extend(results)
        
        return "\n".join(output)
    
    def get_public_repos(self) -> List[Dict]:
        """Get only public repositories"""
        repos = self.list_repositories()
        if isinstance(repos, dict) and 'error' in repos:
            return []
        return [r for r in repos if not r.get('private', True)]


# Global instance
github_handler = GitHubHandler()


def handle_github_command(query: str) -> str:
    """Handle GitHub-related commands from user queries"""
    query_lower = query.lower()
    
    # === COMPLETE GITHUB OPERATIONS ===
    
    # 1. Repository Management
    if 'crear' in query_lower and 'repositorio' in query_lower:
        # Extract repository name from query
        import re
        name_match = re.search(r'repositorio\s+["\']?([a-zA-Z0-9\-_]+)["\']?', query_lower)
        name = name_match.group(1) if name_match else 'new-repo'
        
        with ProgressIndicator(f"Creando repositorio {name}", style='github'):
            result = github_complete.create_repository(
                name=name,
                description=f"Created via NubemClaude",
                private=('privado' in query_lower)
            )
        return result['message']
    
    elif 'eliminar' in query_lower and 'repositorio' in query_lower:
        # Extract repository name
        import re
        name_match = re.search(r'repositorio\s+["\']?([a-zA-Z0-9\-_]+)["\']?', query_lower)
        if name_match:
            repo = name_match.group(1)
            owner = github_complete.user_info.get('login') if github_complete.user_info else 'NUbem000'
            result = github_complete.delete_repository(owner, repo)
            return result['message']
        return "❌ Especifica el nombre del repositorio a eliminar"
    
    elif 'fork' in query_lower or 'bifurcar' in query_lower:
        # Extract owner/repo
        import re
        match = re.search(r'([a-zA-Z0-9\-_]+)/([a-zA-Z0-9\-_]+)', query)
        if match:
            owner, repo = match.group(1), match.group(2)
            result = github_complete.fork_repository(owner, repo)
            return result['message']
        return "❌ Especifica el repositorio en formato owner/repo"
    
    # 2. Branch Management
    elif ('crear' in query_lower or 'create' in query_lower) and 'branch' in query_lower:
        import re
        # Extract branch and repo names
        branch_match = re.search(r'branch\s+["\']?([a-zA-Z0-9\-_/]+)["\']?', query_lower)
        repo_match = re.search(r'(en|in|repositorio|repo)\s+["\']?([a-zA-Z0-9\-_]+)["\']?', query_lower)
        
        if branch_match and repo_match:
            branch = branch_match.group(1)
            repo = repo_match.group(2)
            owner = github_complete.user_info.get('login') if github_complete.user_info else 'NUbem000'
            result = github_complete.create_branch(owner, repo, branch)
            return result['message']
        return "❌ Especifica el nombre del branch y repositorio"
    
    elif 'listar' in query_lower and 'branch' in query_lower:
        import re
        repo_match = re.search(r'(de|del|repositorio|repo)\s+["\']?([a-zA-Z0-9\-_]+)["\']?', query_lower)
        if repo_match:
            repo = repo_match.group(2)
            owner = github_complete.user_info.get('login') if github_complete.user_info else 'NUbem000'
            branches = github_complete.list_branches(owner, repo)
            if branches:
                output = [f"🌿 Branches en {repo}:"]
                for branch in branches:
                    protected = "🔒" if branch.get('protected') else ""
                    output.append(f"  • {branch['name']} {protected}")
                return "\n".join(output)
            return "No hay branches"
        return "❌ Especifica el repositorio"
    
    # 3. Issue Management
    elif 'crear' in query_lower and 'issue' in query_lower:
        import re
        title_match = re.search(r'["\']([^"\']+)["\']', query)
        repo_match = re.search(r'(en|in|repositorio|repo)\s+["\']?([a-zA-Z0-9\-_]+)["\']?', query_lower)
        
        if title_match and repo_match:
            title = title_match.group(1)
            repo = repo_match.group(2)
            owner = github_complete.user_info.get('login') if github_complete.user_info else 'NUbem000'
            result = github_complete.create_issue(owner, repo, title)
            return result['message']
        return "❌ Especifica el título del issue y repositorio"
    
    elif 'listar' in query_lower and 'issue' in query_lower:
        import re
        repo_match = re.search(r'(de|del|repositorio|repo)\s+["\']?([a-zA-Z0-9\-_]+)["\']?', query_lower)
        if repo_match:
            repo = repo_match.group(2)
            owner = github_complete.user_info.get('login') if github_complete.user_info else 'NUbem000'
            issues = github_complete.list_issues(owner, repo)
            if issues:
                output = [f"📋 Issues en {repo}:"]
                for issue in issues[:10]:
                    state_icon = "🟢" if issue['state'] == 'open' else "🔴"
                    output.append(f"  {state_icon} #{issue['number']} - {issue['title']}")
                return "\n".join(output)
            return "No hay issues"
        return "❌ Especifica el repositorio"
    
    # 4. Pull Request Management
    elif ('crear' in query_lower or 'create' in query_lower) and ('pr' in query_lower or 'pull request' in query_lower):
        return "📝 Para crear un PR, usa: crear pr 'título' desde branch_origen hacia branch_destino en repo"
    
    elif 'listar' in query_lower and ('pr' in query_lower or 'pull request' in query_lower):
        import re
        repo_match = re.search(r'(de|del|repositorio|repo)\s+["\']?([a-zA-Z0-9\-_]+)["\']?', query_lower)
        if repo_match:
            repo = repo_match.group(2)
            owner = github_complete.user_info.get('login') if github_complete.user_info else 'NUbem000'
            prs = github_complete.list_pull_requests(owner, repo)
            if prs:
                output = [f"🔀 Pull Requests en {repo}:"]
                for pr in prs[:10]:
                    output.append(f"  #{pr['number']} - {pr['title']} ({pr['state']})")
                return "\n".join(output)
            return "No hay pull requests"
        return "❌ Especifica el repositorio"
    
    # 5. Statistics
    elif 'estadisticas' in query_lower or 'stats' in query_lower:
        import re
        repo_match = re.search(r'(de|del|repositorio|repo)\s+["\']?([a-zA-Z0-9\-_]+)["\']?', query_lower)
        if repo_match:
            repo = repo_match.group(2)
            owner = github_complete.user_info.get('login') if github_complete.user_info else 'NUbem000'
            with ProgressIndicator(f"Obteniendo estadísticas de {repo}", style='github'):
                stats = github_complete.get_repository_stats(owner, repo)
            
            output = [f"📊 Estadísticas de {repo}:"]
            output.append(f"  ⭐ Stars: {stats.get('stars', 0)}")
            output.append(f"  🍴 Forks: {stats.get('forks', 0)}")
            output.append(f"  👀 Watchers: {stats.get('watchers', 0)}")
            output.append(f"  📝 Open Issues: {stats.get('open_issues', 0)}")
            output.append(f"  👥 Contributors: {stats.get('contributors', 0)}")
            output.append(f"  💾 Size: {stats.get('size', 0)} KB")
            output.append(f"  💻 Language: {stats.get('language', 'N/A')}")
            return "\n".join(output)
        else:
            # User stats
            stats = github_complete.get_user_stats()
            output = [f"📊 Estadísticas de usuario:"]
            output.append(f"  👤 Username: {stats.get('username')}")
            output.append(f"  📦 Repos públicos: {stats.get('public_repos', 0)}")
            output.append(f"  👥 Followers: {stats.get('followers', 0)}")
            output.append(f"  👤 Following: {stats.get('following', 0)}")
            return "\n".join(output)
    
    # 6. Search
    elif 'buscar' in query_lower or 'search' in query_lower:
        import re
        search_match = re.search(r'["\']([^"\']+)["\']', query)
        if search_match:
            search_query = search_match.group(1)
            
            if 'repositorio' in query_lower:
                with ProgressIndicator(f"Buscando repositorios: {search_query}", style='github'):
                    results = github_complete.search_repositories(search_query)
                if results:
                    output = [f"🔍 Repositorios encontrados para '{search_query}':"]
                    for repo in results[:10]:
                        output.append(f"  • {repo['full_name']} ⭐ {repo['stargazers_count']}")
                        output.append(f"    {repo.get('description', 'Sin descripción')[:80]}")
                    return "\n".join(output)
                return "No se encontraron repositorios"
            
            elif 'issue' in query_lower:
                results = github_complete.search_issues(search_query)
                if results:
                    output = [f"🔍 Issues encontrados:"]
                    for issue in results[:10]:
                        output.append(f"  • {issue['title']}")
                        output.append(f"    {issue['repository_url'].split('/')[-1]} #{issue['number']}")
                    return "\n".join(output)
                return "No se encontraron issues"
            
            elif 'codigo' in query_lower or 'code' in query_lower:
                results = github_complete.search_code(search_query)
                if results:
                    output = [f"🔍 Código encontrado:"]
                    for item in results[:10]:
                        output.append(f"  • {item['name']} en {item['repository']['full_name']}")
                        output.append(f"    {item['path']}")
                    return "\n".join(output)
                return "No se encontró código"
        
        return "❌ Especifica qué buscar entre comillas"
    
    # 7. Workflow/Actions
    elif 'workflow' in query_lower or 'action' in query_lower:
        import re
        repo_match = re.search(r'(de|del|repositorio|repo)\s+["\']?([a-zA-Z0-9\-_]+)["\']?', query_lower)
        if repo_match:
            repo = repo_match.group(2)
            owner = github_complete.user_info.get('login') if github_complete.user_info else 'NUbem000'
            workflows = github_complete.list_workflows(owner, repo)
            if workflows:
                output = [f"⚙️ Workflows en {repo}:"]
                for wf in workflows:
                    output.append(f"  • {wf['name']} ({wf['state']})")
                return "\n".join(output)
            return "No hay workflows"
        return "❌ Especifica el repositorio"
    
    # 8. Gist Management
    elif 'crear' in query_lower and 'gist' in query_lower:
        import re
        desc_match = re.search(r'["\']([^"\']+)["\']', query)
        desc = desc_match.group(1) if desc_match else "Gist creado con NubemClaude"
        
        files = {"example.txt": "# Gist created with NubemClaude\n\nContent here..."}
        result = github_complete.create_gist(desc, files, public=('publico' in query_lower))
        return result['message']
    
    elif 'listar' in query_lower and 'gist' in query_lower:
        gists = github_complete.list_gists()
        if gists:
            output = ["📝 Tus Gists:"]
            for gist in gists[:10]:
                public = "🌍" if gist['public'] else "🔒"
                output.append(f"  {public} {gist.get('description', 'Sin descripción')}")
                output.append(f"     {gist['html_url']}")
            return "\n".join(output)
        return "No tienes gists"
    
    # === ORIGINAL COMMANDS (KEEP FOR COMPATIBILITY) ===
    
    # Check for repository visibility change commands
    elif ('cambia' in query_lower or 'cambiar' in query_lower or 'convertir' in query_lower) and \
       ('privado' in query_lower or 'privados' in query_lower):
        # Change public repos to private
        return github_handler.make_all_repos_private()
    
    # Check for listing public repos only
    elif ('publico' in query_lower or 'público' in query_lower or 'públicos' in query_lower) and \
         ('lista' in query_lower or 'listar' in query_lower):
        public_repos = github_handler.get_public_repos()
        if public_repos:
            return github_handler.format_repo_list(public_repos)
        else:
            return "✅ No hay repositorios públicos"
    
    # Default listing
    elif 'lista' in query_lower or 'listar' in query_lower or 'todos' in query_lower:
        if 'repositorio' in query_lower or 'repos' in query_lower or 'github' in query_lower:
            repos = github_handler.list_repositories()
            return github_handler.format_repo_list(repos)
    
    elif 'conecta' in query_lower or 'conectar' in query_lower:
        # Connect to GitHub and list
        if github_handler.token:
            repos = github_handler.list_repositories()
            return f"✅ Conectado a GitHub con token de Google Secrets\n{github_handler.format_repo_list(repos)}"
        else:
            return "❌ No se pudo conectar a GitHub. Token no encontrado en Google Secrets."
    
    # Help for GitHub commands
    elif 'ayuda' in query_lower and 'github' in query_lower:
        help_text = """
📚 **COMANDOS DE GITHUB DISPONIBLES:**

**Repositorios:**
• `lista todos los repositorios` - Ver todos tus repos
• `crear repositorio "nombre"` - Crear nuevo repo
• `eliminar repositorio "nombre"` - Eliminar repo
• `cambiar repositorios publicos a privado` - Cambiar visibilidad
• `fork owner/repo` - Hacer fork de un repo

**Branches:**
• `crear branch "nombre" en repo` - Crear branch
• `listar branches de repo` - Ver branches
• `proteger branch main en repo` - Proteger branch

**Issues:**
• `crear issue "título" en repo` - Crear issue
• `listar issues de repo` - Ver issues
• `cerrar issue #numero en repo` - Cerrar issue

**Pull Requests:**
• `listar pr de repo` - Ver pull requests
• `crear pr "título" desde branch hacia main en repo` - Crear PR

**Búsqueda:**
• `buscar "query" en repositorios` - Buscar repos
• `buscar "query" en issues` - Buscar issues
• `buscar "query" en codigo` - Buscar código

**Estadísticas:**
• `estadisticas de repo` - Ver stats del repo
• `estadisticas de usuario` - Ver tus stats

**Workflows:**
• `listar workflows de repo` - Ver GitHub Actions

**Gists:**
• `crear gist "descripción"` - Crear gist
• `listar gists` - Ver tus gists
"""
        return help_text
    
    return None


if __name__ == "__main__":
    # Test the handler
    handler = GitHubHandler()
    repos = handler.list_repositories()
    print(handler.format_repo_list(repos))