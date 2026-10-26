"""Controlled vocabularies. Closed enums so a typo ("Location") can never slip past a DENY rule."""
from enum import StrEnum


class DataCategory(StrEnum):
    LOCATION = "location"
    CONTACTS = "contacts"
    BIOMETRICS = "biometrics"
    EMAIL = "email"
    NAME = "name"
    PHONE = "phone"
    HEALTH = "health"
    FINANCIAL = "financial"
    GOVERNMENT_ID = "government_id"
    BROWSING_HISTORY = "browsing_history"
    DEVICE_ID = "device_id"
    PHOTOS = "photos"
    MESSAGES = "messages"
    PREFERENCES = "preferences"


SENSITIVE_CATEGORIES: frozenset[DataCategory] = frozenset(
    {
        DataCategory.LOCATION,
        DataCategory.CONTACTS,
        DataCategory.BIOMETRICS,
        DataCategory.HEALTH,
        DataCategory.FINANCIAL,
        DataCategory.GOVERNMENT_ID,
        DataCategory.PHOTOS,
        DataCategory.MESSAGES,
    }
)


class Purpose(StrEnum):
    SERVICE_DELIVERY = "service_delivery"
    NAVIGATION = "navigation"
    ACCOUNT_MANAGEMENT = "account_management"
    ADVERTISING = "advertising"
    MARKETING = "marketing"
    ANALYTICS = "analytics"
    PERSONALIZATION = "personalization"
    AI_TRAINING = "ai_training"
    RESEARCH = "research"
    THIRD_PARTY_SHARING = "third_party_sharing"
    LEGAL_COMPLIANCE = "legal_compliance"
    SECURITY = "security"


class ProtectedAction(StrEnum):
    TRANSFER_DATA = "transfer_data"
    ACCEPT_TERMS = "accept_terms"
    SUBMIT_FORM = "submit_form"
    CREATE_ACCOUNT = "create_account"
    SEND_MESSAGE = "send_message"


class PolicyCategory(StrEnum):
    """The eight practice categories the court analyses (from the original concept doc)."""

    LOCATION = "location"
    CONTACTS = "contacts"
    BIOMETRICS = "biometrics"
    THIRD_PARTY_SHARING = "third_party_sharing"
    RETENTION = "retention"
    DELETION = "deletion"
    ADVERTISING = "advertising"
    AI_TRAINING = "ai_training"


class RuleEffect(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


class Decision(StrEnum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    REVIEW = "REVIEW"
