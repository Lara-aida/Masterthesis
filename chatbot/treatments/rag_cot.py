import chainlit as cl
from openai import AsyncOpenAI
from dbpedia_lookup import dbpedia_lookup
import json

# Load API key from file
with open("/Users/lara-aidajopp/Documents/Programming_Stuff/Universität Mannheim/Masterthesis/chatbot/api-key-GPT.txt") as f:
    api_key_GPT = f.read().strip()

# Load system prompt
with open("/Users/lara-aidajopp/Documents/Programming_Stuff/Universität Mannheim/Masterthesis/chatbot/treatments/systemprompts/rag_cot.txt") as s:
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
    init_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": message.content},
    ]

    stream = await client.chat.completions.create(
        messages=init_messages,
        stream=True,
        **settings
    )

    msg = await cl.Message(content="").send()

    # Accumulate streamed tool calls by their CHOICE INDEX (stable across deltas)
    pending_tool_calls = {}  # idx -> {"id": None|str, "name": None|str, "arguments": str}
    assistant_text = ""

    async for chunk in stream:
        choice = chunk.choices[0]
        delta = choice.delta

        # stream any plain text tokens the model emits before tools
        if delta.content:
            assistant_text += delta.content
            await msg.stream_token(delta.content)

        # accumulate tool calls by 'index'; append argument chunks
        if delta.tool_calls:
            for tc in delta.tool_calls:
                idx = tc.index  # stable int across deltas for the same tool call
                slot = pending_tool_calls.setdefault(idx, {"id": None, "name": None, "arguments": ""})
                if getattr(tc, "id", None):
                    slot["id"] = tc.id
                if getattr(tc, "function", None):
                    if getattr(tc.function, "name", None):
                        slot["name"] = tc.function.name
                    if getattr(tc.function, "arguments", None):
                        slot["arguments"] += tc.function.arguments

    # If the model answered directly - it ends here
    if not pending_tool_calls:
        await msg.update()
        return

    # Process the tool call
    for idx, slot in sorted(pending_tool_calls.items()):
        # Parse arguments after full stream - as a JSON
        try:
            args = json.loads(slot["arguments"] or "{}")
        except json.JSONDecodeError:
            args = {}

        # if model didn't pass 'query', fall back to user's message
        query = args.get("query") or message.content
        max_results = int(args.get("max_results", 3))

        # Call your tool
        result = await dbpedia_lookup(query, max_results)

        # Decide success vs fallback
        ok = bool(result) and ("error" not in result.lower()) and ("No DBpedia result" not in result)

        if ok:
            # Build the tool result message the model can read
            try:
                dbp_json = json.loads(result)
            except Exception:
                dbp_json = {"raw": result}

            tool_content = json.dumps({"dbpedia_results": dbp_json})
            call_id = slot["id"] or f"tool_{idx}"  # FIX (2): ensure a string id

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
                                "name": slot["name"] or "dbpedia_lookup",
                                "arguments": json.dumps({"query": query, "max_results": max_results})
                            }
                        }
                    ]
                },
                {"role": "tool", "tool_call_id": call_id, "content": tool_content}
            ]

            followup_cfg = {**settings}  # keep tools enabled for this path

        else:
            # fallback — disable tools so it won't try to call again
            followup_messages = [
                {"role": "system",
                 "content": system_prompt + "\n(Note: No DBpedia entity found. Answer yourself without tools. Mark it with AI-generated.)"},
                {"role": "user", "content": message.content}
            ]
            followup_cfg = {**settings, "tools": [], "tool_choice": "none"}

        followup_resp = await client.chat.completions.create(
            messages=followup_messages,
            stream=False,
            **followup_cfg
        )

        final_text = followup_resp.choices[0].message.content or ""
        if final_text:
            await msg.stream_token(final_text)

        # one tool call per turn—break to avoid duplicate answers
        break

    await msg.update()