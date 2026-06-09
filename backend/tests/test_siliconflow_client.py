import json
from typing import Any

import httpx2
import pytest

from app.adapters.llm.siliconflow_client import (
    LlmProviderConfig,
    MultiProviderLlmClient,
    SiliconFlowConfig,
)
from app.core.errors import LlmRequestError
from app.domain.models import (
    AttachedDocument,
    ChatTurn,
    DocumentSummary,
    SelectedDocument,
    SheetProfile,
    SheetSummary,
    WorkbookProfile,
)


def test_siliconflow_client_generates_summary_routes_and_answers() -> None:
    requests: list[dict[str, Any]] = []
    responses = [
        {
            "document_title": "standards.xlsx",
            "document_type": "standard_matrix",
            "summary_text": "A standards workbook.",
            "business_domain": "standards",
            "coverage_scope": {
                "products": ["household appliances"],
                "standards": ["EN 1"],
            },
            "key_topics": ["EN", "DOW"],
            "positive_routing_terms": ["EN 1", "DOW"],
            "negative_routing_terms": ["pricing"],
            "exact_identifiers": ["EN 1"],
            "suitable_questions": ["Find standards dates"],
            "unsuitable_questions": ["Questions outside the workbook"],
            "sheet_summaries": [
                {
                    "sheet_id": "sheet_1",
                    "sheet_name": "EN",
                    "summary": "EN standards and dates.",
                    "important_columns": ["Code", "DOW"],
                    "likely_question_types": ["date lookup"],
                    "header_terms": ["Code", "DOW"],
                    "sampled_identifiers": ["EN 1"],
                }
            ],
            "routing_notes": "Select for EN DOW lookups.",
        },
        {
            "document_for_this_turn": [
                {
                    "file_id": "file_1",
                    "version_id": "version_1",
                    "match_level": "strong_match",
                    "matched_terms": ["EN", "DOW"],
                    "missing_terms": [],
                    "reason": "Question mentions EN.",
                    "confidence": 0.9,
                }
            ]
        },
        {
            "answer_blocks": [
                {
                    "text": "The workbook contains EN standards.",
                    "evidence_row_ids": ["S001_R1"],
                }
            ],
            "citations": [
                {
                    "version_id": "version_1",
                    "sheet_id": "sheet_1",
                    "row_id": "S001_R1",
                    "quote": "Code DOW",
                }
            ],
            "insufficient_evidence": False,
            "follow_up_suggestions": ["Ask for a DOW date."],
        },
    ]

    def post(_url: str, **kwargs: Any) -> httpx2.Response:
        requests.append(kwargs["json"])
        return httpx2.Response(
            200,
            request=httpx2.Request("POST", "https://api.example.test/v1/chat/completions"),
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(responses.pop(0), ensure_ascii=False)
                        }
                    }
                ]
            },
        )

    client = MultiProviderLlmClient(
        SiliconFlowConfig(
            api_base_url="https://api.example.test/v1",
            api_key="test-key",
            summary_model="deepseek-ai/DeepSeek-V4-Pro",
            router_model="inclusionAI/Ling-flash-2.0",
            answer_model="Qwen/Qwen3.6-27B",
            timeout_seconds=1,
            summary_max_profile_rows=2,
        ),
        post=post,
    )
    profile = WorkbookProfile(
        file_id="file_1",
        version_id="version_1",
        original_filename="standards.xlsx",
        file_hash="hash",
        sheets=[
            SheetProfile(
                sheet_id="sheet_1",
                sheet_code="S001",
                sheet_name="EN",
                row_count=2,
                column_count=2,
                sample_rows=[["Code", "DOW"], ["EN 1", "2024-01-01"]],
                candidate_header=["Code", "DOW"],
                profile_rows=[
                    ["Code", "DOW"],
                    ["EN 1", "2024-01-01"],
                    ["EN 2", "2025-01-01"],
                ],
            )
        ],
    )

    summary = client.generate_document_summary(profile)
    selected = client.route_documents("EN DOW?", [summary], max_documents=1)
    draft_answer = client.answer_with_rows(
        "EN DOW?",
        selected,
        [
            {
                "file_id": "file_1",
                "version_id": "version_1",
                "sheet_id": "sheet_1",
                "sheet_name": "EN",
                "row_id": "S001_R1",
                "cells": ["S001_R1", "Code", "DOW"],
            }
        ],
    )

    assert summary.business_domain == "standards"
    assert summary.document_title == "standards.xlsx"
    assert summary.document_type == "standard_matrix"
    assert summary.coverage_scope["standards"] == ["EN 1"]
    assert summary.positive_routing_terms == ["EN 1", "DOW"]
    assert summary.exact_identifiers == ["EN 1"]
    assert summary.sheet_summaries == [
        SheetSummary(
            sheet_id="sheet_1",
            sheet_name="EN",
            summary="EN standards and dates.",
            important_columns=["Code", "DOW"],
            likely_question_types=["date lookup"],
            header_terms=["Code", "DOW"],
            sampled_identifiers=["EN 1"],
        )
    ]
    assert selected[0].version_id == "version_1"
    assert selected[0].confidence == 0.9
    assert draft_answer.answer_blocks[0].text == "The workbook contains EN standards."
    assert draft_answer.answer_blocks[0].evidence_row_ids == ["S001_R1"]
    assert draft_answer.citations[0].row_id == "S001_R1"
    assert draft_answer.citations[0].quote == "Code DOW"
    assert draft_answer.citations[0].version_id == "version_1"
    assert draft_answer.citations[0].sheet_id == "sheet_1"
    assert [request["model"] for request in requests] == [
        "deepseek-ai/DeepSeek-V4-Pro",
        "inclusionAI/Ling-flash-2.0",
        "Qwen/Qwen3.6-27B",
    ]
    assert "enable_thinking" not in requests[0]
    assert "enable_thinking" not in requests[1]
    assert requests[2]["enable_thinking"] is False
    assert '"version_id": "string"' in requests[2]["messages"][-1]["content"]
    assert '"sheet_id": "string"' in requests[2]["messages"][-1]["content"]
    summary_payload = json.loads(
        requests[0]["messages"][1]["content"].split("Workbook profile:\n", 1)[1]
    )
    assert summary_payload["sheets"][0]["all_rows"][-1] == ["EN 2", "2025-01-01"]
    assert requests[1]["temperature"] == 0.0
    assert requests[1]["max_tokens"] == 1200


def test_siliconflow_router_filters_unknown_version() -> None:
    def post(_url: str, **_kwargs: Any) -> httpx2.Response:
        return httpx2.Response(
            200,
            request=httpx2.Request("POST", "https://api.example.test/v1/chat/completions"),
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "selected_documents": [
                                        {
                                            "file_id": "file_1",
                                            "version_id": "unknown",
                                            "reason": "bad id",
                                        }
                                    ]
                                }
                            )
                        }
                    }
                ]
            },
        )

    client = MultiProviderLlmClient(
        SiliconFlowConfig(
            api_base_url="https://api.example.test/v1",
            api_key="test-key",
            summary_model="deepseek-ai/DeepSeek-V4-Pro",
            router_model="inclusionAI/Ling-flash-2.0",
            answer_model="Qwen/Qwen3.6-27B",
            timeout_seconds=1,
            summary_max_profile_rows=2,
        ),
        post=post,
    )
    selected = client.route_documents(
        "question",
        [
            DocumentSummary(
                summary_id="summary_1",
                file_id="file_1",
                version_id="version_1",
                summary_text="summary",
                business_domain="domain",
                key_topics=[],
                suitable_questions=[],
                unsuitable_questions=[],
                sheet_summaries=[],
                created_at="now",
            )
        ],
        max_documents=1,
    )

    assert selected == []


def test_siliconflow_router_filters_weak_low_confidence_matches() -> None:
    def post(_url: str, **_kwargs: Any) -> httpx2.Response:
        return httpx2.Response(
            200,
            request=httpx2.Request("POST", "https://api.example.test/v1/chat/completions"),
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "document_for_this_turn": [
                                        {
                                            "file_id": "file_1",
                                            "version_id": "version_1",
                                            "match_level": "weak_match",
                                            "matched_terms": ["standard"],
                                            "reason": "Only generic overlap.",
                                            "confidence": 0.4,
                                        }
                                    ]
                                }
                            )
                        }
                    }
                ]
            },
        )

    client = MultiProviderLlmClient(
        SiliconFlowConfig(
            api_base_url="https://api.example.test/v1",
            api_key="test-key",
            summary_model="deepseek-ai/DeepSeek-V4-Pro",
            router_model="inclusionAI/Ling-flash-2.0",
            answer_model="Qwen/Qwen3.6-27B",
            timeout_seconds=1,
            summary_max_profile_rows=2,
        ),
        post=post,
    )

    selected = client.route_documents(
        "Which standard applies?",
        [
            DocumentSummary(
                summary_id="summary_1",
                file_id="file_1",
                version_id="version_1",
                summary_text="summary",
                business_domain="domain",
                key_topics=[],
                suitable_questions=[],
                unsuitable_questions=[],
                sheet_summaries=[],
                created_at="now",
            )
        ],
        max_documents=1,
    )

    assert selected == []


def test_siliconflow_router_sends_catalog_and_routing_memory_messages() -> None:
    requests: list[dict[str, Any]] = []

    def post(_url: str, **kwargs: Any) -> httpx2.Response:
        requests.append(kwargs["json"])
        return httpx2.Response(
            200,
            request=httpx2.Request("POST", "https://api.example.test/v1/chat/completions"),
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "document_for_this_turn": [
                                        {
                                            "file_id": "file_2",
                                            "version_id": "version_2",
                                            "match_level": "strong_match",
                                            "matched_terms": ["regional standards"],
                                            "missing_terms": [],
                                            "reason": "Current question matches catalog.",
                                            "confidence": 0.8,
                                        }
                                    ]
                                }
                            )
                        }
                    }
                ]
            },
        )

    client = MultiProviderLlmClient(
        SiliconFlowConfig(
            api_base_url="https://api.example.test/v1",
            api_key="test-key",
            summary_model="deepseek-ai/DeepSeek-V4-Pro",
            router_model="inclusionAI/Ling-flash-2.0",
            answer_model="Qwen/Qwen3.6-27B",
            timeout_seconds=1,
            summary_max_profile_rows=2,
        ),
        post=post,
    )
    selected = client.route_documents(
        "What applies to the same product in another region?",
        [
            DocumentSummary(
                summary_id="summary_1",
                file_id="file_1",
                version_id="version_1",
                document_title="appliance-lvd.xlsx",
                document_type="standard_matrix",
                summary_text="Attached household appliance standards.",
                business_domain="standards",
                coverage_scope={
                    "products": ["household appliances"],
                    "standards": ["IEC 60335"],
                },
                key_topics=["household appliances"],
                positive_routing_terms=["household appliances", "IEC 60335"],
                negative_routing_terms=["pricing"],
                exact_identifiers=["IEC 60335"],
                suitable_questions=[],
                unsuitable_questions=[],
                sheet_summaries=[
                    SheetSummary(
                        sheet_id="sheet_1",
                        sheet_name="IEC",
                        summary="IEC appliance standards.",
                        important_columns=["Product", "Standard"],
                        likely_question_types=["standard lookup"],
                        header_terms=["Product", "Standard"],
                        sampled_identifiers=["coffee maker"],
                    )
                ],
                routing_notes="Use for appliance safety standard routing.",
                created_at="now",
            ),
            DocumentSummary(
                summary_id="summary_2",
                file_id="file_2",
                version_id="version_2",
                document_title="regional.xlsx",
                document_type="regional_requirement_table",
                summary_text="Candidate regional standards.",
                business_domain="standards",
                coverage_scope={
                    "regions": ["EU"],
                    "standards": ["regional standards"],
                },
                key_topics=["regional standards"],
                positive_routing_terms=["regional standards"],
                negative_routing_terms=[],
                exact_identifiers=["EU"],
                suitable_questions=[],
                unsuitable_questions=[],
                sheet_summaries=[],
                routing_notes="Use for regional standards.",
                created_at="now",
            ),
        ],
        max_documents=2,
        attached_documents=[
            AttachedDocument(
                session_id="session_1",
                file_id="file_1",
                version_id="version_1",
                attached_at="now",
                row_count=10,
                context_hash="hash",
            )
        ],
        previous_turns=[
            ChatTurn(
                turn_id="turn_1",
                session_id="session_1",
                question="What applies to household appliances?",
                answer_text="not sent to router",
                citation_ids=["C1"],
                selected_documents=[
                    SelectedDocument(
                        file_id="file_1",
                        version_id="version_1",
                        reason="Previous turn.",
                    )
                ],
                created_at="now",
            )
        ],
    )

    assert selected[0].version_id == "version_2"

    messages = requests[0]["messages"]
    assert [message["role"] for message in messages] == [
        "system",
        "user",
        "user",
        "assistant",
        "user",
    ]
    assert "Document catalog for routing" in messages[1]["content"]
    assert "not sent to router" not in json.dumps(messages, ensure_ascii=False)
    assert "document_for_this_turn_ids" in messages[3]["content"]
    assert "Maximum documents for this turn: 2" in messages[-1]["content"]
    assert "document_for_this_turn" in messages[-1]["content"]

    catalog = json.loads(messages[1]["content"].split("\n\n", 1)[1])
    assert catalog[0]["version_id"] == "version_1"
    assert catalog[0]["document_title"] == "appliance-lvd.xlsx"
    assert catalog[0]["document_type"] == "standard_matrix"
    assert catalog[0]["coverage_scope"]["standards"] == ["IEC 60335"]
    assert catalog[0]["positive_routing_terms"] == ["household appliances", "IEC 60335"]
    assert catalog[0]["sheet_summaries"][0]["important_columns"] == ["Product", "Standard"]
    assert catalog[0]["attachment_state"] == "attached"
    assert catalog[0]["selected_turn_count"] == 1
    assert catalog[0]["selected_in_last_turn"] is True
    assert catalog[1]["version_id"] == "version_2"
    assert catalog[1]["attachment_state"] == "candidate"


def test_siliconflow_answer_sends_history_as_role_messages() -> None:
    requests: list[dict[str, Any]] = []

    def post(_url: str, **kwargs: Any) -> httpx2.Response:
        requests.append(kwargs["json"])
        return httpx2.Response(
            200,
            request=httpx2.Request("POST", "https://api.example.test/v1/chat/completions"),
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "answer_blocks": [],
                                    "citations": [],
                                    "insufficient_evidence": True,
                                    "follow_up_suggestions": [],
                                }
                            )
                        }
                    }
                ]
            },
        )

    client = MultiProviderLlmClient(
        SiliconFlowConfig(
            api_base_url="https://api.example.test/v1",
            api_key="test-key",
            summary_model="deepseek-ai/DeepSeek-V4-Pro",
            router_model="inclusionAI/Ling-flash-2.0",
            answer_model="Qwen/Qwen3.6-27B",
            timeout_seconds=1,
            summary_max_profile_rows=2,
        ),
        post=post,
    )

    client.answer_with_rows(
        "What LVD standard applies now?",
        [
            SelectedDocument(
                file_id="file_1",
                version_id="version_1",
                reason="Current turn evidence.",
            )
        ],
        rows=[],
        previous_turns=[
            ChatTurn(
                turn_id="turn_1",
                session_id="session_1",
                question="What applies to coffee makers?",
                answer_text="Coffee makers use IEC 60335-2-15.",
                citation_ids=["C1"],
                selected_documents=[
                    SelectedDocument(
                        file_id="file_1",
                        version_id="version_1",
                        reason="Previous evidence.",
                    )
                ],
                created_at="now",
            )
        ],
    )

    messages = requests[0]["messages"]
    assert [message["role"] for message in messages] == [
        "system",
        "user",
        "assistant",
        "user",
    ]
    assert messages[1]["content"] == "What applies to coffee makers?"
    assert "Coffee makers use IEC 60335-2-15." in messages[2]["content"]
    assert "Previous answer metadata" in messages[2]["content"]
    assert "Previous chat turns" not in messages[-1]["content"]


def test_siliconflow_timeout_error_includes_stage_model_and_duration() -> None:
    def post(_url: str, **_kwargs: Any) -> httpx2.Response:
        request = httpx2.Request(
            "POST",
            "https://api.example.test/v1/chat/completions",
        )
        raise httpx2.ReadTimeout("The read operation timed out", request=request)

    client = MultiProviderLlmClient(
        SiliconFlowConfig(
            api_base_url="https://api.example.test/v1",
            api_key="test-key",
            summary_model="deepseek-ai/DeepSeek-V4-Pro",
            router_model="inclusionAI/Ling-flash-2.0",
            answer_model="Qwen/Qwen3.6-27B",
            timeout_seconds=1,
            summary_max_profile_rows=2,
        ),
        post=post,
    )

    with pytest.raises(LlmRequestError) as exc_info:
        client.route_documents(
            "question",
            [
                DocumentSummary(
                    summary_id="summary_1",
                    file_id="file_1",
                    version_id="version_1",
                    summary_text="summary",
                    business_domain="domain",
                    key_topics=[],
                    suitable_questions=[],
                    unsuitable_questions=[],
                    sheet_summaries=[],
                    created_at="now",
                )
            ],
            max_documents=1,
        )

    error = exc_info.value
    assert error.stage == "route_model"
    assert error.model == "inclusionAI/Ling-flash-2.0"
    assert error.duration_seconds >= 0
    assert "stage=route_model" in str(error)
    assert "model=inclusionAI/Ling-flash-2.0" in str(error)
    assert "duration_seconds=" in str(error)


def test_siliconflow_uses_enable_thinking_false_for_supported_models() -> None:
    requests: list[dict[str, Any]] = []

    def post(_url: str, **kwargs: Any) -> httpx2.Response:
        requests.append(kwargs["json"])
        return httpx2.Response(
            200,
            request=httpx2.Request("POST", "https://api.example.test/v1/chat/completions"),
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "selected_documents": [],
                                    "decision_reason": "reuse attached",
                                }
                            )
                        }
                    }
                ]
            },
        )

    client = MultiProviderLlmClient(
        SiliconFlowConfig(
            api_base_url="https://api.example.test/v1",
            api_key="test-key",
            summary_model="deepseek-ai/DeepSeek-V4-Pro",
            router_model="inclusionAI/Ling-flash-2.0",
            answer_model="deepseek-ai/DeepSeek-V4-Pro",
            timeout_seconds=1,
            summary_max_profile_rows=2,
        ),
        post=post,
    )
    client.route_documents(
        "question",
        [
            DocumentSummary(
                summary_id="summary_1",
                file_id="file_1",
                version_id="version_1",
                summary_text="summary",
                business_domain="domain",
                key_topics=[],
                suitable_questions=[],
                unsuitable_questions=[],
                sheet_summaries=[],
                created_at="now",
            )
        ],
        max_documents=3,
        model="Qwen/Qwen3.6-27B",
    )

    assert requests[0]["enable_thinking"] is False


def test_deepseek_official_provider_uses_official_url_and_json_mode() -> None:
    requests: list[dict[str, Any]] = []
    urls: list[str] = []

    def post(url: str, **kwargs: Any) -> httpx2.Response:
        urls.append(url)
        requests.append(kwargs["json"])
        return httpx2.Response(
            200,
            request=httpx2.Request("POST", url),
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "selected_documents": [],
                                    "decision_reason": "no match",
                                }
                            )
                        }
                    }
                ]
            },
        )

    client = MultiProviderLlmClient(
        SiliconFlowConfig(
            api_base_url="https://api.siliconflow.test/v1",
            api_key="siliconflow-key",
            summary_model="deepseek-ai/DeepSeek-V4-Pro",
            router_model="inclusionAI/Ling-flash-2.0",
            answer_model="deepseek-ai/DeepSeek-V4-Pro",
            timeout_seconds=1,
            summary_max_profile_rows=2,
        ),
        post=post,
        extra_providers={
            "deepseek": LlmProviderConfig(
                provider="deepseek",
                label="DeepSeek Official",
                api_base_url="https://api.deepseek.test",
                api_key="deepseek-key",
                summary_model="deepseek-v4-pro",
                router_model="deepseek-v4-flash",
                answer_model="deepseek-v4-pro",
            )
        },
    )

    client.route_documents(
        "question",
        [
            DocumentSummary(
                summary_id="summary_1",
                file_id="file_1",
                version_id="version_1",
                summary_text="summary",
                business_domain="domain",
                key_topics=[],
                suitable_questions=[],
                unsuitable_questions=[],
                sheet_summaries=[],
                created_at="now",
            )
        ],
        max_documents=3,
        model="deepseek-v4-flash",
        provider="deepseek",
    )

    assert urls == ["https://api.deepseek.test/chat/completions"]
    assert requests[0]["model"] == "deepseek-v4-flash"
    assert requests[0]["response_format"] == {"type": "json_object"}
    assert requests[0]["thinking"] == {"type": "disabled"}
