"""
增强的RAG服务 - 支持多轮对话、上下文理解、精准回答
像Cursor一样流畅和精确
"""
import os
from typing import List, Dict, Optional
import logging
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate
from app.services.ai_service import get_ai_service
from app.services.conversation_service import get_conversation_service

logger = logging.getLogger(__name__)


class EnhancedRAGService:
    """增强的RAG服务，支持多轮对话和精准理解"""
    
    def __init__(self, persist_directory: str = "./chroma_db"):
        self.persist_directory = persist_directory
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_API_BASE", "https://api.deepseek.com")
        
        self.embeddings = OpenAIEmbeddings(
            openai_api_key=api_key, 
            openai_api_base=f"{base_url}/v1"
        )
        
        self.ai_service = get_ai_service()
        self.conversation_service = get_conversation_service()
        
        if os.path.exists(persist_directory):
            self.vector_db = Chroma(
                persist_directory=persist_directory, 
                embedding_function=self.embeddings
            )
        else:
            self.vector_db = None

    def add_documents(self, documents: List):
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
        texts = text_splitter.split_documents(documents)
        if self.vector_db is None:
            self.vector_db = Chroma.from_documents(
                documents=texts,
                embedding=self.embeddings,
                persist_directory=self.persist_directory
            )
        else:
            self.vector_db.add_documents(texts)
        self.vector_db.persist()

    def _build_system_prompt(self, conversation_context: Optional[List[Dict]] = None) -> str:
        """构建系统提示词，根据对话上下文动态调整"""
        base_prompt = """你是一个经验丰富的SRE（站点可靠性工程师）和运维专家。你的任务是准确理解用户的问题，并给出专业、准确、有针对性的回答。

**⚠️ 核心原则（必须严格遵守）**：

1. **100%专注用户需求**
   - 仔细分析用户的问题，理解用户真正想了解的内容
   - 只回答用户明确问的问题，不要添加用户没有问的内容
   - 如果用户问的是A，就只回答A，不要额外介绍B、C、D

2. **精准理解上下文**
   - 如果这是多轮对话，要理解之前的对话内容
   - 理解用户的真实意图，而不仅仅是字面意思
   - 如果用户说"继续"或"还有吗"，要基于之前的对话继续

3. **直接、清晰、实用**
   - 给出直接、明确的答案，不要绕弯子
   - 提供可操作的解决方案和命令示例
   - 使用中文回答（除非用户明确要求其他语言）

4. **禁止过度扩展**
   - 不要因为"可能有用"而添加额外信息
   - 不要"为了完整性"而介绍用户没有问的内容
   - 不要添加"相关推荐"或"你可能还想知道"

**回答格式**：
- 简单问题：直接给出答案
- 复杂问题：分步骤说明，使用列表或代码块
- 涉及命令：提供可直接执行的命令示例
- 多轮对话：要连贯，理解上下文

**示例**：
用户："如何重启Docker容器？"
正确回答："可以使用以下命令：
\`\`\`bash
# 重启指定容器
docker restart <容器名或ID>

# 重启所有运行中的容器
docker restart $(docker ps -q)
\`\`\`"
"""
        
        # 如果有对话上下文，添加上下文说明
        if conversation_context and len(conversation_context) > 1:
            context_info = "\n**当前对话上下文**：\n"
            for msg in conversation_context[-3:]:  # 只取最近3条
                role_name = "用户" if msg["role"] == "user" else "助手"
                content_preview = msg["content"][:100] + "..." if len(msg["content"]) > 100 else msg["content"]
                context_info += f"- {role_name}：{content_preview}\n"
            base_prompt += context_info
        
        return base_prompt

    def query(
        self, 
        question: str, 
        user_id: int,
        conversation_id: Optional[str] = None,
        mode: str = "qa"
    ):
        """
        增强的查询方法，支持多轮对话和精准理解
        
        :param question: 用户问题
        :param user_id: 用户ID
        :param conversation_id: 对话ID（用于多轮对话）
        :param mode: 模式（qa/code）
        """
        try:
            # 获取或创建对话上下文
            conv = self.conversation_service.get_or_create_conversation(user_id, conversation_id)
            conversation_id = conv.conversation_id
            
            # 添加用户消息到上下文
            conv.add_message("user", question, {"mode": mode})
            
            # 获取对话上下文（用于AI理解）
            context_messages = conv.get_recent_messages(max_messages=6)
            
            # 构建系统提示词
            system_prompt = self._build_system_prompt(context_messages)
            
            # 根据模式调整提示词
            if mode == "code":
                system_prompt += "\n**代码编写模式**：用户需要可运行的代码，请直接输出代码，可以包含必要的注释。"
            
            # 构建用户提示词（包含对话历史）
            if len(context_messages) > 1:
                # 多轮对话：构建对话历史
                user_prompt = "以下是我们的对话历史：\n\n"
                for msg in context_messages[:-1]:  # 除了最后一条（当前问题）
                    role_name = "用户" if msg["role"] == "user" else "助手"
                    user_prompt += f"{role_name}：{msg['content']}\n\n"
                user_prompt += f"用户（当前问题）：{question}\n\n请基于以上对话历史回答用户的问题。"
            else:
                # 单轮对话
                user_prompt = question
            
            # 调用AI
            if self.vector_db is None:
                # 没有知识库，直接使用LLM
                answer = self.ai_service.invoke_sync(
                    prompt=user_prompt,
                    system_prompt=system_prompt,
                    temperature=0.3
                )
                sources = ["LLM Knowledge"]
            else:
                # 使用RAG检索增强
                answer, sources = self._query_with_rag(user_prompt, system_prompt)
            
            # 添加助手回复到上下文
            conv.add_message("assistant", answer, {"mode": mode, "sources": sources})
            
            return {
                "answer": answer,
                "sources": sources,
                "conversation_id": conversation_id
            }
        
        except Exception as e:
            logger.error(f"查询失败: {e}", exc_info=True)
            return {
                "answer": f"抱歉，处理您的问题时出现错误：{str(e)}",
                "sources": [],
                "conversation_id": conversation_id if 'conversation_id' in locals() else None
            }

    def _query_with_rag(self, question: str, system_prompt: str) -> tuple:
        """使用RAG检索增强回答"""
        try:
            prompt_template = """你是一个经验丰富的SRE运维专家。请基于以下上下文信息，准确回答用户的问题。

**上下文信息**：
{context}

**用户问题**：
{question}

**回答要求**：
1. 仔细阅读上下文信息，找到与问题相关的部分
2. 如果上下文中包含答案，直接基于上下文回答
3. 如果上下文中没有相关信息，可以结合你的专业知识回答，但要明确说明这是基于通用知识
4. 回答要准确、专业、直接，100%专注用户需求
5. 使用中文回答

请开始回答："""

            from langchain.chains import RetrievalQA
            from langchain_core.prompts import PromptTemplate
            
            qa_prompt = PromptTemplate(
                template=prompt_template,
                input_variables=["context", "question"]
            )
            
            rag_llm = self.ai_service.llm
            
            qa_chain = RetrievalQA.from_chain_type(
                llm=rag_llm,
                chain_type="stuff",
                retriever=self.vector_db.as_retriever(search_kwargs={"k": 3}),
                return_source_documents=True,
                chain_type_kwargs={"prompt": qa_prompt}
            )

            result = qa_chain.invoke({"query": question})
            
            answer = result.get("result", "抱歉，无法生成回答")
            sources = [doc.metadata for doc in result.get("source_documents", [])]
            
            return answer, sources
        
        except Exception as e:
            logger.error(f"RAG查询失败: {e}", exc_info=True)
            # 回退到直接LLM
            answer = self.ai_service.invoke_sync(
                prompt=question,
                system_prompt=system_prompt,
                temperature=0.3
            )
            return answer, ["LLM Knowledge (Fallback)"]



async def stream_ai_response(
    prompt: str,
    system_prompt: str = "",
    temperature: float = 0.3
):
    """
    流式调用 AI 服务 (独立函数)
    """
    from app.services.ai_service import get_ai_service
    from langchain_core.messages import SystemMessage, HumanMessage
    
    ai = get_ai_service()
    # 确保 LLM 支持流式 (ChatOpenAI 默认支持)
    # 这里的 ai.llm 是 langchain 对象
    
    messages = []
    if system_prompt:
        messages.append(SystemMessage(content=system_prompt))
    messages.append(HumanMessage(content=prompt))
    
    try:
        async for chunk in ai.llm.astream(messages):
            content = chunk.content
            if content:
                yield content
    except Exception as e:
        yield f"AI Stream Error: {str(e)}"
