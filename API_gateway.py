import json
import time
import uuid
from datetime import datetime
import requests
from typing import Dict, List, Optional, Union

class AlertSeverity:
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

class AlertManager:
    def __init__(self, config_path: str = "alert_config.json"):
        """Initialize the alert manager with configuration."""
        self.config = self._load_config(config_path)
        self.active_alerts = {}  # Store active alerts
        self.alert_history = []  # Store alert history
        self.notification_services = self._initialize_notification_services()
        
    def _load_config(self, config_path: str) -> Dict:
        """Load alert configuration from file."""
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            # Default configuration if file not found
            return {
                "thresholds": {
                    "response_time": {
                        "warning": 1.5,  # 50% above baseline
                        "error": 2.0,    # 100% above baseline
                        "critical": 3.0   # 200% above baseline
                    },
                    "error_rate": {
                        "warning": 0.01,  # 1% error rate
                        "error": 0.05,    # 5% error rate
                        "critical": 0.10   # 10% error rate
                    }
                },
                "notification": {
                    "email": {
                        "enabled": True,
                        "recipients": ["ops@example.com"]
                    },
                    "slack": {
                        "enabled": True,
                        "webhook_url": "https://hooks.slack.com/services/XXX/YYY/ZZZ"
                    },
                    "pagerduty": {
                        "enabled": False,
                        "service_key": "your_pagerduty_service_key"
                    }
                },
                "deduplication_window": 300,  # 5 minutes
                "auto_resolve_time": 3600     # 1 hour
            }
    
    def _initialize_notification_services(self) -> Dict:
        """Initialize notification service connections."""
        services = {}
        
        # Add email notification service
        if self.config["notification"]["email"]["enabled"]:
            services["email"] = EmailNotifier(self.config["notification"]["email"])
            
        # Add Slack notification service
        if self.config["notification"]["slack"]["enabled"]:
            services["slack"] = SlackNotifier(self.config["notification"]["slack"])
            
        # Add PagerDuty notification service
        if self.config["notification"]["pagerduty"]["enabled"]:
            services["pagerduty"] = PagerDutyNotifier(self.config["notification"]["pagerduty"])
            
        return services
    
    def create_alert(self, 
                     alert_type: str,
                     source: str,
                     severity: str,
                     message: str,
                     details: Dict = None,
                     environment: str = "unknown",
                     related_entities: List[str] = None) -> Dict:
        """Create a new alert with the given parameters."""
        # Generate alert ID
        alert_id = str(uuid.uuid4())
        
        # Create alert object
        alert = {
            "id": alert_id,
            "type": alert_type,
            "source": source,
            "severity": severity,
            "message": message,
            "details": details or {},
            "environment": environment,
            "related_entities": related_entities or [],
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "status": "active"
        }
        
        # Check for deduplication
        duplicate_alert = self._check_for_duplicate(alert)
        if duplicate_alert:
            # Update existing alert instead of creating new one
            self._update_alert(duplicate_alert["id"], 
                              {"count": duplicate_alert.get("count", 1) + 1,
                               "updated_at": alert["updated_at"]})
            return duplicate_alert
        
        # Add count for future deduplication
        alert["count"] = 1
        
        # Store the alert
        self.active_alerts[alert_id] = alert
        self.alert_history.append(alert)
        
        # Send notifications
        self._send_notifications(alert)
        
        return alert
    
    def _check_for_duplicate(self, alert: Dict) -> Optional[Dict]:
        """Check if a similar alert already exists within deduplication window."""
        dedup_window = self.config["deduplication_window"]
        current_time = time.time()
        
        for existing_id, existing_alert in self.active_alerts.items():
            # Skip if alert is already resolved
            if existing_alert["status"] != "active":
                continue
                
            # Check if alert was created within deduplication window
            existing_time = datetime.fromisoformat(existing_alert["created_at"]).timestamp()
            if current_time - existing_time > dedup_window:
                continue
                
            # Check if alerts are similar
            if (existing_alert["type"] == alert["type"] and
                existing_alert["source"] == alert["source"] and
                existing_alert["severity"] == alert["severity"] and
                existing_alert["environment"] == alert["environment"]):
                return existing_alert
                
        return None
    
    def _update_alert(self, alert_id: str, update_data: Dict) -> Dict:
        """Update an existing alert with new data."""
        if alert_id not in self.active_alerts:
            raise ValueError(f"Alert with ID {alert_id} not found")
            
        alert = self.active_alerts[alert_id]
        
        # Update the alert with new data
        for key, value in update_data.items():
            alert[key] = value
            
        # Update the timestamp
        alert["updated_at"] = datetime.utcnow().isoformat()
        
        return alert
    
    def resolve_alert(self, alert_id: str, resolution_message: str = None) -> Dict:
        """Resolve an active alert."""
        if alert_id not in self.active_alerts:
            raise ValueError(f"Alert with ID {alert_id} not found")
            
        alert = self.active_alerts[alert_id]
        
        # Update alert status
        alert["status"] = "resolved"
        alert["resolved_at"] = datetime.utcnow().isoformat()
        alert["resolution_message"] = resolution_message
        
        # Send resolution notification
        self._send_resolution_notification(alert)
        
        return alert
    
    def _send_notifications(self, alert: Dict) -> None:
        """Send notifications for a new alert."""
        # Only send notifications for warning, error, and critical alerts
        if alert["severity"] == AlertSeverity.INFO:
            return
            
        for service_name, service in self.notification_services.items():
            try:
                service.send_alert(alert)
            except Exception as e:
                print(f"Failed to send {service_name} notification: {str(e)}")
    
    def _send_resolution_notification(self, alert: Dict) -> None:
        """Send notifications for a resolved alert."""
        # Only send resolution notifications for error and critical alerts
        if alert["severity"] not in [AlertSeverity.ERROR, AlertSeverity.CRITICAL]:
            return
            
        for service_name, service in self.notification_services.items():
            try:
                service.send_resolution(alert)
            except Exception as e:
                print(f"Failed to send {service_name} resolution notification: {str(e)}")
                
    def get_active_alerts(self, 
                         environment: str = None, 
                         severity: str = None,
                         source: str = None) -> List[Dict]:
        """Get active alerts with optional filtering."""
        filtered_alerts = []
        
        for alert in self.active_alerts.values():
            if alert["status"] != "active":
                continue
                
            if environment and alert["environment"] != environment:
                continue
                
            if severity and alert["severity"] != severity:
                continue
                
            if source and alert["source"] != source:
                continue
                
            filtered_alerts.append(alert)
            
        return filtered_alerts
        
    def get_alert_by_id(self, alert_id: str) -> Optional[Dict]:
        """Get an alert by its ID."""
        return self.active_alerts.get(alert_id)


class EmailNotifier:
    """Email notification service."""
    
    def __init__(self, config):
        self.config = config
        
    def send_alert(self, alert):
        """Send an email notification for a new alert."""
        # In a real implementation, use an email library
        recipients = self.config["recipients"]
        subject = f"[{alert['severity'].upper()}] {alert['message']}"
        body = json.dumps(alert, indent=2)
        
        print(f"Sending email to {recipients} with subject: {subject}")
        # Implement actual email sending here
        
    def send_resolution(self, alert):
        """Send an email notification for a resolved alert."""
        recipients = self.config["recipients"]
        subject = f"[RESOLVED] {alert['message']}"
        body = f"Alert has been resolved at {alert['resolved_at']}"
        
        print(f"Sending resolution email to {recipients} with subject: {subject}")
        # Implement actual email sending here


class SlackNotifier:
    """Slack notification service."""
    
    def __init__(self, config):
        self.config = config
        
    def send_alert(self, alert):
        """Send a Slack notification for a new alert."""
        webhook_url = self.config["webhook_url"]
        
        # Create Slack message payload
        color_map = {
            "info": "#439FE0",
            "warning": "#FFCC00",
            "error": "#FF9000",
            "critical": "#FF0000"
        }
        
        payload = {
            "attachments": [
                {
                    "fallback": alert["message"],
                    "color": color_map.get(alert["severity"], "#439FE0"),
                    "title": f"[{alert['severity'].upper()}] {alert['message']}",
                    "text": f"*Source*: {alert['source']}\n*Environment*: {alert['environment']}",
                    "fields": [
                        {
                            "title": "Details",
                            "value": json.dumps(alert["details"], indent=2),
                            "short": False
                        }
                    ],
                    "footer": f"Alert ID: {alert['id']}",
                    "ts": int(datetime.fromisoformat(alert["created_at"]).timestamp())
                }
            ]
        }
        
        # Send to Slack
        try:
            response = requests.post(webhook_url, json=payload)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to send Slack notification: {str(e)}")
        
    def send_resolution(self, alert):
        """Send a Slack notification for a resolved alert."""
        webhook_url = self.config["webhook_url"]
        
        payload = {
            "attachments": [
                {
                    "fallback": f"RESOLVED: {alert['message']}",
                    "color": "#36A64F",  # Green for resolved
                    "title": f"RESOLVED: {alert['message']}",
                    "text": f"Alert has been resolved at {alert['resolved_at']}",
                    "footer": f"Alert ID: {alert['id']}",
                    "ts": int(datetime.fromisoformat(alert["resolved_at"]).timestamp())
                }
            ]
        }
        
        # Send to Slack
        try:
            response = requests.post(webhook_url, json=payload)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to send Slack resolution notification: {str(e)}")


class PagerDutyNotifier:
    """PagerDuty notification service."""
    
    def __init__(self, config):
        self.config = config
        
    def send_alert(self, alert):
        """Send a PagerDuty incident for a new alert."""
        service_key = self.config["service_key"]
        
        # Only create PagerDuty incidents for error and critical alerts
        if alert["severity"] not in [AlertSeverity.ERROR, AlertSeverity.CRITICAL]:
            return
            
        payload = {
            "service_key": service_key,
            "event_type": "trigger",
            "incident_key": alert["id"],
            "description": alert["message"],
            "details": alert
        }
        
        try:
            response = requests.post(
                "https://events.pagerduty.com/generic/2010-04-15/create_event.json",
                json=payload
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to create PagerDuty incident: {str(e)}")
        
    def send_resolution(self, alert):
        """Resolve a PagerDuty incident."""
        service_key = self.config["service_key"]
        
        payload = {
            "service_key": service_key,
            "event_type": "resolve",
            "incident_key": alert["id"],
            "description": f"RESOLVED: {alert['message']}",
            "details": {
                "resolution_message": alert.get("resolution_message", "Alert resolved"),
                "resolved_at": alert["resolved_at"]
            }
        }
        
        try:
            response = requests.post(
                "https://events.pagerduty.com/generic/2010-04-15/create_event.json",
                json=payload
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to resolve PagerDuty incident: {str(e)}")