import chainlit as cl
from openai import AsyncOpenAI

with open("/Users/lara-aidajopp/Documents/Programming_Stuff/Universität Mannheim/Masterthesis/api-key-GPT.txt") as f:
    api_key_GPT = f.read().strip()

client = AsyncOpenAI(api_key=api_key_GPT)

settings = {
    "model": "gpt-4.1-mini-2025-04-14",
    "temperature": 0,
    "max_completion_tokens": 400,
    "response_format": {"type":"text"},
    "tools": [],
    "tool_choice": "auto",
}

@cl.on_message
async def main(message: cl.Message):

    stream = await client.chat.completions.create(
        messages=[
            {"role": "system", "content": "You are an helpful assistant."},

            {
                "role": "user",
                "content": message.content,
            }
        ], stream=True, **settings
    )

    # Create a new message and stream the response
    msg = await cl.Message(content="").send()
    async for chunk in stream:
        if token := chunk.choices[0].delta.content:
            await msg.stream_token(token)

    await msg.update()