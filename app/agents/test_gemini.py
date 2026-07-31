import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

llm = ChatGoogleGenerativeAI(model="gemini-flash-latest", temperature=0)


def get_text(response) -> str:
    """
    Newer Gemini models can return content as a list of structured blocks
    (text + metadata) instead of a plain string. This extracts just the
    actual text, regardless of which format comes back.
    """
    content = response.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return str(content)


if __name__ == "__main__":
    response = llm.invoke("Say hello and confirm you're working, in one short sentence.")
    print(get_text(response))