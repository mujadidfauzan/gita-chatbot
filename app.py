import json
import logging
from datetime import datetime

from flask import Flask, Response, jsonify, render_template, request

from bot import chatbot_with_memory_json
from email_utils import send_email

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Session data store - in a production app, use a proper session management system
sessions = {}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/start", methods=["POST"])
def start_chat():
    # Generate a session ID (in a real app, use proper session management)
    # Here we'll use the email as a simple identifier
    email = request.form.get("email")
    phone = request.form.get("phone")

    if not email or not phone:
        logger.error("Missing email or phone")
        return jsonify({"error": "Email and phone are required"}), 400

    # Initialize session data
    sessions[email] = {
        "email": email,
        "phone": phone,
        "conversation_history": [],
        "start_time": datetime.now().isoformat(),
    }

    logger.info(f"Chat started for user: {email}")
    return jsonify({"status": "OK", "message": "User data received"})


@app.route("/ask", methods=["POST"])
def ask():
    data = request.get_json()
    query = data.get("query", "")
    email = data.get("email", "")

    if not query:
        logger.error("No query provided")
        return jsonify({"error": "No query"}), 400

    if not email or email not in sessions:
        logger.error(f"Invalid session or missing email: {email}")
        return jsonify({"error": "Invalid session"}), 400

    try:
        conversation_history = sessions[email]["conversation_history"]
        # Use the NON-streaming version:
        answer_json = chatbot_with_memory_json(query, conversation_history)
        return jsonify(answer_json)
    except Exception as e:
        logger.error(f"Error generating response: {str(e)}")
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500


def format_conversation_for_email(conversation):
    """Format conversation data for email transcript (plain text version)"""
    transcript = "===== CHAT TRANSCRIPT =====\n\n"

    for entry in conversation:
        timestamp = entry.get("timestamp", "")
        role = entry.get("role", "")
        content = entry.get("content", "")

        # Try to determine if content is JSON and format accordingly
        try:
            if (
                role == "assistant"
                and content.strip().startswith("{")
                and content.strip().endswith("}")
            ):
                json_content = json.loads(content)
                formatted_content = format_json_content(json_content)
                content = formatted_content
        except:
            # If parsing fails, use the original content
            pass

        # Format based on role
        if role == "user":
            transcript += f"[USER] {timestamp}\n{content}\n\n"
        elif role == "assistant":
            transcript += f"[GITA] {timestamp}\n{content}\n\n"

    transcript += "===== END OF TRANSCRIPT ====="
    return transcript


def format_html_conversation_for_email(conversation):
    """Format conversation data for email transcript (HTML version)"""
    transcript = "<h2>Chat Transcript</h2>"

    for entry in conversation:
        timestamp = entry.get("timestamp", "")
        role = entry.get("role", "")
        content = entry.get("content", "")

        # Try to determine if content is JSON and format accordingly
        try:
            if (
                role == "assistant"
                and content.strip().startswith("{")
                and content.strip().endswith("}")
            ):
                json_content = json.loads(content)
                formatted_content = format_json_content_html(json_content)
                content = formatted_content
        except:
            # If parsing fails, use the original content and escape HTML
            content = (
                content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            )
            content = content.replace("\n", "<br>")

        # Format based on role with different styling
        if role == "user":
            transcript += f'<div class="user-message"><p><strong>[USER]</strong> {timestamp}</p><p>{content}</p></div>'
        elif role == "assistant":
            transcript += f'<div class="bot-message"><p><strong>[GITA]</strong> {timestamp}</p><p>{content}</p></div>'

    return transcript


def format_json_content(json_data):
    """Format JSON content for better readability in plain text emails"""
    formatted = ""

    if "title" in json_data and json_data["title"]:
        formatted += f"--- {json_data['title']} ---\n\n"

    if "paragraphs" in json_data and json_data["paragraphs"]:
        for p in json_data["paragraphs"]:
            formatted += f"{p}\n\n"

    if "bullets" in json_data and json_data["bullets"]:
        for i, b in enumerate(json_data["bullets"], 1):
            formatted += f"{i}. {b}\n"
        formatted += "\n"

    if "info_lain" in json_data and json_data["info_lain"]:
        formatted += f"Info Lain: {json_data['info_lain']}\n"

    return formatted


def format_json_content_html(json_data):
    """Format JSON content for better readability in HTML emails"""
    formatted = ""

    if "title" in json_data and json_data["title"]:
        formatted += f"<h3>{json_data['title']}</h3>"

    if "paragraphs" in json_data and json_data["paragraphs"]:
        for p in json_data["paragraphs"]:
            formatted += f"<p>{p}</p>"

    if "bullets" in json_data and json_data["bullets"]:
        formatted += "<ul>"
        for b in json_data["bullets"]:
            formatted += f"<li>{b}</li>"
        formatted += "</ul>"

    if "info_lain" in json_data and json_data["info_lain"]:
        formatted += f"<p> {json_data['info_lain']}</p>"

    return formatted


@app.route("/finish", methods=["POST"])
def finish_chat():
    # For sendBeacon requests, content-type might be different
    if request.content_type and "application/json" in request.content_type:
        data = request.get_json()
    else:
        try:
            # Try to parse data from raw request body
            data = json.loads(request.data.decode("utf-8"))
        except:
            logger.error("Unable to parse request data")
            return jsonify({"error": "Invalid data format", "status": "ERROR"}), 400

    email = data.get("email", "")
    phone = data.get("phone", "")
    conversation = data.get("conversation", [])

    if not email or not phone:
        logger.error("Missing email or phone")
        return (
            jsonify({"error": "Email and phone are required", "status": "ERROR"}),
            400,
        )

    # Format conversation for email
    plain_transcript = format_conversation_for_email(conversation)
    html_transcript = format_html_conversation_for_email(conversation)

    # Send email with transcript
    try:
        send_email(plain_transcript, email, phone, html_transcript=html_transcript)
        logger.info(f"Chat transcript sent for user: {email}")

        # Clean up session if it exists
        if email in sessions:
            del sessions[email]

        return jsonify(
            {
                "status": "OK",
                "message": "Chat ended & transcript sent via email successfully.",
            }
        )
    except Exception as e:
        logger.error(f"Error sending email: {str(e)}")

        # Create a backup of the transcript
        try:
            import time  # Add this import at the top of your file

            backup_file = f"transcript_backup_{email}_{int(time.time())}.txt"
            with open(backup_file, "w") as f:
                f.write(plain_transcript)
            logger.info(f"Transcript backup saved to {backup_file}")

            return (
                jsonify(
                    {
                        "status": "PARTIAL",
                        "message": "Chat ended, but we couldn't send the email transcript. A backup has been saved.",
                    }
                ),
                500,
            )
        except Exception as backup_error:
            logger.error(f"Failed to create transcript backup: {str(backup_error)}")
            return (
                jsonify(
                    {
                        "status": "ERROR",
                        "message": "Failed to send email and create backup. Please contact support.",
                    }
                ),
                500,
            )


if __name__ == "__main__":
    app.run(debug=True)
