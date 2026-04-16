# SPDX-FileCopyrightText: 2025 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
IM Channel Binding Service for user-agent bindings.

This service manages per-user, per-channel bindings between IM channels
and Wegent teams. Bindings are stored in User.preferences JSON field
under the 'im_channels' key.

Storage structure in users.preferences:
{
    "im_channels": {
        "1": {  // channel_id as string key
            "channel_type": "dingtalk",
            "private_team_id": 123,
            "group_bindings": [
                {
                    "conversation_id": "cid_abc123",
                    "group_name": "技术部AI群",
                    "team_id": 123,
                    "bound_at": "2026-04-16T10:00:00Z"
                }
            ]
        }
    }
}
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.cache import cache_manager
from app.models.kind import Kind
from app.models.user import User

# Constants for Messager channel lookup
MESSAGER_KIND = "Messager"
MESSAGER_USER_ID = 0  # System-level resource
from app.schemas.im_channel import (
    ChannelType,
    IMChannelUserBinding,
    IMGroupBinding,
    UpdateIMBindingRequest,
)

logger = logging.getLogger(__name__)

# Redis key prefixes for binding sessions
BINDING_PENDING_PREFIX = "im:binding:pending:"
BINDING_PENDING_INDEX_PREFIX = "im:binding:pending:index:"
# TTL for binding sessions (10 minutes)
BINDING_SESSION_TTL = 10 * 60


class IMChannelBindingService:
    """Service for managing IM channel user bindings."""

    # ==================== User Binding Methods ====================

    @staticmethod
    def get_user_bindings(
        db: Session,
        user_id: int,
    ) -> List[IMChannelUserBinding]:
        """Get all channel bindings for a user.

        Fetches all available Messager channels and enriches them with
        user's binding configuration from User.preferences['im_channels'].

        Args:
            db: Database session
            user_id: User ID

        Returns:
            List of IMChannelUserBinding with channel names populated.
            Returns all available channels, even if user has no bindings configured.
        """
        # Get all enabled Messager channels (global channels created by admin)
        channels = (
            db.query(Kind)
            .filter(
                Kind.kind == MESSAGER_KIND,
                Kind.user_id == MESSAGER_USER_ID,
                Kind.is_active == True,
            )
            .all()
        )

        if not channels:
            return []

        # Get user's existing bindings from preferences
        user = db.query(User).filter(User.id == user_id).first()
        im_channels = {}
        if user and user.preferences:
            try:
                prefs = (
                    json.loads(user.preferences)
                    if isinstance(user.preferences, str)
                    else user.preferences
                )
                im_channels = prefs.get("im_channels", {})
            except (json.JSONDecodeError, TypeError):
                im_channels = {}

        # Build binding objects for all available channels
        bindings = []
        for channel in channels:
            channel_id = channel.id
            channel_id_str = str(channel_id)

            # Get channel type from spec
            channel_type = ""
            try:
                spec = (
                    json.loads(channel.json)
                    if isinstance(channel.json, str)
                    else channel.json
                )
                if spec:
                    channel_type = spec.get("channelType", "")
            except (json.JSONDecodeError, TypeError):
                pass

            # Get user's binding config for this channel (if any)
            data = im_channels.get(channel_id_str, {})
            private_team_id = data.get("private_team_id") if data else None

            # Parse group bindings
            group_bindings = []
            if data:
                for gb in data.get("group_bindings", []):
                    try:
                        bound_at = None
                        if gb.get("bound_at"):
                            try:
                                bound_at = datetime.fromisoformat(gb["bound_at"])
                            except (ValueError, TypeError):
                                pass

                        group_bindings.append(
                            IMGroupBinding(
                                conversation_id=gb.get("conversation_id", ""),
                                group_name=gb.get("group_name", ""),
                                team_id=gb.get("team_id", 0),
                                bound_at=bound_at,
                            )
                        )
                    except Exception as e:
                        logger.warning(f"Failed to parse group binding: {e}")
                        continue

            binding = IMChannelUserBinding(
                channel_id=channel_id,
                channel_name=channel.name,
                channel_type=channel_type,
                private_team_id=private_team_id,
                group_bindings=group_bindings,
            )
            bindings.append(binding)

        return bindings

    @staticmethod
    def update_binding(
        db: Session,
        user_id: int,
        channel_id: int,
        request: UpdateIMBindingRequest,
    ) -> Optional[IMChannelUserBinding]:
        """Update binding for a user and channel.

        Updates private_team_id if provided. If group is provided, adds or
        updates the group binding (matched by conversation_id).

        Args:
            db: Database session
            user_id: User ID
            channel_id: Channel ID
            request: Update request with private_team_id and/or group binding

        Returns:
            Updated IMChannelUserBinding or None if user not found
        """
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return None

        # Parse preferences
        try:
            prefs = (
                json.loads(user.preferences)
                if isinstance(user.preferences, str)
                else user.preferences
            )
        except (json.JSONDecodeError, TypeError):
            prefs = {}

        if "im_channels" not in prefs:
            prefs["im_channels"] = {}

        channel_id_str = str(channel_id)

        # Get or create channel binding data
        if channel_id_str not in prefs["im_channels"]:
            # Need to fetch channel type from Kind
            channel = (
                db.query(Kind)
                .filter(Kind.id == channel_id, Kind.kind == "Messager")
                .first()
            )
            if not channel:
                logger.warning(f"Channel {channel_id} not found")
                return None

            try:
                spec = (
                    json.loads(channel.json)
                    if isinstance(channel.json, str)
                    else channel.json
                )
                channel_type = spec.get("channelType", "")
            except (json.JSONDecodeError, TypeError):
                channel_type = ""

            prefs["im_channels"][channel_id_str] = {
                "channel_type": channel_type,
                "group_bindings": [],
            }

        channel_data = prefs["im_channels"][channel_id_str]

        # Update private_team_id if provided
        if request.private_team_id is not None:
            channel_data["private_team_id"] = request.private_team_id

        # Add or update group binding if provided
        if request.group is not None:
            group_bindings = channel_data.get("group_bindings", [])

            # Find existing binding by conversation_id
            existing_idx = None
            for idx, gb in enumerate(group_bindings):
                if gb.get("conversation_id") == request.group.conversation_id:
                    existing_idx = idx
                    break

            new_group_binding = {
                "conversation_id": request.group.conversation_id,
                "group_name": request.group.group_name,
                "team_id": request.group.team_id,
                "bound_at": datetime.now(timezone.utc).isoformat(),
            }

            if existing_idx is not None:
                # Preserve original bound_at for existing bindings
                old_bound_at = group_bindings[existing_idx].get("bound_at")
                if old_bound_at:
                    new_group_binding["bound_at"] = old_bound_at
                group_bindings[existing_idx] = new_group_binding
            else:
                group_bindings.append(new_group_binding)

            channel_data["group_bindings"] = group_bindings

        # Save updated preferences
        user.preferences = json.dumps(prefs)
        db.add(user)
        db.commit()

        # Return updated binding
        bindings = IMChannelBindingService.get_user_bindings(db, user_id)
        for binding in bindings:
            if binding.channel_id == channel_id:
                return binding

        return None

    @staticmethod
    def remove_group_binding(
        db: Session,
        user_id: int,
        channel_id: int,
        conversation_id: str,
    ) -> Optional[IMChannelUserBinding]:
        """Remove a group binding for a user and channel.

        Args:
            db: Database session
            user_id: User ID
            channel_id: Channel ID
            conversation_id: Conversation ID of the group binding to remove

        Returns:
            Updated IMChannelUserBinding or None if not found
        """
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return None

        # Parse preferences
        try:
            prefs = (
                json.loads(user.preferences)
                if isinstance(user.preferences, str)
                else user.preferences
            )
        except (json.JSONDecodeError, TypeError):
            prefs = {}

        im_channels = prefs.get("im_channels", {})
        channel_id_str = str(channel_id)

        if channel_id_str not in im_channels:
            return None

        channel_data = im_channels[channel_id_str]
        group_bindings = channel_data.get("group_bindings", [])

        # Remove matching group binding
        new_bindings = [
            gb for gb in group_bindings if gb.get("conversation_id") != conversation_id
        ]

        if len(new_bindings) == len(group_bindings):
            # No binding was removed
            return None

        channel_data["group_bindings"] = new_bindings

        # Save updated preferences
        user.preferences = json.dumps(prefs)
        db.add(user)
        db.commit()

        # Return updated binding
        bindings = IMChannelBindingService.get_user_bindings(db, user_id)
        for binding in bindings:
            if binding.channel_id == channel_id:
                return binding

        return None

    @staticmethod
    def resolve_team_for_message(
        db: Session,
        user_id: int,
        channel_id: int,
        message_context: Any,  # MessageContext or dict with conversation_type and conversation_id
    ) -> Optional[int]:
        """Resolve which team should handle an incoming message.

        Checks for group bindings if message is from a group chat,
        otherwise falls back to private_team_id.

        Args:
            db: Database session
            user_id: User ID
            channel_id: Channel ID
            message_context: Message context with conversation_type and conversation_id

        Returns:
            Team ID to use, or None if no binding found (handler will use default)
        """
        user = db.query(User).filter(User.id == user_id).first()
        if not user or not user.preferences:
            return None

        # Parse preferences
        try:
            prefs = (
                json.loads(user.preferences)
                if isinstance(user.preferences, str)
                else user.preferences
            )
        except (json.JSONDecodeError, TypeError):
            return None

        im_channels = prefs.get("im_channels", {})
        channel_id_str = str(channel_id)

        if channel_id_str not in im_channels:
            return None

        channel_data = im_channels[channel_id_str]

        # Extract conversation info from message_context
        conversation_type = getattr(message_context, "conversation_type", None)
        conversation_id = getattr(message_context, "conversation_id", None)

        if isinstance(message_context, dict):
            conversation_type = message_context.get("conversation_type")
            conversation_id = message_context.get("conversation_id")

        # Check group binding for group chats
        if conversation_type == "group" and conversation_id:
            group_bindings = channel_data.get("group_bindings", [])
            for gb in group_bindings:
                if gb.get("conversation_id") == conversation_id:
                    return gb.get("team_id")

        # Fall back to private_team_id
        return channel_data.get("private_team_id")

    # ==================== Redis Session Methods ====================

    @staticmethod
    def _generate_session_key(user_id: int, channel_id: int) -> str:
        """Generate Redis key for binding session."""
        return f"{BINDING_PENDING_PREFIX}{user_id}:{channel_id}"

    @staticmethod
    def _generate_session_index_key(user_id: int) -> str:
        """Generate Redis key for binding session index."""
        return f"{BINDING_PENDING_INDEX_PREFIX}{user_id}"

    @staticmethod
    async def start_binding_session(
        user_id: int,
        channel_id: int,
    ) -> bool:
        """Start a binding discovery session.

        Creates a pending session with 10-minute TTL.

        Args:
            user_id: User ID
            channel_id: Channel ID

        Returns:
            True if session created successfully
        """
        session_key = IMChannelBindingService._generate_session_key(user_id, channel_id)
        index_key = IMChannelBindingService._generate_session_index_key(user_id)

        session_data = {
            "user_id": user_id,
            "channel_id": channel_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            # Store session data
            result = await cache_manager.set(
                session_key,
                session_data,
                expire=BINDING_SESSION_TTL,
            )

            if result:
                # Add to index for quick lookup
                await cache_manager.set(
                    index_key,
                    {"channel_id": channel_id, "session_key": session_key},
                    expire=BINDING_SESSION_TTL,
                )

            return result
        except Exception as e:
            logger.error(f"Failed to start binding session: {e}")
            return False

    @staticmethod
    async def cancel_binding_session(
        user_id: int,
        channel_id: int,
    ) -> bool:
        """Cancel a binding discovery session.

        Args:
            user_id: User ID
            channel_id: Channel ID

        Returns:
            True if session cancelled successfully
        """
        session_key = IMChannelBindingService._generate_session_key(user_id, channel_id)
        index_key = IMChannelBindingService._generate_session_index_key(user_id)

        try:
            # Delete session
            await cache_manager.delete(session_key)
            # Delete index
            await cache_manager.delete(index_key)
            return True
        except Exception as e:
            logger.error(f"Failed to cancel binding session: {e}")
            return False

    @staticmethod
    async def get_binding_session(
        user_id: int,
        channel_id: int,
    ) -> Optional[Dict[str, Any]]:
        """Get active binding session if exists.

        Args:
            user_id: User ID
            channel_id: Channel ID

        Returns:
            Session data or None if not found/expired
        """
        session_key = IMChannelBindingService._generate_session_key(user_id, channel_id)

        try:
            data = await cache_manager.get(session_key)
            return data
        except Exception as e:
            logger.error(f"Failed to get binding session: {e}")
            return None

    @staticmethod
    async def handle_binding_from_message(
        db: Session,
        user_id: int,
        channel_id: int,
        conversation_id: str,
        group_name: str,
        team_id: int,
    ) -> Optional[IMChannelUserBinding]:
        """Handle binding discovery from an incoming message.

        Called when a message is received during binding discovery.
        Creates or updates the group binding and clears the session.

        Args:
            db: Database session
            user_id: User ID
            channel_id: Channel ID
            conversation_id: Conversation ID from the message
            group_name: Display name of the group
            team_id: Team ID to bind to the group

        Returns:
            Updated IMChannelUserBinding or None if failed
        """
        # Check if session exists
        session = await IMChannelBindingService.get_binding_session(user_id, channel_id)
        if not session:
            logger.warning(
                f"No active binding session for user {user_id}, channel {channel_id}"
            )
            return None

        # Create group binding request
        group_binding = IMGroupBinding(
            conversation_id=conversation_id,
            group_name=group_name,
            team_id=team_id,
            bound_at=datetime.now(timezone.utc),
        )

        request = UpdateIMBindingRequest(group=group_binding)

        # Update binding
        result = IMChannelBindingService.update_binding(
            db=db,
            user_id=user_id,
            channel_id=channel_id,
            request=request,
        )

        if result:
            # Clear session after successful binding
            await IMChannelBindingService.cancel_binding_session(user_id, channel_id)
            logger.info(
                f"Created group binding for user {user_id}, channel {channel_id}, "
                f"conversation {conversation_id}, team {team_id}"
            )

        return result


# Singleton instance
binding_service = IMChannelBindingService()
