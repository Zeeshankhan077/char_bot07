from flask import Flask, render_template, request, jsonify, session
from chatbot.chat import handle_chat
from dotenv import load_dotenv
from utils.calendly_client import CalendlyClient
import traceback
import os
import logging
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_limiter.errors import RateLimitExceeded

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'some_secret_key')

# Initialize rate limiter
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

# Initialize Calendly client
calendly_client = CalendlyClient()

# Ordered fields to collect and corresponding questions
fields = ['name', 'email', 'budget']
questions = {
    'name': "May I have your name?",
    'email': "What's a good email address to reach you at?",
    'budget': "What's your budget for finding the perfect property?"
}

@app.route("/")
def index():
    logger.info("Serving index page")
    return render_template("index.html")

@app.route("/api/chat", methods=["POST"])
@limiter.limit("10 per minute")
def chat():
    try:
        data = request.get_json(force=True)
        message = data.get("message", "").strip()

        if not message:
            return jsonify({
                "error": "Message cannot be empty.",
                "answer": "Please type a message to continue.",
                "lead_score": 0,
                "lead_status": "Unknown",
                "crm_status": "Skipped",
                "crm_response": "No message provided",
                "raw_llm_reply": ""
            }), 400

        # Initialize session variables if not present
        if 'chat_history' not in session:
            session['chat_history'] = ""
            logger.info("Initializing new chat session")
        if 'user_info' not in session:
            session['user_info'] = {}
        if 'awaiting_field' not in session:
            session['awaiting_field'] = 'name'

        # Get session data
        user_info = session.get('user_info', {})
        chat_history = session.get('chat_history', "")
        awaiting_field = session.get('awaiting_field')

        # Handle user information collection
        if awaiting_field:
            user_info[awaiting_field] = message
            session['user_info'] = user_info
            session.modified = True

            # Determine next field to collect
            if awaiting_field == 'name':
                session['awaiting_field'] = 'email'
                answer = "What's a good email address to reach you at?"
            elif awaiting_field == 'email':
                session['awaiting_field'] = 'budget'
                answer = "What's your budget for finding the perfect property?"
            else:
                session['awaiting_field'] = None
                answer = "Great! Now, how can I help you find the perfect property today?"

            chat_history += f"\nUser: {message}\nBot: {answer}"
            session['chat_history'] = chat_history
            session.modified = True

            return jsonify({
                "answer": answer,
                "lead_score": 10 * len(user_info),
                "lead_status": "Collecting Info",
                "crm_status": "Success",
                "crm_response": "User info updated",
                "raw_llm_reply": ""
            })

        # Normal conversation flow
        result = handle_chat(
            name=user_info.get('name', 'Guest User'),
            email=user_info.get('email', 'guest@example.com'),
            message=message,
            chat_history=chat_history,
            budget=user_info.get('budget', '')
        )

        # Update session with new chat history
        session['chat_history'] = result['chat_history']
        session.modified = True

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error in chat endpoint: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            "error": str(e),
            "answer": "Oops, something went wrong! Let's try again.",
            "lead_score": 0,
            "lead_status": "Unknown",
            "crm_status": "Error",
            "crm_response": "CRM update failed.",
            "raw_llm_reply": ""
        }), 500

@app.route("/api/schedule", methods=["POST"])
def schedule_viewing():
    try:
        data = request.get_json()
        user_email = data.get("email")
        start_time = data.get("start_time")

        if not user_email or not start_time:
            return jsonify({"error": "Email and start time are required"}), 400

        # Create Calendly event
        event = calendly_client.create_event(start_time, user_email)
        if event:
            return jsonify({
                "success": True,
                "booking_url": event.get("booking_url"),
                "event_id": event.get("uri")
            })
        else:
            return jsonify({"error": "Failed to create event"}), 500

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/api/available-times", methods=["GET"])
def get_available_times():
    try:
        start_time = request.args.get("start_time")
        end_time = request.args.get("end_time")

        if not start_time or not end_time:
            return jsonify({"error": "Start time and end time are required"}), 400

        available_times = calendly_client.get_available_times(start_time, end_time)
        if available_times:
            return jsonify(available_times)
        else:
            return jsonify({"error": "Failed to get available times"}), 500

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.errorhandler(RateLimitExceeded)
def handle_ratelimit_error(e):
    return jsonify({
        "error": "Rate limit exceeded",
        "answer": "I apologize, but you've reached the maximum number of requests. Please wait a moment before trying again.",
        "lead_score": 0,
        "lead_status": "Unknown",
        "crm_status": "Skipped",
        "crm_response": "Rate limit exceeded",
        "raw_llm_reply": ""
    }), 429

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"Starting Flask app on port {port}")
    # Set debug to False in production
    debug_mode = os.environ.get("FLASK_DEBUG", "False").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug_mode)