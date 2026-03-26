# SPDX-FileCopyrightText: 2025 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Subscription Market service for browsing and renting market subscriptions.

This module provides the SubscriptionMarketService class for:
- Browsing market subscriptions (visibility=market)
- Renting market subscriptions
- Managing user's rental subscriptions
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import desc, func
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models.kind import Kind
from app.models.user import User
from app.schemas.subscription import (
    MarketSubscriptionDetail,
    RentalCountResponse,
    RentalSubscriptionResponse,
    RentSubscriptionRequest,
    Subscription,
    SubscriptionTaskType,
    SubscriptionTriggerType,
    SubscriptionVisibility,
)
from app.services.subscription.helpers import (
    build_trigger_config,
    calculate_next_execution_time,
    extract_trigger_config,
)
from app.services.subscription.market_access import (
    can_view_market_subscription,
    get_market_whitelist_user_ids_from_internal,
)

logger = logging.getLogger(__name__)


def _get_trigger_description(
    trigger_type: SubscriptionTriggerType,
    trigger_config: Dict[str, Any],
) -> str:
    """Generate a human-readable trigger description."""
    if trigger_type == SubscriptionTriggerType.CRON:
        expression = trigger_config.get("expression", "")
        timezone_str = trigger_config.get("timezone", "UTC")
        return f"Cron: {expression} ({timezone_str})"
    elif trigger_type == SubscriptionTriggerType.INTERVAL:
        value = trigger_config.get("value", 1)
        unit = trigger_config.get("unit", "hours")
        return f"Every {value} {unit}"
    elif trigger_type == SubscriptionTriggerType.ONE_TIME:
        execute_at = trigger_config.get("execute_at", "")
        return f"One time at {execute_at}"
    elif trigger_type == SubscriptionTriggerType.EVENT:
        event_type = trigger_config.get("event_type", "webhook")
        return f"Event: {event_type}"
    return "Unknown trigger"


class SubscriptionMarketService:
    """Service class for Subscription Market operations."""

    def _safe_trigger_type(self, raw_trigger_type: Any) -> SubscriptionTriggerType:
        """Parse trigger type safely with cron fallback."""
        try:
            return SubscriptionTriggerType(raw_trigger_type)
        except Exception:
            return SubscriptionTriggerType.CRON

    def _extract_raw_trigger_config(
        self,
        trigger_type: SubscriptionTriggerType,
        raw_trigger: Any,
    ) -> Dict[str, Any]:
        """Extract trigger config from raw JSON for display fallback."""
        trigger = raw_trigger if isinstance(raw_trigger, dict) else {}

        if trigger_type == SubscriptionTriggerType.CRON:
            cron = trigger.get("cron") if isinstance(trigger.get("cron"), dict) else {}
            return {
                "expression": cron.get("expression", ""),
                "timezone": cron.get("timezone", "UTC"),
            }

        if trigger_type == SubscriptionTriggerType.INTERVAL:
            interval = (
                trigger.get("interval")
                if isinstance(trigger.get("interval"), dict)
                else {}
            )
            return {
                "value": interval.get("value", 1),
                "unit": interval.get("unit", "hours"),
            }

        if trigger_type == SubscriptionTriggerType.ONE_TIME:
            one_time = (
                trigger.get("one_time")
                if isinstance(trigger.get("one_time"), dict)
                else {}
            )
            return {
                "execute_at": one_time.get("execute_at", ""),
            }

        if trigger_type == SubscriptionTriggerType.EVENT:
            event = (
                trigger.get("event") if isinstance(trigger.get("event"), dict) else {}
            )
            result = {"event_type": event.get("event_type", "webhook")}
            git_push = event.get("git_push")
            if isinstance(git_push, dict):
                result["git_push"] = {
                    "repository": git_push.get("repository", ""),
                    "branch": git_push.get("branch"),
                }
            return result

        return {}

    def _build_market_view_from_raw_json(
        self,
        subscription: Kind,
        *,
        trigger_type: SubscriptionTriggerType,
    ) -> Optional[Dict[str, Any]]:
        """Build market display fields from raw JSON when schema validation fails."""
        raw_json = subscription.json if isinstance(subscription.json, dict) else {}
        spec = raw_json.get("spec")
        if not isinstance(spec, dict):
            return None

        raw_display_name = spec.get("displayName")
        display_name = (
            raw_display_name.strip()
            if isinstance(raw_display_name, str) and raw_display_name.strip()
            else subscription.name
        )

        raw_description = spec.get("description")
        description = raw_description if isinstance(raw_description, str) else None

        raw_visibility = spec.get("visibility", SubscriptionVisibility.PRIVATE.value)
        try:
            visibility = SubscriptionVisibility(raw_visibility)
        except Exception:
            visibility = SubscriptionVisibility.PRIVATE

        raw_task_type = spec.get("taskType", SubscriptionTaskType.COLLECTION.value)
        try:
            task_type = SubscriptionTaskType(raw_task_type)
        except Exception:
            task_type = SubscriptionTaskType.COLLECTION

        model_ref_raw = spec.get("modelRef")
        model_ref = None
        if isinstance(model_ref_raw, dict):
            name = model_ref_raw.get("name")
            namespace = model_ref_raw.get("namespace", "default")
            if isinstance(name, str) and name:
                model_ref = {
                    "name": name,
                    "namespace": namespace if isinstance(namespace, str) else "default",
                }

        return {
            "display_name": display_name,
            "description": description,
            "task_type": task_type,
            "visibility": visibility,
            "trigger_config": self._extract_raw_trigger_config(
                trigger_type, spec.get("trigger")
            ),
            "model_ref": model_ref,
        }

    def _build_market_view(
        self,
        subscription: Kind,
        *,
        trigger_type: SubscriptionTriggerType,
    ) -> Optional[Dict[str, Any]]:
        """Build market display fields with tolerant fallback parsing."""
        try:
            subscription_crd = Subscription.model_validate(subscription.json)
            model_ref = None
            if subscription_crd.spec.modelRef:
                model_ref = {
                    "name": subscription_crd.spec.modelRef.name,
                    "namespace": subscription_crd.spec.modelRef.namespace,
                }

            return {
                "display_name": subscription_crd.spec.displayName,
                "description": subscription_crd.spec.description,
                "task_type": subscription_crd.spec.taskType,
                "visibility": getattr(
                    subscription_crd.spec,
                    "visibility",
                    SubscriptionVisibility.PRIVATE,
                ),
                "trigger_config": extract_trigger_config(subscription_crd.spec.trigger),
                "model_ref": model_ref,
            }
        except ValidationError as exc:
            fallback_view = self._build_market_view_from_raw_json(
                subscription, trigger_type=trigger_type
            )
            if fallback_view is not None:
                logger.debug(
                    "[SubscriptionMarket] Recover invalid subscription CRD for market "
                    "display: id=%s name=%s error=%s",
                    subscription.id,
                    subscription.name,
                    exc,
                )
                return fallback_view

            logger.warning(
                "[SubscriptionMarket] Skip invalid subscription CRD: id=%s name=%s "
                "error=%s",
                subscription.id,
                subscription.name,
                exc,
            )
            return None

    def discover_market_subscriptions(
        self,
        db: Session,
        *,
        user_id: int,
        sort_by: str = "rental_count",
        search: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> Tuple[List[MarketSubscriptionDetail], int]:
        """
        Discover market subscriptions (visibility=market).

        Args:
            db: Database session
            user_id: Current user ID
            sort_by: Sort by 'rental_count' or 'recent'
            search: Optional search query for name/description
            skip: Pagination offset
            limit: Pagination limit

        Returns:
            Tuple of (list of MarketSubscriptionDetail, total count)
        """
        # Query all active subscriptions
        query = db.query(Kind).filter(
            Kind.kind == "Subscription",
            Kind.is_active == True,
        )

        subscriptions = query.all()

        # Filter for market visibility subscriptions
        market_subscriptions = []
        for sub in subscriptions:
            internal = (
                sub.json.get("_internal", {}) if isinstance(sub.json, dict) else {}
            )
            trigger_type = self._safe_trigger_type(internal.get("trigger_type", "cron"))
            market_view = self._build_market_view(sub, trigger_type=trigger_type)
            if market_view is None:
                continue

            visibility = market_view["visibility"]
            market_whitelist_user_ids = get_market_whitelist_user_ids_from_internal(
                internal
            )
            if can_view_market_subscription(
                visibility=visibility,
                owner_user_id=sub.user_id,
                current_user_id=user_id,
                whitelist_user_ids=market_whitelist_user_ids,
            ):
                market_subscriptions.append(
                    {
                        "subscription": sub,
                        "market_view": market_view,
                        "trigger_type": trigger_type,
                    }
                )

        # Apply search filter
        if search:
            search_lower = search.lower()
            filtered = []
            for market_sub in market_subscriptions:
                market_view = market_sub["market_view"]
                display_name = market_view["display_name"].lower()
                description = (market_view["description"] or "").lower()
                if search_lower in display_name or search_lower in description:
                    filtered.append(market_sub)
            market_subscriptions = filtered

        # Get user's rented subscriptions for is_rented check
        rented_source_ids = self._get_user_rented_source_ids(db, user_id)

        # Convert to response and collect rental counts
        result_items = []
        for market_sub in market_subscriptions:
            sub = market_sub["subscription"]
            market_view = market_sub["market_view"]
            trigger_type = market_sub["trigger_type"]
            internal = (
                sub.json.get("_internal", {}) if isinstance(sub.json, dict) else {}
            )

            # Get owner username
            owner = db.query(User).filter(User.id == sub.user_id).first()
            owner_username = owner.user_name if owner else "Unknown"

            result_items.append(
                MarketSubscriptionDetail(
                    id=sub.id,
                    name=sub.name,
                    display_name=market_view["display_name"],
                    description=market_view["description"],
                    task_type=market_view["task_type"],
                    trigger_type=trigger_type,
                    trigger_description=_get_trigger_description(
                        trigger_type, market_view["trigger_config"]
                    ),
                    owner_user_id=sub.user_id,
                    owner_username=owner_username,
                    rental_count=internal.get("rental_count", 0),
                    is_rented=sub.id in rented_source_ids,
                    created_at=sub.created_at,
                    updated_at=sub.updated_at,
                )
            )

        # Sort
        if sort_by == "rental_count":
            result_items.sort(key=lambda x: x.rental_count, reverse=True)
        else:  # recent
            result_items.sort(key=lambda x: x.updated_at, reverse=True)

        total = len(result_items)

        # Apply pagination
        result_items = result_items[skip : skip + limit]

        return result_items, total

    def get_market_subscription_detail(
        self,
        db: Session,
        *,
        subscription_id: int,
        user_id: int,
    ) -> MarketSubscriptionDetail:
        """
        Get market subscription detail (hides sensitive information).

        Args:
            db: Database session
            subscription_id: Subscription ID
            user_id: Current user ID

        Returns:
            MarketSubscriptionDetail

        Raises:
            HTTPException: If subscription not found or not market visibility
        """
        subscription = (
            db.query(Kind)
            .filter(
                Kind.id == subscription_id,
                Kind.kind == "Subscription",
                Kind.is_active == True,
            )
            .first()
        )

        if not subscription:
            raise HTTPException(status_code=404, detail="Subscription not found")

        internal = (
            subscription.json.get("_internal", {})
            if isinstance(subscription.json, dict)
            else {}
        )
        trigger_type = self._safe_trigger_type(internal.get("trigger_type", "cron"))
        market_view = self._build_market_view(subscription, trigger_type=trigger_type)
        if market_view is None:
            raise HTTPException(status_code=404, detail="Subscription not found")

        visibility = market_view["visibility"]

        if visibility != SubscriptionVisibility.MARKET:
            raise HTTPException(
                status_code=404, detail="Subscription not found in market"
            )

        market_whitelist_user_ids = get_market_whitelist_user_ids_from_internal(
            internal
        )
        if not can_view_market_subscription(
            visibility=visibility,
            owner_user_id=subscription.user_id,
            current_user_id=user_id,
            whitelist_user_ids=market_whitelist_user_ids,
        ):
            raise HTTPException(
                status_code=403, detail="Access denied to this market subscription"
            )

        # Get owner username
        owner = db.query(User).filter(User.id == subscription.user_id).first()
        owner_username = owner.user_name if owner else "Unknown"

        # Check if user has rented this subscription
        rented_source_ids = self._get_user_rented_source_ids(db, user_id)

        return MarketSubscriptionDetail(
            id=subscription.id,
            name=subscription.name,
            display_name=market_view["display_name"],
            description=market_view["description"],
            task_type=market_view["task_type"],
            trigger_type=trigger_type,
            trigger_description=_get_trigger_description(
                trigger_type, market_view["trigger_config"]
            ),
            owner_user_id=subscription.user_id,
            owner_username=owner_username,
            rental_count=internal.get("rental_count", 0),
            is_rented=subscription.id in rented_source_ids,
            created_at=subscription.created_at,
            updated_at=subscription.updated_at,
        )

    def rent_subscription(
        self,
        db: Session,
        *,
        source_subscription_id: int,
        renter_user_id: int,
        request: RentSubscriptionRequest,
    ) -> RentalSubscriptionResponse:
        """
        Rent a market subscription.

        Creates a new subscription with sourceSubscriptionRef pointing to the
        source subscription. The rental subscription only stores trigger config
        and optional model_ref; team/prompt/workspace are read from source at
        execution time.

        Args:
            db: Database session
            source_subscription_id: Source subscription ID to rent
            renter_user_id: Renter user ID
            request: Rental configuration

        Returns:
            RentalSubscriptionResponse

        Raises:
            HTTPException: If validation fails
        """
        # Validate source subscription exists and is market visibility
        source = (
            db.query(Kind)
            .filter(
                Kind.id == source_subscription_id,
                Kind.kind == "Subscription",
                Kind.is_active == True,
            )
            .first()
        )

        if not source:
            raise HTTPException(status_code=404, detail="Source subscription not found")

        source_internal = (
            source.json.get("_internal", {}) if isinstance(source.json, dict) else {}
        )
        source_trigger_type = self._safe_trigger_type(
            source_internal.get("trigger_type", "cron")
        )
        source_view = self._build_market_view(source, trigger_type=source_trigger_type)
        if source_view is None:
            raise HTTPException(
                status_code=400, detail="Source subscription is invalid"
            )

        visibility = source_view["visibility"]

        if visibility != SubscriptionVisibility.MARKET:
            raise HTTPException(
                status_code=400, detail="Source subscription is not available in market"
            )

        market_whitelist_user_ids = get_market_whitelist_user_ids_from_internal(
            source_internal
        )
        if not can_view_market_subscription(
            visibility=visibility,
            owner_user_id=source.user_id,
            current_user_id=renter_user_id,
            whitelist_user_ids=market_whitelist_user_ids,
        ):
            raise HTTPException(
                status_code=403, detail="Access denied to this market subscription"
            )

        # Prevent users from renting their own subscriptions
        if source.user_id == renter_user_id:
            raise HTTPException(
                status_code=400, detail="Cannot rent your own subscription"
            )

        # Check if user already rented this subscription
        existing_rental = self._get_user_rental_for_source(
            db, renter_user_id, source_subscription_id
        )
        if existing_rental:
            raise HTTPException(
                status_code=400, detail="You have already rented this subscription"
            )

        # Validate rental subscription name uniqueness
        existing = (
            db.query(Kind)
            .filter(
                Kind.user_id == renter_user_id,
                Kind.kind == "Subscription",
                Kind.name == request.name,
                Kind.namespace == "default",
                Kind.is_active == True,
            )
            .first()
        )

        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Subscription with name '{request.name}' already exists",
            )

        # Get source owner username
        source_owner = db.query(User).filter(User.id == source.user_id).first()
        source_owner_username = source_owner.user_name if source_owner else "Unknown"

        # Build trigger config
        trigger = build_trigger_config(request.trigger_type, request.trigger_config)

        # Calculate next execution time
        next_execution_time = calculate_next_execution_time(
            request.trigger_type, request.trigger_config
        )
        if next_execution_time is None:
            next_execution_time = datetime.now(timezone.utc).replace(tzinfo=None)

        # Build model_ref if provided
        from app.schemas.kind import ModelRef

        model_ref = None
        if request.model_ref:
            model_ref = ModelRef(
                name=request.model_ref.get("name", ""),
                namespace=request.model_ref.get("namespace", "default"),
            )

        # Build rental subscription CRD JSON
        # Note: teamRef, promptTemplate, workspaceRef are NOT stored in rental
        # They are read from source subscription at execution time
        from app.schemas.subscription import (
            SourceSubscriptionRef,
            SubscriptionMetadata,
            SubscriptionSpec,
            SubscriptionStatus,
            SubscriptionTaskType,
            SubscriptionTeamRef,
        )

        spec = SubscriptionSpec(
            displayName=request.display_name,
            taskType=source_view["task_type"],  # Copy task type from source
            visibility=SubscriptionVisibility.PRIVATE,  # Rentals are always private
            trigger=trigger,
            teamRef=SubscriptionTeamRef(
                name="__rental_placeholder__", namespace="default"
            ),  # Placeholder
            promptTemplate="__rental_placeholder__",  # Placeholder
            enabled=True,
            description=f"Rental of: {source_view['display_name']}",
            sourceSubscriptionRef=SourceSubscriptionRef(
                id=source.id,
                name=source.name,
                namespace=source.namespace,
            ),
            modelRef=model_ref,
        )

        rental_crd = Subscription(
            metadata=SubscriptionMetadata(
                name=request.name,
                namespace="default",
                displayName=request.display_name,
            ),
            spec=spec,
            status=SubscriptionStatus(),
        )

        crd_json = rental_crd.model_dump(mode="json")
        crd_json["_internal"] = {
            "team_id": 0,  # Not used for rentals
            "workspace_id": 0,  # Not used for rentals
            "webhook_token": "",
            "webhook_secret": "",
            "enabled": True,
            "trigger_type": request.trigger_type.value,
            "next_execution_time": (
                next_execution_time.isoformat() if next_execution_time else None
            ),
            "last_execution_time": None,
            "last_execution_status": "",
            "execution_count": 0,
            "success_count": 0,
            "failure_count": 0,
            "bound_task_id": 0,
            # Rental-specific fields
            "is_rental": True,
            "source_subscription_id": source.id,
            "source_subscription_name": source.name,
            "source_subscription_display_name": source_view["display_name"],
            "source_owner_username": source_owner_username,
        }

        # Create rental subscription
        rental = Kind(
            user_id=renter_user_id,
            kind="Subscription",
            name=request.name,
            namespace="default",
            json=crd_json,
            is_active=True,
        )
        db.add(rental)

        # Increment rental count on source subscription
        source_internal["rental_count"] = source_internal.get("rental_count", 0) + 1
        source.json["_internal"] = source_internal
        flag_modified(source, "json")

        db.commit()
        db.refresh(rental)

        return RentalSubscriptionResponse(
            id=rental.id,
            name=rental.name,
            display_name=request.display_name,
            namespace="default",
            source_subscription_id=source.id,
            source_subscription_name=source.name,
            source_subscription_display_name=source_view["display_name"],
            source_owner_user_id=source.user_id,
            source_owner_username=source_owner_username,
            trigger_type=request.trigger_type,
            trigger_config=request.trigger_config,
            model_ref=request.model_ref,
            enabled=True,
            last_execution_time=None,
            last_execution_status=None,
            next_execution_time=next_execution_time,
            execution_count=0,
            created_at=rental.created_at,
            updated_at=rental.updated_at,
        )

    def get_user_rentals(
        self,
        db: Session,
        *,
        user_id: int,
        skip: int = 0,
        limit: int = 20,
    ) -> Tuple[List[RentalSubscriptionResponse], int]:
        """
        Get user's rental subscriptions.

        Args:
            db: Database session
            user_id: User ID
            skip: Pagination offset
            limit: Pagination limit

        Returns:
            Tuple of (list of RentalSubscriptionResponse, total count)
        """
        # Query all active subscriptions for the user
        query = db.query(Kind).filter(
            Kind.user_id == user_id,
            Kind.kind == "Subscription",
            Kind.is_active == True,
        )

        subscriptions = query.all()

        # Filter for rental subscriptions
        rentals = []
        for sub in subscriptions:
            internal = sub.json.get("_internal", {})
            if internal.get("is_rental", False):
                rentals.append(sub)

        total = len(rentals)

        # Sort by updated_at desc
        rentals.sort(key=lambda x: x.updated_at, reverse=True)

        # Apply pagination
        rentals = rentals[skip : skip + limit]

        # Convert to response
        result = []
        for rental in rentals:
            internal = (
                rental.json.get("_internal", {})
                if isinstance(rental.json, dict)
                else {}
            )
            trigger_type = self._safe_trigger_type(internal.get("trigger_type", "cron"))
            rental_view = self._build_market_view(rental, trigger_type=trigger_type)
            if rental_view is None:
                continue

            # Parse execution times
            next_execution_time = None
            if internal.get("next_execution_time"):
                try:
                    next_execution_time = datetime.fromisoformat(
                        internal["next_execution_time"]
                    )
                except (ValueError, TypeError):
                    pass

            last_execution_time = None
            if internal.get("last_execution_time"):
                try:
                    last_execution_time = datetime.fromisoformat(
                        internal["last_execution_time"]
                    )
                except (ValueError, TypeError):
                    pass

            # Get source owner info
            source_id = internal.get("source_subscription_id")
            source_owner_user_id = 0
            if source_id:
                source_sub = db.query(Kind).filter(Kind.id == source_id).first()
                if source_sub:
                    source_owner_user_id = source_sub.user_id

            result.append(
                RentalSubscriptionResponse(
                    id=rental.id,
                    name=rental.name,
                    display_name=rental_view["display_name"],
                    namespace=rental.namespace,
                    source_subscription_id=internal.get("source_subscription_id", 0),
                    source_subscription_name=internal.get(
                        "source_subscription_name", ""
                    ),
                    source_subscription_display_name=internal.get(
                        "source_subscription_display_name", ""
                    ),
                    source_owner_user_id=source_owner_user_id,
                    source_owner_username=internal.get("source_owner_username", ""),
                    trigger_type=trigger_type,
                    trigger_config=rental_view["trigger_config"],
                    model_ref=rental_view["model_ref"],
                    enabled=internal.get("enabled", True),
                    last_execution_time=last_execution_time,
                    last_execution_status=internal.get("last_execution_status"),
                    next_execution_time=next_execution_time,
                    execution_count=internal.get("execution_count", 0),
                    created_at=rental.created_at,
                    updated_at=rental.updated_at,
                )
            )

        return result, total

    def get_rental_count(
        self,
        db: Session,
        *,
        subscription_id: int,
    ) -> RentalCountResponse:
        """
        Get rental count for a market subscription.

        Args:
            db: Database session
            subscription_id: Subscription ID

        Returns:
            RentalCountResponse

        Raises:
            HTTPException: If subscription not found
        """
        subscription = (
            db.query(Kind)
            .filter(
                Kind.id == subscription_id,
                Kind.kind == "Subscription",
                Kind.is_active == True,
            )
            .first()
        )

        if not subscription:
            raise HTTPException(status_code=404, detail="Subscription not found")

        internal = subscription.json.get("_internal", {})

        return RentalCountResponse(
            subscription_id=subscription.id,
            rental_count=internal.get("rental_count", 0),
        )

    def _get_user_rented_source_ids(self, db: Session, user_id: int) -> set:
        """Get set of source subscription IDs that user has rented."""
        query = db.query(Kind).filter(
            Kind.user_id == user_id,
            Kind.kind == "Subscription",
            Kind.is_active == True,
        )

        source_ids = set()
        for sub in query.all():
            internal = sub.json.get("_internal", {})
            if internal.get("is_rental", False):
                source_id = internal.get("source_subscription_id")
                if source_id:
                    source_ids.add(source_id)

        return source_ids

    def _get_user_rental_for_source(
        self, db: Session, user_id: int, source_subscription_id: int
    ) -> Optional[Kind]:
        """Get user's rental subscription for a specific source."""
        query = db.query(Kind).filter(
            Kind.user_id == user_id,
            Kind.kind == "Subscription",
            Kind.is_active == True,
        )

        for sub in query.all():
            internal = sub.json.get("_internal", {})
            if (
                internal.get("is_rental", False)
                and internal.get("source_subscription_id") == source_subscription_id
            ):
                return sub

        return None


# Singleton instance
subscription_market_service = SubscriptionMarketService()
