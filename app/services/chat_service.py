"""
AI Chat Service — Terracota product specialist chatbot.

Uses OpenAI GPT-4o-mini with the full product knowledge base
embedded in the system prompt (no RAG needed for this KB size).
"""

import uuid
from datetime import datetime, timedelta, timezone

from openai import OpenAI

from app.extensions import db
from app.models.chat import ChatMessage, ChatSession

SYSTEM_PROMPT = """\
Você é o assistente virtual do Terracota, plataforma de rotulagem nutricional \
conforme ANVISA. Responda SOMENTE sobre: produto Terracota, funcionalidades, \
planos, preços, conformidade ANVISA (RDC 429/2020, IN 75/2020, RDC 26/2015), \
fluxo de uso e suporte.

REGRAS:
1. Responda em português brasileiro, tom profissional mas acessível.
2. Seja conciso (2-4 parágrafos máximo). Use listas quando apropriado.
3. Se a pergunta NÃO for sobre Terracota/rotulagem/ANVISA, diga: \
"Essa pergunta está fora da minha especialidade. Posso ajudar com dúvidas \
sobre o Terracota, rotulagem nutricional e conformidade ANVISA."
4. Se o usuário precisar de ajuda específica que você não consegue resolver, \
ofereça: "Para esse caso específico, recomendo falar com nosso time \
especialista por e-mail. Eles respondem em até 24h úteis."
5. NUNCA invente informações. Se não souber, diga que não tem essa informação.
6. NUNCA forneça orientação regulatória como substituto de um nutricionista.

KNOWLEDGE BASE:
{knowledge_base}"""

KNOWLEDGE_BASE = """\
## Produto
Terracota é uma plataforma web que gera tabelas nutricionais em conformidade \
com ANVISA (RDC 429/2020, IN 75/2020) em minutos. O motor aplica \
automaticamente regras de arredondamento (Anexo IV e XXII da IN 75), cálculo \
de energia pelo método Atwater, %VD e declaração de alérgenos (RDC 26/2015).

## Como Funciona (3 passos)
1. Entrada: Importação de Excel ou cadastro manual de ingredientes e porção
2. Processamento: Motor aplica IN 75, %VD, energia, alérgenos automaticamente
3. Saída: PDF regulatório pronto para design e impressão

## Planos e Preços
- Essencial (Grátis): 1 tabela/mês, 10 ingredientes, sem exportação. Sem cartão.
- Start (R$ 39,90/mês): 3 tabelas/mês, 25 ingredientes, PDF, templates.
- Pro (R$ 79,90/mês): 10 tabelas/mês, 80 ingredientes, PDF+PNG, templates, \
histórico. Mais popular.
- Studio (R$ 199,90/mês): Ilimitado, branding personalizado, todas features.
Todos os planos: cancelamento sem multa, conformidade RDC 429 + IN 75 + \
RDC 26, importação Excel.

## Funcionalidades
- Conformidade automática (IN 75, %VD, Atwater, arredondamentos)
- Importação Excel (detecta colunas PT/EN, formato BR 1.234,56, até 500 linhas)
- Alérgenos RDC 26/2015 (8+ alérgenos, seção "Informações Importantes")
- Exportação PDF (Start+) e PNG (Pro+)
- Branding personalizado (Studio)
- Histórico de versões (Pro+)
- Tempo médio: <5 min do input ao PDF exportável

## Público-alvo
- Nutricionistas e consultores (múltiplos clientes, padronização IN 75)
- Fábricas e indústrias (risco regulatório, recalls, escala)
- Marcas artesanais e startups (primeiro produto, sem expertise regulatória)

## Conformidade ANVISA
- >60% dos rótulos no Brasil têm desvios técnicos
- Multas: R$ 75 mil a R$ 1,5 milhão
- Consequências: recalls, atrasos, dano à marca
- Terracota NÃO substitui nutricionista — automatiza cálculo e conformidade

## Suporte
- E-mail: comercial@terracotabpo.com
- Resposta em até 24h úteis
- Cada plano inclui suporte por e-mail
- Para casos regulatórios específicos, recomendamos consultar nutricionista

## Conta e Segurança
- Reset de senha na tela de login
- Trocar senha em Conta > Configurações
- Excluir conta em Conta > Configurações > Zona de Perigo
- Exportar dados (LGPD) em Conta > Configurações"""


class ChatService:
    """Manages AI chat sessions using OpenAI streaming."""

    def __init__(self):
        self.client = None
        self.model = "gpt-4o-mini"
        self.max_history = 20
        self.max_tokens = 500
        self.temperature = 0.3

    def init_app(self, app):
        api_key = app.config.get("OPENAI_API_KEY", "")
        if api_key:
            self.client = OpenAI(api_key=api_key)
        self.model = app.config.get("OPENAI_MODEL", "gpt-4o-mini")
        self.max_history = app.config.get("CHAT_MAX_HISTORY", 20)
        self.max_tokens = app.config.get("CHAT_MAX_TOKENS", 500)
        self.temperature = app.config.get("CHAT_TEMPERATURE", 0.3)

    @property
    def available(self):
        return self.client is not None

    def get_or_create_session(self, session_id=None, user_id=None):
        """Return existing session or create a new one."""
        if session_id:
            session = db.session.get(ChatSession, session_id)
            if session:
                session.last_activity = datetime.now(timezone.utc)
                db.session.commit()
                return session

        new_session = ChatSession(
            id=str(uuid.uuid4()),
            user_id=user_id,
        )
        db.session.add(new_session)
        db.session.commit()
        return new_session

    def _build_messages(self, session):
        """Build the OpenAI messages array: system + last N messages."""
        system_msg = {
            "role": "system",
            "content": SYSTEM_PROMPT.format(knowledge_base=KNOWLEDGE_BASE),
        }

        recent = (
            ChatMessage.query.filter_by(session_id=session.id)
            .order_by(ChatMessage.created_at.desc())
            .limit(self.max_history)
            .all()
        )
        recent.reverse()  # chronological

        history = [{"role": m.role, "content": m.content} for m in recent]
        return [system_msg] + history

    def chat_stream(self, session, user_message):
        """Generator that yields text chunks from the streaming response."""
        user_msg = ChatMessage(
            session_id=session.id,
            role="user",
            content=user_message[:5000],
        )
        db.session.add(user_msg)
        session.message_count += 1
        db.session.commit()

        messages = self._build_messages(session)

        stream = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            stream=True,
        )

        full_response = []
        for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                full_response.append(delta.content)
                yield delta.content

        assistant_content = "".join(full_response)
        assistant_msg = ChatMessage(
            session_id=session.id,
            role="assistant",
            content=assistant_content,
        )
        db.session.add(assistant_msg)
        session.message_count += 1
        db.session.commit()

    def cleanup_expired_sessions(self, ttl_hours=24):
        """Delete sessions and messages older than *ttl_hours*."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=ttl_hours)
        expired = ChatSession.query.filter(
            ChatSession.last_activity < cutoff
        ).all()
        count = len(expired)
        for s in expired:
            db.session.delete(s)  # cascade deletes messages
        db.session.commit()
        return count


# Singleton used by the blueprint
chat_service = ChatService()
