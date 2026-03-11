"""
SQLAlchemy models — import all models here so Alembic can discover them.
"""

from app.models.user import User  # noqa: F401
from app.models.plan import Plan, Subscription, UsageRecord  # noqa: F401
from app.models.table import NutritionTable, TableVersion  # noqa: F401
from app.models.audit import AuditLog  # noqa: F401
from app.models.support import SupportTicket  # noqa: F401
from app.models.billing import StripeEvent  # noqa: F401
from app.models.chatbot import (  # noqa: F401
    ChatbotConversation,
    ChatbotFeedback,
    ChatbotKnowledgeChunk,
    ChatbotKnowledgeDocument,
    ChatbotMessage,
)
