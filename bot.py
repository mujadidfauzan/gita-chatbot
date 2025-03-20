import json
import os
import time
from typing import Dict, Generator, List

import requests
from dotenv import load_dotenv
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

load_dotenv()
api_key = os.getenv("KEY_API_OPENROUTER")
if not api_key:
    raise ValueError(
        "API key not found. Please set KEY_API_OPENROUTER in your environment"
    )

# Initialize embedding model & vector store
embedding_model = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
vectorstore = FAISS.load_local(
    "faiss_index2",
    embedding_model,
    allow_dangerous_deserialization=True,
)


def get_relevant_context(query: str) -> str:
    """Get relevant document context for a query."""
    retriever = vectorstore.as_retriever()
    related_docs = retriever.invoke(query)
    return "\n".join(doc.page_content for doc in related_docs)


def prepare_messages(
    query: str, conversation_history: List[Dict], context: str
) -> List[Dict]:
    """Prepare messages for the API call."""
    system_prompt = (
        "Kamu adalah asisten AI bernama GITA yang dirancang untuk menjawab segala pertanyaan tentang perusahaan ini. "
        "Bertindaklah sebagai customer service dan kamu merupakan bagian dari perusahaan kami! "
        "Gunakan database yang tersedia untuk memberikan jawaban yang akurat dan relevan. "
        "Jawablah secara alami, jelas, dan informatif dan Pastikan jawaban merupakan jawaban yang ringkas dan tidak terlalu panjang, tetapi tetap informatif dan menarik "
        "Jawablah hanya dalam format JSON valid, "
        "dengan struktur minimal sbb:\n"
        "{\n"
        '  "title": string,\n'
        '  "paragraphs": ["...", "..."],\n'
        '  "bullets": ["...", "..."],\n'
        '  "info_lain": " "\n'
        "}\n"
        "Pastikan output benar-benar JSON (tanpa tambahan kata lain di luar JSON). "
        "Jangan gunakan emot atau kalimat di luar struktur JSON."
    )

    messages = [{"role": "system", "content": system_prompt}]
    # Add previous conversation to messages
    messages.extend(conversation_history)
    # Add user message with context + query
    messages.append(
        {
            "role": "user",
            "content": f"Informasi database:\n{context}\n\nPertanyaan: {query}",
        }
    )

    return messages


def chatbot_with_memory_json(
    query: str, conversation_history: List[Dict] = None
) -> Dict:
    """
    Non-streaming version of the chatbot.
    Returns a Python dict.
    """
    if conversation_history is None:
        conversation_history = []

    # Get relevant context
    context = get_relevant_context(query)

    # Prepare messages
    messages = prepare_messages(query, conversation_history, context)

    # Make request
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "deepseek/deepseek-r1:free",  # Change model as needed
        "messages": messages,
        "stream": False,
        "temperature": 0.3,
        "presence_penalty": 0.5,
        "frequency_penalty": 0.5,
    }

    resp = requests.post(url, headers=headers, json=payload)
    data = resp.json()

    # Get answer text (should be JSON string)
    answer_text = data["choices"][0]["message"]["content"]
    # print(f"Response from API: {answer_text}")

    # Try to parse JSON
    try:
        answer_json = json.loads(answer_text)
        # print(f"Parsed JSON: {answer_json}")
    except Exception as e:
        # Fallback if parsing fails
        answer_json = {
            "title": "Error",
            # "paragraphs": "{Coba Lagi}",
        }

    # Record conversation history
    conversation_history.append({"role": "user", "content": query})
    conversation_history.append({"role": "assistant", "content": answer_text})

    return answer_json


def chatbot_with_memory_json_stream(
    query: str, conversation_history: List[Dict] = None
) -> Generator[Dict, None, None]:
    """
    Streaming version of the chatbot.
    Yields partial JSON objects as they are received.
    """
    if conversation_history is None:
        conversation_history = []

    # Get relevant context
    context = get_relevant_context(query)

    # Prepare messages
    messages = prepare_messages(query, conversation_history, context)

    # Make streaming request
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    payload = {
        "model": "deepseek/deepseek-r1:free",  # Change model as needed
        "messages": messages,
        "stream": True,  # Enable streaming
        "temperature": 0.3,
        "presence_penalty": 0.5,
        "frequency_penalty": 0.5,
    }

    # Use stream=True for requests to handle SSE
    response = requests.post(url, headers=headers, json=payload, stream=True)

    if response.status_code != 200:
        error_json = {
            "title": "Error",
            "paragraphs": [f"Error: {response.status_code}", response.text],
            "bullets": [],
            "info_lain": "Ada kesalahan dalam permintaan",
        }
        yield error_json
        return

    # Track conversation for history update
    conversation_history.append({"role": "user", "content": query})

    # Process the streaming response
    buffer = ""
    accumulated_json = {"title": "", "paragraphs": [], "bullets": [], "info_lain": ""}

    for line in response.iter_lines():
        if line:
            line = line.decode("utf-8")

            # Skip lines that don't contain data
            if not line.startswith("data: "):
                continue

            # Extract the data part
            data = line[6:]  # Remove 'data: ' prefix

            # Skip [DONE] message
            if data == "[DONE]":
                break

            try:
                # Parse the JSON data
                chunk = json.loads(data)

                # Extract text content
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                content = delta.get("content", "")

                if content:
                    buffer += content

                    # Try to parse accumulated buffer as JSON
                    try:
                        # As we receive chunks, some might be partial JSON
                        # We'll try to extract what we can from the buffer
                        # and update our accumulated JSON

                        # Simple approach: look for complete JSON fields
                        if '"title":' in buffer and accumulated_json["title"] == "":
                            # Try to extract title
                            title_start = buffer.find('"title"') + 8
                            title_end = buffer.find('"', title_start + 2)
                            if title_end > title_start:
                                accumulated_json["title"] = buffer[
                                    title_start + 1 : title_end
                                ]

                        # Extract paragraphs (simplified approach)
                        if '"paragraphs":' in buffer:
                            para_match = buffer.find('"paragraphs"')
                            if para_match > -1 and "]" in buffer[para_match:]:
                                # Try to extract complete paragraphs array
                                para_start = buffer.find("[", para_match)
                                para_end = buffer.find("]", para_start)
                                if para_end > para_start:
                                    para_json = buffer[para_start : para_end + 1]
                                    try:
                                        paras = json.loads(para_json)
                                        accumulated_json["paragraphs"] = paras
                                    except:
                                        pass

                        # Extract bullets (simplified approach)
                        if '"bullets":' in buffer:
                            bullet_match = buffer.find('"bullets"')
                            if bullet_match > -1 and "]" in buffer[bullet_match:]:
                                # Try to extract complete bullets array
                                bullet_start = buffer.find("[", bullet_match)
                                bullet_end = buffer.find("]", bullet_start)
                                if bullet_end > bullet_start:
                                    bullet_json = buffer[bullet_start : bullet_end + 1]
                                    try:
                                        bullets = json.loads(bullet_json)
                                        accumulated_json["bullets"] = bullets
                                    except:
                                        pass

                        # Extract info_lain
                        if '"info_lain":' in buffer:
                            info_start = buffer.find('"info_lain"') + 12
                            info_end = buffer.find('"', info_start + 2)
                            if info_end > info_start:
                                accumulated_json["info_lain"] = buffer[
                                    info_start + 1 : info_end
                                ]

                        # See if we now have a complete JSON
                        try:
                            complete_json = json.loads(buffer)
                            accumulated_json = complete_json  # If we parsed successfully, use the complete JSON
                            # But still yield incremental updates
                        except:
                            # Continue accumulating parts
                            pass

                        # Yield the current state
                        yield accumulated_json

                    except json.JSONDecodeError:
                        # Continue accumulating until we get valid JSON
                        pass

            except json.JSONDecodeError:
                # Skip invalid JSON
                continue

    # Try to parse the complete buffer at the end
    try:
        final_json = json.loads(buffer)
        yield final_json
        conversation_history.append({"role": "assistant", "content": buffer})
    except json.JSONDecodeError:
        # If we still can't parse it, yield whatever we've accumulated
        yield accumulated_json
        conversation_history.append(
            {"role": "assistant", "content": json.dumps(accumulated_json)}
        )
