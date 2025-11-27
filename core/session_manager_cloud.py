#!/usr/bin/env python3
"""
Cloud Session Manager for NubemSuperFClaude
Manages chat sessions with Firestore synchronization
"""

import os
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from google.cloud import firestore
from colorama import init, Fore, Style
import hashlib
import logging

init(autoreset=True)
logger = logging.getLogger(__name__)

class CloudSessionManager:
    """Manages chat sessions with Firestore cloud synchronization"""
    
    def __init__(self, project_id: str = None, db_path: str = None):
        """Initialize session manager with Firestore and local SQLite"""
        
        # Local SQLite database
        self.db_path = Path(db_path or os.path.expanduser("~/.nubem_sessions/sessions.db"))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()
        
        # Firestore client
        self.project_id = project_id or os.environ.get('GOOGLE_CLOUD_PROJECT', 'nubemsuperfclaude')
        try:
            self.firestore_client = firestore.Client(project=self.project_id)
            self.sessions_collection = self.firestore_client.collection('sessions')
            self.cloud_enabled = True
            print(f"{Fore.GREEN}✅ Firestore conectado (proyecto: {self.project_id}){Style.RESET_ALL}")
        except Exception as e:
            logger.warning(f"Firestore no disponible: {e}")
            self.cloud_enabled = False
            print(f"{Fore.YELLOW}⚠️  Usando solo almacenamiento local{Style.RESET_ALL}")
    
    def _init_database(self):
        """Initialize SQLite database for local cache"""
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
                cloud_synced BOOLEAN DEFAULT 0,
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
                cloud_synced BOOLEAN DEFAULT 0,
                FOREIGN KEY(session_id) REFERENCES sessions(session_id)
            )
        """)
        
        conn.commit()
        conn.close()
    
    def create_session(self, session_id: str = None, title: str = None) -> str:
        """Create a new session in both local and cloud storage"""
        if not session_id:
            session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        now = datetime.now()
        session_data = {
            'session_id': session_id,
            'created_at': now,
            'updated_at': now,
            'title': title or f"Sesión {session_id}",
            'message_count': 0,
            'status': 'active',
            'messages': []
        }
        
        # Save to local SQLite
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO sessions (session_id, created_at, updated_at, title, status, cloud_synced)
            VALUES (?, ?, ?, ?, 'active', ?)
        """, (session_id, now, now, session_data['title'], 1 if self.cloud_enabled else 0))
        conn.commit()
        conn.close()
        
        # Save to Firestore
        if self.cloud_enabled:
            try:
                self.sessions_collection.document(session_id).set({
                    'created_at': firestore.SERVER_TIMESTAMP,
                    'updated_at': firestore.SERVER_TIMESTAMP,
                    'title': session_data['title'],
                    'message_count': 0,
                    'status': 'active',
                    'messages': []
                })
                logger.info(f"Sesión {session_id} creada en Firestore")
            except Exception as e:
                logger.error(f"Error guardando en Firestore: {e}")
        
        return session_id
    
    def add_message(self, session_id: str, role: str, content: str, 
                   model: str = None, tokens: int = None):
        """Add a message to both local and cloud storage"""
        
        timestamp = datetime.now()
        
        # Save to local SQLite
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Add message
        cursor.execute("""
            INSERT INTO messages (session_id, timestamp, role, content, model, tokens, cloud_synced)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (session_id, timestamp, role, content, model, tokens, 1 if self.cloud_enabled else 0))
        
        # Update session
        cursor.execute("""
            UPDATE sessions 
            SET updated_at = ?, 
                message_count = message_count + 1
            WHERE session_id = ?
        """, (timestamp, session_id))
        
        conn.commit()
        conn.close()
        
        # Save to Firestore
        if self.cloud_enabled:
            try:
                session_ref = self.sessions_collection.document(session_id)
                
                # Add message to subcollection
                messages_ref = session_ref.collection('messages')
                messages_ref.add({
                    'timestamp': firestore.SERVER_TIMESTAMP,
                    'role': role,
                    'content': content,
                    'model': model,
                    'tokens': tokens
                })
                
                # Update session metadata
                session_ref.update({
                    'updated_at': firestore.SERVER_TIMESTAMP,
                    'message_count': firestore.Increment(1)
                })
                
                logger.info(f"Mensaje guardado en Firestore para sesión {session_id}")
            except Exception as e:
                logger.error(f"Error guardando mensaje en Firestore: {e}")
    
    def get_session_messages(self, session_id: str) -> List[Dict]:
        """Get messages from a session (preferring cloud if available)"""
        
        messages = []
        
        if self.cloud_enabled:
            try:
                # Get from Firestore
                session_ref = self.sessions_collection.document(session_id)
                messages_ref = session_ref.collection('messages')
                
                for msg in messages_ref.order_by('timestamp').stream():
                    msg_data = msg.to_dict()
                    messages.append({
                        'role': msg_data.get('role'),
                        'content': msg_data.get('content'),
                        'timestamp': msg_data.get('timestamp'),
                        'model': msg_data.get('model')
                    })
                
                if messages:
                    print(f"{Fore.GREEN}✅ {len(messages)} mensajes cargados desde Firestore{Style.RESET_ALL}")
                    return messages
            except Exception as e:
                logger.error(f"Error leyendo de Firestore: {e}")
        
        # Fallback to local SQLite
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT timestamp, role, content, model, tokens
            FROM messages
            WHERE session_id = ?
            ORDER BY timestamp
        """, (session_id,))
        
        for row in cursor.fetchall():
            messages.append({
                'timestamp': row[0],
                'role': row[1],
                'content': row[2],
                'model': row[3],
                'tokens': row[4]
            })
        
        conn.close()
        
        if messages:
            print(f"{Fore.YELLOW}📁 {len(messages)} mensajes cargados desde almacenamiento local{Style.RESET_ALL}")
        
        return messages
    
    def list_sessions(self, limit: int = 10) -> List[Dict]:
        """List recent sessions (from cloud if available)"""
        
        sessions = []
        
        if self.cloud_enabled:
            try:
                # Get from Firestore
                query = self.sessions_collection.order_by(
                    'updated_at', direction=firestore.Query.DESCENDING
                ).limit(limit)
                
                for doc in query.stream():
                    session_data = doc.to_dict()
                    session_data['session_id'] = doc.id
                    sessions.append(session_data)
                
                if sessions:
                    print(f"{Fore.GREEN}☁️  {len(sessions)} sesiones desde Firestore{Style.RESET_ALL}")
                    return sessions
            except Exception as e:
                logger.error(f"Error listando sesiones de Firestore: {e}")
        
        # Fallback to local SQLite
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT session_id, created_at, updated_at, title, message_count, status
            FROM sessions
            ORDER BY updated_at DESC
            LIMIT ?
        """, (limit,))
        
        for row in cursor.fetchall():
            sessions.append({
                'session_id': row[0],
                'created_at': row[1],
                'updated_at': row[2],
                'title': row[3],
                'message_count': row[4],
                'status': row[5]
            })
        
        conn.close()
        
        if sessions:
            print(f"{Fore.YELLOW}💾 {len(sessions)} sesiones desde almacenamiento local{Style.RESET_ALL}")
        
        return sessions
    
    def sync_to_cloud(self):
        """Sync local sessions to Firestore"""
        if not self.cloud_enabled:
            print(f"{Fore.YELLOW}⚠️  Firestore no está disponible{Style.RESET_ALL}")
            return
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get unsynced sessions
        cursor.execute("""
            SELECT session_id, created_at, updated_at, title, message_count, status
            FROM sessions
            WHERE cloud_synced = 0
        """)
        
        synced_count = 0
        for row in cursor.fetchall():
            try:
                self.sessions_collection.document(row[0]).set({
                    'created_at': row[1],
                    'updated_at': row[2],
                    'title': row[3],
                    'message_count': row[4],
                    'status': row[5]
                })
                
                # Mark as synced
                cursor.execute("""
                    UPDATE sessions SET cloud_synced = 1 WHERE session_id = ?
                """, (row[0],))
                
                synced_count += 1
            except Exception as e:
                logger.error(f"Error sincronizando sesión {row[0]}: {e}")
        
        conn.commit()
        conn.close()
        
        if synced_count > 0:
            print(f"{Fore.GREEN}✅ {synced_count} sesiones sincronizadas con Firestore{Style.RESET_ALL}")

# Singleton instance
_session_manager = None

def get_session_manager() -> CloudSessionManager:
    """Get or create the singleton session manager"""
    global _session_manager
    if _session_manager is None:
        _session_manager = CloudSessionManager()
    return _session_manager