import os
import requests
import logging
from dotenv import load_dotenv
from crm.hubspot_client import create_or_update_contact
from chatbot.vector_search import retrieve_context
from utils.calendly_client import CalendlyClient, CalendlyError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Check if Groq API key is configured
if not GROQ_API_KEY:
    logger.warning("Groq API key not found in environment variables. LLM functionality will be limited.")

# Initialize Calendly client
calendly_client = CalendlyClient()

def calculate_lead_score(user_data):
    """Calculate a lead score based on weighted parameters."""
    score = (
        user_data.get("interest_level", 0) +
        user_data.get("budget_match", 0) +
        user_data.get("engagement_time", 0) +
        user_data.get("follow_up", 0) +
        user_data.get("offer_response", 0) +
        user_data.get("appointment", 0) +
        user_data.get("past_interactions", 0)
    )
    return min(score, 100)

def classify_lead(score):
    """Classify the lead based on score."""
    if score >= 80:
        return "Hot Lead", "Immediate follow-up with personalized offers."
    elif score >= 50:
        return "Warm Lead", "Schedule automated follow-ups and send promotions."
    elif score >= 30:
        return "Cold Lead", "Engage with newsletters and remarketing strategies."
    else:
        return "Unqualified", "Minimal contact. Add to long-term CRM campaigns."

def create_scheduling_suggestion(name, email, property_details=None):
    """Create a scheduling suggestion with Calendly link."""
    try:
        if property_details:
            # Create property-specific consultation link
            booking_link = calendly_client.create_property_consultation_link(
                property_details=property_details,
                invitee_name=name,
                invitee_email=email
            )
        else:
            # Create general consultation link
            result = calendly_client.create_scheduling_link(
                name=name,
                email=email
            )
            booking_link = result.get('booking_link')

        return f"I can help you schedule a consultation. Please use this link to book a time that works for you: {booking_link}"
    except CalendlyError as e:
        return "I apologize, but I'm having trouble creating a scheduling link right now. Please try again later."
    except Exception as e:
        return "I apologize, but I'm having trouble creating a scheduling link right now. Please try again later."

def call_groq_llama(context, question, lead_params):
    """Call Groq's LLaMA API with enhanced prompt."""
    # Check if Groq API key is configured
    if not GROQ_API_KEY:
        logger.warning("Groq API key not found. Using fallback response.")
        return (
            "I'm sorry, but I'm currently operating in limited mode. Please contact support for assistance.",
            50,
            "Warm Lead",
            False,
            "API key not configured"
        )

    # Run garbage collection before making API call to free up memory
    try:
        import gc
        gc.collect()
        logger.debug("Garbage collection run before API call")
    except Exception as e:
        logger.warning(f"Failed to run garbage collection: {str(e)}")

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    system_prompt = (
        "You are a professional real estate assistant for XYZ Real Estate. "
        "Follow these guidelines:\n"
        "1. Keep responses concise (2-3 lines maximum)\n"
        "2. For properties, include only:\n"
        "   - Location and key features\n"
        "   - Price and payment options\n"
        "3. For plots, mention only:\n"
        "   - Plot size and status\n"
        "   - Price and location\n"
        "4. For company info:\n"
        "   - Brief overview\n"
        "   - Key strengths\n"
        "5. For services:\n"
        "   - Main service offerings\n"
        "   - Key benefits\n"
        "6. For offers:\n"
        "   - Current offer details\n"
        "   - Validity period\n"
        "7. Always maintain a professional yet friendly tone\n"
        "8. End with a relevant follow-up question\n"
        "After your response, on a new line output:\n"
        "Lead Score: [score]\n"
        "Qualification: [Hot/Warm/Cold]\n"
        "Schedule Meeting: [true/false]"
    )

    user_prompt = f"""
Previous Chat History:
{context}

Current Question: {question}

Lead Parameters:
- Interest Level: {lead_params['interest_level']}
- Budget Match: {lead_params['budget_match']}
- Engagement Time: {lead_params['engagement_time']}
- Follow-up Shown: {lead_params['follow_up']}
- Offer Response: {lead_params['offer_response']}
- Appointment Scheduled: {lead_params['appointment']}
- Past Interactions: {lead_params['past_interactions']}

Remember to:
1. Provide comprehensive information
2. Include specific details and examples
3. Maintain context from previous messages
4. Suggest relevant next steps
"""
    data = {
        "model": "llama3-70b-8192",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 150,   # Reduced from 300 to 150
        "top_p": 0.9,
        "frequency_penalty": 0.3,
        "presence_penalty": 0.3
    }

    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        result = response.json()
        reply = result["choices"][0]["message"]["content"]

        lines = reply.split('\n')
        short_reply = []
        lead_score = 50
        qualification = "Warm"
        schedule_meeting = False

        for line in lines:
            if "Lead Score:" in line:
                try:
                    lead_score = int(line.split(':')[1].strip())
                except:
                    pass
            elif "Qualification:" in line:
                qualification = line.split(':')[1].strip()
            elif "Schedule Meeting:" in line:
                schedule_meeting = "true" in line.lower()
            else:
                short_reply.append(line)

        short_reply = '\n'.join(short_reply).strip()

        # Run garbage collection after API call to free up memory
        try:
            import gc
            gc.collect()
        except Exception:
            pass

        return short_reply, lead_score, qualification, schedule_meeting, reply

    except requests.RequestException as e:
        return f"Error: {str(e)}", 0, "Unknown", False, str(e)
    except Exception as e:
        return f"Error: {str(e)}", 0, "Unknown", False, str(e)

def handle_chat(name, email, message, chat_history, budget):
    """Handle chat logic with dynamic lead scoring."""
    # Check if this is the first message
    if not chat_history:
        return {
            "answer": "Hello! I'm your real estate assistant. How can I help?",
            "lead_score": 0,
            "lead_status": "Collecting Info",
            "crm_status": "Skipped",
            "crm_response": "Initial greeting",
            "raw_llm_reply": "",
            "chat_history": "Bot: Hello! I'm your real estate assistant. How can I help?"
        }

    # Check for scheduling request
    if any(word in message.lower() for word in ['schedule', 'book', 'appointment', 'meeting', 'call']):
        scheduling_suggestion = create_scheduling_suggestion(name, email)
        return {
            "answer": scheduling_suggestion,
            "lead_score": 80,
            "lead_status": "Hot Lead",
            "crm_status": "Success",
            "crm_response": "Scheduling link provided",
            "raw_llm_reply": scheduling_suggestion,
            "chat_history": chat_history + f"\nUser: {message}\nBot: {scheduling_suggestion}"
        }

    # Maintain more context for better responses
    chat_lines = chat_history.split('\n')
    recent_context = '\n'.join(chat_lines[-3:]) if len(chat_lines) > 3 else chat_history

    # Check if vector search is enabled
    if os.environ.get("ENABLE_VECTOR_SEARCH", "True").lower() == "true":
        try:
            vector_context = retrieve_context(message)
        except Exception as e:
            logger.error(f"Error retrieving vector context: {str(e)}")
            vector_context = ["Vector search unavailable."]
    else:
        vector_context = ["Vector search disabled."]

    context = f"User: name={name}, email={email}, budget={budget}\n{vector_context}\nRecent Chat:\n{recent_context}"
    chat_history += f"\nUser: {message}"

    # Enhanced lead parameters
    num_messages = len([m for m in chat_history.split('\n') if m.startswith('User:')])
    lead_params = {
        "interest_level": min(30, num_messages * 5),
        "budget_match": 20 if budget else 0,
        "engagement_time": min(15, num_messages * 3),
        "follow_up": 10 if "follow up" in message.lower() else 0,
        "offer_response": 10 if "offer" in message.lower() else 0,
        "appointment": 10 if "appointment" in message.lower() else 0,
        "past_interactions": 5 if num_messages > 1 else 0
    }

    # Get response from Groq
    answer, groq_lead_score, groq_qualification, schedule_meeting, full_reply = call_groq_llama(context, message, lead_params)

    # Check for topic repetition
    if len(chat_lines) > 1:
        prev_response = chat_lines[-1]
        if answer.lower() in prev_response.lower():
            # Modify response to avoid repetition
            answer = "Let me provide some additional information: " + answer

    chat_history += f"\nBot: {answer}"

    # Update CRM
    try:
        crm_status_code, crm_response = create_or_update_contact(
            email=email,
            name=name,
            budget=budget,
            lead_type=groq_qualification,
            lead_score=groq_lead_score,
            qualification=groq_qualification,
            chat_history=chat_history,
            user_type="User"
        )
    except:
        crm_status_code, crm_response = 500, "CRM update failed"

    return {
        "answer": answer,
        "lead_score": groq_lead_score,
        "lead_status": groq_qualification,
        "crm_status": "Success" if crm_status_code in [200, 201] else f"Error: {crm_status_code}",
        "crm_response": crm_response,
        "raw_llm_reply": full_reply,
        "chat_history": chat_history
    }
