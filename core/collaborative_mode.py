#!/usr/bin/env python3
"""
Modo Colaborativo para NubemSuperFClaude
Permite colaboración en tiempo real entre múltiples usuarios
"""

import asyncio
import json
import time
import uuid
from typing import Dict, List, Set, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum
import logging
import hashlib

logger = logging.getLogger(__name__)


class UserRole(Enum):
    """Roles de usuario en sesión colaborativa"""
    OWNER = "owner"
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"


class MessageType(Enum):
    """Tipos de mensajes en colaboración"""
    CHAT = "chat"
    COMMAND = "command"
    RESULT = "result"
    ANNOTATION = "annotation"
    SYSTEM = "system"
    TYPING = "typing"
    PRESENCE = "presence"


@dataclass
class User:
    """Usuario en sesión colaborativa"""
    id: str
    name: str
    email: str
    role: UserRole
    avatar_url: Optional[str] = None
    joined_at: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    is_online: bool = False


@dataclass
class Message:
    """Mensaje en sesión colaborativa"""
    id: str
    type: MessageType
    user_id: str
    content: str
    timestamp: datetime
    metadata: Dict[str, Any] = None
    reply_to: Optional[str] = None
    reactions: Dict[str, List[str]] = None  # emoji -> list of user_ids


@dataclass
class CollaborativeSession:
    """Sesión colaborativa"""
    id: str
    name: str
    owner_id: str
    created_at: datetime
    updated_at: datetime
    users: Dict[str, User]
    messages: List[Message]
    settings: Dict[str, Any]
    is_active: bool = True
    max_users: int = 10
    tags: List[str] = None


class CollaborationManager:
    """Gestor de sesiones colaborativas"""

    def __init__(self):
        self.sessions: Dict[str, CollaborativeSession] = {}
        self.user_sessions: Dict[str, Set[str]] = {}  # user_id -> session_ids
        self.websocket_connections: Dict[str, Any] = {}  # user_id -> websocket
        self.typing_status: Dict[str, Dict[str, float]] = {}  # session_id -> {user_id: timestamp}

    async def create_session(
        self,
        name: str,
        owner: User,
        settings: Optional[Dict] = None
    ) -> CollaborativeSession:
        """Crear nueva sesión colaborativa"""
        session_id = str(uuid.uuid4())
        now = datetime.now()

        session = CollaborativeSession(
            id=session_id,
            name=name,
            owner_id=owner.id,
            created_at=now,
            updated_at=now,
            users={owner.id: owner},
            messages=[],
            settings=settings or {},
            tags=[]
        )

        self.sessions[session_id] = session

        # Registrar usuario en sesión
        if owner.id not in self.user_sessions:
            self.user_sessions[owner.id] = set()
        self.user_sessions[owner.id].add(session_id)

        # Mensaje del sistema
        await self.add_message(
            session_id,
            Message(
                id=str(uuid.uuid4()),
                type=MessageType.SYSTEM,
                user_id="system",
                content=f"{owner.name} created the session",
                timestamp=now
            )
        )

        logger.info(f"Created collaborative session: {session_id}")
        return session

    async def join_session(
        self,
        session_id: str,
        user: User
    ) -> bool:
        """Unirse a una sesión existente"""
        if session_id not in self.sessions:
            logger.error(f"Session {session_id} not found")
            return False

        session = self.sessions[session_id]

        # Verificar límite de usuarios
        if len(session.users) >= session.max_users:
            logger.warning(f"Session {session_id} is full")
            return False

        # Añadir usuario
        user.joined_at = datetime.now()
        user.is_online = True
        session.users[user.id] = user

        # Registrar sesión del usuario
        if user.id not in self.user_sessions:
            self.user_sessions[user.id] = set()
        self.user_sessions[user.id].add(session_id)

        # Notificar a otros usuarios
        await self.broadcast_to_session(
            session_id,
            {
                "type": "user_joined",
                "user": asdict(user),
                "timestamp": datetime.now().isoformat()
            },
            exclude_user=user.id
        )

        # Mensaje del sistema
        await self.add_message(
            session_id,
            Message(
                id=str(uuid.uuid4()),
                type=MessageType.SYSTEM,
                user_id="system",
                content=f"{user.name} joined the session",
                timestamp=datetime.now()
            )
        )

        logger.info(f"User {user.id} joined session {session_id}")
        return True

    async def leave_session(
        self,
        session_id: str,
        user_id: str
    ) -> bool:
        """Abandonar una sesión"""
        if session_id not in self.sessions:
            return False

        session = self.sessions[session_id]

        if user_id not in session.users:
            return False

        user = session.users[user_id]
        user.is_online = False
        user.last_seen = datetime.now()

        # Eliminar de sesiones del usuario
        if user_id in self.user_sessions:
            self.user_sessions[user_id].discard(session_id)

        # Notificar a otros usuarios
        await self.broadcast_to_session(
            session_id,
            {
                "type": "user_left",
                "user_id": user_id,
                "timestamp": datetime.now().isoformat()
            },
            exclude_user=user_id
        )

        # Mensaje del sistema
        await self.add_message(
            session_id,
            Message(
                id=str(uuid.uuid4()),
                type=MessageType.SYSTEM,
                user_id="system",
                content=f"{user.name} left the session",
                timestamp=datetime.now()
            )
        )

        return True

    async def add_message(
        self,
        session_id: str,
        message: Message
    ) -> bool:
        """Añadir mensaje a la sesión"""
        if session_id not in self.sessions:
            return False

        session = self.sessions[session_id]
        session.messages.append(message)
        session.updated_at = datetime.now()

        # Broadcast a todos los usuarios
        await self.broadcast_to_session(
            session_id,
            {
                "type": "new_message",
                "message": {
                    "id": message.id,
                    "type": message.type.value,
                    "user_id": message.user_id,
                    "content": message.content,
                    "timestamp": message.timestamp.isoformat(),
                    "metadata": message.metadata,
                    "reply_to": message.reply_to
                }
            }
        )

        return True

    async def execute_command(
        self,
        session_id: str,
        user_id: str,
        command: str,
        args: Dict[str, Any]
    ) -> Any:
        """Ejecutar comando colaborativo"""
        if session_id not in self.sessions:
            return None

        session = self.sessions[session_id]

        # Verificar permisos
        user = session.users.get(user_id)
        if not user or user.role == UserRole.VIEWER:
            logger.warning(f"User {user_id} cannot execute commands")
            return None

        # Añadir mensaje de comando
        command_message = Message(
            id=str(uuid.uuid4()),
            type=MessageType.COMMAND,
            user_id=user_id,
            content=command,
            timestamp=datetime.now(),
            metadata=args
        )
        await self.add_message(session_id, command_message)

        # Ejecutar comando (aquí se integraría con el sistema principal)
        result = await self._process_command(command, args)

        # Añadir mensaje de resultado
        result_message = Message(
            id=str(uuid.uuid4()),
            type=MessageType.RESULT,
            user_id="system",
            content=json.dumps(result),
            timestamp=datetime.now(),
            reply_to=command_message.id
        )
        await self.add_message(session_id, result_message)

        return result

    async def add_annotation(
        self,
        session_id: str,
        user_id: str,
        message_id: str,
        annotation: str
    ) -> bool:
        """Añadir anotación a un mensaje"""
        if session_id not in self.sessions:
            return False

        annotation_message = Message(
            id=str(uuid.uuid4()),
            type=MessageType.ANNOTATION,
            user_id=user_id,
            content=annotation,
            timestamp=datetime.now(),
            reply_to=message_id
        )

        return await self.add_message(session_id, annotation_message)

    async def add_reaction(
        self,
        session_id: str,
        user_id: str,
        message_id: str,
        emoji: str
    ) -> bool:
        """Añadir reacción a un mensaje"""
        if session_id not in self.sessions:
            return False

        session = self.sessions[session_id]

        # Buscar mensaje
        for message in session.messages:
            if message.id == message_id:
                if message.reactions is None:
                    message.reactions = {}

                if emoji not in message.reactions:
                    message.reactions[emoji] = []

                if user_id not in message.reactions[emoji]:
                    message.reactions[emoji].append(user_id)

                # Notificar cambio
                await self.broadcast_to_session(
                    session_id,
                    {
                        "type": "reaction_added",
                        "message_id": message_id,
                        "user_id": user_id,
                        "emoji": emoji
                    }
                )

                return True

        return False

    async def update_typing_status(
        self,
        session_id: str,
        user_id: str,
        is_typing: bool
    ):
        """Actualizar estado de escritura"""
        if session_id not in self.sessions:
            return

        if session_id not in self.typing_status:
            self.typing_status[session_id] = {}

        if is_typing:
            self.typing_status[session_id][user_id] = time.time()
        else:
            self.typing_status[session_id].pop(user_id, None)

        # Notificar a otros usuarios
        await self.broadcast_to_session(
            session_id,
            {
                "type": "typing_status",
                "user_id": user_id,
                "is_typing": is_typing
            },
            exclude_user=user_id
        )

    async def get_active_typers(self, session_id: str) -> List[str]:
        """Obtener usuarios escribiendo actualmente"""
        if session_id not in self.typing_status:
            return []

        now = time.time()
        active_typers = []

        # Limpiar estados viejos (> 5 segundos)
        for user_id, timestamp in list(self.typing_status[session_id].items()):
            if now - timestamp < 5:
                active_typers.append(user_id)
            else:
                del self.typing_status[session_id][user_id]

        return active_typers

    async def broadcast_to_session(
        self,
        session_id: str,
        data: Dict[str, Any],
        exclude_user: Optional[str] = None
    ):
        """Broadcast mensaje a todos los usuarios de la sesión"""
        if session_id not in self.sessions:
            return

        session = self.sessions[session_id]

        for user_id in session.users:
            if user_id == exclude_user:
                continue

            if user_id in self.websocket_connections:
                try:
                    websocket = self.websocket_connections[user_id]
                    await websocket.send_json(data)
                except Exception as e:
                    logger.error(f"Error broadcasting to user {user_id}: {e}")

    async def get_session_history(
        self,
        session_id: str,
        limit: int = 100,
        offset: int = 0
    ) -> List[Message]:
        """Obtener historial de mensajes de la sesión"""
        if session_id not in self.sessions:
            return []

        session = self.sessions[session_id]
        messages = session.messages[offset:offset + limit]
        return messages

    async def search_messages(
        self,
        session_id: str,
        query: str,
        user_id: Optional[str] = None,
        message_type: Optional[MessageType] = None
    ) -> List[Message]:
        """Buscar mensajes en la sesión"""
        if session_id not in self.sessions:
            return []

        session = self.sessions[session_id]
        results = []

        for message in session.messages:
            # Filtrar por usuario
            if user_id and message.user_id != user_id:
                continue

            # Filtrar por tipo
            if message_type and message.type != message_type:
                continue

            # Buscar en contenido
            if query.lower() in message.content.lower():
                results.append(message)

        return results

    async def export_session(
        self,
        session_id: str,
        format: str = "json"
    ) -> str:
        """Exportar sesión a diferentes formatos"""
        if session_id not in self.sessions:
            return ""

        session = self.sessions[session_id]

        if format == "json":
            return json.dumps({
                "session": {
                    "id": session.id,
                    "name": session.name,
                    "created_at": session.created_at.isoformat(),
                    "updated_at": session.updated_at.isoformat()
                },
                "users": [asdict(u) for u in session.users.values()],
                "messages": [
                    {
                        "id": m.id,
                        "type": m.type.value,
                        "user_id": m.user_id,
                        "content": m.content,
                        "timestamp": m.timestamp.isoformat()
                    }
                    for m in session.messages
                ]
            }, indent=2)

        elif format == "markdown":
            md = f"# {session.name}\n\n"
            md += f"Created: {session.created_at}\n\n"
            md += "## Participants\n\n"

            for user in session.users.values():
                md += f"- {user.name} ({user.role.value})\n"

            md += "\n## Conversation\n\n"

            for msg in session.messages:
                user = session.users.get(msg.user_id)
                username = user.name if user else "System"
                md += f"**{username}** ({msg.timestamp.strftime('%H:%M')}): {msg.content}\n\n"

            return md

        return ""

    async def _process_command(self, command: str, args: Dict[str, Any]) -> Any:
        """Procesar comando (integración con sistema principal)"""
        # Aquí se integraría con el sistema de comandos principal
        # Por ahora, simulamos algunos comandos
        if command == "summarize":
            return {"summary": "Session summary generated"}
        elif command == "analyze":
            return {"analysis": "Code analysis completed"}
        else:
            return {"error": f"Unknown command: {command}"}

    async def cleanup_inactive_sessions(self, inactive_hours: int = 24):
        """Limpiar sesiones inactivas"""
        now = datetime.now()
        inactive_threshold = now - timedelta(hours=inactive_hours)

        sessions_to_remove = []

        for session_id, session in self.sessions.items():
            if session.updated_at < inactive_threshold:
                # Verificar si hay usuarios online
                has_online_users = any(u.is_online for u in session.users.values())

                if not has_online_users:
                    sessions_to_remove.append(session_id)

        for session_id in sessions_to_remove:
            del self.sessions[session_id]
            logger.info(f"Cleaned up inactive session: {session_id}")

        return len(sessions_to_remove)


# Singleton
_collaboration_manager: Optional[CollaborationManager] = None


def get_collaboration_manager() -> CollaborationManager:
    """Obtener instancia global del gestor de colaboración"""
    global _collaboration_manager
    if _collaboration_manager is None:
        _collaboration_manager = CollaborationManager()
    return _collaboration_manager


# Testing
if __name__ == "__main__":
    async def test_collaboration():
        manager = get_collaboration_manager()

        # Crear usuarios
        owner = User(
            id="user1",
            name="Alice",
            email="alice@example.com",
            role=UserRole.OWNER
        )

        editor = User(
            id="user2",
            name="Bob",
            email="bob@example.com",
            role=UserRole.EDITOR
        )

        # Crear sesión
        session = await manager.create_session(
            name="Project Planning",
            owner=owner
        )
        print(f"Created session: {session.id}")

        # Unir usuario
        await manager.join_session(session.id, editor)

        # Enviar mensajes
        await manager.add_message(
            session.id,
            Message(
                id=str(uuid.uuid4()),
                type=MessageType.CHAT,
                user_id=owner.id,
                content="Let's plan the new feature",
                timestamp=datetime.now()
            )
        )

        await manager.add_message(
            session.id,
            Message(
                id=str(uuid.uuid4()),
                type=MessageType.CHAT,
                user_id=editor.id,
                content="Sounds good! What's the timeline?",
                timestamp=datetime.now()
            )
        )

        # Ejecutar comando
        result = await manager.execute_command(
            session.id,
            owner.id,
            "summarize",
            {}
        )
        print(f"Command result: {result}")

        # Exportar sesión
        export = await manager.export_session(session.id, "markdown")
        print(f"\nSession export:\n{export}")

    asyncio.run(test_collaboration())