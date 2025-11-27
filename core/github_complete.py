#!/usr/bin/env python3
"""
GitHub Complete Handler - Full GitHub API functionality
"""

import os
import requests
import json
import base64
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import logging
from core.progress_indicator import ProgressIndicator, MultiStepProgress

logger = logging.getLogger(__name__)

class GitHubComplete:
    """Complete GitHub API handler with all functionalities"""
    
    def __init__(self):
        self.token = None
        self.base_url = "https://api.github.com"
        self.load_github_token()
        self.user_info = None
        
    def load_github_token(self):
        """Load GitHub token from environment or Google Secrets"""
        try:
            from core.secrets_loader import initialize_secrets
            initialize_secrets()
            
            self.token = os.environ.get('GITHUB_TOKEN') or os.environ.get('GITHUB_API_TOKEN')
            
            if self.token:
                logger.info("✅ GitHub token loaded successfully")
                self._get_user_info()
            else:
                logger.warning("⚠️ GitHub token not found")
        except Exception as e:
            logger.error(f"Error loading GitHub token: {e}")
    
    def _get_user_info(self):
        """Get authenticated user information"""
        try:
            response = self._make_request("GET", "/user")
            if response and response.status_code == 200:
                self.user_info = response.json()
                logger.info(f"✅ Authenticated as: {self.user_info.get('login')}")
        except Exception as e:
            logger.error(f"Error getting user info: {e}")
    
    def _make_request(self, method: str, endpoint: str, data: Dict = None, params: Dict = None):
        """Make authenticated request to GitHub API"""
        if not self.token:
            return None
            
        headers = {
            'Authorization': f'token {self.token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        url = f"{self.base_url}{endpoint}" if endpoint.startswith('/') else endpoint
        
        try:
            if method == "GET":
                return requests.get(url, headers=headers, params=params)
            elif method == "POST":
                return requests.post(url, headers=headers, json=data)
            elif method == "PATCH":
                return requests.patch(url, headers=headers, json=data)
            elif method == "PUT":
                return requests.put(url, headers=headers, json=data)
            elif method == "DELETE":
                return requests.delete(url, headers=headers)
        except Exception as e:
            logger.error(f"Request error: {e}")
            return None
    
    # ============= REPOSITORY MANAGEMENT =============
    
    def create_repository(self, name: str, description: str = "", private: bool = True, 
                         auto_init: bool = True, gitignore_template: str = "Python") -> Dict:
        """Create a new repository"""
        with ProgressIndicator(f"Creating repository {name}", style='github'):
            data = {
                "name": name,
                "description": description,
                "private": private,
                "auto_init": auto_init,
                "gitignore_template": gitignore_template
            }
            
            response = self._make_request("POST", "/user/repos", data)
            
            if response and response.status_code == 201:
                repo = response.json()
                return {
                    "success": True,
                    "message": f"✅ Repository '{name}' created successfully",
                    "url": repo.get('html_url'),
                    "clone_url": repo.get('clone_url')
                }
            else:
                return {
                    "success": False,
                    "message": f"❌ Failed to create repository: {response.status_code if response else 'No response'}"
                }
    
    def delete_repository(self, owner: str, repo: str) -> Dict:
        """Delete a repository"""
        with ProgressIndicator(f"Deleting repository {repo}", style='github'):
            response = self._make_request("DELETE", f"/repos/{owner}/{repo}")
            
            if response and response.status_code == 204:
                return {
                    "success": True,
                    "message": f"✅ Repository '{repo}' deleted successfully"
                }
            else:
                return {
                    "success": False,
                    "message": f"❌ Failed to delete repository: {response.status_code if response else 'No response'}"
                }
    
    def fork_repository(self, owner: str, repo: str, organization: str = None) -> Dict:
        """Fork a repository"""
        with ProgressIndicator(f"Forking {owner}/{repo}", style='github'):
            data = {"organization": organization} if organization else {}
            response = self._make_request("POST", f"/repos/{owner}/{repo}/forks", data)
            
            if response and response.status_code in [202, 201]:
                fork = response.json()
                return {
                    "success": True,
                    "message": f"✅ Repository forked successfully",
                    "url": fork.get('html_url')
                }
            else:
                return {
                    "success": False,
                    "message": f"❌ Failed to fork repository"
                }
    
    def update_repository(self, owner: str, repo: str, **kwargs) -> Dict:
        """Update repository settings (name, description, private, etc.)"""
        with ProgressIndicator(f"Updating repository {repo}", style='github'):
            response = self._make_request("PATCH", f"/repos/{owner}/{repo}", kwargs)
            
            if response and response.status_code == 200:
                return {
                    "success": True,
                    "message": f"✅ Repository updated successfully"
                }
            else:
                return {
                    "success": False,
                    "message": f"❌ Failed to update repository"
                }
    
    # ============= BRANCH MANAGEMENT =============
    
    def list_branches(self, owner: str, repo: str) -> List[Dict]:
        """List all branches in a repository"""
        response = self._make_request("GET", f"/repos/{owner}/{repo}/branches")
        if response and response.status_code == 200:
            return response.json()
        return []
    
    def create_branch(self, owner: str, repo: str, branch_name: str, from_branch: str = "main") -> Dict:
        """Create a new branch"""
        with ProgressIndicator(f"Creating branch {branch_name}", style='github'):
            # Get the SHA of the source branch
            ref_response = self._make_request("GET", f"/repos/{owner}/{repo}/git/refs/heads/{from_branch}")
            
            if not ref_response or ref_response.status_code != 200:
                return {"success": False, "message": f"❌ Source branch '{from_branch}' not found"}
            
            sha = ref_response.json()['object']['sha']
            
            # Create new branch
            data = {
                "ref": f"refs/heads/{branch_name}",
                "sha": sha
            }
            
            response = self._make_request("POST", f"/repos/{owner}/{repo}/git/refs", data)
            
            if response and response.status_code == 201:
                return {
                    "success": True,
                    "message": f"✅ Branch '{branch_name}' created successfully"
                }
            else:
                return {
                    "success": False,
                    "message": f"❌ Failed to create branch"
                }
    
    def delete_branch(self, owner: str, repo: str, branch_name: str) -> Dict:
        """Delete a branch"""
        with ProgressIndicator(f"Deleting branch {branch_name}", style='github'):
            response = self._make_request("DELETE", f"/repos/{owner}/{repo}/git/refs/heads/{branch_name}")
            
            if response and response.status_code == 204:
                return {
                    "success": True,
                    "message": f"✅ Branch '{branch_name}' deleted successfully"
                }
            else:
                return {
                    "success": False,
                    "message": f"❌ Failed to delete branch"
                }
    
    def protect_branch(self, owner: str, repo: str, branch: str, require_reviews: int = 1) -> Dict:
        """Enable branch protection"""
        data = {
            "required_status_checks": None,
            "enforce_admins": True,
            "required_pull_request_reviews": {
                "required_approving_review_count": require_reviews,
                "dismiss_stale_reviews": True
            },
            "restrictions": None
        }
        
        response = self._make_request("PUT", f"/repos/{owner}/{repo}/branches/{branch}/protection", data)
        
        if response and response.status_code == 200:
            return {
                "success": True,
                "message": f"✅ Branch protection enabled for '{branch}'"
            }
        else:
            return {
                "success": False,
                "message": f"❌ Failed to protect branch"
            }
    
    # ============= ISSUE MANAGEMENT =============
    
    def create_issue(self, owner: str, repo: str, title: str, body: str = "", 
                    labels: List[str] = None, assignees: List[str] = None) -> Dict:
        """Create a new issue"""
        with ProgressIndicator(f"Creating issue: {title[:30]}...", style='github'):
            data = {
                "title": title,
                "body": body,
                "labels": labels or [],
                "assignees": assignees or []
            }
            
            response = self._make_request("POST", f"/repos/{owner}/{repo}/issues", data)
            
            if response and response.status_code == 201:
                issue = response.json()
                return {
                    "success": True,
                    "message": f"✅ Issue #{issue['number']} created",
                    "url": issue['html_url'],
                    "number": issue['number']
                }
            else:
                return {
                    "success": False,
                    "message": f"❌ Failed to create issue"
                }
    
    def list_issues(self, owner: str, repo: str, state: str = "open", 
                   labels: str = None, per_page: int = 30) -> List[Dict]:
        """List repository issues"""
        params = {
            "state": state,
            "per_page": per_page
        }
        if labels:
            params["labels"] = labels
            
        response = self._make_request("GET", f"/repos/{owner}/{repo}/issues", params=params)
        
        if response and response.status_code == 200:
            return response.json()
        return []
    
    def close_issue(self, owner: str, repo: str, issue_number: int) -> Dict:
        """Close an issue"""
        data = {"state": "closed"}
        response = self._make_request("PATCH", f"/repos/{owner}/{repo}/issues/{issue_number}", data)
        
        if response and response.status_code == 200:
            return {
                "success": True,
                "message": f"✅ Issue #{issue_number} closed"
            }
        else:
            return {
                "success": False,
                "message": f"❌ Failed to close issue"
            }
    
    def comment_issue(self, owner: str, repo: str, issue_number: int, comment: str) -> Dict:
        """Add comment to an issue"""
        data = {"body": comment}
        response = self._make_request("POST", f"/repos/{owner}/{repo}/issues/{issue_number}/comments", data)
        
        if response and response.status_code == 201:
            return {
                "success": True,
                "message": f"✅ Comment added to issue #{issue_number}"
            }
        else:
            return {
                "success": False,
                "message": f"❌ Failed to add comment"
            }
    
    # ============= PULL REQUEST MANAGEMENT =============
    
    def create_pull_request(self, owner: str, repo: str, title: str, head: str, 
                          base: str = "main", body: str = "") -> Dict:
        """Create a pull request"""
        with ProgressIndicator(f"Creating PR: {title[:30]}...", style='github'):
            data = {
                "title": title,
                "head": head,
                "base": base,
                "body": body
            }
            
            response = self._make_request("POST", f"/repos/{owner}/{repo}/pulls", data)
            
            if response and response.status_code == 201:
                pr = response.json()
                return {
                    "success": True,
                    "message": f"✅ Pull Request #{pr['number']} created",
                    "url": pr['html_url'],
                    "number": pr['number']
                }
            else:
                return {
                    "success": False,
                    "message": f"❌ Failed to create pull request"
                }
    
    def list_pull_requests(self, owner: str, repo: str, state: str = "open") -> List[Dict]:
        """List pull requests"""
        params = {"state": state}
        response = self._make_request("GET", f"/repos/{owner}/{repo}/pulls", params=params)
        
        if response and response.status_code == 200:
            return response.json()
        return []
    
    def merge_pull_request(self, owner: str, repo: str, pr_number: int, 
                          commit_message: str = None) -> Dict:
        """Merge a pull request"""
        data = {}
        if commit_message:
            data["commit_message"] = commit_message
            
        response = self._make_request("PUT", f"/repos/{owner}/{repo}/pulls/{pr_number}/merge", data)
        
        if response and response.status_code == 200:
            return {
                "success": True,
                "message": f"✅ Pull Request #{pr_number} merged"
            }
        else:
            return {
                "success": False,
                "message": f"❌ Failed to merge pull request"
            }
    
    # ============= FILE OPERATIONS =============
    
    def get_file_content(self, owner: str, repo: str, path: str, branch: str = "main") -> Dict:
        """Get file content from repository"""
        params = {"ref": branch}
        response = self._make_request("GET", f"/repos/{owner}/{repo}/contents/{path}", params=params)
        
        if response and response.status_code == 200:
            data = response.json()
            content = base64.b64decode(data['content']).decode('utf-8') if 'content' in data else None
            return {
                "success": True,
                "content": content,
                "sha": data.get('sha'),
                "size": data.get('size')
            }
        else:
            return {
                "success": False,
                "message": f"❌ File not found"
            }
    
    def create_or_update_file(self, owner: str, repo: str, path: str, content: str, 
                             message: str, branch: str = "main", sha: str = None) -> Dict:
        """Create or update a file in repository"""
        with ProgressIndicator(f"Updating file: {path}", style='github'):
            encoded_content = base64.b64encode(content.encode()).decode()
            
            data = {
                "message": message,
                "content": encoded_content,
                "branch": branch
            }
            
            if sha:
                data["sha"] = sha
            
            response = self._make_request("PUT", f"/repos/{owner}/{repo}/contents/{path}", data)
            
            if response and response.status_code in [200, 201]:
                return {
                    "success": True,
                    "message": f"✅ File '{path}' updated successfully"
                }
            else:
                return {
                    "success": False,
                    "message": f"❌ Failed to update file"
                }
    
    def delete_file(self, owner: str, repo: str, path: str, message: str, 
                   sha: str, branch: str = "main") -> Dict:
        """Delete a file from repository"""
        data = {
            "message": message,
            "sha": sha,
            "branch": branch
        }
        
        response = self._make_request("DELETE", f"/repos/{owner}/{repo}/contents/{path}", data)
        
        if response and response.status_code == 200:
            return {
                "success": True,
                "message": f"✅ File '{path}' deleted successfully"
            }
        else:
            return {
                "success": False,
                "message": f"❌ Failed to delete file"
            }
    
    # ============= COLLABORATOR MANAGEMENT =============
    
    def add_collaborator(self, owner: str, repo: str, username: str, 
                        permission: str = "push") -> Dict:
        """Add collaborator to repository"""
        data = {"permission": permission}
        response = self._make_request("PUT", f"/repos/{owner}/{repo}/collaborators/{username}", data)
        
        if response and response.status_code in [201, 204]:
            return {
                "success": True,
                "message": f"✅ User '{username}' added as collaborator"
            }
        else:
            return {
                "success": False,
                "message": f"❌ Failed to add collaborator"
            }
    
    def remove_collaborator(self, owner: str, repo: str, username: str) -> Dict:
        """Remove collaborator from repository"""
        response = self._make_request("DELETE", f"/repos/{owner}/{repo}/collaborators/{username}")
        
        if response and response.status_code == 204:
            return {
                "success": True,
                "message": f"✅ User '{username}' removed from collaborators"
            }
        else:
            return {
                "success": False,
                "message": f"❌ Failed to remove collaborator"
            }
    
    def list_collaborators(self, owner: str, repo: str) -> List[Dict]:
        """List repository collaborators"""
        response = self._make_request("GET", f"/repos/{owner}/{repo}/collaborators")
        
        if response and response.status_code == 200:
            return response.json()
        return []
    
    # ============= RELEASE MANAGEMENT =============
    
    def create_release(self, owner: str, repo: str, tag: str, name: str, 
                      body: str = "", draft: bool = False, prerelease: bool = False) -> Dict:
        """Create a new release"""
        with ProgressIndicator(f"Creating release {tag}", style='github'):
            data = {
                "tag_name": tag,
                "name": name,
                "body": body,
                "draft": draft,
                "prerelease": prerelease
            }
            
            response = self._make_request("POST", f"/repos/{owner}/{repo}/releases", data)
            
            if response and response.status_code == 201:
                release = response.json()
                return {
                    "success": True,
                    "message": f"✅ Release '{name}' created",
                    "url": release['html_url']
                }
            else:
                return {
                    "success": False,
                    "message": f"❌ Failed to create release"
                }
    
    def list_releases(self, owner: str, repo: str) -> List[Dict]:
        """List repository releases"""
        response = self._make_request("GET", f"/repos/{owner}/{repo}/releases")
        
        if response and response.status_code == 200:
            return response.json()
        return []
    
    # ============= WORKFLOW/ACTIONS MANAGEMENT =============
    
    def list_workflows(self, owner: str, repo: str) -> List[Dict]:
        """List GitHub Actions workflows"""
        response = self._make_request("GET", f"/repos/{owner}/{repo}/actions/workflows")
        
        if response and response.status_code == 200:
            return response.json().get('workflows', [])
        return []
    
    def trigger_workflow(self, owner: str, repo: str, workflow_id: str, 
                        ref: str = "main", inputs: Dict = None) -> Dict:
        """Trigger a workflow run"""
        data = {
            "ref": ref,
            "inputs": inputs or {}
        }
        
        response = self._make_request("POST", 
                                     f"/repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches", 
                                     data)
        
        if response and response.status_code == 204:
            return {
                "success": True,
                "message": f"✅ Workflow triggered successfully"
            }
        else:
            return {
                "success": False,
                "message": f"❌ Failed to trigger workflow"
            }
    
    def list_workflow_runs(self, owner: str, repo: str, workflow_id: str = None) -> List[Dict]:
        """List workflow runs"""
        endpoint = f"/repos/{owner}/{repo}/actions/runs"
        if workflow_id:
            endpoint = f"/repos/{owner}/{repo}/actions/workflows/{workflow_id}/runs"
            
        response = self._make_request("GET", endpoint)
        
        if response and response.status_code == 200:
            return response.json().get('workflow_runs', [])
        return []
    
    # ============= GIST MANAGEMENT =============
    
    def create_gist(self, description: str, files: Dict[str, str], public: bool = False) -> Dict:
        """Create a new gist"""
        data = {
            "description": description,
            "public": public,
            "files": {name: {"content": content} for name, content in files.items()}
        }
        
        response = self._make_request("POST", "/gists", data)
        
        if response and response.status_code == 201:
            gist = response.json()
            return {
                "success": True,
                "message": f"✅ Gist created",
                "url": gist['html_url'],
                "id": gist['id']
            }
        else:
            return {
                "success": False,
                "message": f"❌ Failed to create gist"
            }
    
    def list_gists(self) -> List[Dict]:
        """List user's gists"""
        response = self._make_request("GET", "/gists")
        
        if response and response.status_code == 200:
            return response.json()
        return []
    
    # ============= TEAM MANAGEMENT =============
    
    def create_team(self, org: str, name: str, description: str = "", 
                   privacy: str = "closed") -> Dict:
        """Create a team in organization"""
        data = {
            "name": name,
            "description": description,
            "privacy": privacy
        }
        
        response = self._make_request("POST", f"/orgs/{org}/teams", data)
        
        if response and response.status_code == 201:
            return {
                "success": True,
                "message": f"✅ Team '{name}' created"
            }
        else:
            return {
                "success": False,
                "message": f"❌ Failed to create team"
            }
    
    def add_team_member(self, org: str, team_slug: str, username: str) -> Dict:
        """Add member to team"""
        response = self._make_request("PUT", f"/orgs/{org}/teams/{team_slug}/memberships/{username}")
        
        if response and response.status_code in [200, 201]:
            return {
                "success": True,
                "message": f"✅ User '{username}' added to team"
            }
        else:
            return {
                "success": False,
                "message": f"❌ Failed to add team member"
            }
    
    # ============= SEARCH FUNCTIONALITY =============
    
    def search_repositories(self, query: str, sort: str = "stars", order: str = "desc") -> List[Dict]:
        """Search for repositories"""
        params = {
            "q": query,
            "sort": sort,
            "order": order
        }
        
        response = self._make_request("GET", "/search/repositories", params=params)
        
        if response and response.status_code == 200:
            return response.json().get('items', [])
        return []
    
    def search_code(self, query: str, repo: str = None) -> List[Dict]:
        """Search for code"""
        if repo:
            query = f"{query} repo:{repo}"
            
        params = {"q": query}
        response = self._make_request("GET", "/search/code", params=params)
        
        if response and response.status_code == 200:
            return response.json().get('items', [])
        return []
    
    def search_issues(self, query: str, repo: str = None) -> List[Dict]:
        """Search for issues"""
        if repo:
            query = f"{query} repo:{repo}"
            
        params = {"q": query}
        response = self._make_request("GET", "/search/issues", params=params)
        
        if response and response.status_code == 200:
            return response.json().get('items', [])
        return []
    
    # ============= STATISTICS =============
    
    def get_repository_stats(self, owner: str, repo: str) -> Dict:
        """Get comprehensive repository statistics"""
        stats = {}
        
        # Get repository info
        repo_response = self._make_request("GET", f"/repos/{owner}/{repo}")
        if repo_response and repo_response.status_code == 200:
            repo_data = repo_response.json()
            stats['stars'] = repo_data.get('stargazers_count', 0)
            stats['forks'] = repo_data.get('forks_count', 0)
            stats['watchers'] = repo_data.get('watchers_count', 0)
            stats['open_issues'] = repo_data.get('open_issues_count', 0)
            stats['size'] = repo_data.get('size', 0)
            stats['language'] = repo_data.get('language')
        
        # Get contributors
        contrib_response = self._make_request("GET", f"/repos/{owner}/{repo}/contributors")
        if contrib_response and contrib_response.status_code == 200:
            stats['contributors'] = len(contrib_response.json())
        
        # Get commit activity
        activity_response = self._make_request("GET", f"/repos/{owner}/{repo}/stats/commit_activity")
        if activity_response and activity_response.status_code == 200:
            stats['commit_activity'] = activity_response.json()
        
        return stats
    
    def get_user_stats(self, username: str = None) -> Dict:
        """Get user statistics"""
        endpoint = "/user" if not username else f"/users/{username}"
        response = self._make_request("GET", endpoint)
        
        if response and response.status_code == 200:
            user_data = response.json()
            return {
                "username": user_data.get('login'),
                "name": user_data.get('name'),
                "public_repos": user_data.get('public_repos', 0),
                "followers": user_data.get('followers', 0),
                "following": user_data.get('following', 0),
                "created_at": user_data.get('created_at'),
                "bio": user_data.get('bio')
            }
        return {}


# Global instance
github_complete = GitHubComplete()


def execute_github_command(command: str, **kwargs) -> str:
    """Execute GitHub command based on natural language input"""
    command_lower = command.lower()
    
    # Repository operations
    if 'crear' in command_lower and 'repositorio' in command_lower:
        name = kwargs.get('name', 'new-repo')
        desc = kwargs.get('description', '')
        private = kwargs.get('private', True)
        result = github_complete.create_repository(name, desc, private)
        return result['message']
    
    elif 'eliminar' in command_lower and 'repositorio' in command_lower:
        owner = kwargs.get('owner', github_complete.user_info.get('login'))
        repo = kwargs.get('repo')
        if repo:
            result = github_complete.delete_repository(owner, repo)
            return result['message']
        return "❌ Especifica el repositorio a eliminar"
    
    # Branch operations
    elif 'crear' in command_lower and 'branch' in command_lower:
        owner = kwargs.get('owner', github_complete.user_info.get('login'))
        repo = kwargs.get('repo')
        branch = kwargs.get('branch')
        if repo and branch:
            result = github_complete.create_branch(owner, repo, branch)
            return result['message']
        return "❌ Especifica el repositorio y nombre del branch"
    
    # Issue operations
    elif 'crear' in command_lower and 'issue' in command_lower:
        owner = kwargs.get('owner', github_complete.user_info.get('login'))
        repo = kwargs.get('repo')
        title = kwargs.get('title')
        body = kwargs.get('body', '')
        if repo and title:
            result = github_complete.create_issue(owner, repo, title, body)
            return result['message']
        return "❌ Especifica el repositorio y título del issue"
    
    elif 'listar' in command_lower and 'issue' in command_lower:
        owner = kwargs.get('owner', github_complete.user_info.get('login'))
        repo = kwargs.get('repo')
        if repo:
            issues = github_complete.list_issues(owner, repo)
            if issues:
                output = [f"📋 Issues en {repo}:"]
                for issue in issues[:10]:
                    output.append(f"  #{issue['number']} - {issue['title']}")
                return "\n".join(output)
            return "No hay issues abiertos"
        return "❌ Especifica el repositorio"
    
    # Pull Request operations
    elif 'crear' in command_lower and ('pr' in command_lower or 'pull request' in command_lower):
        owner = kwargs.get('owner', github_complete.user_info.get('login'))
        repo = kwargs.get('repo')
        title = kwargs.get('title')
        head = kwargs.get('head')
        base = kwargs.get('base', 'main')
        if repo and title and head:
            result = github_complete.create_pull_request(owner, repo, title, head, base)
            return result['message']
        return "❌ Especifica repositorio, título y branch"
    
    # Statistics
    elif 'estadisticas' in command_lower or 'stats' in command_lower:
        owner = kwargs.get('owner', github_complete.user_info.get('login'))
        repo = kwargs.get('repo')
        if repo:
            stats = github_complete.get_repository_stats(owner, repo)
            output = [f"📊 Estadísticas de {repo}:"]
            output.append(f"  ⭐ Stars: {stats.get('stars', 0)}")
            output.append(f"  🍴 Forks: {stats.get('forks', 0)}")
            output.append(f"  👥 Contributors: {stats.get('contributors', 0)}")
            output.append(f"  📝 Open Issues: {stats.get('open_issues', 0)}")
            return "\n".join(output)
        else:
            stats = github_complete.get_user_stats()
            output = [f"📊 Estadísticas de usuario:"]
            output.append(f"  👤 {stats.get('username')}")
            output.append(f"  📦 Repos públicos: {stats.get('public_repos', 0)}")
            output.append(f"  👥 Followers: {stats.get('followers', 0)}")
            return "\n".join(output)
    
    # Search
    elif 'buscar' in command_lower or 'search' in command_lower:
        query = kwargs.get('query', '')
        if 'repositorio' in command_lower:
            results = github_complete.search_repositories(query)
            if results:
                output = [f"🔍 Resultados para '{query}':"]
                for repo in results[:5]:
                    output.append(f"  • {repo['full_name']} ⭐ {repo['stargazers_count']}")
                return "\n".join(output)
        elif 'issue' in command_lower:
            results = github_complete.search_issues(query)
            if results:
                output = [f"🔍 Issues encontrados:"]
                for issue in results[:5]:
                    output.append(f"  • {issue['title']}")
                return "\n".join(output)
        return "❌ Especifica qué buscar (repositorio, issue, código)"
    
    return None


if __name__ == "__main__":
    # Test the complete handler
    gh = GitHubComplete()
    
    if gh.token:
        print("✅ GitHub Complete Handler initialized")
        print(f"👤 Authenticated as: {gh.user_info.get('login')}")
        
        # Example: Get user stats
        stats = gh.get_user_stats()
        print(f"\n📊 User Statistics:")
        for key, value in stats.items():
            print(f"  {key}: {value}")