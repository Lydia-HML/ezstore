"""路由決策的單元測試：不需要 API key、MCP Server 或網路。"""

import pytest

from quotation_agent.routing import (
    REFUSAL_MESSAGE,
    REQUIRED_ARGS,
    ROUTE_CLARIFY,
    ROUTE_REFUSE,
    clarify_message,
    plan,
)
from quotation_agent.schemas import Intent, IntentResult, Pending

QT = "QT-20260330-001"


@pytest.mark.parametrize(
    ("result", "expected_args"),
    [
        (
            IntentResult(intent=Intent.GET_QUOTATION, quotation_number=QT),
            {"quotation_number": QT},
        ),
        (
            IntentResult(
                intent=Intent.LIST_CUSTOMER_QUOTATIONS, customer_name="史塔克工業"
            ),
            {"customer_name": "史塔克工業"},
        ),
        (
            IntentResult(intent=Intent.DUPLICATE_QUOTATION, quotation_number=QT),
            {"quotation_number": QT},
        ),
        (
            IntentResult(
                intent=Intent.UPDATE_PRICING_FACTOR,
                quotation_number=QT,
                new_pricing_factor=1.5,
            ),
            {"quotation_number": QT, "new_pricing_factor": 1.5},
        ),
        (
            IntentResult(
                intent=Intent.ADJUST_TOTAL_PRICE,
                quotation_number=QT,
                target_total_price=8000,
            ),
            {"quotation_number": QT, "target_total_price": 8000},
        ),
        (
            IntentResult(intent=Intent.CONVERT_TO_ORDER, quotation_number=QT),
            {"quotation_number": QT},
        ),
    ],
)
def test_complete_request_routes_to_its_tool(result, expected_args):
    plan_, pending = plan(result, None)
    assert plan_.route == result.intent.value
    assert plan_.args == expected_args
    assert pending is None


def test_only_required_args_are_sent_to_the_tool():
    result = IntentResult(
        intent=Intent.GET_QUOTATION, quotation_number=QT, customer_name="史塔克工業"
    )
    plan_, _ = plan(result, None)
    assert plan_.args == {"quotation_number": QT}


def test_off_topic_is_refused_and_clears_pending():
    pending = Pending(intent=Intent.GET_QUOTATION)
    plan_, next_pending = plan(IntentResult(intent=Intent.OFF_TOPIC), pending)
    assert plan_.route == ROUTE_REFUSE
    assert next_pending is None


def test_off_topic_is_refused_even_if_fields_were_extracted():
    result = IntentResult(intent=Intent.OFF_TOPIC, customer_name="史塔克工業")
    plan_, _ = plan(result, None)
    assert plan_.route == ROUTE_REFUSE


def test_provide_info_with_nothing_to_continue_is_refused():
    plan_, pending = plan(IntentResult(intent=Intent.PROVIDE_INFO), None)
    assert plan_.route == ROUTE_REFUSE
    assert pending is None


def test_missing_field_asks_then_completes_on_next_turn():
    first, pending = plan(IntentResult(intent=Intent.GET_QUOTATION), None)
    assert first.route == ROUTE_CLARIFY
    assert first.missing == ["quotation_number"]
    assert "報價單編號" in clarify_message(first)
    assert pending == Pending(intent=Intent.GET_QUOTATION)

    second, pending = plan(
        IntentResult(intent=Intent.PROVIDE_INFO, quotation_number=QT), pending
    )
    assert second.route == Intent.GET_QUOTATION.value
    assert second.args == {"quotation_number": QT}
    assert pending is None


def test_partial_fields_are_kept_across_turns():
    first, pending = plan(
        IntentResult(intent=Intent.UPDATE_PRICING_FACTOR, quotation_number=QT), None
    )
    assert first.missing == ["new_pricing_factor"]

    second, _ = plan(
        IntentResult(intent=Intent.PROVIDE_INFO, new_pricing_factor=1.5), pending
    )
    assert second.route == Intent.UPDATE_PRICING_FACTOR.value
    assert second.args == {"quotation_number": QT, "new_pricing_factor": 1.5}


def test_switching_operation_does_not_reuse_old_args():
    pending = Pending(
        intent=Intent.LIST_CUSTOMER_QUOTATIONS, args={"quotation_number": "QT-OLD"}
    )
    plan_, _ = plan(IntentResult(intent=Intent.GET_QUOTATION), pending)
    assert plan_.route == ROUTE_CLARIFY
    assert plan_.missing == ["quotation_number"]


def test_data_without_operation_asks_which_operation():
    first, pending = plan(
        IntentResult(intent=Intent.PROVIDE_INFO, quotation_number=QT), None
    )
    assert first.route == ROUTE_CLARIFY
    assert first.missing == ["operation"]
    assert "哪一項操作" in clarify_message(first)

    second, _ = plan(IntentResult(intent=Intent.DUPLICATE_QUOTATION), pending)
    assert second.route == Intent.DUPLICATE_QUOTATION.value
    assert second.args == {"quotation_number": QT}


def test_every_operation_intent_has_required_args():
    operations = set(Intent) - {Intent.PROVIDE_INFO, Intent.OFF_TOPIC}
    assert set(REQUIRED_ARGS) == operations


def test_refusal_message_has_no_link():
    assert "http" not in REFUSAL_MESSAGE
