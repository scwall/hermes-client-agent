"""Conversation-to-runtime mapping."""

import logging

from hermes_agent.acp.models import AcpConversation

_log = logging.getLogger("hermes-agent")


class ConversationStore:
    def resolve(self, conversation_id, runtime_id, workspace="", model=""):
        return AcpConversation.get_or_create_for_runtime(conversation_id, runtime_id, workspace, model)

    def get_runtime_id(self, conversation_id):
        conv = AcpConversation.get_by_conversation_id(conversation_id)
        return conv.runtime_id if conv else None

    def get_upstream_session(self, conversation_id):
        conv = AcpConversation.get_by_conversation_id(conversation_id)
        return conv.upstream_session_id if conv else None

    def set_upstream_session(self, conversation_id, upstream_session_id):
        AcpConversation.update_upstream_session(conversation_id, upstream_session_id)


_conversation_store = None


def get_conversation_store():
    global _conversation_store
    if _conversation_store is None:
        _conversation_store = ConversationStore()
    return _conversation_store
