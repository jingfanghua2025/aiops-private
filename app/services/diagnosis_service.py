import os
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.schema import SystemMessage
from langchain.memory import ConversationBufferMemory

class DiagnosisService:
    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_API_BASE", "https://api.deepseek.com")
        model_name = os.getenv("MODEL_NAME", "deepseek-chat")
        
        self.llm = ChatOpenAI(
            model_name=model_name, 
            temperature=0.3,
            openai_api_key=api_key,
            openai_api_base=base_url
        )
        self.memory = ConversationBufferMemory(return_messages=True)

    async def start_diagnosis(self, issue: str):
        system_prompt = """你是一个专业的 SRE 诊断专家。你的目标是通过多轮对话引导用户定位运维问题。
1. 分析用户提供的信息。
2. 如果信息不足，提出排查建议（具体的 Linux 命令）。
3. 如果问题已定位，提供修复方案。"""

        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content=system_prompt),
            MessagesPlaceholder(variable_name="history"),
            ("user", "{input}")
        ])

        chain = prompt | self.llm
        history = self.memory.load_memory_variables({})["history"]
        response = await chain.ainvoke({"input": issue, "history": history})
        self.memory.save_context({"input": issue}, {"output": response.content})
        
        return response.content
