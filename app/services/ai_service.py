"""
统一的AI服务，支持多个模型提供商
支持：DeepSeek、豆包（DashScope）、OpenAI等
"""
import os
import json
from typing import Optional, Dict, Any, List
from langchain_openai import ChatOpenAI
from langchain_core.language_models.chat_models import BaseChatModel
import logging

logger = logging.getLogger(__name__)


class AIService:
    """统一的AI服务，支持多个模型提供商"""
    
    def __init__(self, model_provider: Optional[str] = None):
        """
        初始化AI服务
        :param model_provider: 模型提供商，可选值：'deepseek', 'dashscope', 'openai', 'auto'
                               如果为None或'auto'，则根据环境变量自动选择
        """
        self.model_provider = model_provider or os.getenv("AI_MODEL_PROVIDER", "auto")
        self.llm = self._init_llm()  # 暴露llm属性供其他服务使用
    
    def _init_llm(self) -> BaseChatModel:
        """根据配置初始化LLM"""
        if self.model_provider == "auto":
            # 自动选择：优先DeepSeek，其次豆包
            if os.getenv("OPENAI_API_KEY") and os.getenv("OPENAI_API_BASE"):
                self.model_provider = "deepseek"
            elif os.getenv("DASHSCOPE_API_KEY"):
                self.model_provider = "dashscope"
            else:
                self.model_provider = "deepseek"  # 默认
        
        if self.model_provider == "deepseek":
            return self._init_deepseek()
        elif self.model_provider == "dashscope":
            return self._init_dashscope()
        elif self.model_provider == "openai":
            return self._init_openai()
        else:
            logger.warning(f"未知的模型提供商: {self.model_provider}，使用DeepSeek作为默认")
            return self._init_deepseek()
    
    def _init_deepseek(self) -> BaseChatModel:
        """初始化DeepSeek模型"""
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_API_BASE", "https://api.deepseek.com")
        model_name = os.getenv("MODEL_NAME", "deepseek-chat")
        
        if not api_key:
            raise ValueError("DeepSeek需要配置 OPENAI_API_KEY")
        
        return ChatOpenAI(
            model_name=model_name,
            temperature=0.1,
            openai_api_key=api_key,
            openai_api_base=base_url
        )
    
    def _init_dashscope(self) -> BaseChatModel:
        """初始化豆包（DashScope）模型"""
        try:
            # 尝试使用langchain_community的ChatTongyi
            from langchain_community.chat_models import ChatTongyi
            api_key = os.getenv("DASHSCOPE_API_KEY")
            model_name = os.getenv("DASHSCOPE_MODEL_NAME", "qwen-turbo")
            
            if not api_key:
                raise ValueError("豆包需要配置 DASHSCOPE_API_KEY")
            
            return ChatTongyi(
                model=model_name,
                temperature=0.1,
                dashscope_api_key=api_key
            )
        except ImportError:
            # 如果langchain_community没有ChatTongyi，尝试使用OpenAI兼容接口
            logger.warning("ChatTongyi不可用，尝试使用DashScope的OpenAI兼容接口")
            api_key = os.getenv("DASHSCOPE_API_KEY")
            model_name = os.getenv("DASHSCOPE_MODEL_NAME", "qwen-turbo")
            base_url = os.getenv("DASHSCOPE_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1")
            
            if not api_key:
                raise ValueError("豆包需要配置 DASHSCOPE_API_KEY")
            
            # 使用OpenAI兼容接口
            return ChatOpenAI(
                model_name=model_name,
                temperature=0.1,
                openai_api_key=api_key,
                openai_api_base=base_url
            )
    
    def _init_openai(self) -> BaseChatModel:
        """初始化OpenAI模型"""
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
        model_name = os.getenv("MODEL_NAME", "gpt-3.5-turbo")
        
        if not api_key:
            raise ValueError("OpenAI需要配置 OPENAI_API_KEY")
        
        return ChatOpenAI(
            model_name=model_name,
            temperature=0.1,
            openai_api_key=api_key,
            openai_api_base=base_url
        )
    
    async def invoke(self, prompt: str, system_prompt: Optional[str] = None, temperature: Optional[float] = None) -> str:
        """
        调用AI模型
        :param prompt: 用户提示词
        :param system_prompt: 系统提示词（可选）
        :param temperature: 温度参数（可选，覆盖默认值）
        :return: AI返回的文本
        """
        try:
            # 如果指定了temperature，临时修改
            original_temp = self.llm.temperature
            if temperature is not None:
                self.llm.temperature = temperature
            
            # 构建消息
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            
            # 调用模型
            if hasattr(self.llm, 'ainvoke'):
                response = await self.llm.ainvoke(messages if len(messages) > 1 else prompt)
            else:
                response = self.llm.invoke(messages if len(messages) > 1 else prompt)
            
            # 恢复原始temperature
            if temperature is not None:
                self.llm.temperature = original_temp
            
            # 提取内容
            if hasattr(response, 'content'):
                return response.content.strip()
            else:
                return str(response).strip()
        
        except Exception as e:
            logger.error(f"AI调用失败 (provider={self.model_provider}): {e}")
            raise
    
    def invoke_sync(self, prompt: str, system_prompt: Optional[str] = None, temperature: Optional[float] = None) -> str:
        """
        同步调用AI模型
        :param prompt: 用户提示词
        :param system_prompt: 系统提示词（可选）
        :param temperature: 温度参数（可选）
        :return: AI返回的文本
        """
        try:
            original_temp = self.llm.temperature
            if temperature is not None:
                self.llm.temperature = temperature
            
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            
            response = self.llm.invoke(messages if len(messages) > 1 else prompt)
            
            if temperature is not None:
                self.llm.temperature = original_temp
            
            if hasattr(response, 'content'):
                return response.content.strip()
            else:
                return str(response).strip()
        
        except Exception as e:
            logger.error(f"AI调用失败 (provider={self.model_provider}): {e}")
            raise


# 全局单例（延迟初始化）
_ai_service_instance: Optional[AIService] = None


def get_ai_service(model_provider: Optional[str] = None) -> AIService:
    """获取AI服务单例"""
    global _ai_service_instance
    if _ai_service_instance is None:
        _ai_service_instance = AIService(model_provider)
    return _ai_service_instance


def reset_ai_service():
    """重置AI服务（用于测试或重新配置）"""
    global _ai_service_instance
    _ai_service_instance = None

