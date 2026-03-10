"""
Chatbot persistence models.
"""

from datetime import datetime, timedelta, timezone

from app.extensions import db


def _utcnow():
    return datetime.now(timezone.utc)


class ChatbotConversation(db.Model):
    __tablename__ = "chatbot_conversations"

    id = db.Column(db.String(36), primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=True, index=True
    )
    anon_token_hash = db.Column(db.String(64), nullable=True, index=True)
    status = db.Column(db.String(20), nullable=False, default="open", index=True)
    source_page = db.Column(db.String(120), nullable=True)
    locale = db.Column(db.String(16), nullable=False, default="pt-BR")
    session_summary = db.Column(db.Text, nullable=True)
    last_user_intent = db.Column(db.String(50), nullable=True)
    last_confidence = db.Column(db.String(10), nullable=True)
    last_model = db.Column(db.String(50), nullable=True)
    turns_count = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=_utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow, index=True)

    user = db.relationship(
        "User", backref=db.backref("chatbot_conversations", lazy="dynamic")
    )
    messages = db.relationship(
        "ChatbotMessage",
        backref="conversation",
        lazy="dynamic",
        cascade="all, delete-orphan",
        order_by="ChatbotMessage.created_at.asc()",
    )

    def retention_cutoff(self, *, anon_days: int, auth_days: int) -> datetime:
        days = auth_days if self.user_id else anon_days
        return _utcnow() - timedelta(days=days)


class ChatbotMessage(db.Model):
    __tablename__ = "chatbot_messages"

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(
        db.String(36),
        db.ForeignKey("chatbot_conversations.id"),
        nullable=False,
        index=True,
    )
    role = db.Column(db.String(20), nullable=False)
    content = db.Column(db.Text, nullable=False)
    citations_json = db.Column(db.JSON, nullable=True)
    model = db.Column(db.String(50), nullable=True)
    prompt_tokens = db.Column(db.Integer, nullable=False, default=0)
    completion_tokens = db.Column(db.Integer, nullable=False, default=0)
    latency_ms = db.Column(db.Integer, nullable=True)
    flagged = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=_utcnow, index=True)

    feedback = db.relationship(
        "ChatbotFeedback",
        backref="message",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )


class ChatbotFeedback(db.Model):
    __tablename__ = "chatbot_feedback"

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(
        db.String(36),
        db.ForeignKey("chatbot_conversations.id"),
        nullable=False,
        index=True,
    )
    message_id = db.Column(
        db.Integer, db.ForeignKey("chatbot_messages.id"), nullable=False, index=True
    )
    rating = db.Column(db.String(10), nullable=False)
    note = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow, index=True)

    conversation = db.relationship(
        "ChatbotConversation",
        backref=db.backref("feedback_entries", lazy="dynamic"),
    )


class ChatbotKnowledgeDocument(db.Model):
    __tablename__ = "chatbot_knowledge_documents"

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(120), nullable=False, unique=True, index=True)
    source_type = db.Column(db.String(50), nullable=False, index=True)
    source_title = db.Column(db.String(255), nullable=False)
    canonical_url = db.Column(db.String(500), nullable=True)
    version_hash = db.Column(db.String(64), nullable=False, index=True)
    scope_tags_json = db.Column(db.JSON, nullable=False, default=list)
    body = db.Column(db.Text, nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=_utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow, index=True)

    chunks = db.relationship(
        "ChatbotKnowledgeChunk",
        backref="document",
        lazy="dynamic",
        cascade="all, delete-orphan",
        order_by="ChatbotKnowledgeChunk.chunk_index.asc()",
    )


class ChatbotKnowledgeChunk(db.Model):
    __tablename__ = "chatbot_knowledge_chunks"

    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(
        db.Integer,
        db.ForeignKey("chatbot_knowledge_documents.id"),
        nullable=False,
        index=True,
    )
    chunk_index = db.Column(db.Integer, nullable=False)
    content = db.Column(db.Text, nullable=False)
    token_count = db.Column(db.Integer, nullable=False, default=0)
    scope_tags_json = db.Column(db.JSON, nullable=False, default=list)
    embedding_json = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow, index=True)

    __table_args__ = (
        db.UniqueConstraint(
            "document_id",
            "chunk_index",
            name="uq_chatbot_knowledge_chunks_document_index",
        ),
    )
