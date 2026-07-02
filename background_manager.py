"""
Background Command Manager - Tracks active background tasks in Quiz Bot
Prevents multiple simultaneous operations on same quiz/user
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Set, Optional
from enum import Enum

logger = logging.getLogger(__name__)

class CommandType(Enum):
    """Types of background commands"""
    QUIZ_RUNNING = "quiz_running"
    QUIZ_EDITING = "quiz_editing"
    POLL_SENDING = "poll_sending"
    LEADERBOARD_COMPILING = "leaderboard_compiling"
    QUIZ_CREATION = "quiz_creation"

class BackgroundCommand:
    """Represents an active background command"""
    def __init__(self, command_id: str, command_type: CommandType, user_id: int, 
                 chat_id: int, command_name: str):
        self.command_id = command_id
        self.command_type = command_type
        self.user_id = user_id
        self.chat_id = chat_id
        self.command_name = command_name
        self.start_time = datetime.now()
        self.task: Optional[asyncio.Task] = None
    
    def __str__(self):
        elapsed = (datetime.now() - self.start_time).total_seconds()
        return f"{self.command_name} ({elapsed:.1f}s)"

class BackgroundCommandManager:
    """Global manager for all background commands"""
    
    def __init__(self):
        # Dictionary: chat_id -> set of active command IDs
        self.active_commands: Dict[int, Set[str]] = {}
        # Dictionary: command_id -> BackgroundCommand
        self.commands_data: Dict[str, BackgroundCommand] = {}
        # Dictionary: (chat_id, user_id) -> Set of command IDs (user-specific tracking)
        self.user_commands: Dict[tuple, Set[str]] = {}
        self.command_counter = 0
    
    def start_command(self, command_type: CommandType, user_id: int, chat_id: int,
                     command_name: str) -> str:
        """
        Register a new background command
        Returns command_id
        """
        self.command_counter += 1
        command_id = f"bg_{self.command_counter}_{chat_id}_{user_id}"
        
        bg_cmd = BackgroundCommand(command_id, command_type, user_id, chat_id, command_name)
        
        # Add to active commands
        if chat_id not in self.active_commands:
            self.active_commands[chat_id] = set()
        self.active_commands[chat_id].add(command_id)
        
        # Add to user-specific tracking
        user_key = (chat_id, user_id)
        if user_key not in self.user_commands:
            self.user_commands[user_key] = set()
        self.user_commands[user_key].add(command_id)
        
        # Store command data
        self.commands_data[command_id] = bg_cmd
        
        logger.info(f"✅ Background command started: {command_name} (ID: {command_id})")
        return command_id
    
    def end_command(self, command_id: str) -> bool:
        """
        Mark a command as completed
        Returns True if command was found and removed
        """
        if command_id not in self.commands_data:
            logger.warning(f"Command not found: {command_id}")
            return False
        
        bg_cmd = self.commands_data[command_id]
        chat_id = bg_cmd.chat_id
        user_id = bg_cmd.user_id
        
        # Remove from active commands
        if chat_id in self.active_commands:
            self.active_commands[chat_id].discard(command_id)
            if not self.active_commands[chat_id]:
                del self.active_commands[chat_id]
        
        # Remove from user-specific tracking
        user_key = (chat_id, user_id)
        if user_key in self.user_commands:
            self.user_commands[user_key].discard(command_id)
            if not self.user_commands[user_key]:
                del self.user_commands[user_key]
        
        del self.commands_data[command_id]
        
        logger.info(f"✅ Background command completed: {bg_cmd.command_name}")
        return True
    
    def has_active_commands(self, chat_id: Optional[int] = None, 
                           user_id: Optional[int] = None) -> bool:
        """
        Check if there are active commands
        If chat_id provided: check for that chat
        If user_id also provided: check for that user in that chat
        """
        if chat_id is None:
            return bool(self.active_commands)
        
        if user_id is None:
            return chat_id in self.active_commands and bool(self.active_commands[chat_id])
        
        user_key = (chat_id, user_id)
        return bool(self.user_commands.get(user_key, set()))
    
    def get_active_commands(self, chat_id: Optional[int] = None,
                           user_id: Optional[int] = None) -> list:
        """Get list of active command objects"""
        if chat_id is None:
            return list(self.commands_data.values())
        
        if user_id is None:
            cmd_ids = self.active_commands.get(chat_id, set())
            return [self.commands_data[cid] for cid in cmd_ids if cid in self.commands_data]
        
        user_key = (chat_id, user_id)
        cmd_ids = self.user_commands.get(user_key, set())
        return [self.commands_data[cid] for cid in cmd_ids if cid in self.commands_data]
    
    def get_warning_message(self, chat_id: Optional[int] = None,
                           user_id: Optional[int] = None) -> Optional[str]:
        """
        Get warning message if there are active commands
        Returns None if no active commands
        """
        active_cmds = self.get_active_commands(chat_id, user_id)
        
        if not active_cmds:
            return None
        
        warning_header = f"⚠️  **WARNING: {len(active_cmds)} background command(s) active:**\n\n"
        command_list = "\n".join([f"  • {cmd}" for cmd in active_cmds])
        warning_footer = "\n\n⏳ *Please wait for these to complete or use /cancel*"
        
        return warning_header + command_list + warning_footer
    
    def cancel_user_commands(self, chat_id: int, user_id: int) -> int:
        """
        Cancel all commands for a specific user in a chat
        Returns number of commands cancelled
        """
        user_key = (chat_id, user_id)
        cmd_ids = list(self.user_commands.get(user_key, set()))
        
        cancelled_count = 0
        for cmd_id in cmd_ids:
            if self.end_command(cmd_id):
                cancelled_count += 1
        
        logger.info(f"Cancelled {cancelled_count} command(s) for user {user_id} in chat {chat_id}")
        return cancelled_count
    
    def cancel_chat_commands(self, chat_id: int) -> int:
        """
        Cancel all commands in a chat
        Returns number of commands cancelled
        """
        cmd_ids = list(self.active_commands.get(chat_id, set()))
        
        cancelled_count = 0
        for cmd_id in cmd_ids:
            if self.end_command(cmd_id):
                cancelled_count += 1
        
        logger.info(f"Cancelled {cancelled_count} command(s) in chat {chat_id}")
        return cancelled_count

# Global manager instance
bg_manager = BackgroundCommandManager()

# =============================================
# DECORATOR FUNCTIONS
# =============================================

def track_background_command(command_type: CommandType, command_name: str):
    """
    Decorator to automatically track background commands
    
    Usage:
    @track_background_command(CommandType.QUIZ_RUNNING, "Send Poll")
    async def send_next_group_poll(chat_id, context):
        ...
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Extract chat_id from args/kwargs
            chat_id = kwargs.get('chat_id') or (args[0] if args else None)
            user_id = kwargs.get('user_id') or 0
            
            if chat_id is None:
                # If can't determine chat_id, just run the function
                return await func(*args, **kwargs)
            
            # Start tracking
            cmd_id = bg_manager.start_command(command_type, user_id, chat_id, command_name)
            
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                # End tracking
                bg_manager.end_command(cmd_id)
        
        return wrapper
    return decorator

# =============================================
# HELPER FUNCTIONS
# =============================================

async def check_active_commands_before_action(update, chat_id: int, user_id: int,
                                             show_warning: bool = True) -> bool:
    """
    Check if user has active commands before performing an action
    
    Args:
        update: Telegram update object
        chat_id: Chat ID
        user_id: User ID
        show_warning: Whether to send warning message
    
    Returns:
        True if no active commands, False if active commands exist
    """
    if bg_manager.has_active_commands(chat_id, user_id):
        if show_warning:
            warning_msg = bg_manager.get_warning_message(chat_id, user_id)
            if update.callback_query:
                await update.callback_query.answer(warning_msg, show_alert=True)
            else:
                await update.message.reply_text(warning_msg, parse_mode="Markdown")
        
        return False
    
    return True
