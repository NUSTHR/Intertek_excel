import json
from typing import Any

import httpx2
import pytest

from app.adapters.llm.siliconflow_client import (
    LlmProviderConfig,
    SiliconFlowConfig,
    SiliconFlowLlmClient,
)
from app.core.errors import LlmRequestError
from app.domain.models import DocumentSummary, SheetProfile, SheetSummary, WorkbookProfile


def test_siliconflow_client_generates_summary_routes_and_answers() -> None:
    requests: list[dict[str, Any]] = []
    responses = [
        {
            "summary_text": "A standards workbook.",
            "business_domain": "standards",
            "key_topics": ["EN", "DOW"],
            "suitable_questions": ["Find standards dates"],
            "unsuitable_questions": ["Questions outside the workbook"],
            "sheet_summaries": [
                {
                    "sheet_id": "sheet_1",
                    "sheet_name": "EN",
                    "summary": "EN standards and dates.",
                    "important_columns": ["Code", "DOW"],
                    "likely_question_types": ["date lookup"],
                }
            ],
        },
        {
            "selected_documents": [
                {
                    "file_id": "file_1",
                    "version_id": "version_1",
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
            "citations": [{"row_id": "S001_R1", "quote": "Code DOW"}],
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

    client = SiliconFlowLlmClient(
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
    assert summary.sheet_summaries == [
        SheetSummary(
            sheet_id="sheet_1",
            sheet_name="EN",
            summary="EN standards and dates.",
            important_columns=["Code", "DOW"],
            likely_question_types=["date lookup"],
        )
    ]
    assert selected[0].version_id == "version_1"
    assert selected[0].confidence == 0.9
    assert draft_answer.answer_blocks[0].text == "The workbook contains EN standards."
    assert draft_answer.answer_blocks[0].evidence_row_ids == ["S001_R1"]
    assert draft_answer.citations[0].row_id == "S001_R1"
    assert draft_answer.citations[0].quote == "Code DOW"
    assert [request["model"] for request in requests] == [
        "deepseek-ai/DeepSeek-V4-Pro",
        "inclusionAI/Ling-flash-2.0",
        "Qwen/Qwen3.6-27B",
    ]
    assert "enable_thinking" not in requests[0]
    assert "enable_thinking" not in requests[1]
    assert requests[2]["enable_thinking"] is False


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

    client = SiliconFlowLlmClient(
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


def test_siliconflow_timeout_error_includes_stage_model_and_duration() -> None:
    def post(_url: str, **_kwargs: Any) -> httpx2.Response:
        request = httpx2.Request(
            "POST",
            "https://api.example.test/v1/chat/completions",
        )
        raise httpx2.ReadTimeout("The read operation timed out", request=request)

    client = SiliconFlowLlmClient(
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

    client = SiliconFlowLlmClient(
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

    client = SiliconFlowLlmClient(
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
