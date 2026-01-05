"""
对话上下文管理服务
支持多轮对话，保持上下文连贯性，像Cursor一样流畅
"""
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import json
import logging

logger = logging.getLogger(__name__)


class ConversationContext:
    """对话上下文管理"""
    
    def __init__(self, user_id: int, conversation_id: Optional[str] = None):
        self.user_id = user_id
        self.conversation_id = conversation_id or f"conv_{user_id}_{int(datetime.now().timestamp())}"
        self.messages: List[Dict] = []
        self.created_at = datetime.now()
        self.last_updated = datetime.now()
        self.metadata: Dict = {}
    
    def add_message(self, role: str, content: str, metadata: Optional[Dict] = None):
        """添加消息到上下文"""
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {}
        }
        self.messages.append(message)
        self.last_updated = datetime.now()
    
    def get_recent_messages(self, max_messages: int = 10) -> List[Dict]:
        """获取最近的对话消息（用于上下文）"""
        return self.messages[-max_messages:] if len(self.messages) > max_messages else self.messages
    
    def get_conversation_summary(self) -> str:
        """生成对话摘要（用于长对话的上下文压缩）"""
        if not self.messages:
            return ""
        
        user_messages = [m for m in self.messages if m["role"] == "user"]
        assistant_messages = [m for m in self.messages if m["role"] == "assistant"]
        
        summary = f"对话包含 {len(user_messages)} 条用户消息和 {len(assistant_messages)} 条助手回复。"
        if user_messages:
            summary += f" 最近用户问题：{user_messages[-1]['content'][:100]}"
        return summary
    
    def clear(self):
        """清空对话历史"""
        self.messages = []
        self.last_updated = datetime.now()
    
    def to_dict(self) -> Dict:
        """转换为字典（用于存储）"""
        return {
            "conversation_id": self.conversation_id,
            "user_id": self.user_id,
            "messages": self.messages,
            "created_at": self.created_at.isoformat(),
            "last_updated": self.last_updated.isoformat(),
            "metadata": self.metadata
        }


class ConversationService:
    """对话服务管理器"""
    
    def __init__(self):
        # 内存存储（生产环境可改为Redis或数据库）
        self.conversations: Dict[str, ConversationContext] = {}
        self.user_conversations: Dict[int, List[str]] = {}  # user_id -> [conversation_ids]
        self.max_conversation_age = timedelta(hours=24)  # 24小时后清理旧对话
    
    def get_or_create_conversation(self, user_id: int, conversation_id: Optional[str] = None) -> ConversationContext:
        """获取或创建对话上下文"""
        if conversation_id and conversation_id in self.conversations:
            conv = self.conversations[conversation_id]
            # 检查是否过期
            if datetime.now() - conv.last_updated > self.max_conversation_age:
                logger.info(f"对话 {conversation_id} 已过期，创建新对话")
                del self.conversations[conversation_id]
                return self._create_new_conversation(user_id)
            return conv
        
        return self._create_new_conversation(user_id)
    
    def _create_new_conversation(self, user_id: int) -> ConversationContext:
        """创建新对话"""
        conv = ConversationContext(user_id)
        self.conversations[conv.conversation_id] = conv
        
        if user_id not in self.user_conversations:
            self.user_conversations[user_id] = []
        self.user_conversations[user_id].append(conv.conversation_id)
        
        logger.info(f"为用户 {user_id} 创建新对话 {conv.conversation_id}")
        return conv
    
    def add_message(self, conversation_id: str, role: str, content: str, metadata: Optional[Dict] = None):
        """添加消息到对话"""
        if conversation_id in self.conversations:
            self.conversations[conversation_id].add_message(role, content, metadata)
        else:
            logger.warning(f"对话 {conversation_id} 不存在")
    
    def get_conversation_context(self, conversation_id: str, max_messages: int = 10) -> List[Dict]:
        """获取对话上下文（用于AI理解）"""
        if conversation_id in self.conversations:
            return self.conversations[conversation_id].get_recent_messages(max_messages)
        return []
    
    def clear_conversation(self, conversation_id: str):
        """清空对话历史"""
        if conversation_id in self.conversations:
            self.conversations[conversation_id].clear()
    
    def delete_conversation(self, conversation_id: str):
        """删除对话"""
        if conversation_id in self.conversations:
            conv = self.conversations[conversation_id]
            user_id = conv.user_id
            del self.conversations[conversation_id]
            
            if user_id in self.user_conversations:
                self.user_conversations[user_id] = [
                    cid for cid in self.user_conversations[user_id] if cid != conversation_id
                ]
    
    def cleanup_old_conversations(self):
        """清理过期对话"""
        now = datetime.now()
        expired = []
        for conv_id, conv in self.conversations.items():
            if now - conv.last_updated > self.max_conversation_age:
                expired.append(conv_id)
        
        for conv_id in expired:
            self.delete_conversation(conv_id)
        
        if expired:
            logger.info(f"清理了 {len(expired)} 个过期对话")


# 全局单例
_conversation_service = ConversationService()


def get_conversation_service() -> ConversationService:
    """获取对话服务单例"""
    return _conversation_service

