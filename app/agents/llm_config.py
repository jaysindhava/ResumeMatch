import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq

load_dotenv()


def _collect_keys(prefix: str) -> list[str]:
    """
    Collects all env vars matching a naming pattern like GROQ_API_KEY,
    GROQ_API_KEY_2, GROQ_API_KEY_3, etc. Skips any that aren't set, so
    this works fine with just 1 key or scales up to as many as you add.
    """
    keys = []
    first = os.getenv(prefix)
    if first:
        keys.append(first)
    i = 2
    while True:
        key = os.getenv(f"{prefix}_{i}")
        if not key:
            break
        keys.append(key)
        i += 1
    return keys


groq_keys = _collect_keys("GROQ_API_KEY")
gemini_keys = _collect_keys("GOOGLE_API_KEY")

if not groq_keys:
    raise ValueError("No GROQ_API_KEY found in .env")
if not gemini_keys:
    raise ValueError("No GOOGLE_API_KEY found in .env")

# ChatGroq instances: primary openai/gpt-oss-120b, then qwen/qwen3.8-27b
groq_instances = [
    ChatGroq(model="openai/gpt-oss-120b", temperature=0, api_key=k) for k in groq_keys
] + [
    ChatGroq(model="qwen/qwen3.8-27b", temperature=0, api_key=k) for k in groq_keys
]

# One Gemini instance per key, for both the flash and flash-lite models
gemini_flash_instances = [ChatGoogleGenerativeAI(model="gemini-flash-latest", temperature=0, google_api_key=k) for k in gemini_keys]
gemini_flash_lite_instances = [ChatGoogleGenerativeAI(model="gemini-flash-lite-latest", temperature=0, google_api_key=k) for k in gemini_keys]

print(f"LLM config: {len(groq_keys)} Groq key(s), {len(gemini_keys)} Gemini key(s) loaded.")

# Main chain: tries every Groq key/model first, then Gemini flash, then Gemini flash-lite
llm = groq_instances[0].with_fallbacks(
    groq_instances[1:] + gemini_flash_instances + gemini_flash_lite_instances
)

# Extraction chain: same rotation
extraction_llm = groq_instances[0].with_fallbacks(
    groq_instances[1:] + gemini_flash_instances + gemini_flash_lite_instances
)


def get_text(response) -> str:
    """
    Extracts plain text from an LLM response, regardless of which provider
    answered (Gemini can return structured content blocks with metadata;
    Groq/most others return plain strings).
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
    print("\nTesting rotation chain...")
    response = llm.invoke("Say hello in one short sentence and mention which model you are.")
    print(get_text(response))