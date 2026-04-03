"""
Notification System
Handles desktop notifications and sound alerts
"""

import os
import sys
from typing import Optional
from pathlib import Path

from .config import config
from .logger import logger


class NotificationManager:
    """Manages notifications for price alerts and events"""
    
    def __init__(self):
        self.desktop_available = False
        self.sound_available = False
        self.is_foreground = False  # Track if app is in foreground
        
        self._init_desktop_notifications()
        self._init_sound_system()
    
    def _init_desktop_notifications(self):
        """Initialize desktop notification system"""
        if not config.enable_desktop_notifications:
            return
        
        try:
            from plyer import notification
            self.notification = notification
            self.desktop_available = True
            logger.info("Desktop notifications initialized")
        except ImportError:
            logger.warning("plyer not available - desktop notifications disabled")
        except Exception as e:
            logger.warning(f"Failed to initialize desktop notifications: {e}")
    
    def _init_sound_system(self):
        """Initialize sound alert system"""
        if not config.enable_sound_alerts:
            return
        
        try:
            import pygame
            pygame.mixer.init()
            self.pygame = pygame
            self.sound_available = True
            logger.info("Sound system initialized")
        except ImportError:
            logger.warning("pygame not available - sound alerts disabled")
        except Exception as e:
            logger.warning(f"Failed to initialize sound system: {e}")
    
    def set_foreground_status(self, is_foreground: bool):
        """Update whether the app is currently in foreground"""
        self.is_foreground = is_foreground
    
    def notify(self, title: str, message: str, urgency: str = "normal", sound: str = "default"):
        """
        Send a notification
        
        Args:
            title: Notification title
            message: Notification message
            urgency: Urgency level (low, normal, critical)
            sound: Sound to play (default, alert, warning, success)
        """
        logger.alert(f"{title}: {message}")
        
        # Desktop notification (if in background)
        if not self.is_foreground and self.desktop_available:
            self._send_desktop_notification(title, message, urgency)
        
        # Sound alert (if in foreground)
        if self.is_foreground and self.sound_available:
            self._play_sound(sound)
    
    def _send_desktop_notification(self, title: str, message: str, urgency: str = "normal"):
        """Send desktop notification"""
        try:
            self.notification.notify(
                title=title,
                message=message,
                app_name="Pump.fun Bot",
                timeout=10 if urgency == "normal" else 30
            )
        except Exception as e:
            logger.warning(f"Failed to send desktop notification: {e}")
    
    def _play_sound(self, sound_type: str = "default"):
        """Play sound alert"""
        try:
            # For now, use system beep
            # In future, we can add custom sound files
            if sys.platform == "darwin":  # macOS
                os.system('afplay /System/Library/Sounds/Glass.aiff')
            elif sys.platform == "linux":
                os.system('paplay /usr/share/sounds/freedesktop/stereo/bell.oga 2>/dev/null || beep')
            elif sys.platform == "win32":
                import winsound
                frequency = 1000 if sound_type == "default" else 1500
                duration = 200 if sound_type == "default" else 400
                winsound.Beep(frequency, duration)
        except Exception as e:
            logger.debug(f"Could not play sound: {e}")
    
    def price_alert(self, token_name: str, old_price: float, new_price: float, change_percent: float):
        """Send price change alert"""
        direction = "📈" if change_percent > 0 else "📉"
        title = f"{direction} Price Alert: {token_name}"
        message = f"Price changed {change_percent:+.2f}%\n{old_price:.6f} → {new_price:.6f} SOL"
        
        urgency = "critical" if abs(change_percent) > 20 else "normal"
        sound = "alert" if abs(change_percent) > 20 else "default"
        
        self.notify(title, message, urgency, sound)
    
    def volume_alert(self, token_name: str, volume: float, threshold: float):
        """Send volume spike alert"""
        title = f"📊 Volume Alert: {token_name}"
        message = f"Volume spike detected: {volume:.2f} SOL\n(Threshold: {threshold:.2f} SOL)"
        
        self.notify(title, message, "normal", "default")
    
    def mcap_milestone(self, token_name: str, mcap: float):
        """Send market cap milestone alert"""
        title = f"🎯 Milestone Reached: {token_name}"
        
        # Determine milestone
        if mcap >= 1_000_000:
            milestone = f"${mcap/1_000_000:.1f}M"
        elif mcap >= 100_000:
            milestone = f"${mcap/1_000:.0f}K"
        else:
            milestone = f"${mcap:.0f}"
        
        message = f"Market cap reached: {milestone}"
        
        self.notify(title, message, "normal", "success")
    
    def trade_executed(self, action: str, token_name: str, amount: float, price: float):
        """Send trade execution notification"""
        emoji = "🟢" if action.lower() == "buy" else "🔴"
        title = f"{emoji} Trade Executed: {action.upper()}"
        message = f"{token_name}\n{amount:.4f} tokens @ {price:.6f} SOL"
        
        self.notify(title, message, "normal", "success")
    
    def error_alert(self, error_type: str, message: str):
        """Send error alert"""
        title = f"⚠️ Error: {error_type}"
        
        self.notify(title, message, "critical", "warning")
    
    def bonding_curve_complete(self, token_name: str):
        """Send bonding curve completion alert"""
        title = f"🚀 Bonding Curve Complete!"
        message = f"{token_name} has graduated to Raydium"
        
        self.notify(title, message, "critical", "success")


# Global notification manager instance
notification_manager = NotificationManager()
