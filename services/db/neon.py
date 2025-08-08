# backend/services/database.py

import os
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from postgrest import AsyncPostgrestClient
from postgrest.exceptions import APIError
# CountMethod import removed - not currently used

class NeonDatabase:
    def __init__(self):
        # Validate required environment variables
        if not os.getenv("NEON_DATA_API_URL"):
            raise ValueError("NEON_DATA_API_URL environment variable is required")
        if not os.getenv("NEON_API_KEY"):
            raise ValueError("NEON_API_KEY environment variable is required")
        
        # For service-to-service calls, we can use the API key directly
        # The Data API accepts both JWT tokens (for user auth) and API keys
        headers = {
            "apikey": os.getenv("NEON_API_KEY"),
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        # If you have JWT token from Neon Auth, add it
        jwt_token = os.getenv("NEON_JWT_TOKEN")
        if jwt_token:
            headers["Authorization"] = f"Bearer {jwt_token}"
        
        schema = os.getenv("NEON_SCHEMA", "public")
        logging.info(f"Initializing NeonDatabase with schema: {schema}")
        
        self.client = AsyncPostgrestClient(
            base_url=os.getenv("NEON_DATA_API_URL"),
            headers=headers,
            schema=schema  # Use NEON_SCHEMA env var, default to public
        )
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # Clean up the client connection when exiting context
        await self.client.aclose()
        return False  # Don't suppress exceptions
    
    # Session management
    async def create_session(self, user_id: Optional[str] = None) -> str:
        """Create new session and return session_id"""
        try:
            response = await self.client.from_("sessions").insert({
                "user_id": user_id
            }).execute()
            
            if response.data and len(response.data) > 0:
                return response.data[0]['session_id']
            raise Exception("Failed to create session")
        except APIError as e:
            logging.error(f"Error creating session: {e}")
            raise
    
    # Status updates (migrated from Firebase update_status)
    async def update_status(
        self, 
        session_id: str, 
        status: str,
        additional_info: Optional[Dict] = None
    ):
        """Update processing status for session - compatible with existing Firebase method"""
        try:
            # Get current count for this session
            count_response = await self.client.from_("update_counters").select("count").eq(
                "session_id", session_id
            ).execute()
            
            # Handle case where no counter exists yet
            count = 1
            if count_response.data and len(count_response.data) > 0:
                count = count_response.data[0]['count'] + 1
            
            # Upsert counter
            await self.client.from_("update_counters").upsert({
                "session_id": session_id,
                "count": count
            }, on_conflict="session_id").execute()
            
            # Insert status update
            data = {
                'session_id': session_id,
                'status': status,
                'timestamp': datetime.now().isoformat(),
                'sequence_number': count
            }
            
            if additional_info:
                data['additional_info'] = additional_info
            
            await self.client.from_("update_status").insert(data).execute()
            
            logging.info(f"Status updated for session {session_id}: {status}")
        except APIError as e:
            logging.error(f"Error updating status: {e}")
            raise
    
    # Notify user (migrated from Firebase notify_user)
    async def notify_user(self, session_id: str, final_result: Dict[str, Any]):
        """Store final completed result - compatible with existing Firebase method"""
        try:
            final_result['status'] = 'completed'
            final_result['session_id'] = session_id
            final_result['created_at'] = datetime.now().isoformat()
            
            # Upsert into completed_results table
            await self.client.from_("completed_results").upsert(
                final_result,
                on_conflict="session_id"
            ).execute()
            
            logging.info(f"User notified for session {session_id}")
        except APIError as e:
            logging.error(f"Error notifying user: {e}")
            raise
    
    # Store OpenAI usage data
    async def store_openai_usage(
        self,
        session_id: str,
        openai_id: str,
        request_type: str,
        model_used: str,
        tokens: Dict[str, int]
    ):
        """Store OpenAI API usage data"""
        try:
            await self.client.from_("openai_responses").insert({
                "session_id": session_id,
                "openai_id": openai_id,
                "request_type": request_type,
                "model_used": model_used,
                "completion_tokens": tokens.get('completion_tokens', 0),
                "prompt_tokens": tokens.get('prompt_tokens', 0),
                "total_tokens": tokens.get('total_tokens', 0)
            }).execute()
        except APIError as e:
            logging.error(f"Error storing OpenAI usage: {e}")
            # Non-critical error, don't raise
    
    # Get session results (new helper method)
    async def get_session_results(self, session_id: str) -> Optional[Dict]:
        """Get completed results for a session"""
        try:
            response = await self.client.from_("completed_results").select("*").eq(
                "session_id", session_id
            ).execute()
            # Return first result if exists, otherwise None
            if response.data and len(response.data) > 0:
                return response.data[0]
            return None
        except APIError as e:
            logging.error(f"Error getting session results: {e}")
            return None
    
    # Get status updates (new helper method)
    async def get_status_updates(self, session_id: str) -> List[Dict]:
        """Get all status updates for a session"""
        try:
            response = await self.client.from_("update_status").select("*").eq(
                "session_id", session_id
            ).order("sequence_number").execute()
            return response.data or []
        except APIError as e:
            logging.error(f"Error getting status updates: {e}")
            return []
    


    # Connection test method
    async def test_connection(self) -> bool:
        """Test if the database connection is working"""
        try:
            # Try to query the sessions table
            response = await self.client.from_("sessions").select("*").limit(1).execute()
            logging.info("Database connection test successful")
            return True
        except APIError as e:
            logging.error(f"Database connection test failed: {e}")
            return False
        except Exception as e:
            logging.error(f"Unexpected error during connection test: {e}")
            return False

# Global database instance
db = NeonDatabase()

# Backwards compatibility - map old Firebase methods to new ones
notify_user = db.notify_user
update_status = db.update_status