import requests
import os
import json
import logging
from datetime import datetime
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
# Get API key from environment variables
HUBSPOT_API_KEY = os.getenv('HUBSPOT_API_KEY')

# Check if API key is present
if not HUBSPOT_API_KEY:
    logger.warning("HubSpot API key not found in environment variables. HubSpot integration will be disabled.")

def create_or_update_contact(email, name, budget, lead_type, lead_score, qualification, chat_history, user_type):
    """Create or update a contact in HubSpot CRM with enhanced error handling and response formatting."""
    # Check if HubSpot API key is available
    if not HUBSPOT_API_KEY:
        logger.warning("Skipping HubSpot CRM update: API key not configured")
        return 503, {"error": "HubSpot API key not configured", "message": "CRM integration disabled"}

    url = "https://api.hubapi.com/crm/v3/objects/contacts"
    headers = {
        "Authorization": f"Bearer {HUBSPOT_API_KEY}",
        "Content-Type": "application/json"
    }

    # Ensure all values are strings and truncate long values
    properties = {
        "email": email,
        "firstname": name,
        "budget": str(budget) if budget else "",
        "lead_type": lead_type if lead_type else "Unknown",
        "lead_score": str(lead_score) if lead_score else "0",
        "lead_qualification": qualification if qualification else "Unqualified",
        "chat_history": chat_history[:5000] if chat_history else "",
        "user_type": user_type if user_type else "Website Visitor",
        "last_interaction": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "lifecycle_stage": "lead"
    }

    # Add additional useful properties
    if "looking" in chat_history.lower() or "searching" in chat_history.lower():
        properties["hs_lead_status"] = "New"
    elif "price" in chat_history.lower() or "cost" in chat_history.lower():
        properties["hs_lead_status"] = "In Progress"
    elif "buy" in chat_history.lower() or "purchase" in chat_history.lower():
        properties["hs_lead_status"] = "Open Deal"

    # Search for existing contact
    search_url = "https://api.hubapi.com/crm/v3/objects/contacts/search"
    search_payload = {
        "filterGroups": [{"filters": [{"propertyName": "email", "operator": "EQ", "value": email}]}]
    }

    logger.info(f"Searching for contact with email: {email}")

    try:
        # Search for existing contact
        search_response = requests.post(search_url, headers=headers, json=search_payload)
        search_response.raise_for_status()
        results = search_response.json().get("results", [])

        # Format response data
        response_data = {}

        if results:
            # Update existing contact
            contact_id = results[0]["id"]
            existing_properties = results[0].get("properties", {})
            logger.info(f"Found existing contact with ID: {contact_id}")

            # Merge with existing properties to preserve history
            if "lead_score" in existing_properties and existing_properties.get("lead_score"):
                old_score = int(existing_properties.get("lead_score", "0"))
                new_score = int(properties.get("lead_score", "0"))
                # Use the higher score
                properties["lead_score"] = str(max(old_score, new_score))

            update_url = f"{url}/{contact_id}"
            response = requests.patch(update_url, headers=headers, json={"properties": properties})
            response.raise_for_status()

            response_data = {
                "id": contact_id,
                "action": "updated",
                "properties": response.json().get("properties", {}),
                "message": "Contact updated successfully"
            }
        else:
            # Create new contact
            logger.info(f"Creating new contact with email: {email}")
            response = requests.post(url, headers=headers, json={"properties": properties})
            response.raise_for_status()

            contact_id = response.json().get("id")
            response_data = {
                "id": contact_id,
                "action": "created",
                "properties": response.json().get("properties", {}),
                "message": "Contact created successfully"
            }

        logger.info(f"HubSpot operation successful: {response_data['action']} contact {contact_id}")
        return response.status_code, response_data
    except requests.RequestException as e:
        logger.error(f"HubSpot API error: {str(e)}")
        if hasattr(e, 'response') and e.response:
            logger.error(f"Response: {e.response.text}")
        return 500, {"error": str(e)}

def test_hubspot_connection():
    """Test the HubSpot API connection with the provided API key."""
    # Check if HubSpot API key is available
    if not HUBSPOT_API_KEY:
        logger.warning("Cannot test HubSpot connection: API key not configured")
        return {
            "status": "error",
            "message": "HubSpot API key not configured",
            "api_key_used": "None"
        }

    url = "https://api.hubapi.com/crm/v3/properties/contacts"
    headers = {
        "Authorization": f"Bearer {HUBSPOT_API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        logger.info("Testing HubSpot API connection...")
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        # Get the first few properties to verify data access
        properties = response.json().get("results", [])[:5]
        property_names = [prop.get("name") for prop in properties]

        logger.info(f"HubSpot API connection successful! Found properties: {property_names}")
        return {
            "status": "success",
            "message": "HubSpot API connection successful",
            "sample_properties": property_names,
            "api_key_used": HUBSPOT_API_KEY[:10] + "..." # Show only first part of API key for security
        }
    except requests.RequestException as e:
        error_message = str(e)
        response_text = ""
        if hasattr(e, 'response') and e.response:
            response_text = e.response.text

        logger.error(f"HubSpot API connection failed: {error_message}")
        logger.error(f"Response: {response_text}")

        return {
            "status": "error",
            "message": f"HubSpot API connection failed: {error_message}",
            "response": response_text,
            "api_key_used": HUBSPOT_API_KEY[:10] + "..." # Show only first part of API key for security
        }