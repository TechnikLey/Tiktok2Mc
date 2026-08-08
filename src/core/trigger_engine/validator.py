from __future__ import annotations

from core.trigger_engine.models import ValidationError


class PayloadValidator:
    """Validates trigger input before dispatch.

    Handles all validation concerns so the engine only sees clean data.
    """

    MAX_USER_LENGTH = 64
    MAX_COMMENT_LENGTH = 500
    MAX_TRIGGER_NAME_LENGTH = 128

    def validate_trigger(
        self,
        trigger_name: str,
        *,
        gift_id: str | None = None,
        gift_name: str | None = None,
    ) -> list[ValidationError]:
        errors: list[ValidationError] = []

        if not trigger_name or not trigger_name.strip():
            errors.append(
                ValidationError(
                    field="trigger",
                    message="Trigger name is required.",
                    code="TRIGGER_EMPTY",
                )
            )
            return errors

        trigger_str = trigger_name.strip()

        if len(trigger_str) > self.MAX_TRIGGER_NAME_LENGTH:
            errors.append(
                ValidationError(
                    field="trigger",
                    message=f"Trigger name exceeds {self.MAX_TRIGGER_NAME_LENGTH} characters.",
                    code="TRIGGER_NAME_TOO_LONG",
                )
            )

        if gift_id is not None:
            self._validate_gift_id(gift_id, errors)

        if gift_name is not None and not gift_name.strip():
            errors.append(
                ValidationError(
                    field="gift_name",
                    message="Gift name must not be empty when provided.",
                    code="GIFT_NAME_EMPTY",
                )
            )

        return errors

    def validate_comment(
        self,
        user: str,
        text: str,
        *,
        moderator: bool = False,
        superfan: bool = False,
        fanclub: bool = False,
    ) -> list[ValidationError]:
        errors: list[ValidationError] = []

        if not user or not user.strip():
            errors.append(
                ValidationError(
                    field="user",
                    message="User name is required.",
                    code="USER_EMPTY",
                )
            )
        elif len(user) > self.MAX_USER_LENGTH:
            errors.append(
                ValidationError(
                    field="user",
                    message=f"User name exceeds {self.MAX_USER_LENGTH} characters.",
                    code="USER_TOO_LONG",
                )
            )

        if not text or not text.strip():
            errors.append(
                ValidationError(
                    field="text",
                    message="Comment text is required.",
                    code="COMMENT_EMPTY",
                )
            )
        elif len(text) > self.MAX_COMMENT_LENGTH:
            errors.append(
                ValidationError(
                    field="text",
                    message=f"Comment text exceeds {self.MAX_COMMENT_LENGTH} characters.",
                    code="COMMENT_TOO_LONG",
                )
            )

        return errors

    def validate_user(self, user: str | None) -> list[ValidationError]:
        errors: list[ValidationError] = []
        if user is None or not user.strip():
            return errors
        if len(user) > self.MAX_USER_LENGTH:
            errors.append(
                ValidationError(
                    field="user",
                    message=f"User name exceeds {self.MAX_USER_LENGTH} characters.",
                    code="USER_TOO_LONG",
                )
            )
        return errors

    def _validate_gift_id(self, gift_id: str, errors: list[ValidationError]) -> None:
        if not gift_id or not gift_id.strip():
            errors.append(
                ValidationError(
                    field="gift_id",
                    message="Gift ID is required when gift type is selected.",
                    code="GIFT_ID_EMPTY",
                )
            )
            return
        try:
            val = int(gift_id)
            if val <= 0:
                errors.append(
                    ValidationError(
                        field="gift_id",
                        message="Gift ID must be a positive integer.",
                        code="GIFT_ID_INVALID",
                    )
                )
        except (ValueError, TypeError):
            errors.append(
                ValidationError(
                    field="gift_id",
                    message="Gift ID must be a numeric value.",
                    code="GIFT_ID_NOT_NUMERIC",
                )
            )
