from typing import NotRequired, TypedDict

from langgraph.graph import END, START, StateGraph

from app.domain.models import ChatAnswer, ChatRouteResult
from app.ports.chat_workflow import (
    ChatWorkflowActions,
    ChatWorkflowRequest,
)


class _ChatGraphState(TypedDict):
    request: ChatWorkflowRequest
    actions: ChatWorkflowActions
    route_result: NotRequired[ChatRouteResult]
    answer: NotRequired[ChatAnswer]


class LangGraphChatWorkflow:
    """LangGraph-backed orchestration for the chat route and answer chain."""

    def __init__(self) -> None:
        graph = StateGraph(_ChatGraphState)
        graph.add_node("route", self._route_question)
        graph.add_node("answer", self._answer_question)
        graph.add_edge(START, "route")
        graph.add_edge("route", "answer")
        graph.add_edge("answer", END)
        self._graph = graph.compile()

    def answer_question(
        self,
        request: ChatWorkflowRequest,
        actions: ChatWorkflowActions,
    ) -> ChatAnswer:
        result = self._graph.invoke(
            {
                "request": request,
                "actions": actions,
            }
        )
        answer = result.get("answer")
        if answer is None:
            raise RuntimeError("chat workflow completed without an answer")
        return answer

    def _route_question(self, state: _ChatGraphState) -> dict[str, ChatRouteResult]:
        request = state["request"]
        route_result = state["actions"].route_question(
            request.question,
            session_id=request.session_id,
            router_model=request.router_model,
            router_provider=request.router_provider,
        )
        return {"route_result": route_result}

    def _answer_question(self, state: _ChatGraphState) -> dict[str, ChatAnswer]:
        request = state["request"]
        route_result = state["route_result"]
        answer = state["actions"].answer_routed_question(
            question=request.question,
            session_id=route_result.session_id,
            route_result=route_result,
            answer_model=request.answer_model,
            answer_provider=request.answer_provider,
        )
        return {"answer": answer}
