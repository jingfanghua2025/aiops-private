import os
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate

class ScriptService:
    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_API_BASE", "https://api.deepseek.com")
        model_name = os.getenv("MODEL_NAME", "deepseek-chat")
        
        self.llm = ChatOpenAI(
            model_name=model_name, 
            temperature=0.2,
            openai_api_key=api_key,
            openai_api_base=base_url
        )

    async def generate_script(self, requirement: str, language: str = "bash"):
        system_prompt = f"""你是一个资深运维专家。根据用户需求生成高质量、安全、带详细注释的 {language} 脚本。"""
        user_prompt = f"需求: {requirement}\n请直接输出代码块，不要包含解释文字。"

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("user", user_prompt)
        ])

        chain = prompt | self.llm
        response = await chain.ainvoke({})
        return response.content

    def security_check(self, script_content: str):
        dangerous = ["rm -rf /", "mkfs", "dd if=/dev/zero"]
        issues = [f"发现危险命令: {cmd}" for cmd in dangerous if cmd in script_content]
        return {"safe": len(issues) == 0, "issues": issues}
