"""add chatbot support tables

Revision ID: e4c8a13d9b77
Revises: d7e3f2a1b4c5
Create Date: 2026-03-09 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e4c8a13d9b77"
down_revision = "d7e3f2a1b4c5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "chatbot_conversations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("anon_token_hash", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("source_page", sa.String(length=120), nullable=True),
        sa.Column("locale", sa.String(length=16), nullable=False),
        sa.Column("session_summary", sa.Text(), nullable=True),
        sa.Column("last_user_intent", sa.String(length=50), nullable=True),
        sa.Column("last_confidence", sa.String(length=10), nullable=True),
        sa.Column("last_model", sa.String(length=50), nullable=True),
        sa.Column("turns_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("chatbot_conversations", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_chatbot_conversations_user_id"), ["user_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_chatbot_conversations_anon_token_hash"), ["anon_token_hash"], unique=False)
        batch_op.create_index(batch_op.f("ix_chatbot_conversations_status"), ["status"], unique=False)
        batch_op.create_index(batch_op.f("ix_chatbot_conversations_created_at"), ["created_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_chatbot_conversations_updated_at"), ["updated_at"], unique=False)

    op.create_table(
        "chatbot_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("citations_json", sa.JSON(), nullable=True),
        sa.Column("model", sa.String(length=50), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("flagged", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["conversation_id"], ["chatbot_conversations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("chatbot_messages", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_chatbot_messages_conversation_id"), ["conversation_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_chatbot_messages_created_at"), ["created_at"], unique=False)

    op.create_table(
        "chatbot_feedback",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("rating", sa.String(length=10), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["conversation_id"], ["chatbot_conversations.id"]),
        sa.ForeignKeyConstraint(["message_id"], ["chatbot_messages.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("chatbot_feedback", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_chatbot_feedback_conversation_id"), ["conversation_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_chatbot_feedback_message_id"), ["message_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_chatbot_feedback_created_at"), ["created_at"], unique=False)

    op.create_table(
        "chatbot_knowledge_documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("source_title", sa.String(length=255), nullable=False),
        sa.Column("canonical_url", sa.String(length=500), nullable=True),
        sa.Column("version_hash", sa.String(length=64), nullable=False),
        sa.Column("scope_tags_json", sa.JSON(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("chatbot_knowledge_documents", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_chatbot_knowledge_documents_slug"), ["slug"], unique=True)
        batch_op.create_index(batch_op.f("ix_chatbot_knowledge_documents_source_type"), ["source_type"], unique=False)
        batch_op.create_index(batch_op.f("ix_chatbot_knowledge_documents_version_hash"), ["version_hash"], unique=False)
        batch_op.create_index(batch_op.f("ix_chatbot_knowledge_documents_created_at"), ["created_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_chatbot_knowledge_documents_updated_at"), ["updated_at"], unique=False)

    op.create_table(
        "chatbot_knowledge_chunks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("scope_tags_json", sa.JSON(), nullable=False),
        sa.Column("embedding_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["chatbot_knowledge_documents.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id",
            "chunk_index",
            name="uq_chatbot_knowledge_chunks_document_index",
        ),
    )
    with op.batch_alter_table("chatbot_knowledge_chunks", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_chatbot_knowledge_chunks_document_id"), ["document_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_chatbot_knowledge_chunks_created_at"), ["created_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_chatbot_knowledge_chunks_updated_at"), ["updated_at"], unique=False)

    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS chatbot_knowledge_chunks_fts
            USING fts5(
                chunk_id UNINDEXED,
                content,
                source_title,
                scope_tags
            )
            """
        )


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute("DROP TABLE IF EXISTS chatbot_knowledge_chunks_fts")

    with op.batch_alter_table("chatbot_knowledge_chunks", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_chatbot_knowledge_chunks_updated_at"))
        batch_op.drop_index(batch_op.f("ix_chatbot_knowledge_chunks_created_at"))
        batch_op.drop_index(batch_op.f("ix_chatbot_knowledge_chunks_document_id"))
    op.drop_table("chatbot_knowledge_chunks")

    with op.batch_alter_table("chatbot_knowledge_documents", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_chatbot_knowledge_documents_updated_at"))
        batch_op.drop_index(batch_op.f("ix_chatbot_knowledge_documents_created_at"))
        batch_op.drop_index(batch_op.f("ix_chatbot_knowledge_documents_version_hash"))
        batch_op.drop_index(batch_op.f("ix_chatbot_knowledge_documents_source_type"))
        batch_op.drop_index(batch_op.f("ix_chatbot_knowledge_documents_slug"))
    op.drop_table("chatbot_knowledge_documents")

    with op.batch_alter_table("chatbot_feedback", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_chatbot_feedback_created_at"))
        batch_op.drop_index(batch_op.f("ix_chatbot_feedback_message_id"))
        batch_op.drop_index(batch_op.f("ix_chatbot_feedback_conversation_id"))
    op.drop_table("chatbot_feedback")

    with op.batch_alter_table("chatbot_messages", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_chatbot_messages_created_at"))
        batch_op.drop_index(batch_op.f("ix_chatbot_messages_conversation_id"))
    op.drop_table("chatbot_messages")

    with op.batch_alter_table("chatbot_conversations", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_chatbot_conversations_updated_at"))
        batch_op.drop_index(batch_op.f("ix_chatbot_conversations_created_at"))
        batch_op.drop_index(batch_op.f("ix_chatbot_conversations_status"))
        batch_op.drop_index(batch_op.f("ix_chatbot_conversations_anon_token_hash"))
        batch_op.drop_index(batch_op.f("ix_chatbot_conversations_user_id"))
    op.drop_table("chatbot_conversations")
