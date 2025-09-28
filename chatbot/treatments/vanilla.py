import chainlit as cl
from openai import AsyncOpenAI

# Load API key from file
with open("/Users/lara-aidajopp/Documents/Programming_Stuff/Universität Mannheim/Masterthesis/api-key-GPT.txt") as f:
    api_key_GPT = f.read().strip()

with open ("/Users/lara-aidajopp/Documents/Programming_Stuff/Universität Mannheim/Masterthesis/treatments/systemprompts/vanilla.txt") as s:
    system_prompt = s.read()

client = AsyncOpenAI(api_key=api_key_GPT)

settings = {
    "model": "gpt-4.1-mini-2025-04-14",
    "temperature": 0,
    "max_completion_tokens": 525,
    "response_format": {"type": "text"},
    "tools": [],
    "tool_choice": "auto"
}

@cl.on_message
async def main(message: cl.Message):
    # Load existing or start new history
    history = cl.user_session.get("history", [])

    # Add the current user message and enlarge the history of the current session
    history.append({"role": "user", "content": message.content})

    # Ensure that the system prompt comes first, to ensure that the history is considered always
    messages = [{"role": "system", "content": system_prompt}] + history

    # Send the conversation history to the model's API
    stream = await client.chat.completions.create(
        messages=messages,
        stream=True,
        **settings
    )

    # Chainlit message without history
    msg = await cl.Message(content="").send()

    # Collect the assistant's reply
    assistant_reply = ""
    async for chunk in stream:
        if token := chunk.choices[0].delta.content:
            assistant_reply += token
            await msg.stream_token(token)

    await msg.update()

    # Add the assistants reply to history
    history.append({"role": "assistant", "content": assistant_reply})
    cl.user_session.set("history", history)
