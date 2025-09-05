import os
import json
import requests
import base64
from datetime import datetime, timezone
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

# Global variables for runtime tokens
_github_token = None
_repo_name = None

def set_github_credentials(token, repo):
    """Set GitHub credentials at runtime"""
    global _github_token, _repo_name
    _github_token = token
    _repo_name = repo
    logger.info(f"GitHub credentials updated for repo: {repo}")

def get_github_credentials():
    """Get GitHub credentials from runtime or environment"""
    global _github_token, _repo_name
    
    # First try runtime variables
    if _github_token and _repo_name:
        return _github_token, _repo_name
    
    # Fallback to environment variables (for backward compatibility)
    token = os.getenv("GITHUB_TOKEN")
    repo = os.getenv("REPO")
    
    return token, repo

def push_to_github():
    """Enhanced GitHub push with better error handling and metrics"""
    token, repo_name = get_github_credentials()
    branch = os.getenv("BRANCH", "main")
    file_path_in_repo = "token_ind.json"
    local_file_path = "token_ind.json"
    
    if not token or not repo_name:
        raise Exception("GitHub credentials not set. Use /setup command first.")
    
    # Check if local file exists
    if not os.path.exists(local_file_path):
        raise Exception(f"Local file {local_file_path} not found")
    
    # Read and validate local file content
    try:
        with open(local_file_path, "r", encoding="utf-8") as f:
            new_content = f.read()
        
        # Validate JSON format
        token_data = json.loads(new_content)
        token_count = len(token_data)
        
        if token_count == 0:
            raise Exception("No tokens found in local file")
        
    except json.JSONDecodeError:
        raise Exception("Local file contains invalid JSON")
    except Exception as e:
        raise Exception(f"Error reading local file: {str(e)}")
    
    # GitHub API headers
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "TokenBot/1.0"
    }
    
    # Get repository info first (to validate access)
    repo_url = f"https://api.github.com/repos/{repo_name}"
    repo_response = requests.get(repo_url, headers=headers, timeout=30)
    
    if repo_response.status_code != 200:
        if repo_response.status_code == 401:
            raise Exception("Invalid GitHub token - please check your token")
        elif repo_response.status_code == 404:
            raise Exception(f"Repository {repo_name} not found or no access")
        else:
            raise Exception(f"Cannot access repository {repo_name}: {repo_response.status_code}")
    
    # Get current file info (if exists)
    get_url = f"https://api.github.com/repos/{repo_name}/contents/{file_path_in_repo}"
    response = requests.get(get_url, headers=headers, timeout=30)
    
    # Prepare enhanced commit message with timestamp and metrics
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    commit_message = f"📄 Update {file_path_in_repo} - {token_count} tokens | {timestamp}"
    
    # Prepare commit data
    commit_data = {
        "message": commit_message,
        "content": base64.b64encode(new_content.encode()).decode(),
        "branch": branch
    }
    
    # Check if file exists and handle accordingly
    if response.status_code == 200:
        # File exists, update it
        file_info = response.json()
        commit_data["sha"] = file_info["sha"]
        action = "Updated"
        
        # Check if content is different (avoid unnecessary commits)
        current_content = base64.b64decode(file_info["content"]).decode()
        if current_content.strip() == new_content.strip():
            return f"⚡ No changes detected - {file_path_in_repo} is already up to date"
            
    elif response.status_code == 404:
        # File doesn't exist, create it
        action = "Created"
    else:
        raise Exception(f"Error checking file status: {response.status_code} - {response.text}")
    
    # Push to GitHub with retry mechanism
    put_url = f"https://api.github.com/repos/{repo_name}/contents/{file_path_in_repo}"
    
    try:
        push_response = requests.put(put_url, headers=headers, json=commit_data, timeout=60)
        
        if push_response.status_code in [200, 201]:
            # Success - get commit details
            commit_info = push_response.json()
            commit_sha = commit_info.get("commit", {}).get("sha", "unknown")[:7]
            
            success_msg = f"✅ {action} {file_path_in_repo} in {repo_name}"
            success_msg += f"\n📊 Tokens: {token_count}"
            success_msg += f"\n🔗 Commit: {commit_sha}"
            success_msg += f"\n📅 Time: {timestamp}"
            
            logger.info(f"GitHub push successful: {action} {file_path_in_repo} - {token_count} tokens")
            return success_msg
            
        else:
            # Handle specific error codes
            if push_response.status_code == 409:
                error_msg = "⚠ Conflict: File was modified by someone else"
            elif push_response.status_code == 422:
                error_msg = "⚠ Validation error: Invalid file content or branch"
            elif push_response.status_code == 403:
                error_msg = "⚠ Permission denied: Check GitHub token permissions"
            elif push_response.status_code == 404:
                error_msg = f"⚠ Repository or branch not found: {repo_name}/{branch}"
            else:
                error_msg = f"⚠ GitHub API Error: {push_response.status_code}"
            
            # Add response details for debugging
            try:
                error_details = push_response.json()
                if "message" in error_details:
                    error_msg += f"\nDetails: {error_details['message']}"
            except:
                error_msg += f"\nResponse: {push_response.text[:200]}"
            
            logger.error(f"GitHub push failed: {error_msg}")
            raise Exception(error_msg)
            
    except requests.exceptions.Timeout:
        raise Exception("⚠ GitHub API timeout - please try again")
    except requests.exceptions.ConnectionError:
        raise Exception("⚠ Connection error - check internet connection")
    except requests.exceptions.RequestException as e:
        raise Exception(f"⚠ Request error: {str(e)}")

def create_backup():
    """Create backup of current token file"""
    try:
        if not os.path.exists("token_ind.json"):
            return "⚠️ No token file to backup"
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"backup_token_ind_{timestamp}.json"
        
        with open("token_ind.json", "r") as src, open(backup_filename, "w") as dst:
            dst.write(src.read())
        
        return f"✅ Backup created: {backup_filename}"
        
    except Exception as e:
        return f"⚠ Backup failed: {str(e)}"

def validate_github_connection():
    """Test GitHub connection and permissions"""
    try:
        token, repo_name = get_github_credentials()
        
        if not token or not repo_name:
            return False, "GitHub credentials not set. Use /setup command first."
        
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        # Test repository access
        repo_url = f"https://api.github.com/repos/{repo_name}"
        response = requests.get(repo_url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            repo_info = response.json()
            return True, f"✅ Connected to {repo_info.get('full_name', repo_name)}"
        elif response.status_code == 404:
            return False, "Repository not found or no access"
        elif response.status_code == 401:
            return False, "Invalid GitHub token"
        else:
            return False, f"API Error: {response.status_code}"
            
    except Exception as e:
        return False, f"Connection test failed: {str(e)}"

def get_repo_stats():
    """Get repository statistics"""
    try:
        token, repo_name = get_github_credentials()
        
        if not token or not repo_name:
            return None
        
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        # Get repository info
        repo_url = f"https://api.github.com/repos/{repo_name}"
        response = requests.get(repo_url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            repo_info = response.json()
            
            # Get recent commits
            commits_url = f"https://api.github.com/repos/{repo_name}/commits"
            commits_response = requests.get(commits_url, headers=headers, params={"per_page": 5}, timeout=15)
            
            stats = {
                "name": repo_info.get("full_name"),
                "size": repo_info.get("size", 0),
                "updated": repo_info.get("updated_at"),
                "commits": len(commits_response.json()) if commits_response.status_code == 200 else 0
            }
            
            return stats
            
    except Exception as e:
        logger.error(f"Error getting repo stats: {e}")
        return None

def is_github_configured():
    """Check if GitHub credentials are configured"""
    token, repo_name = get_github_credentials()
    return bool(token and repo_name)

if __name__ == "__main__":
    # Test the enhanced function
    try:
        print("🔍 Testing GitHub connection...")
        is_connected, message = validate_github_connection()
        print(message)
        
        if is_connected:
            print("\n📊 Getting repository stats...")
            stats = get_repo_stats()
            if stats:
                print(f"Repository: {stats['name']}")
                print(f"Size: {stats['size']} KB")
                print(f"Last Updated: {stats['updated']}")
            
            if os.path.exists("token_ind.json"):
                print("\n🚀 Pushing to GitHub...")
                result = push_to_github()
                print(result)
            else:
                print("\n⚠️ token_ind.json not found - skipping push test")
                
    except Exception as e:
        print(f"⚠ Test failed: {e}")