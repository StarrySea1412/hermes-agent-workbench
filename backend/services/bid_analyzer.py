import json
from pathlib import Path
from typing import Optional

from services.encryption_service import get_encryption
from django.conf import settings

OPENAI_COMPATIBLE_PROVIDERS = {
    "openai", "azure", "deepseek", "gemini",
    "kimi", "zhipu", "minimax", "qwen",
    "openrouter", "ollama", "custom",
}

ANTHROPIC_PROVIDERS = {"anthropic"}


class BidAnalyzer:
    def __init__(self, config):
        self.config = config
        self.provider = config.provider or "openai"
        encryption = get_encryption()
        api_key = encryption.decrypt(config.api_key_encrypted)

        if self.provider in ANTHROPIC_PROVIDERS:
            self._init_anthropic_llm(api_key)
        else:
            self._init_openai_llm(api_key)

    def _init_openai_llm(self, api_key):
        from langchain_openai import ChatOpenAI
        self.llm = ChatOpenAI(
            api_key=api_key,
            base_url=self.config.base_url,
            model=self.config.model_name,
            temperature=0.3,
            max_tokens=4000,
        )

    def _init_anthropic_llm(self, api_key):
        try:
            from langchain_anthropic import ChatAnthropic
            self.llm = ChatAnthropic(
                anthropic_api_key=api_key,
                base_url=self.config.base_url,
                model=self.config.model_name,
                temperature=0.3,
                max_tokens=4000,
            )
        except ImportError:
            raise ImportError("langchain-anthropic not installed. Run: pip install langchain-anthropic")

    def _load_document(self, file_path):
        path = Path(file_path)
        suffix = path.suffix.lower()

        if suffix == ".pdf":
            return self._load_pdf(file_path)
        elif suffix in [".docx", ".doc"]:
            return self._load_docx(file_path)
        else:
            return self._load_text(file_path)

    def _load_pdf(self, file_path):
        from langchain_community.document_loaders import PyPDFLoader
        loader = PyPDFLoader(file_path)
        pages = loader.load()
        return "\n\n".join([page.page_content for page in pages])

    def _load_docx(self, file_path):
        from langchain_community.document_loaders import Docx2txtLoader
        loader = Docx2txtLoader(file_path)
        docs = loader.load()
        return "\n\n".join([doc.page_content for doc in docs])

    def _load_text(self, file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()

    def analyze(self, file_path):
        print(f"[BidAnalyzer] 开始分析文件: {file_path}")

        content = self._load_document(file_path)
        print(f"[步骤1/4] 文档加载完成，共 {len(content)} 字符")

        prompt = self._build_analysis_prompt(content)
        print("[步骤3/4] 正在调用AI分析...")
        result = self.llm.invoke(prompt)
        ai_response = result.content
        print(f"[步骤3/4] AI分析完成，返回 {len(ai_response)} 字符")

        parsed = self._parse_result(ai_response)
        print(f"[BidAnalyzer] 分析完成! 项目: {parsed.get('project_name')}")
        return parsed

    def _build_analysis_prompt(self, document_content):
        system_template = """你是一个资深的招投标专家和标书撰写顾问。
你的任务是从招标文件中提取关键信息，并给出专业的建议。

请仔细阅读以下招标文件内容，提取以下信息：
1. 项目名称 - 招标项目的正式名称
2. 项目编号 - 如果有的话
3. 采购人/招标方 - 谁在采购
4. 预算金额 - 项目预算
5. 投标截止时间 - 截止日期
6. 技术要求 - 主要的技术规格、性能要求等（列出关键点）
7. 评分标准 - 评分的关键维度和要点
8. 注意事项 - 特别需要注意的要求或限制
9. 建议章节 - 根据招标要求，建议标书应该包含哪些章节

输出格式要求：必须返回有效的JSON格式，字段如下：
{{
  "project_name": "项目名称",
  "project_number": "项目编号（没有则null）",
  "purchaser": "采购人",
  "budget": "预算金额",
  "deadline": "截止日期",
  "tech_requirements": ["技术要求1", "技术要求2", ...],
  "scoring_criteria": ["评分标准1", "评分标准2", ...],
  "key_points": ["注意点1", "注意点2", ...],
  "suggested_chapters": ["建议章节1", "建议章节2", ...]
}}

重要：只返回JSON，不要有其他文字说明。"""

        user_template = """以下是招标文件内容：

{document_content}

请根据以上内容进行分析，返回JSON格式的结果。"""

        from langchain_core.prompts import ChatPromptTemplate
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_template),
            ("user", user_template)
        ])

        formatted_prompt = prompt.format(document_content=document_content[:15000])
        return formatted_prompt

    def _parse_result(self, ai_response):
        text = ai_response.strip()

        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1])

        try:
            data = json.loads(text)
            return data
        except json.JSONDecodeError:
            start_idx = text.find("{")
            end_idx = text.rfind("}") + 1
            if start_idx != -1 and end_idx > start_idx:
                json_str = text[start_idx:end_idx]
                return json.loads(json_str)

        return {
            "project_name": "解析失败",
            "tech_requirements": [],
            "scoring_criteria": [],
            "key_points": [f"原始响应: {ai_response[:500]}"],
            "suggested_chapters": [],
        }
