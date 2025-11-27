#!/usr/bin/env python3
"""
Basic Alerting System for NubemSuperFClaude
Sistema de alerting básico para monitorear el estado del sistema
"""

import asyncio
import logging
import smtplib
from typing import Dict, Any, List, Optional, Callable, Union
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from email.mime.text import MIMEText as MimeText
from email.mime.multipart import MIMEMultipart as MimeMultipart
import json
import os

logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """Niveles de severidad de alertas"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertStatus(Enum):
    """Estados de alertas"""
    ACTIVE = "active"
    RESOLVED = "resolved"
    ACKNOWLEDGED = "acknowledged"
    SUPPRESSED = "suppressed"


@dataclass
class AlertRule:
    """Regla de alerting"""
    name: str
    condition: Callable[[], bool]
    severity: AlertSeverity
    message: str
    check_interval_seconds: int = 60
    cooldown_minutes: int = 10
    enabled: bool = True
    notify_channels: List[str] = field(default_factory=lambda: ["log"])
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Alert:
    """Una alerta generada"""
    rule_name: str
    severity: AlertSeverity
    message: str
    timestamp: datetime
    status: AlertStatus = AlertStatus.ACTIVE
    details: Dict[str, Any] = field(default_factory=dict)
    resolved_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    notification_sent: bool = False


@dataclass
class NotificationChannel:
    """Canal de notificación"""
    name: str
    type: str  # "email", "webhook", "log", "file"
    config: Dict[str, Any]
    enabled: bool = True


class AlertingSystem:
    """Sistema de alerting básico"""
    
    def __init__(self):
        self.rules: Dict[str, AlertRule] = {}
        self.active_alerts: Dict[str, Alert] = {}
        self.alert_history: List[Alert] = []
        self.notification_channels: Dict[str, NotificationChannel] = {}
        self.last_checks: Dict[str, datetime] = {}
        self.cooldowns: Dict[str, datetime] = {}
        
        self._running = False
        self._check_task: Optional[asyncio.Task] = None
        
        # Setup default channels
        self._setup_default_channels()
        
        # Setup default rules
        self._setup_default_rules()
        
    def _setup_default_channels(self):
        """Configurar canales de notificación por defecto"""
        
        # Log channel
        self.notification_channels["log"] = NotificationChannel(
            name="log",
            type="log",
            config={"level": "WARNING"},
            enabled=True
        )
        
        # File channel
        self.notification_channels["file"] = NotificationChannel(
            name="file",
            type="file",
            config={
                "path": "logs/alerts.json",
                "format": "json"
            },
            enabled=True
        )
        
        # Email channel (if configured)
        smtp_host = os.getenv("SMTP_HOST")
        smtp_user = os.getenv("SMTP_USER")
        smtp_pass = os.getenv("SMTP_PASS")
        alert_email = os.getenv("ALERT_EMAIL")
        
        if all([smtp_host, smtp_user, smtp_pass, alert_email]):
            self.notification_channels["email"] = NotificationChannel(
                name="email",
                type="email",
                config={
                    "smtp_host": smtp_host,
                    "smtp_port": int(os.getenv("SMTP_PORT", 587)),
                    "smtp_user": smtp_user,
                    "smtp_pass": smtp_pass,
                    "from_email": smtp_user,
                    "to_emails": [alert_email],
                    "use_tls": os.getenv("SMTP_TLS", "true").lower() == "true"
                },
                enabled=True
            )
        
        # Webhook channel (if configured)
        webhook_url = os.getenv("ALERT_WEBHOOK_URL")
        if webhook_url:
            self.notification_channels["webhook"] = NotificationChannel(
                name="webhook",
                type="webhook", 
                config={
                    "url": webhook_url,
                    "method": "POST",
                    "headers": {"Content-Type": "application/json"}
                },
                enabled=True
            )
    
    def _setup_default_rules(self):
        """Configurar reglas de alerting por defecto"""
        
        # High memory usage alert
        self.add_rule(AlertRule(
            name="high_memory_usage",
            condition=self._check_memory_usage,
            severity=AlertSeverity.HIGH,
            message="System memory usage is critically high",
            check_interval_seconds=30,
            cooldown_minutes=5,
            notify_channels=["log", "file", "email"]
        ))
        
        # Redis connection alert  
        self.add_rule(AlertRule(
            name="redis_connection_failed",
            condition=self._check_redis_connection,
            severity=AlertSeverity.CRITICAL,
            message="Redis connection is failing",
            check_interval_seconds=60,
            cooldown_minutes=2,
            notify_channels=["log", "file", "email", "webhook"]
        ))
        
        # Qdrant connection alert
        self.add_rule(AlertRule(
            name="qdrant_connection_failed", 
            condition=self._check_qdrant_connection,
            severity=AlertSeverity.HIGH,
            message="Qdrant connection is failing",
            check_interval_seconds=120,
            cooldown_minutes=5,
            notify_channels=["log", "file", "email"]
        ))
        
        # High error rate alert
        self.add_rule(AlertRule(
            name="high_error_rate",
            condition=self._check_error_rate,
            severity=AlertSeverity.MEDIUM,
            message="System error rate is elevated",
            check_interval_seconds=300,  # 5 minutes
            cooldown_minutes=15,
            notify_channels=["log", "file"]
        ))
    
    def _check_memory_usage(self) -> bool:
        """Verificar uso de memoria"""
        try:
            import psutil
            memory_percent = psutil.virtual_memory().percent
            return memory_percent > 85.0
        except Exception:
            return False
    
    def _check_redis_connection(self) -> bool:
        """Verificar conexión a Redis"""
        try:
            from core.health_checker import check_redis_health
            import asyncio
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(check_redis_health())
            loop.close()
            
            return result.status.value != "healthy"
        except Exception:
            return True  # Assume failed if can't check
    
    def _check_qdrant_connection(self) -> bool:
        """Verificar conexión a Qdrant"""
        try:
            from core.health_checker import check_qdrant_health
            import asyncio
            
            loop = asyncio.new_event_loop() 
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(check_qdrant_health())
            loop.close()
            
            return result.status.value != "healthy"
        except Exception:
            return True  # Assume failed if can't check
    
    def _check_error_rate(self) -> bool:
        """Verificar tasa de errores"""
        try:
            from core.personas_metrics import get_personas_metrics
            metrics = get_personas_metrics()
            
            # Check recent activity
            now = datetime.now()
            recent_interactions = [
                interaction for interaction in metrics.interaction_history
                if (now - interaction.timestamp) <= timedelta(minutes=15)
            ]
            
            if len(recent_interactions) < 10:
                return False  # Not enough data
            
            error_rate = sum(1 for i in recent_interactions if not i.success) / len(recent_interactions)
            return error_rate > 0.2  # More than 20% error rate
            
        except Exception:
            return False
    
    def add_rule(self, rule: AlertRule):
        """Agregar regla de alerting"""
        self.rules[rule.name] = rule
        logger.info(f"Added alert rule: {rule.name}")
    
    def remove_rule(self, rule_name: str):
        """Remover regla de alerting"""
        if rule_name in self.rules:
            del self.rules[rule_name]
            logger.info(f"Removed alert rule: {rule_name}")
    
    def add_notification_channel(self, channel: NotificationChannel):
        """Agregar canal de notificación"""
        self.notification_channels[channel.name] = channel
        logger.info(f"Added notification channel: {channel.name}")
    
    async def check_rules(self):
        """Verificar todas las reglas de alerting"""
        now = datetime.now()
        
        for rule_name, rule in self.rules.items():
            if not rule.enabled:
                continue
            
            # Check if it's time to run this rule
            last_check = self.last_checks.get(rule_name, datetime.min)
            if (now - last_check).total_seconds() < rule.check_interval_seconds:
                continue
            
            # Check if rule is in cooldown
            cooldown_until = self.cooldowns.get(rule_name, datetime.min)
            if now < cooldown_until:
                continue
            
            try:
                # Run the condition check
                condition_result = rule.condition()
                
                if condition_result:
                    # Condition is true - fire alert if not already active
                    if rule_name not in self.active_alerts:
                        alert = Alert(
                            rule_name=rule_name,
                            severity=rule.severity,
                            message=rule.message,
                            timestamp=now,
                            details=rule.metadata.copy()
                        )
                        
                        self.active_alerts[rule_name] = alert
                        self.alert_history.append(alert)
                        
                        # Send notifications
                        await self._send_notifications(alert, rule)
                        
                        # Set cooldown
                        self.cooldowns[rule_name] = now + timedelta(minutes=rule.cooldown_minutes)
                        
                        logger.warning(f"Alert fired: {rule_name} - {rule.message}")
                
                else:
                    # Condition is false - resolve alert if active
                    if rule_name in self.active_alerts:
                        alert = self.active_alerts[rule_name]
                        alert.status = AlertStatus.RESOLVED
                        alert.resolved_at = now
                        
                        del self.active_alerts[rule_name]
                        
                        logger.info(f"Alert resolved: {rule_name}")
                
                self.last_checks[rule_name] = now
                
            except Exception as e:
                logger.error(f"Error checking rule {rule_name}: {e}")
    
    async def _send_notifications(self, alert: Alert, rule: AlertRule):
        """Enviar notificaciones para una alerta"""
        for channel_name in rule.notify_channels:
            if channel_name not in self.notification_channels:
                continue
            
            channel = self.notification_channels[channel_name]
            if not channel.enabled:
                continue
            
            try:
                await self._send_notification(alert, channel)
            except Exception as e:
                logger.error(f"Failed to send notification via {channel_name}: {e}")
    
    async def _send_notification(self, alert: Alert, channel: NotificationChannel):
        """Enviar notificación por un canal específico"""
        
        if channel.type == "log":
            level = channel.config.get("level", "WARNING")
            log_func = getattr(logger, level.lower(), logger.warning)
            log_func(f"ALERT [{alert.severity.value.upper()}] {alert.rule_name}: {alert.message}")
        
        elif channel.type == "file":
            await self._send_file_notification(alert, channel)
        
        elif channel.type == "email":
            await self._send_email_notification(alert, channel)
        
        elif channel.type == "webhook":
            await self._send_webhook_notification(alert, channel)
    
    async def _send_file_notification(self, alert: Alert, channel: NotificationChannel):
        """Enviar notificación a archivo"""
        file_path = channel.config.get("path", "alerts.log")
        format_type = channel.config.get("format", "text")
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        if format_type == "json":
            alert_data = {
                "rule_name": alert.rule_name,
                "severity": alert.severity.value,
                "message": alert.message,
                "timestamp": alert.timestamp.isoformat(),
                "status": alert.status.value,
                "details": alert.details
            }
            
            with open(file_path, "a") as f:
                f.write(json.dumps(alert_data) + "\n")
        else:
            with open(file_path, "a") as f:
                f.write(f"[{alert.timestamp.isoformat()}] ALERT [{alert.severity.value.upper()}] {alert.rule_name}: {alert.message}\n")
    
    async def _send_email_notification(self, alert: Alert, channel: NotificationChannel):
        """Enviar notificación por email"""
        config = channel.config
        
        msg = MimeMultipart()
        msg['From'] = config['from_email']
        msg['To'] = ", ".join(config['to_emails'])
        msg['Subject'] = f"NubemSuperFClaude Alert: {alert.rule_name}"
        
        body = f"""
Alert Details:
- Rule: {alert.rule_name}
- Severity: {alert.severity.value.upper()}
- Message: {alert.message}
- Timestamp: {alert.timestamp.isoformat()}
- Status: {alert.status.value}

Additional Details:
{json.dumps(alert.details, indent=2)}

--
NubemSuperFClaude Alerting System
        """
        
        msg.attach(MimeText(body, 'plain'))
        
        # Send email in thread to avoid blocking
        def send_email():
            try:
                server = smtplib.SMTP(config['smtp_host'], config['smtp_port'])
                if config.get('use_tls', True):
                    server.starttls()
                server.login(config['smtp_user'], config['smtp_pass'])
                text = msg.as_string()
                server.sendmail(config['from_email'], config['to_emails'], text)
                server.quit()
            except Exception as e:
                logger.error(f"Failed to send email: {e}")
        
        import threading
        threading.Thread(target=send_email).start()
    
    async def _send_webhook_notification(self, alert: Alert, channel: NotificationChannel):
        """Enviar notificación via webhook"""
        import aiohttp
        
        config = channel.config
        payload = {
            "alert": {
                "rule_name": alert.rule_name,
                "severity": alert.severity.value,
                "message": alert.message,
                "timestamp": alert.timestamp.isoformat(),
                "status": alert.status.value,
                "details": alert.details
            },
            "system": "NubemSuperFClaude"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                config['url'],
                json=payload,
                headers=config.get('headers', {}),
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status != 200:
                    logger.warning(f"Webhook returned status {response.status}")
    
    async def start(self):
        """Iniciar sistema de alerting"""
        if self._running:
            return
        
        self._running = True
        self._check_task = asyncio.create_task(self._run_checks())
        logger.info("Alerting system started")
    
    async def stop(self):
        """Detener sistema de alerting"""
        if not self._running:
            return
        
        self._running = False
        if self._check_task:
            self._check_task.cancel()
            try:
                await self._check_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Alerting system stopped")
    
    async def _run_checks(self):
        """Ejecutar checks de alerting en bucle"""
        while self._running:
            try:
                await self.check_rules()
                await asyncio.sleep(10)  # Check every 10 seconds
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in alerting check loop: {e}")
                await asyncio.sleep(30)  # Wait longer after error
    
    def get_active_alerts(self) -> List[Alert]:
        """Obtener alertas activas"""
        return list(self.active_alerts.values())
    
    def get_alert_history(self, hours: int = 24) -> List[Alert]:
        """Obtener historial de alertas"""
        cutoff = datetime.now() - timedelta(hours=hours)
        return [alert for alert in self.alert_history if alert.timestamp >= cutoff]
    
    def acknowledge_alert(self, rule_name: str) -> bool:
        """Reconocer una alerta"""
        if rule_name in self.active_alerts:
            self.active_alerts[rule_name].status = AlertStatus.ACKNOWLEDGED
            self.active_alerts[rule_name].acknowledged_at = datetime.now()
            logger.info(f"Alert acknowledged: {rule_name}")
            return True
        return False
    
    def get_system_stats(self) -> Dict[str, Any]:
        """Obtener estadísticas del sistema de alerting"""
        return {
            "rules": {
                "total": len(self.rules),
                "enabled": sum(1 for rule in self.rules.values() if rule.enabled)
            },
            "alerts": {
                "active": len(self.active_alerts),
                "total_history": len(self.alert_history)
            },
            "channels": {
                "total": len(self.notification_channels),
                "enabled": sum(1 for ch in self.notification_channels.values() if ch.enabled)
            },
            "system": {
                "running": self._running,
                "last_check_count": len(self.last_checks)
            }
        }


# Singleton alerting system
_alerting_system: Optional[AlertingSystem] = None


def get_alerting_system() -> AlertingSystem:
    """Obtener instancia singleton del sistema de alerting"""
    global _alerting_system
    
    if _alerting_system is None:
        _alerting_system = AlertingSystem()
    
    return _alerting_system