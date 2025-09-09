import chainlit as cl
from openai import AsyncOpenAI
from dbpedia_lookup import dbpedia_lookup
import json

# Load API key from file
with open("/Users/lara-aidajopp/Documents/Programming_Stuff/Universität Mannheim/Masterthesis/api-key-GPT.txt") as f:
    api_key_GPT = f.read().strip()

# Load system prompt
with open("/Users/lara-aidajopp/Documents/Programming_Stuff/Universität Mannheim/Masterthesis/treatments/systemprompts/rag.txt") as s:
    system_prompt = s.read()

client = AsyncOpenAI(api_key=api_key_GPT)

settings = {
    "model": "gpt-4.1-mini-2025-04-14",
    "temperature": 0,
    "max_completion_tokens": 525,
    "response_format": {"type": "text"},
    "tools": [
        {
            "type": "function",
            "function": {
                "name": "dbpedia_lookup",
                "description": "Look up top 3 matching entities in DBpedia and return dbo:abstract and 5 further properties for each entity.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query string (nouns from user query)"},
                        "max_results": {"type": "integer", "description": "Max results to return"}
                    },
                    "required": ["query"]
                }
            }
        }
    ],
    "tool_choice": "auto"
}

# Handles the chat
@cl.on_message
async def main(message: cl.Message):
    # Load existing or start new history
    history = cl.user_session.get("history", [])

    # Add the current user message
    history.append({"role": "user", "content": message.content})

    # Ensure system prompt is always first
    messages = [{"role": "system", "content": system_prompt}] + history

    # Send conversation to the model
    stream = await client.chat.completions.create(
        messages=messages,
        stream=True,
        **settings
    )

    msg = await cl.Message(content="").send()
    assistant_reply = ""

    # Buffer for tool calls (since arguments arrive in pieces)
    pending_tool_calls = {}

    async for chunk in stream:
        choice = chunk.choices[0]

        # Handle tool calls incrementally
        if choice.delta.tool_calls:
            for tool_call in choice.delta.tool_calls:
                call_id = tool_call.id

                if call_id not in pending_tool_calls:
                    pending_tool_calls[call_id] = {
                        "name": tool_call.function.name,
                        "arguments": ""
                    }

                if tool_call.function.arguments:
                    pending_tool_calls[call_id]["arguments"] += tool_call.function.arguments
                    print("Tool call ongoing. Line 82")

        # Handle streamed text
        if token := choice.delta.content:
            assistant_reply += token
            await msg.stream_token(token)

        # Handle completion
        if choice.finish_reason:
            break

    # Process completed tool calls
    for call_id, call in pending_tool_calls.items():
        print("Final accumulation of calls ongoing. (Line 95)")
        try:
            args = json.loads(call["arguments"])
            print("Parsed arguments: " + json.dumps(args, indent=2))
        except json.JSONDecodeError as e:
            args = {}
            print("Failure.")

        query = args.get("query")
        max_results = args.get("max_results", 3)

        print(f"Calling dbpedia_lookup with query={query}, max_results={max_results}")
        result = await dbpedia_lookup(query, max_results)
        print(f"dbpedia_lookup result:\n{result[:500]}...")

        if "error" in result.lower() or "No DBpedia result" in result:
            fallback = (
                "DBpedia lookup returned no relevant results. "
                "Please generate an AI-based answer instead and mark it as AI-generated. "
                "Follow the system prompt."
            )
            history.append({
                "role": "tool",
                "name": "dbpedia_lookup",
                "content": fallback
            })
        else:
            reminder = (
                "Here are the top 3 DBpedia lookup results. "
                "Select the most relevant entity, "
                "follow the system prompt (use dbo:abstract as main source for your answer, "
                "enrich the answer with the top 3 values of the further 5 properties of the selected entity)."
            )
            history.append({
                "role": "tool",
                "name": "dbpedia_lookup",
                "content": f"{reminder}\n\nResults:\n{result}"
            })

    await msg.update()

    # Save assistant reply
    history.append({"role": "assistant", "content": assistant_reply})
    cl.user_session.set("history", history)