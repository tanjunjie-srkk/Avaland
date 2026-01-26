import asyncio
from agent_framework.azure import AzureOpenAIChatClient

instructions = "You are a helpful assistant that answers concisely."
name = "TestAgent"

async def main():
    chat_client = AzureOpenAIChatClient(
        api_key="HIqssNjgEFrPz3CaLZzjLAtXosVNRrm5aiKCIRrNSXl9XxAt7zSaJQQJ99CAACHYHv6XJ3w3AAAAACOGpKdo",
        deployment_name="gpt-5.2-chat",
        endpoint="https://tanjj-4934-resource.cognitiveservices.azure.com/openai/responses?api-version=2025-04-01-preview",
        api_version="2024-12-01-preview"
    )

    response = await chat_client.chat(
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Tell me a joke about computers."}
        ]
    )

    print(response.text)


asyncio.run(main())
