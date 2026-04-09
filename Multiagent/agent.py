import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (
    AGENT_OPENAI_API_KEY,
    AGENT_OPENAI_DEPLOYMENT,
    AGENT_OPENAI_ENDPOINT,
    AGENT_OPENAI_API_VERSION,
)

from agent_framework.azure import AzureOpenAIChatClient

instructions = "You are a helpful assistant that answers concisely."
name = "TestAgent"

async def main():
    chat_client = AzureOpenAIChatClient(
        api_key=AGENT_OPENAI_API_KEY,
        deployment_name=AGENT_OPENAI_DEPLOYMENT,
        endpoint=AGENT_OPENAI_ENDPOINT,
        api_version=AGENT_OPENAI_API_VERSION,
    )

    response = await chat_client.chat(
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Tell me a joke about computers."}
        ]
    )

    print(response.text)


asyncio.run(main())
