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

@cl.on_message
async def main(message: cl.Message):
    # First call: model may request a tool
    init_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": message.content}
    ]

    stream = await client.chat.completions.create(
        messages=init_messages,
        stream=True,
        **settings
    )

    msg = await cl.Message(content="").send()
    assistant_reply = ""
    pending_tool_calls = {}

    async for chunk in stream:
        choice = chunk.choices[0]

        # Capture tool calls
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
                    print("Tool call ongoing...")

        # Stream any plain text tokens (in case model responds directly)
        if token := choice.delta.content:
            assistant_reply += token
            await msg.stream_token(token)

        if choice.finish_reason:
            break

    # Process tool calls
    for call_id, call in pending_tool_calls.items():
        try:
            args = json.loads(call["arguments"])
            print("Parsed tool args:\n" + json.dumps(args, indent=2))
        except json.JSONDecodeError:
            args = {}
            print("Failed to parse tool arguments")

        query = args.get("query")
        max_results = args.get("max_results", 3)

        print(f"Calling dbpedia_lookup with query={query}, max_results={max_results}")
        result = await dbpedia_lookup(query, max_results)

        if "error" in result.lower() or "No DBpedia result" in result:
            tool_content = (
                "DBpedia lookup returned no relevant results. "
                "Please generate an AI-based answer instead and mark it as AI-generated. "
                "Follow the system prompt."
            )
        else:
            reminder = (
                "Here are the top 3 DBpedia lookup results. "
                "Select the most relevant entity, "
                "follow the system prompt (use dbo:abstract as main source for your answer, "
                "enrich the answer with the top 3 values of the further 5 properties of the selected entity)."
            )
            tool_content = f"{reminder}\n\nResults:\n{result}"

        # Rebuild clean conversation for follow-up
        followup_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message.content},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": "dbpedia_lookup",
                            "arguments": json.dumps(args)
                        }
                    }
                ]
            },
            {"role": "tool", "tool_call_id": call_id, "content": tool_content}
        ]

        # Second pass: model generates final answer with tool results
        followup_stream = await client.chat.completions.create(
            messages=followup_messages,
            stream=True,
            **settings
        )
        async for chunk in followup_stream:
            choice = chunk.choices[0]
            if token := choice.delta.content:
                assistant_reply += token
                await msg.stream_token(token)
            if choice.finish_reason:
                break

    await msg.update()