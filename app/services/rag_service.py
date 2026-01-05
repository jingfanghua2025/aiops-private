import os
from typing import List
import logging
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate
from app.services.ai_service import get_ai_service

logger = logging.getLogger(__name__)


class RAGService:
    def __init__(self, persist_directory: str = "./chroma_db"):
        self.persist_directory = persist_directory
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_API_BASE", "https://api.deepseek.com")
        
        # 使用 OpenAI 兼容接口对接 DeepSeek（用于embeddings）
        self.embeddings = OpenAIEmbeddings(
            openai_api_key=api_key, 
            openai_api_base=f"{base_url}/v1"
        )
        
        # 使用统一的AI服务（支持多模型）
        self.ai_service = get_ai_service()
        
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

    def query(self, question: str):
        """
        改进的查询方法，使用更好的提示词避免答非所问
        """
        # 改进的系统提示词：严格禁止答非所问
        system_prompt = """你是一个经验丰富的SRE（站点可靠性工程师）和运维专家。你的任务是准确理解用户的问题，并给出专业、准确、有针对性的回答。

**⚠️ 核心原则（必须严格遵守）**：
1. **严格按用户问题回答，禁止添加用户没有问的内容**
   - 如果用户问"如何重启服务"，就只回答重启服务的方法，不要额外介绍服务管理、监控、日志等
   - 如果用户问"如何查看文件"，就只回答查看文件的方法，不要额外介绍文件编辑、权限、备份等
   - 如果用户问"什么是Docker"，就只回答Docker的定义和基本概念，不要额外介绍Kubernetes、容器编排等

2. **直接回答问题，不要偏离主题**
   - 仔细分析用户的问题，理解用户真正想了解的内容
   - 针对用户的问题给出直接、明确的答案
   - 不要因为"可能有用"而添加用户没有问的信息

3. **禁止过度扩展**
   - 不要因为用户问了A，就自动介绍B、C、D相关内容
   - 不要"为了完整性"而添加用户没有要求的信息
   - 不要"以防万一"而添加额外的说明（除非用户明确要求）

4. **使用中文回答**：除非用户明确要求使用其他语言，否则使用中文回答

5. **专业且实用**：提供专业、可操作的运维建议和解决方案

**❌ 错误示例（答非所问）**：
用户问题："如何重启Docker容器？"
错误回答："重启Docker容器可以使用docker restart命令。另外，Docker还有很多其他命令，比如docker ps查看容器、docker logs查看日志、docker exec进入容器...（继续介绍很多用户没有问的内容）"  // ❌ 用户只问了如何重启，不要介绍其他命令

**✅ 正确示例（只回答用户问的）**：
用户问题："如何重启Docker容器？"
正确回答："可以使用以下命令重启Docker容器：
1. 重启指定容器：docker restart <容器名或ID>
2. 重启所有运行中的容器：docker restart $(docker ps -q)
如果需要先停止再启动，可以使用：docker stop <容器名> 然后 docker start <容器名>"  // ✅ 只回答用户问的重启方法

**回答格式**：
- 如果问题简单，直接给出答案
- 如果问题复杂，可以分步骤说明
- 可以适当使用列表、代码块等格式提高可读性
- 如果涉及命令，提供可直接执行的命令示例"""

        if self.vector_db is None:
            # 即使没有知识库，也可以直接用 LLM 回答
            try:
                answer = self.ai_service.invoke_sync(
                    prompt=question,
                    system_prompt=system_prompt,
                    temperature=0.3
                )
                return {"answer": answer, "sources": ["LLM Knowledge"]}
            except Exception as e:
                logger.error(f"AI查询失败: {e}", exc_info=True)
                return {
                    "answer": f"抱歉，处理您的问题时出现错误：{str(e)}",
                    "sources": []
                }

        # 使用RAG检索增强回答
        try:
            # 改进的提示词模板
            prompt_template = """你是一个经验丰富的SRE运维专家。请基于以下上下文信息，准确回答用户的问题。

**上下文信息**：
{context}

**用户问题**：
{question}

**回答要求**：
1. 仔细阅读上下文信息，找到与问题相关的部分
2. 如果上下文中包含答案，直接基于上下文回答
3. 如果上下文中没有相关信息，可以结合你的专业知识回答，但要明确说明这是基于通用知识
4. 回答要准确、专业、直接，不要答非所问
5. 使用中文回答

请开始回答："""

            # 使用langchain的RetrievalQA，但我们需要自定义prompt
            from langchain.chains import RetrievalQA
            from langchain_core.prompts import PromptTemplate
            
            qa_prompt = PromptTemplate(
                template=prompt_template,
                input_variables=["context", "question"]
            )
            
            # 创建QA链
            # 使用统一AI服务的LLM（ai_service暴露了llm属性）
            qa_chain = RetrievalQA.from_chain_type(
                llm=self.ai_service.llm,
                chain_type="stuff",
                retriever=self.vector_db.as_retriever(search_kwargs={"k": 3}),  # 检索前3个相关文档
                return_source_documents=True,
                chain_type_kwargs={"prompt": qa_prompt}
            )

            result = qa_chain.invoke({"query": question})
            
            return {
                "answer": result.get("result", "抱歉，无法生成回答"),
                "sources": [doc.metadata for doc in result.get("source_documents", [])]
            }
        
        except Exception as e:
            logger.error(f"RAG查询失败: {e}", exc_info=True)
            # 回退到直接LLM回答
            try:
                answer = self.ai_service.invoke_sync(
                    prompt=question,
                    system_prompt=system_prompt,
                    temperature=0.3
                )
                return {"answer": answer, "sources": ["LLM Knowledge (Fallback)"]}
            except Exception as e2:
                logger.error(f"回退查询也失败: {e2}", exc_info=True)
                return {
                    "answer": f"抱歉，处理您的问题时出现错误：{str(e2)}",
                    "sources": []
                }
