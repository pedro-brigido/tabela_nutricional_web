"""
Chatbot retrieval, persistence, and OpenAI orchestration.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import current_app
from markupsafe import Markup
from sqlalchemy import and_, or_

from app.extensions import db
from app.models.chatbot import (
    ChatbotConversation,
    ChatbotFeedback,
    ChatbotKnowledgeChunk,
    ChatbotKnowledgeDocument,
    ChatbotMessage,
)
from app.services.audit_service import log_action

DEFAULT_SUGGESTED_QUESTIONS = [
    "Qual plano faz mais sentido para 10 tabelas por mês?",
    "O que muda entre Start, Pro e Studio?",
    "Como funciona a exportação em PDF e PNG?",
    "Preciso de cartão para começar?",
    "Como o Terracota ajuda na conformidade com a ANVISA?",
]

STOPWORDS = {
    "a", "o", "e", "de", "da", "do", "das", "dos", "para", "com", "uma", "um",
    "como", "que", "no", "na", "em", "por", "ou", "se", "eu", "meu", "minha",
}

OUT_OF_SCOPE_PATTERNS = (
    "criptomoeda",
    "futebol",
    "horoscopo",
    "politica internacional",
    "programa em python do zero",
)

REGULATORY_DEEP_PATTERNS = (
    "posso comercializar",
    "qual enquadramento",
    "qual rdc se aplica",
    "laudo",
    "responsavel tecnico",
    "responsabilidade legal",
    "consulta juridica",
    "multa",
    "autuacao",
    "processo administrativo",
    "registro anvisa",
)

INTENT_KEYWORDS = {
    "pricing": ("plano", "planos", "preco", "preço", "gratis", "grátis", "assinatura"),
    "export": ("pdf", "png", "export", "impress", "rotulo", "rótulo"),
    "company": ("empresa", "terracota", "suporte", "humano", "contato", "time"),
    "billing": ("cartao", "cartão", "cancelar", "upgrade", "cobranca", "cobrança", "stripe"),
    "product": ("como funciona", "calcula", "ingrediente", "excel", "tabela", "tabela nutricional"),
    "privacy": ("privacidade", "lgpd", "dados", "email", "e-mail"),
}

SOURCE_WEIGHTS = {
    "plans": 1.35,
    "faq": 1.20,
    "policy": 1.15,
    "support": 1.10,
    "company": 1.00,
    "product": 1.00,
}

CHATBOT_FTS_TABLE = "chatbot_knowledge_chunks_fts"
_OPENAI_CAPABILITY_COOLDOWN_UNTIL = {
    "moderation": 0.0,
    "embeddings": 0.0,
    "responses": 0.0,
}


class ChatbotError(RuntimeError):
    """Base chatbot exception."""


class ChatbotUnavailableError(ChatbotError):
    """Raised when the assistant cannot answer right now."""


class ChatbotOwnershipError(ChatbotError):
    """Raised when a conversation does not belong to the requester."""


class ChatbotModerationError(ChatbotError):
    """Raised when a message is blocked."""


@dataclass
class RetrievedChunk:
    chunk: ChatbotKnowledgeChunk
    lexical_score: float = 0.0
    semantic_score: float = 0.0

    @property
    def combined_score(self) -> float:
        weight = SOURCE_WEIGHTS.get(self.chunk.document.source_type, 1.0)
        return (self.lexical_score + self.semantic_score) * weight


def _conversation_id(conversation: ChatbotConversation | str) -> str:
    if isinstance(conversation, str):
        return conversation
    return str(conversation.id)


def _bind_conversation(conversation: ChatbotConversation | str) -> ChatbotConversation:
    bound = db.session.get(ChatbotConversation, _conversation_id(conversation))
    if not bound:
        raise ChatbotError("Conversa não encontrada.")
    return bound


def _openai_cooldown_seconds() -> int:
    return max(int(current_app.config.get("CHATBOT_OPENAI_COOLDOWN_SECONDS", 180)), 0)


def _openai_error_is_expected(exc: Exception) -> bool:
    name = exc.__class__.__name__.lower()
    message = str(exc).lower()
    expected_terms = (
        "ratelimit",
        "timeout",
        "connection",
        "apierror",
        "insufficient_quota",
        "too many requests",
        "rate limit",
        "temporarily unavailable",
    )
    return any(term in name or term in message for term in expected_terms)


def _openai_capability_available(capability: str) -> bool:
    blocked_until = _OPENAI_CAPABILITY_COOLDOWN_UNTIL.get(capability, 0.0)
    return time.monotonic() >= blocked_until


def _register_openai_failure(capability: str, exc: Exception) -> None:
    cooldown_seconds = _openai_cooldown_seconds()
    if cooldown_seconds > 0:
        _OPENAI_CAPABILITY_COOLDOWN_UNTIL[capability] = time.monotonic() + cooldown_seconds
    message = (
        f"Chatbot {capability} unavailable; cooling down for {cooldown_seconds}s."
        if cooldown_seconds > 0
        else f"Chatbot {capability} unavailable."
    )
    if _openai_error_is_expected(exc):
        current_app.logger.warning("%s Provider said: %s", message, exc)
        return
    current_app.logger.warning("%s", message, exc_info=True)


def chatbot_enabled() -> bool:
    return bool(current_app.config.get("CHATBOT_ENABLED", False))


def ensure_chatbot_storage() -> None:
    """Create the FTS table used by the hybrid lexical retrieval layer."""
    if "sqlite" not in current_app.config.get("SQLALCHEMY_DATABASE_URI", ""):
        return

    db.session.execute(
        db.text(
            f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS {CHATBOT_FTS_TABLE}
            USING fts5(
                chunk_id UNINDEXED,
                content,
                source_title,
                scope_tags
            )
            """
        )
    )
    db.session.commit()


def build_initial_messages() -> list[dict]:
    return [
        {
            "role": "assistant",
            "content": (
                "Sou o assistente do Terracota. Posso ajudar com planos, funcionamento "
                "do produto, cobrança, exportação, FAQ pública e informações da empresa."
            ),
            "citations": [],
        }
    ]


def sanitize_message(value: str, *, max_chars: int = 1200) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    text = Markup(text).striptags()
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


def hash_anon_token(token: str) -> str:
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def get_or_create_conversation(
    *,
    user_id: int | None,
    anon_token_hash: str | None,
    source_page: str | None,
    locale: str | None,
) -> ChatbotConversation:
    prune_expired_conversations()
    query = ChatbotConversation.query.filter_by(status="open")
    if user_id:
        conversation = query.filter_by(user_id=user_id).order_by(
            ChatbotConversation.updated_at.desc()
        ).first()
    else:
        conversation = query.filter_by(anon_token_hash=anon_token_hash).order_by(
            ChatbotConversation.updated_at.desc()
        ).first()

    if conversation:
        return conversation

    conversation = ChatbotConversation(
        id=str(uuid.uuid4()),
        user_id=user_id,
        anon_token_hash=anon_token_hash,
        source_page=(source_page or "landing-faq")[:120],
        locale=(locale or "pt-BR")[:16],
    )
    db.session.add(conversation)
    db.session.commit()

    log_action(
        "chatbot.session.open",
        user_id=user_id,
        details={"conversation_id": conversation.id, "source_page": conversation.source_page},
    )
    return conversation


def get_conversation_for_actor(
    conversation_id: str,
    *,
    user_id: int | None,
    anon_token_hash: str | None,
) -> ChatbotConversation | None:
    conversation = db.session.get(ChatbotConversation, conversation_id)
    if not conversation:
        return None
    if user_id and conversation.user_id == user_id:
        return conversation
    if not user_id and conversation.anon_token_hash and conversation.anon_token_hash == anon_token_hash:
        return conversation
    raise ChatbotOwnershipError("Conversa não pertence a este usuário.")


def serialize_messages(conversation: ChatbotConversation, *, limit: int = 14) -> list[dict]:
    rows = (
        ChatbotMessage.query.filter_by(conversation_id=_conversation_id(conversation))
        .order_by(ChatbotMessage.created_at.desc())
        .limit(limit)
        .all()
    )
    rows.reverse()
    return [
        {
            "id": row.id,
            "role": row.role,
            "content": row.content,
            "citations": row.citations_json or [],
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


def serialize_conversation(conversation: ChatbotConversation) -> dict:
    return {
        "conversation_id": conversation.id,
        "summary": conversation.session_summary or "",
        "messages": serialize_messages(conversation),
        "suggested_questions": DEFAULT_SUGGESTED_QUESTIONS,
    }


def record_feedback(
    *,
    conversation: ChatbotConversation,
    message_id: int,
    rating: str,
    note: str = "",
) -> ChatbotFeedback:
    message = ChatbotMessage.query.filter_by(
        id=message_id,
        conversation_id=conversation.id,
    ).first()
    if not message:
        raise ChatbotError("Mensagem inválida para esta conversa.")
    feedback = ChatbotFeedback(
        conversation_id=conversation.id,
        message_id=message.id,
        rating=(rating or "")[:10],
        note=(note or "").strip()[:1000] or None,
    )
    db.session.add(feedback)
    db.session.commit()
    log_action(
        "chatbot.feedback",
        user_id=conversation.user_id,
        details={
            "conversation_id": conversation.id,
            "message_id": message_id,
            "rating": feedback.rating,
        },
    )
    return feedback


def build_handoff_link(conversation: ChatbotConversation, answer: str) -> str:
    message = (
        f"Origem: chatbot\n"
        f"Conversation ID: {conversation.id}\n\n"
        f"Resumo do assistente:\n{answer[:900]}"
    )
    from flask import url_for

    return url_for(
        "support.contact",
        category="other",
        subject="Conversa com especialista IA",
        message=message,
        source="chatbot",
        conversation_id=conversation.id,
    )


def confidence_from_chunks(chunks: list[RetrievedChunk]) -> str:
    if not chunks:
        return "low"
    top_score = chunks[0].combined_score
    support_score = chunks[1].combined_score if len(chunks) > 1 else 0.0
    if top_score >= 0.9 and support_score >= 0.25:
        return "high"
    if top_score >= 0.45:
        return "medium"
    return "low"


def classify_intent(message: str) -> str:
    lowered = (message or "").lower()
    for pattern in OUT_OF_SCOPE_PATTERNS:
        if pattern in lowered:
            return "out_of_scope"
    for pattern in REGULATORY_DEEP_PATTERNS:
        if pattern in lowered:
            return "regulatory_deep"
    for intent, keywords in INTENT_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return intent
    return "product"


def safe_fallback_payload(
    *,
    conversation: ChatbotConversation,
    intent: str,
    reason: str,
) -> dict:
    if intent in {"regulatory_deep", "out_of_scope"}:
        answer = (
            "Consigo ajudar com o produto, planos, empresa e operação do Terracota. "
            "Para esse tipo de análise específica, o melhor caminho é falar com um especialista por e-mail."
        )
    else:
        answer = (
            "Não consegui montar uma resposta confiável agora. "
            "Posso te encaminhar para o suporte humano com o contexto desta conversa."
        )
    return {
        "answer": answer,
        "citations": [],
        "confidence": "low",
        "needs_human": True,
        "suggested_actions": [
            "Falar com especialista por e-mail",
            "Ver central de ajuda completa",
        ],
        "handoff_url": build_handoff_link(conversation, answer),
        "reason": reason,
    }


def build_curated_documents() -> list[dict]:
    docs_dir = Path(__file__).resolve().parent.parent / "ai" / "knowledge"
    documents: list[dict] = []
    if docs_dir.exists():
        for path in sorted(docs_dir.glob("*.md")):
            body = path.read_text(encoding="utf-8").strip()
            documents.append(
                {
                    "slug": path.stem,
                    "source_type": _source_type_from_slug(path.stem),
                    "source_title": path.stem.replace("_", " ").title(),
                    "canonical_url": "/#faq",
                    "scope_tags": path.stem.split("_"),
                    "body": body,
                }
            )
    documents.extend(_build_structured_documents())
    return documents


def _source_type_from_slug(slug: str) -> str:
    for prefix in ("faq", "policy", "support", "product", "company"):
        if slug.startswith(prefix):
            return prefix
    return "product"


def _build_structured_documents() -> list[dict]:
    from app.services.plan_service import list_plans, marketing_plans

    try:
        plans = list_plans()
    except Exception:
        plans = marketing_plans()

    if not plans:
        plans = marketing_plans()

    plan_lines = []
    for plan in plans:
        tables = (
            "Ilimitadas"
            if plan.max_tables_per_month is None
            else str(plan.max_tables_per_month)
        )
        ingredients = (
            "Ilimitados"
            if plan.max_ingredients_per_table is None
            else str(plan.max_ingredients_per_table)
        )
        features = []
        if getattr(plan, "has_templates", False):
            features.append("templates")
        if getattr(plan, "has_pdf_export", False):
            features.append("exportação PDF")
        if getattr(plan, "has_png_export", False):
            features.append("exportação PNG")
        if getattr(plan, "has_version_history", False):
            features.append("histórico")
        if getattr(plan, "has_branding", False):
            features.append("branding no PDF")
        feature_text = ", ".join(features) if features else "recursos essenciais"
        plan_lines.append(
            f"- {plan.name} ({plan.slug}): R$ {plan.price_brl:.2f}/mês, "
            f"{tables} tabelas por mês, {ingredients} ingredientes por tabela, {feature_text}."
        )

    faq_body = "\n".join(
        [
            "- A tabela gerada segue RDC 429/2020, IN 75/2020 e RDC 26/2015 no fluxo do produto.",
            "- O Terracota não substitui o nutricionista responsável.",
            "- O plano grátis pode ser usado sem cartão.",
            "- Cancelamento é sem multa e sem carência.",
            "- O suporte humano responde em até 24 horas úteis.",
        ]
    )

    return [
        {
            "slug": "plans_structured",
            "source_type": "plans",
            "source_title": "Planos e Limites Terracota",
            "canonical_url": "/#planos",
            "scope_tags": ["planos", "precos", "limites", "pricing"],
            "body": "\n".join(plan_lines),
        },
        {
            "slug": "faq_structured",
            "source_type": "faq",
            "source_title": "FAQ Público Terracota",
            "canonical_url": "/#faq",
            "scope_tags": ["faq", "duvidas", "suporte"],
            "body": faq_body,
        },
    ]


def _chunk_document(body: str, *, max_chars: int = 700, overlap: int = 120) -> list[str]:
    text = re.sub(r"\n{3,}", "\n\n", body.strip())
    if len(text) <= max_chars:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        if end < len(text):
            next_break = text.rfind("\n\n", start, end)
            if next_break > start + 200:
                end = next_break
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def _version_hash(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def sync_knowledge_base() -> dict:
    ensure_chatbot_storage()
    created = 0
    updated = 0
    chunk_count = 0
    active_slugs: set[str] = set()
    existing = {
        doc.slug: doc for doc in ChatbotKnowledgeDocument.query.all()
    }

    for spec in build_curated_documents():
        body = spec["body"].strip()
        version_hash = _version_hash(body)
        active_slugs.add(spec["slug"])
        document = existing.get(spec["slug"])
        if document is None:
            document = ChatbotKnowledgeDocument(
                slug=spec["slug"],
                source_type=spec["source_type"],
                source_title=spec["source_title"],
                canonical_url=spec["canonical_url"],
                version_hash=version_hash,
                scope_tags_json=spec["scope_tags"],
                body=body,
                is_active=True,
            )
            db.session.add(document)
            db.session.flush()
            created += 1
        elif document.version_hash != version_hash or not document.is_active:
            document.source_type = spec["source_type"]
            document.source_title = spec["source_title"]
            document.canonical_url = spec["canonical_url"]
            document.version_hash = version_hash
            document.scope_tags_json = spec["scope_tags"]
            document.body = body
            document.is_active = True
            ChatbotKnowledgeChunk.query.filter_by(document_id=document.id).delete()
            updated += 1
        else:
            document.source_type = spec["source_type"]
            document.source_title = spec["source_title"]
            document.canonical_url = spec["canonical_url"]
            document.scope_tags_json = spec["scope_tags"]
            document.is_active = True

        if not document.chunks.count():
            for index, chunk in enumerate(_chunk_document(body)):
                db.session.add(
                    ChatbotKnowledgeChunk(
                        document_id=document.id,
                        chunk_index=index,
                        content=chunk,
                        token_count=max(1, len(chunk.split())),
                        scope_tags_json=spec["scope_tags"],
                    )
                )
                chunk_count += 1

    for slug, document in existing.items():
        if slug not in active_slugs:
            document.is_active = False

    db.session.commit()
    rebuild_fts_index()
    return {"created": created, "updated": updated, "chunks": chunk_count}


def prune_expired_conversations() -> int:
    anon_days = int(current_app.config.get("CHATBOT_ANON_RETENTION_DAYS", 30))
    auth_days = int(current_app.config.get("CHATBOT_AUTH_RETENTION_DAYS", 180))
    current_time = datetime.now(timezone.utc)
    cutoff_anon = current_time - timedelta(days=anon_days)
    cutoff_auth = current_time - timedelta(days=auth_days)

    stale = ChatbotConversation.query.filter(
        or_(
            and_(
                ChatbotConversation.user_id.is_(None),
                ChatbotConversation.updated_at < cutoff_anon,
            ),
            and_(
                ChatbotConversation.user_id.isnot(None),
                ChatbotConversation.updated_at < cutoff_auth,
            ),
        )
    ).all()
    if not stale:
        return 0

    deleted = len(stale)
    for conversation in stale:
        db.session.delete(conversation)
    db.session.commit()
    return deleted


def rebuild_fts_index() -> None:
    ensure_chatbot_storage()
    db.session.execute(db.text(f"DELETE FROM {CHATBOT_FTS_TABLE}"))
    rows = (
        db.session.query(ChatbotKnowledgeChunk, ChatbotKnowledgeDocument)
        .join(ChatbotKnowledgeDocument, ChatbotKnowledgeDocument.id == ChatbotKnowledgeChunk.document_id)
        .filter(ChatbotKnowledgeDocument.is_active.is_(True))
        .all()
    )
    for chunk, document in rows:
        db.session.execute(
            db.text(
                f"""
                INSERT INTO {CHATBOT_FTS_TABLE}(chunk_id, content, source_title, scope_tags)
                VALUES (:chunk_id, :content, :source_title, :scope_tags)
                """
            ),
            {
                "chunk_id": chunk.id,
                "content": chunk.content,
                "source_title": document.source_title,
                "scope_tags": " ".join(document.scope_tags_json or []),
            },
        )
    db.session.commit()


def reembed_knowledge_base(*, only_missing: bool = True) -> dict:
    rows = ChatbotKnowledgeChunk.query.order_by(ChatbotKnowledgeChunk.id.asc()).all()
    pending = [row for row in rows if not only_missing or not row.embedding_json]
    if not pending:
        return {"embedded": 0}

    embeddings = embed_texts([row.content for row in pending])
    for row, embedding in zip(pending, embeddings):
        row.embedding_json = embedding
    db.session.commit()
    return {"embedded": len(pending)}


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    client = _openai_client()
    response = client.embeddings.create(
        model=current_app.config["CHATBOT_EMBEDDING_MODEL"],
        input=texts,
    )
    return [list(item.embedding) for item in response.data]


def moderate_message(text: str) -> bool:
    if not current_app.config.get("OPENAI_API_KEY") or not _openai_capability_available("moderation"):
        return False
    try:
        client = _openai_client()
        response = client.moderations.create(
            model=current_app.config["CHATBOT_MODERATION_MODEL"],
            input=text,
        )
        result = response.results[0]
        flagged = getattr(result, "flagged", None)
        if flagged is None and isinstance(result, dict):
            flagged = result.get("flagged", False)
        return bool(flagged)
    except Exception as exc:
        # Fail-open for availability: if moderation provider is temporarily unavailable,
        # continue with normal flow instead of crashing the request.
        _register_openai_failure("moderation", exc)
        return False


def _openai_client():
    api_key = (current_app.config.get("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise ChatbotUnavailableError("OPENAI_API_KEY não configurada.")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ChatbotUnavailableError("SDK OpenAI indisponível neste ambiente.") from exc
    timeout = current_app.config.get("CHATBOT_OPENAI_TIMEOUT_SECONDS", 20)
    return OpenAI(api_key=api_key, timeout=timeout)


def _fts_query(message: str) -> str:
    terms = []
    for token in re.findall(r"[a-zA-Z0-9À-ÿ]{3,}", message.lower()):
        if token not in STOPWORDS:
            terms.append(token.replace('"', ""))
    if not terms:
        return ""
    return " OR ".join(dict.fromkeys(terms))


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if not norm_a or not norm_b:
        return 0.0
    return dot / (norm_a * norm_b)


def retrieve_chunks(message: str, *, limit: int = 5) -> list[RetrievedChunk]:
    ensure_chatbot_storage()
    indexed = {
        row.id: RetrievedChunk(chunk=row)
        for row in (
            db.session.query(ChatbotKnowledgeChunk)
            .join(ChatbotKnowledgeDocument)
            .filter(ChatbotKnowledgeDocument.is_active.is_(True))
            .all()
        )
    }
    if not indexed:
        sync_knowledge_base()
        indexed = {
            row.id: RetrievedChunk(chunk=row)
            for row in (
                db.session.query(ChatbotKnowledgeChunk)
                .join(ChatbotKnowledgeDocument)
                .filter(ChatbotKnowledgeDocument.is_active.is_(True))
                .all()
            )
        }

    query = _fts_query(message)
    if query:
        try:
            lexical_rows = db.session.execute(
                db.text(
                    f"""
                    SELECT chunk_id, bm25({CHATBOT_FTS_TABLE}) AS rank
                    FROM {CHATBOT_FTS_TABLE}
                    WHERE {CHATBOT_FTS_TABLE} MATCH :query
                    ORDER BY rank
                    LIMIT :limit
                    """
                ),
                {"query": query, "limit": max(limit * 2, 8)},
            ).fetchall()
        except Exception:
            lexical_rows = []
        for row in lexical_rows:
            item = indexed.get(int(row.chunk_id))
            if item:
                item.lexical_score = max(item.lexical_score, 1 / (1 + abs(float(row.rank or 0))))

    embedding_candidates = [
        item for item in indexed.values() if item.chunk.embedding_json
    ]
    if (
        embedding_candidates
        and current_app.config.get("OPENAI_API_KEY")
        and _openai_capability_available("embeddings")
    ):
        try:
            query_embedding = embed_texts([message])[0]
            for item in embedding_candidates:
                score = _cosine_similarity(query_embedding, item.chunk.embedding_json or [])
                item.semantic_score = max(item.semantic_score, max(score, 0.0))
        except Exception as exc:
            _register_openai_failure("embeddings", exc)

    ranked = sorted(
        indexed.values(),
        key=lambda item: item.combined_score,
        reverse=True,
    )
    return [item for item in ranked[:limit] if item.combined_score > 0]


def _context_block(chunks: list[RetrievedChunk]) -> tuple[str, list[dict]]:
    parts = []
    citations = []
    for index, item in enumerate(chunks, start=1):
        doc = item.chunk.document
        snippet = item.chunk.content[:220].strip()
        parts.append(
            f"[Fonte {index}] {doc.source_title} ({doc.canonical_url or '/'})\n{item.chunk.content}"
        )
        citations.append(
            {
                "title": doc.source_title,
                "url": doc.canonical_url or "/",
                "snippet": snippet,
            }
        )
    return "\n\n".join(parts), citations


def _message_window(conversation: ChatbotConversation, *, limit: int = 6) -> list[ChatbotMessage]:
    rows = (
        ChatbotMessage.query.filter_by(conversation_id=_conversation_id(conversation))
        .order_by(ChatbotMessage.created_at.desc())
        .limit(limit)
        .all()
    )
    rows.reverse()
    return rows


def _build_response_prompt(
    *,
    conversation: ChatbotConversation,
    user_message: str,
    intent: str,
    context_text: str,
) -> list[dict]:
    system_prompt = (
        "Você é o assistente do Terracota. "
        "Responda em português do Brasil. "
        "Seu escopo é: produto Terracota, planos, cobrança, exportação, FAQ pública, empresa e privacidade. "
        "Não invente preços, limites, políticas ou promessas regulatórias. "
        "Quando a pergunta exigir interpretação jurídica/regulatória específica, responda com cautela e recomende suporte humano. "
        "Use apenas o contexto fornecido. "
        "Retorne JSON puro com as chaves: answer, confidence, needs_human, citations, suggested_actions."
    )
    messages = [{"role": "system", "content": system_prompt}]
    if conversation.session_summary:
        messages.append(
            {
                "role": "system",
                "content": f"Resumo da conversa até aqui:\n{conversation.session_summary}",
            }
        )
    messages.append(
        {
            "role": "system",
            "content": f"Intenção classificada: {intent}. Contexto recuperado:\n{context_text}",
        }
    )
    for row in _message_window(conversation):
        messages.append({"role": row.role, "content": row.content})
    messages.append({"role": "user", "content": user_message})
    return messages


def _build_streaming_prompt(
    *,
    conversation: ChatbotConversation,
    user_message: str,
    intent: str,
    context_text: str,
) -> list[dict]:
    system_prompt = (
        "Você é o assistente do Terracota. "
        "Responda em português do Brasil, de forma objetiva e clara. "
        "Seu escopo é: produto Terracota, planos, cobrança, exportação, FAQ pública, empresa e privacidade. "
        "Use apenas o contexto fornecido. "
        "Não invente preços, limites, políticas ou garantias regulatórias. "
        "Se a pergunta exigir interpretação jurídica ou regulatória específica, responda com cautela e recomende suporte humano. "
        "Retorne apenas a resposta final em texto simples, sem JSON."
    )
    messages = [{"role": "system", "content": system_prompt}]
    if conversation.session_summary:
        messages.append(
            {
                "role": "system",
                "content": f"Resumo da conversa até aqui:\n{conversation.session_summary}",
            }
        )
    messages.append(
        {
            "role": "system",
            "content": f"Intenção classificada: {intent}. Contexto recuperado:\n{context_text}",
        }
    )
    for row in _message_window(conversation):
        messages.append({"role": row.role, "content": row.content})
    messages.append({"role": "user", "content": user_message})
    return messages


def _response_to_text(response) -> str:
    output_text = getattr(response, "output_text", None)
    if output_text:
        return output_text
    data = response.model_dump() if hasattr(response, "model_dump") else {}
    if isinstance(data, dict):
        text = data.get("output_text")
        if text:
            return text
    return ""


def _parse_model_payload(payload_text: str, *, citations: list[dict]) -> dict:
    payload_text = (payload_text or "").strip()
    match = re.search(r"\{.*\}", payload_text, flags=re.DOTALL)
    if not match:
        raise ValueError("Resposta do modelo não trouxe JSON.")
    parsed = json.loads(match.group(0))
    answer = (parsed.get("answer") or "").strip()
    confidence = (parsed.get("confidence") or "low").strip().lower()
    if confidence not in {"low", "medium", "high"}:
        confidence = "low"
    suggested_actions = parsed.get("suggested_actions") or []
    if not isinstance(suggested_actions, list):
        suggested_actions = []
    model_citations = parsed.get("citations") or []
    safe_citations = []
    if isinstance(model_citations, list):
        for item in model_citations[:3]:
            if isinstance(item, dict):
                safe_citations.append(
                    {
                        "title": (item.get("title") or "")[:255],
                        "url": (item.get("url") or "/")[:500],
                        "snippet": (item.get("snippet") or "")[:300],
                    }
                )
    if not safe_citations:
        safe_citations = citations[:3]
    return {
        "answer": answer,
        "confidence": confidence,
        "needs_human": bool(parsed.get("needs_human", False)),
        "citations": safe_citations,
        "suggested_actions": suggested_actions[:4],
    }


def _usage_tokens(response) -> tuple[int, int]:
    usage = getattr(response, "usage", None)
    if not usage:
        return 0, 0
    prompt_tokens = getattr(usage, "input_tokens", 0)
    completion_tokens = getattr(usage, "output_tokens", 0)
    if isinstance(usage, dict):
        prompt_tokens = usage.get("input_tokens", 0)
        completion_tokens = usage.get("output_tokens", 0)
    return int(prompt_tokens or 0), int(completion_tokens or 0)


def _event_to_dict(event) -> dict:
    if isinstance(event, dict):
        return event
    if hasattr(event, "model_dump"):
        try:
            dumped = event.model_dump()
            if isinstance(dumped, dict):
                return dumped
        except Exception:
            return {}
    return {}


def _event_type(event) -> str:
    value = getattr(event, "type", None)
    if value:
        return str(value)
    return str(_event_to_dict(event).get("type", ""))


def _event_usage_tokens(event) -> tuple[int, int]:
    response_obj = getattr(event, "response", None)
    usage_obj = getattr(response_obj, "usage", None) if response_obj else None
    if usage_obj is not None:
        prompt_tokens = getattr(usage_obj, "input_tokens", None)
        completion_tokens = getattr(usage_obj, "output_tokens", None)
        if isinstance(usage_obj, dict):
            prompt_tokens = usage_obj.get("input_tokens", usage_obj.get("prompt_tokens", 0))
            completion_tokens = usage_obj.get("output_tokens", usage_obj.get("completion_tokens", 0))
        if prompt_tokens is not None or completion_tokens is not None:
            return int(prompt_tokens or 0), int(completion_tokens or 0)

    data = _event_to_dict(event)
    response_data = data.get("response")
    usage_data = None
    if isinstance(response_data, dict):
        usage_data = response_data.get("usage")
    if not usage_data:
        usage_data = data.get("usage")
    if isinstance(usage_data, dict):
        prompt_tokens = usage_data.get("input_tokens", usage_data.get("prompt_tokens", 0))
        completion_tokens = usage_data.get("output_tokens", usage_data.get("completion_tokens", 0))
        return int(prompt_tokens or 0), int(completion_tokens or 0)
    return 0, 0


def _event_output_text(event) -> str:
    response_obj = getattr(event, "response", None)
    if response_obj is not None:
        output_text = getattr(response_obj, "output_text", None)
        if output_text:
            return str(output_text).strip()
        if hasattr(response_obj, "model_dump"):
            try:
                dumped = response_obj.model_dump()
                if isinstance(dumped, dict):
                    text = dumped.get("output_text")
                    if text:
                        return str(text).strip()
            except Exception:
                pass

    data = _event_to_dict(event)
    response_data = data.get("response")
    if isinstance(response_data, dict):
        text = response_data.get("output_text")
        if text:
            return str(text).strip()
    text = data.get("text")
    if text:
        return str(text).strip()
    return ""


def _stream_error_message(event) -> str:
    message_text = getattr(event, "message", None)
    if message_text:
        return str(message_text).strip()

    data = _event_to_dict(event)
    if isinstance(data.get("error"), dict):
        candidate = data["error"].get("message")
        if candidate:
            return str(candidate).strip()
    candidate = data.get("message")
    if candidate:
        return str(candidate).strip()
    return ""


def _stream_model_response(*, client, messages: list[dict], model: str):
    answer_parts: list[str] = []
    prompt_tokens = 0
    completion_tokens = 0
    try:
        stream = client.responses.create(
            model=model,
            input=messages,
            stream=True,
        )

        for event in stream:
            event_type = _event_type(event)
            if event_type == "response.output_text.delta":
                delta = getattr(event, "delta", None)
                if delta is None:
                    delta = _event_to_dict(event).get("delta", "")
                if delta:
                    answer_parts.append(str(delta))
                    yield ("delta", {"delta": str(delta)})
                continue

            if event_type in {"response.output_text.done", "response.output_text.final"}:
                final_chunk = getattr(event, "text", None)
                if final_chunk is None:
                    final_chunk = _event_output_text(event)
                if final_chunk and not "".join(answer_parts).strip():
                    answer_parts.append(str(final_chunk))
                continue

            if event_type in {"response.completed", "response.done"}:
                ev_prompt_tokens, ev_completion_tokens = _event_usage_tokens(event)
                prompt_tokens = max(prompt_tokens, ev_prompt_tokens)
                completion_tokens = max(completion_tokens, ev_completion_tokens)
                final_text = _event_output_text(event)
                if final_text and not "".join(answer_parts).strip():
                    answer_parts = [final_text]
                continue

            if event_type in {"response.error", "error"}:
                raise ChatbotUnavailableError(
                    _stream_error_message(event) or "Falha ao gerar resposta em streaming."
                )
    except Exception as exc:
        _register_openai_failure("responses", exc)
        raise

    answer = "".join(answer_parts).strip()
    return answer, prompt_tokens, completion_tokens


def _generate_grounded_answer(
    *,
    conversation: ChatbotConversation,
    user_message: str,
    intent: str,
    chunks: list[RetrievedChunk],
) -> tuple[dict, int, int, str]:
    conversation = _bind_conversation(conversation)
    context_text, citations = _context_block(chunks)
    messages = _build_response_prompt(
        conversation=conversation,
        user_message=user_message,
        intent=intent,
        context_text=context_text,
    )
    client = _openai_client()
    primary_model = current_app.config["CHATBOT_MODEL"]
    try:
        response = client.responses.create(model=primary_model, input=messages)
    except Exception as exc:
        _register_openai_failure("responses", exc)
        raise
    prompt_tokens, completion_tokens = _usage_tokens(response)
    parsed = _parse_model_payload(_response_to_text(response), citations=citations)
    used_model = primary_model

    if (
        parsed["confidence"] == "low"
        and not parsed["needs_human"]
        and current_app.config.get("CHATBOT_FALLBACK_MODEL")
        and current_app.config["CHATBOT_FALLBACK_MODEL"] != primary_model
    ):
        fallback_model = current_app.config["CHATBOT_FALLBACK_MODEL"]
        try:
            retry = client.responses.create(model=fallback_model, input=messages)
        except Exception as exc:
            _register_openai_failure("responses", exc)
            raise
        retry_prompt_tokens, retry_completion_tokens = _usage_tokens(retry)
        prompt_tokens += retry_prompt_tokens
        completion_tokens += retry_completion_tokens
        retry_payload = _parse_model_payload(_response_to_text(retry), citations=citations)
        if retry_payload.get("answer"):
            parsed = retry_payload
            used_model = fallback_model

    parsed["citations"] = parsed.get("citations") or citations[:3]
    return parsed, prompt_tokens, completion_tokens, used_model


def _maybe_summarize(conversation: ChatbotConversation) -> None:
    conversation = _bind_conversation(conversation)
    threshold = int(current_app.config.get("CHATBOT_MAX_TURNS_BEFORE_SUMMARY", 6))
    if threshold <= 0 or conversation.turns_count == 0 or conversation.turns_count % threshold != 0:
        return
    if not current_app.config.get("OPENAI_API_KEY") or not _openai_capability_available("responses"):
        recent = serialize_messages(conversation, limit=6)
        conversation.session_summary = " | ".join(item["content"][:140] for item in recent[-4:])
        db.session.commit()
        return

    recent = serialize_messages(conversation, limit=8)
    prompt = [
        {
            "role": "system",
            "content": (
                "Resuma a conversa em português em no máximo 5 linhas, "
                "focando em intenção do usuário, dúvidas em aberto e contexto útil."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(recent, ensure_ascii=False),
        },
    ]
    client = _openai_client()
    try:
        response = client.responses.create(model=current_app.config["CHATBOT_MODEL"], input=prompt)
        summary = _response_to_text(response).strip()
    except Exception as exc:
        _register_openai_failure("responses", exc)
        summary = ""
    conversation.session_summary = summary[:1200] if summary else conversation.session_summary
    db.session.commit()


def create_message(
    *,
    conversation: ChatbotConversation,
    role: str,
    content: str,
    citations: list[dict] | None = None,
    model: str | None = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    latency_ms: int | None = None,
    flagged: bool = False,
) -> ChatbotMessage:
    row = ChatbotMessage(
        conversation_id=conversation.id,
        role=role,
        content=content,
        citations_json=citations or [],
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_ms=latency_ms,
        flagged=flagged,
    )
    db.session.add(row)
    db.session.commit()
    return row


def process_user_message(
    *,
    conversation: ChatbotConversation,
    message: str,
    page_context: str | None = None,
    locale: str | None = None,
) -> dict:
    conversation = _bind_conversation(conversation)
    text = sanitize_message(message)
    if not text:
        raise ChatbotError("Mensagem vazia.")

    if moderate_message(text):
        create_message(
            conversation=conversation,
            role="user",
            content=text,
            flagged=True,
        )
        raise ChatbotModerationError("Mensagem bloqueada por segurança.")

    create_message(
        conversation=conversation,
        role="user",
        content=text,
    )

    conversation.source_page = (page_context or conversation.source_page or "landing-faq")[:120]
    conversation.locale = (locale or conversation.locale or "pt-BR")[:16]
    conversation.turns_count += 1

    intent = classify_intent(text)
    conversation.last_user_intent = intent
    db.session.commit()

    if intent in {"out_of_scope", "regulatory_deep"}:
        payload = safe_fallback_payload(
            conversation=conversation,
            intent=intent,
            reason="scope_guardrail",
        )
        assistant_row = create_message(
            conversation=conversation,
            role="assistant",
            content=payload["answer"],
            citations=payload["citations"],
            flagged=False,
        )
        payload["message_id"] = assistant_row.id
        return payload

    sync_if_needed()
    chunks = retrieve_chunks(text)
    if not chunks or not _openai_capability_available("responses"):
        payload = safe_fallback_payload(
            conversation=conversation,
            intent=intent,
            reason="no_context" if not chunks else "openai_unavailable",
        )
        assistant_row = create_message(
            conversation=conversation,
            role="assistant",
            content=payload["answer"],
            citations=payload["citations"],
        )
        payload["message_id"] = assistant_row.id
        return payload

    started = time.perf_counter()
    try:
        payload, prompt_tokens, completion_tokens, used_model = _generate_grounded_answer(
            conversation=conversation,
            user_message=text,
            intent=intent,
            chunks=chunks,
        )
    except Exception:
        payload = safe_fallback_payload(
            conversation=conversation,
            intent=intent,
            reason="model_failure",
        )
        prompt_tokens = 0
        completion_tokens = 0
        used_model = None
    latency_ms = int((time.perf_counter() - started) * 1000)

    if not payload.get("answer"):
        payload = safe_fallback_payload(
            conversation=conversation,
            intent=intent,
            reason="empty_answer",
        )

    payload.setdefault("handoff_url", build_handoff_link(conversation, payload["answer"]))
    if payload["confidence"] == "low":
        payload["needs_human"] = True
        payload["handoff_url"] = build_handoff_link(conversation, payload["answer"])
        if "Falar com especialista por e-mail" not in payload["suggested_actions"]:
            payload["suggested_actions"].insert(0, "Falar com especialista por e-mail")

    assistant_row = create_message(
        conversation=conversation,
        role="assistant",
        content=payload["answer"],
        citations=payload["citations"],
        model=used_model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_ms=latency_ms,
    )
    payload["message_id"] = assistant_row.id
    payload["conversation_id"] = conversation.id

    conversation.last_confidence = payload["confidence"]
    conversation.last_model = used_model
    db.session.commit()

    _maybe_summarize(conversation)
    log_action(
        "chatbot.message.answer",
        user_id=conversation.user_id,
        details={
            "conversation_id": conversation.id,
            "intent": intent,
            "confidence": payload["confidence"],
            "needs_human": payload["needs_human"],
            "latency_ms": latency_ms,
        },
    )
    return payload


def stream_user_message(
    *,
    conversation: ChatbotConversation,
    message: str,
    page_context: str | None = None,
    locale: str | None = None,
):
    conversation = _bind_conversation(conversation)
    text = sanitize_message(message)
    if not text:
        raise ChatbotError("Mensagem vazia.")

    if moderate_message(text):
        create_message(
            conversation=conversation,
            role="user",
            content=text,
            flagged=True,
        )
        raise ChatbotModerationError("Mensagem bloqueada por segurança.")

    create_message(
        conversation=conversation,
        role="user",
        content=text,
    )

    conversation.source_page = (page_context or conversation.source_page or "landing-faq")[:120]
    conversation.locale = (locale or conversation.locale or "pt-BR")[:16]
    conversation.turns_count += 1

    intent = classify_intent(text)
    conversation.last_user_intent = intent
    db.session.commit()

    if intent in {"out_of_scope", "regulatory_deep"}:
        payload = safe_fallback_payload(
            conversation=conversation,
            intent=intent,
            reason="scope_guardrail",
        )
        assistant_row = create_message(
            conversation=conversation,
            role="assistant",
            content=payload["answer"],
            citations=payload["citations"],
        )
        payload["message_id"] = assistant_row.id
        payload["conversation_id"] = conversation.id
        conversation.last_confidence = payload["confidence"]
        db.session.commit()
        _maybe_summarize(conversation)
        yield ("done", payload)
        return

    sync_if_needed()
    chunks = retrieve_chunks(text)
    if not chunks or not current_app.config.get("OPENAI_API_KEY"):
        payload = safe_fallback_payload(
            conversation=conversation,
            intent=intent,
            reason="no_context" if not chunks else "openai_unavailable",
        )
        assistant_row = create_message(
            conversation=conversation,
            role="assistant",
            content=payload["answer"],
            citations=payload["citations"],
        )
        payload["message_id"] = assistant_row.id
        payload["conversation_id"] = conversation.id
        conversation.last_confidence = payload["confidence"]
        db.session.commit()
        _maybe_summarize(conversation)
        yield ("done", payload)
        return

    context_text, citations = _context_block(chunks)
    messages = _build_streaming_prompt(
        conversation=conversation,
        user_message=text,
        intent=intent,
        context_text=context_text,
    )
    client = _openai_client()
    primary_model = current_app.config["CHATBOT_MODEL"]
    fallback_model = (
        current_app.config.get("CHATBOT_FALLBACK_MODEL")
        if current_app.config.get("CHATBOT_FALLBACK_MODEL")
        else None
    )
    used_model = primary_model
    started = time.perf_counter()
    prompt_tokens = 0
    completion_tokens = 0

    try:
        answer, prompt_tokens, completion_tokens = yield from _stream_model_response(
            client=client,
            messages=messages,
            model=primary_model,
        )
    except Exception:
        if fallback_model and fallback_model != primary_model:
            yield (
                "replace",
                {"message": "Refazendo a resposta com o modelo alternativo..."},
            )
            try:
                used_model = fallback_model
                answer, fallback_prompt_tokens, fallback_completion_tokens = yield from _stream_model_response(
                    client=client,
                    messages=messages,
                    model=fallback_model,
                )
                prompt_tokens += fallback_prompt_tokens
                completion_tokens += fallback_completion_tokens
            except Exception:
                payload = safe_fallback_payload(
                    conversation=conversation,
                    intent=intent,
                    reason="stream_failure",
                )
                assistant_row = create_message(
                    conversation=conversation,
                    role="assistant",
                    content=payload["answer"],
                    citations=payload["citations"],
                )
                payload["message_id"] = assistant_row.id
                payload["conversation_id"] = conversation.id
                conversation.last_confidence = payload["confidence"]
                db.session.commit()
                _maybe_summarize(conversation)
                yield ("done", payload)
                return
        else:
            payload = safe_fallback_payload(
                conversation=conversation,
                intent=intent,
                reason="stream_failure",
            )
            assistant_row = create_message(
                conversation=conversation,
                role="assistant",
                content=payload["answer"],
                citations=payload["citations"],
            )
            payload["message_id"] = assistant_row.id
            payload["conversation_id"] = conversation.id
            conversation.last_confidence = payload["confidence"]
            db.session.commit()
            _maybe_summarize(conversation)
            yield ("done", payload)
            return

    if not answer:
        payload = safe_fallback_payload(
            conversation=conversation,
            intent=intent,
            reason="empty_stream_answer",
        )
    else:
        confidence = confidence_from_chunks(chunks)
        needs_human = confidence == "low"
        suggested_actions = ["Ver central de ajuda completa"]
        if needs_human:
            suggested_actions.insert(0, "Falar com especialista por e-mail")
        payload = {
            "answer": answer,
            "citations": citations[:3],
            "confidence": confidence,
            "needs_human": needs_human,
            "suggested_actions": suggested_actions,
            "handoff_url": build_handoff_link(conversation, answer),
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            },
        }
    payload.setdefault("model", used_model)
    payload.setdefault(
        "usage",
        {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        },
    )

    latency_ms = int((time.perf_counter() - started) * 1000)
    assistant_row = create_message(
        conversation=conversation,
        role="assistant",
        content=payload["answer"],
        citations=payload["citations"],
        model=used_model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_ms=latency_ms,
    )
    payload["message_id"] = assistant_row.id
    payload["conversation_id"] = conversation.id
    conversation.last_confidence = payload["confidence"]
    conversation.last_model = used_model
    db.session.commit()

    _maybe_summarize(conversation)
    log_action(
        "chatbot.message.answer",
        user_id=conversation.user_id,
        details={
            "conversation_id": conversation.id,
            "intent": intent,
            "confidence": payload["confidence"],
            "needs_human": payload["needs_human"],
            "latency_ms": latency_ms,
            "mode": "stream",
        },
    )
    yield ("done", payload)


def sync_if_needed() -> None:
    ensure_chatbot_storage()
    if ChatbotKnowledgeDocument.query.filter_by(is_active=True).count() == 0:
        sync_knowledge_base()
    if (
        current_app.config.get("OPENAI_API_KEY")
        and ChatbotKnowledgeChunk.query.filter(ChatbotKnowledgeChunk.embedding_json.isnot(None)).count() == 0
        and _openai_capability_available("embeddings")
    ):
        try:
            reembed_knowledge_base()
        except Exception as exc:
            _register_openai_failure("embeddings", exc)


def chatbot_metrics() -> dict:
    total_conversations = ChatbotConversation.query.count()
    recent_conversations = (
        ChatbotConversation.query.order_by(ChatbotConversation.updated_at.desc())
        .limit(25)
        .all()
    )
    total_feedback = ChatbotFeedback.query.count()
    negative_feedback = ChatbotFeedback.query.filter_by(rating="down").count()
    flagged_messages = ChatbotMessage.query.filter_by(flagged=True).count()
    handoff_count = (
        ChatbotMessage.query.filter(ChatbotMessage.content.ilike("%especialista%")).count()
    )
    avg_latency = (
        db.session.query(db.func.avg(ChatbotMessage.latency_ms))
        .filter(ChatbotMessage.latency_ms.isnot(None))
        .scalar()
        or 0
    )
    total_prompt_tokens = (
        db.session.query(db.func.sum(ChatbotMessage.prompt_tokens)).scalar() or 0
    )
    total_completion_tokens = (
        db.session.query(db.func.sum(ChatbotMessage.completion_tokens)).scalar() or 0
    )
    return {
        "total_conversations": total_conversations,
        "recent_conversations": recent_conversations,
        "total_feedback": total_feedback,
        "negative_feedback": negative_feedback,
        "flagged_messages": flagged_messages,
        "handoff_count": handoff_count,
        "avg_latency": int(avg_latency or 0),
        "total_prompt_tokens": int(total_prompt_tokens),
        "total_completion_tokens": int(total_completion_tokens),
    }
