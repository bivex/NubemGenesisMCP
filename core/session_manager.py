#!/usr/bin/env python3
"""
Session Manager for NubemSuperFClaude
Manages chat sessions with summaries and recovery
"""

import os
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from colorama import init, Fore, Style
import hashlib

init(autoreset=True)

class SessionManager:
    """Manages chat sessions with persistence and recovery"""
    
    def __init__(self, db_path: str = None):
        """Initialize session manager with database"""
        self.db_path = Path(db_path or os.path.expanduser("~/.nubem_sessions/sessions.db"))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()
    
    def _init_database(self):
        """Initialize SQLite database for sessions"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create sessions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                created_at TIMESTAMP,
                updated_at TIMESTAMP,
                title TEXT,
                summary TEXT,
                message_count INTEGER DEFAULT 0,
                model_used TEXT,
                multi_llm BOOLEAN DEFAULT 0,
                models_used TEXT,
                status TEXT DEFAULT 'active',
                metadata TEXT
            )
        """)
        
        # Create messages table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                timestamp TIMESTAMP,
                role TEXT,
                content TEXT,
                model TEXT,
                tokens INTEGER,
                FOREIGN KEY(session_id) REFERENCES sessions(session_id)
            )
        """)
        
        # Create index for faster queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_sessions_updated 
            ON sessions(updated_at DESC)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_session 
            ON messages(session_id)
        """)
        
        conn.commit()
        conn.close()
    
    def create_session(self, session_id: str = None, title: str = None) -> str:
        """Create a new session"""
        if not session_id:
            session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        now = datetime.now()
        cursor.execute("""
            INSERT INTO sessions (session_id, created_at, updated_at, title, status)
            VALUES (?, ?, ?, ?, 'active')
        """, (session_id, now, now, title or f"Sesión {session_id}"))
        
        conn.commit()
        conn.close()
        
        return session_id
    
    def add_message(self, session_id: str, role: str, content: str, 
                   model: str = None, tokens: int = None):
        """Add a message to a session"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Add message
        cursor.execute("""
            INSERT INTO messages (session_id, timestamp, role, content, model, tokens)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (session_id, datetime.now(), role, content, model, tokens))
        
        # Update session
        cursor.execute("""
            UPDATE sessions 
            SET updated_at = ?, 
                message_count = message_count + 1
            WHERE session_id = ?
        """, (datetime.now(), session_id))
        
        # Auto-generate summary if needed
        if role == "user":
            self._update_session_summary(cursor, session_id, content)
        
        conn.commit()
        conn.close()
    
    def _update_session_summary(self, cursor, session_id: str, user_message: str):
        """Update session summary based on first messages"""
        # Get current summary
        cursor.execute("""
            SELECT summary, message_count, title 
            FROM sessions 
            WHERE session_id = ?
        """, (session_id,))
        
        result = cursor.fetchone()
        if result:
            summary, msg_count, title = result
            
            # Update title with first user message if still default
            if title.startswith("Sesión") and msg_count <= 2:
                new_title = user_message[:50] + ("..." if len(user_message) > 50 else "")
                cursor.execute("""
                    UPDATE sessions 
                    SET title = ? 
                    WHERE session_id = ?
                """, (new_title, session_id))
            
            # Update summary with first few messages
            if msg_count <= 3:
                if not summary:
                    summary = f"📝 {user_message[:100]}"
                else:
                    summary += f"\n➜ {user_message[:100]}"
                
                cursor.execute("""
                    UPDATE sessions 
                    SET summary = ? 
                    WHERE session_id = ?
                """, (summary[:500], session_id))
    
    def get_recent_sessions(self, limit: int = 7) -> List[Dict[str, Any]]:
        """Get recent sessions with summaries"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                session_id,
                created_at,
                updated_at,
                title,
                summary,
                message_count,
                model_used,
                multi_llm,
                models_used,
                status
            FROM sessions 
            WHERE status = 'active'
            ORDER BY updated_at DESC 
            LIMIT ?
        """, (limit,))
        
        sessions = []
        for row in cursor.fetchall():
            # Get last messages for better context
            cursor.execute("""
                SELECT role, content, model 
                FROM messages 
                WHERE session_id = ? 
                ORDER BY timestamp DESC 
                LIMIT 3
            """, (row[0],))
            
            last_messages = cursor.fetchall()
            
            sessions.append({
                'session_id': row[0],
                'created_at': row[1],
                'updated_at': row[2],
                'title': row[3],
                'summary': row[4],
                'message_count': row[5],
                'model_used': row[6],
                'multi_llm': row[7],
                'models_used': row[8],
                'status': row[9],
                'last_messages': last_messages
            })
        
        conn.close()
        return sessions
    
    def get_session_messages(self, session_id: str) -> List[Dict[str, Any]]:
        """Get all messages from a session"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT timestamp, role, content, model, tokens
            FROM messages 
            WHERE session_id = ? 
            ORDER BY timestamp ASC
        """, (session_id,))
        
        messages = []
        for row in cursor.fetchall():
            messages.append({
                'timestamp': row[0],
                'role': row[1],
                'content': row[2],
                'model': row[3],
                'tokens': row[4]
            })
        
        conn.close()
        return messages
    
    def display_recent_sessions(self) -> Optional[str]:
        """Display recent sessions and allow selection"""
        sessions = self.get_recent_sessions(7)
        
        if not sessions:
            return None
        
        print(f"\n{Fore.CYAN}═══════════════════════════════════════════════════════════{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}📚 Sesiones Recientes{Style.RESET_ALL}")
        print(f"{Fore.CYAN}═══════════════════════════════════════════════════════════{Style.RESET_ALL}\n")
        
        for i, session in enumerate(sessions, 1):
            # Parse dates
            created = datetime.fromisoformat(session['created_at'])
            updated = datetime.fromisoformat(session['updated_at'])
            
            # Calculate time ago
            time_ago = self._format_time_ago(updated)
            
            # Display session info
            print(f"{Fore.GREEN}[{i}]{Style.RESET_ALL} {Fore.CYAN}{session['title']}{Style.RESET_ALL}")
            print(f"    📅 {time_ago} | 💬 {session['message_count']} mensajes")
            
            # Show summary or last message
            if session['summary']:
                summary_lines = session['summary'].split('\n')
                for line in summary_lines[:2]:  # Show first 2 lines
                    if line.strip():
                        print(f"    {Fore.YELLOW}{line[:80]}{Style.RESET_ALL}")
            elif session['last_messages']:
                # Show last user message
                for role, content, _ in session['last_messages']:
                    if role == 'user':
                        print(f"    💭 {content[:80]}...")
                        break
            
            # Show models used if multi-LLM
            if session.get('multi_llm') and session.get('models_used'):
                print(f"    🤖 Modelos: {session['models_used']}")
            
            print()
        
        print(f"{Fore.CYAN}───────────────────────────────────────────────────────────{Style.RESET_ALL}")
        print(f"{Fore.GREEN}[N]{Style.RESET_ALL} Nueva sesión")
        print(f"{Fore.YELLOW}[R]{Style.RESET_ALL} Refrescar lista")
        print(f"{Fore.RED}[Q]{Style.RESET_ALL} Salir")
        print()
        
        return sessions
    
    def _format_time_ago(self, dt: datetime) -> str:
        """Format datetime as time ago"""
        now = datetime.now()
        diff = now - dt
        
        if diff.total_seconds() < 60:
            return "Hace momentos"
        elif diff.total_seconds() < 3600:
            minutes = int(diff.total_seconds() / 60)
            return f"Hace {minutes} min"
        elif diff.total_seconds() < 86400:
            hours = int(diff.total_seconds() / 3600)
            return f"Hace {hours}h"
        elif diff.days == 1:
            return "Ayer"
        elif diff.days < 7:
            return f"Hace {diff.days} días"
        else:
            return dt.strftime("%d/%m/%Y")
    
    def continue_session(self, session_id: str) -> Dict[str, Any]:
        """Load a session for continuation"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get session info
        cursor.execute("""
            SELECT * FROM sessions 
            WHERE session_id = ?
        """, (session_id,))
        
        session_data = cursor.fetchone()
        if not session_data:
            conn.close()
            return None
        
        # Get messages
        messages = self.get_session_messages(session_id)
        
        # Update session as active
        cursor.execute("""
            UPDATE sessions 
            SET status = 'active', updated_at = ?
            WHERE session_id = ?
        """, (datetime.now(), session_id))
        
        conn.commit()
        conn.close()
        
        return {
            'session_id': session_id,
            'title': session_data[3],
            'messages': messages,
            'message_count': session_data[5],
            'multi_llm': session_data[7],
            'models_used': session_data[8]
        }
    
    def export_session(self, session_id: str, format: str = 'markdown') -> str:
        """Export session to different formats"""
        messages = self.get_session_messages(session_id)
        
        if format == 'markdown':
            content = f"# Sesión {session_id}\n\n"
            content += f"**Fecha**: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
            content += "---\n\n"
            
            for msg in messages:
                role_emoji = "👤" if msg['role'] == 'user' else "🤖"
                content += f"### {role_emoji} {msg['role'].capitalize()}\n"
                content += f"{msg['content']}\n\n"
            
            return content
        
        elif format == 'json':
            return json.dumps(messages, indent=2, ensure_ascii=False, default=str)
        
        return ""
    
    def cleanup_old_sessions(self, days: int = 30):
        """Clean up sessions older than specified days"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cutoff_date = datetime.now() - timedelta(days=days)
        
        # Mark old sessions as archived
        cursor.execute("""
            UPDATE sessions 
            SET status = 'archived'
            WHERE updated_at < ? AND status = 'active'
        """, (cutoff_date,))
        
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        
        return affected
    
    def search_sessions(self, query: str) -> List[Dict[str, Any]]:
        """Search sessions by content"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Search in messages
        cursor.execute("""
            SELECT DISTINCT s.session_id, s.title, s.updated_at, s.message_count
            FROM sessions s
            JOIN messages m ON s.session_id = m.session_id
            WHERE m.content LIKE ? OR s.title LIKE ?
            ORDER BY s.updated_at DESC
            LIMIT 20
        """, (f'%{query}%', f'%{query}%'))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'session_id': row[0],
                'title': row[1],
                'updated_at': row[2],
                'message_count': row[3]
            })
        
        conn.close()
        return results


# CLI interface
if __name__ == "__main__":
    import sys
    
    manager = SessionManager()
    
    if len(sys.argv) < 2:
        print(f"{Fore.CYAN}Session Manager for NubemSuperFClaude{Style.RESET_ALL}")
        print("\nUsage:")
        print("  list     - Show recent sessions")
        print("  search   - Search sessions")
        print("  export   - Export a session")
        print("  cleanup  - Archive old sessions")
        sys.exit(0)
    
    command = sys.argv[1]
    
    if command == "list":
        sessions = manager.display_recent_sessions()
    
    elif command == "search":
        if len(sys.argv) < 3:
            print("Usage: session_manager.py search <query>")
        else:
            query = " ".join(sys.argv[2:])
            results = manager.search_sessions(query)
            print(f"\n{Fore.CYAN}Search results for '{query}':{Style.RESET_ALL}")
            for r in results:
                print(f"  • {r['title']} ({r['session_id']})")
    
    elif command == "cleanup":
        affected = manager.cleanup_old_sessions(30)
        print(f"{Fore.GREEN}✅ Archived {affected} old sessions{Style.RESET_ALL}")
    
    else:
        print(f"{Fore.RED}Unknown command: {command}{Style.RESET_ALL}")