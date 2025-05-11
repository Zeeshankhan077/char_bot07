import os
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
import urllib.parse
import logging
from typing import Dict, List, Optional, Union, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()

CALENDLY_API_KEY = os.getenv("CALENDLY_API_KEY")
CALENDLY_USERNAME = os.getenv("CALENDLY_USERNAME")

class CalendlyError(Exception):
    """Base exception for Calendly client errors"""
    pass

class CalendlyAuthError(CalendlyError):
    """Authentication related errors"""
    pass

class CalendlyAPIError(CalendlyError):
    """API related errors"""
    pass

class CalendlyClient:
    def __init__(self):
        """Initialize Calendly client with API credentials"""
        self.enabled = True
        self.base_url = "https://api.calendly.com"
        self.user_details = None

        # Check if Calendly is configured
        if not CALENDLY_API_KEY or not CALENDLY_USERNAME:
            logger.warning("Calendly integration is disabled: Missing API key or username")
            self.enabled = False
            return

        self.headers = {
            "Authorization": f"Bearer {CALENDLY_API_KEY.strip()}",
            "Content-Type": "application/json"
        }

        try:
            self.user_details = self._get_user_details()
            if not self.user_details:
                logger.warning("Failed to authenticate with Calendly")
                self.enabled = False
        except CalendlyAuthError as e:
            logger.error(f"Authentication error: {str(e)}")
            self.enabled = False
        except Exception as e:
            logger.error(f"Unexpected error during initialization: {str(e)}")
            self.enabled = False

    def _get_user_details(self) -> Dict[str, str]:
        """Get user details including organization and user URI"""
        try:
            response = requests.get(f"{self.base_url}/users/me", headers=self.headers)
            response.raise_for_status()
            user_data = response.json()

            return {
                "user_uri": user_data["resource"]["uri"],
                "organization": user_data["resource"]["current_organization"],
                "username": user_data["resource"]["name"],
                "scheduling_url": user_data["resource"]["scheduling_url"]
            }
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                logger.error("Invalid or expired API key")
                raise CalendlyAuthError("Invalid or expired API key")
            logger.error(f"HTTP error: {str(e)}")
            raise CalendlyAPIError(f"HTTP error: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            raise CalendlyError(f"Unexpected error: {str(e)}")

    def get_available_slots(self, days_ahead: int = 7) -> List[Dict]:
        """Get available scheduling slots for the next X days"""
        if not self.enabled or not self.user_details:
            logger.warning("Calendly integration is disabled")
            return []

        try:
            event_types_url = f"{self.base_url}/event_types"
            response = requests.get(
                event_types_url,
                headers=self.headers,
                params={"organization": self.user_details["organization"]}
            )
            response.raise_for_status()
            return response.json().get("collection", [])
        except Exception as e:
            logger.error(f"Error getting available slots: {str(e)}")
            return []

    def create_scheduling_link(self, name: str, email: str, event_type_uri: Optional[str] = None) -> Dict[str, str]:
        """Create a scheduling link with prefilled information"""
        if not self.enabled:
            logger.warning("Calendly integration is disabled")
            return {"status": "error", "message": "Calendly integration is disabled"}

        try:
            event_types = self.get_available_slots()
            if not event_types:
                return {"status": "error", "message": "No event types found"}

            event_type = next(
                (et for et in event_types if et["uri"] == event_type_uri),
                event_types[0]
            )

            base_url = self.user_details.get("scheduling_url", "").rstrip('/') if self.user_details else ""
            if not base_url and CALENDLY_USERNAME:
                base_url = f"https://calendly.com/{CALENDLY_USERNAME}"
            elif not base_url:
                return {"status": "error", "message": "Calendly username not configured"}

            event_slug = event_type.get("slug", event_type["name"].lower().replace(' ', '-'))
            params = {
                "name": name,
                "email": email
            }

            query_string = urllib.parse.urlencode(params)
            scheduling_url = f"{base_url}/{event_slug}?{query_string}"

            return {
                "status": "success",
                "booking_link": scheduling_url,
                "event_type": event_type["name"],
                "duration": event_type.get("duration", 30)
            }
        except Exception as e:
            logger.error(f"Error creating scheduling link: {str(e)}")
            return {"status": "error", "message": str(e)}

    def schedule_meeting(self, name: str, email: str, start_time: str, event_type_uri: Optional[str] = None) -> Dict[str, str]:
        """Schedule a meeting directly"""
        if not self.enabled:
            logger.warning("Calendly integration is disabled")
            return {"status": "error", "message": "Calendly integration is disabled"}

        try:
            if not event_type_uri:
                event_types = self.get_available_slots()
                if not event_types:
                    return {"status": "error", "message": "No event types found"}
                event_type_uri = event_types[0]["uri"]

            data = {
                "start_time": start_time,
                "event_type": event_type_uri,
                "invitees": [{"email": email, "name": name}]
            }

            response = requests.post(
                f"{self.base_url}/scheduled_events",
                headers=self.headers,
                json=data
            )
            response.raise_for_status()
            event_data = response.json()["resource"]

            return {
                "status": "success",
                "event_uri": event_data["uri"],
                "start_time": start_time
            }
        except Exception as e:
            logger.error(f"Error scheduling meeting: {str(e)}")
            return {"status": "error", "message": str(e)}

    def create_property_consultation_link(self, property_details: Dict, invitee_name: str, invitee_email: str) -> str:
        """Create a scheduling link for property consultation"""
        if not self.enabled:
            logger.warning("Calendly integration is disabled")
            return "Calendly integration is disabled. Please contact support."

        try:
            result = self.create_scheduling_link(invitee_name, invitee_email)
            if result["status"] != "success":
                logger.warning(f"Failed to create scheduling link: {result.get('message')}")
                return f"Unable to create scheduling link: {result.get('message')}"

            property_info = (
                f"Property: {property_details.get('type', 'N/A')} in {property_details.get('location', 'N/A')}\n"
                f"Size: {property_details.get('size', 'N/A')}\n"
                f"Price: {property_details.get('price', 'N/A')}"
            )

            encoded_info = urllib.parse.quote(property_info)
            final_url = f"{result['booking_link']}&details={encoded_info}"

            logger.info(f"Created consultation link for property: {property_details.get('id', 'N/A')}")
            return final_url
        except Exception as e:
            logger.error(f"Error creating property consultation link: {str(e)}")
            return f"Error creating scheduling link: {str(e)}"