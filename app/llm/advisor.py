"""LLM advisory layer."""

from __future__ import annotations

import json
import logging
from typing import Any

import requests

from app.config.schema import AppConfig
from app.llm.prompts import build_review_prompt
from app.utils.models import FeatureSet, LLMAdvice, LLMDecision, LLMSignalAction, MarketRegime, PortfolioSnapshot, Signal


logger = logging.getLogger(__name__)


class LLMAdvisor:
    """Review deterministic signals without controlling execution."""

    def __init__(self, config: AppConfig) -> None:
        """Initialize the advisor."""
        self.config = config
        self._auth_disabled = False

    def review(
        self,
        signals: list[Signal],
        features: FeatureSet,
        regime: MarketRegime,
        snapshot: PortfolioSnapshot,
    ) -> LLMAdvice:
        """Generate bounded advisory output."""
        if not signals:
            return LLMAdvice(
                summary="No signals to review",
                signal_actions=[],
                parameter_suggestions={},
                enabled=self.config.llm.enabled,
                used=False,
                status="no_signals",
                decision_present=False,
                decision_valid=False,
            )

        prompt = build_review_prompt(
            signals=signals[: self.config.llm.max_signals_per_review],
            features=features,
            regime=regime,
            snapshot=snapshot,
        )
        logger.debug("LLM review prompt prepared: %s", prompt)
        if not self.config.llm.enabled:
            return LLMAdvice(
                summary="LLM disabled",
                signal_actions=[],
                parameter_suggestions={},
                enabled=False,
                used=False,
                status="disabled",
                decision_present=False,
                decision_valid=False,
            )
        if self._auth_disabled:
            return LLMAdvice(
                summary="LLM disabled after OpenAI authentication failure; fix OPENAI_API_KEY and restart the service",
                signal_actions=[],
                parameter_suggestions={},
                enabled=True,
                used=False,
                status="auth_disabled",
                decision_present=False,
                decision_valid=False,
            )

        api_key = self.config.env.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            return LLMAdvice(
                summary="LLM enabled but OPENAI_API_KEY is missing",
                signal_actions=[],
                parameter_suggestions={},
                enabled=True,
                used=False,
                status="missing_api_key",
                decision_present=False,
                decision_valid=False,
            )

        payload = self._build_request_payload(prompt=prompt, repair=False)
        raw_advice, request_status = self._request_structured_advice(api_key=api_key, payload=payload)
        if raw_advice is None:
            return request_status

        signal_actions, parameter_suggestions, advice = self._parse_advice(raw_advice, signal_count=len(signals))
        if advice.decision_present and not advice.decision_valid:
            logger.warning("LLM decision contract invalid; falling back to deterministic allow")
        if not advice.decision_present:
            repair_payload = self._build_request_payload(
                prompt=prompt,
                repair=True,
                prior_status=advice.status,
            )
            repaired_raw_advice, repaired_status = self._request_structured_advice(api_key=api_key, payload=repair_payload)
            if repaired_raw_advice is not None:
                signal_actions, parameter_suggestions, advice = self._parse_advice(repaired_raw_advice, signal_count=len(signals))
            else:
                advice = repaired_status

        if advice.decision_present and not advice.decision_valid:
            logger.warning("LLM decision contract invalid after retry; falling back to deterministic allow")
        advice.signal_actions = signal_actions
        advice.parameter_suggestions = parameter_suggestions
        return advice

    def _extract_structured_payload(self, response_body: dict[str, Any]) -> dict[str, Any]:
        """Extract the structured JSON payload from a Responses API result."""
        if isinstance(response_body.get("output_text"), str):
            raw_text = response_body["output_text"]
            logger.debug("LLM raw structured text: %s", raw_text[:4000])
            return json.loads(raw_text)

        for item in response_body.get("output", []):
            if item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                    raw_text = content["text"]
                    logger.debug("LLM raw structured text: %s", raw_text[:4000])
                    return json.loads(raw_text)

        raise ValueError("No structured output_text found in response")

    def _build_request_payload(self, *, prompt: str, repair: bool, prior_status: str | None = None) -> dict[str, Any]:
        """Build the request payload for the structured LLM review call."""
        instructions = (
            "You are a conservative BTC paper-trading risk reviewer. "
            "Review only the provided signals. "
            "Return valid JSON only. "
            "The JSON object must include: "
            "decision (object with action, confidence, reason, reason_code, score), "
            "summary (string), "
            "signal_actions (array of objects with signal_index, action, size_multiplier, rationale), "
            "parameter_suggestions (object with numeric values only). "
            "Never recommend increasing signal size. "
            "Keep parameter suggestions sparse and numeric."
        )
        if repair:
            instructions += (
                " The previous response was invalid or missing the required decision object. "
                "Return ONLY the required JSON object. "
                "If you cannot comply, emit decision.action=allow, confidence=0.0, score=0.0, reason_code=invalid_contract."
            )
            if prior_status:
                instructions += f" Prior status: {prior_status}."
        return {
            "model": self.config.llm.model,
            "instructions": instructions,
            "input": [
                {
                    "role": "user",
                    "content": f"Return JSON only.\n{prompt}",
                }
            ],
            "text": {
                "format": {"type": "json_object"},
            },
        }

    def _request_structured_advice(self, *, api_key: str, payload: dict[str, Any]) -> tuple[dict[str, Any] | None, LLMAdvice]:
        """Call the LLM endpoint and parse the structured payload."""
        try:
            response = requests.post(
                self.config.llm.api_base_url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self.config.llm.timeout_seconds,
            )
            status_code = int(getattr(response, "status_code", 200))
            if status_code in {401, 403}:
                self._auth_disabled = True
                logger.error(
                    "Disabling LLM reviews after OpenAI authentication failure status=%s; fix OPENAI_API_KEY and restart",
                    status_code,
                )
                return None, LLMAdvice(
                    summary="LLM disabled after OpenAI authentication failure; fix OPENAI_API_KEY and restart the service",
                    signal_actions=[],
                    parameter_suggestions={},
                    enabled=True,
                    used=False,
                    status="auth_failure",
                    decision_present=False,
                    decision_valid=False,
                )
            response.raise_for_status()
            raw_advice = self._extract_structured_payload(response.json())
            logger.debug("LLM structured keys: %s", sorted(raw_advice.keys()))
            return raw_advice, LLMAdvice(
                summary="",
                signal_actions=[],
                parameter_suggestions={},
                enabled=True,
                used=True,
                status="",
            )
        except requests.RequestException as exc:
            response = getattr(exc, "response", None)
            if response is not None:
                logger.warning(
                    "LLM review request failed status=%s body=%s",
                    response.status_code,
                    response.text[:1000],
                )
            else:
                logger.warning("LLM review request failed: %s", exc)
            return None, LLMAdvice(
                summary=f"LLM request failed: {exc}",
                signal_actions=[],
                parameter_suggestions={},
                enabled=True,
                used=False,
                status="request_failed",
                decision_present=False,
                decision_valid=False,
            )
        except (json.JSONDecodeError, ValueError, TypeError, KeyError) as exc:
            logger.warning("LLM review payload could not be parsed: %s", exc)
            return None, LLMAdvice(
                summary=f"LLM response parse failed: {exc}",
                signal_actions=[],
                parameter_suggestions={},
                enabled=True,
                used=False,
                status="parse_failed",
                decision_present=False,
                decision_valid=False,
            )

    def _parse_advice(
        self,
        raw_advice: dict[str, Any],
        *,
        signal_count: int,
    ) -> tuple[list[LLMSignalAction], dict[str, float], LLMAdvice]:
        """Convert raw JSON into the bounded advice contract."""
        signal_actions = self._sanitize_signal_actions(raw_advice.get("signal_actions", []), signal_count=signal_count)
        parameter_suggestions = self._sanitize_parameter_suggestions(raw_advice.get("parameter_suggestions", {}))
        raw_decision = raw_advice.get("decision")
        decision_present = isinstance(raw_decision, dict)
        decision = self._sanitize_decision(raw_decision) if decision_present else None
        decision_valid = decision is not None
        summary = str(raw_advice.get("summary", "LLM review completed")).strip() or "LLM review completed"
        advice = LLMAdvice(
            summary=summary,
            signal_actions=signal_actions,
            parameter_suggestions=parameter_suggestions,
            decision=decision,
            decision_present=decision_present,
            decision_valid=decision_valid,
            enabled=True,
            used=True,
            status="reviewed" if decision_valid else "invalid_decision_contract",
        )
        return signal_actions, parameter_suggestions, advice

    def _sanitize_signal_actions(
        self,
        raw_actions: list[dict[str, Any]],
        *,
        signal_count: int,
    ) -> list[LLMSignalAction]:
        """Clamp the model output to the bounded action space accepted by the runtime."""
        sanitized: list[LLMSignalAction] = []
        seen_indices: set[int] = set()
        min_multiplier = min(max(self.config.llm.min_size_multiplier, 0.0), 1.0)
        for raw_action in raw_actions:
            try:
                signal_index = int(raw_action["signal_index"])
            except (KeyError, TypeError, ValueError):
                continue
            if signal_index < 0 or signal_index >= signal_count or signal_index in seen_indices:
                continue

            action = str(raw_action.get("action", "allow")).strip().lower()
            if action not in {"allow", "block", "reduce"}:
                continue
            if action == "block" and not self.config.llm.allow_blocking:
                action = "reduce"

            try:
                size_multiplier = float(raw_action.get("size_multiplier", 1.0))
            except (TypeError, ValueError):
                size_multiplier = 1.0
            size_multiplier = min(max(size_multiplier, min_multiplier), 1.0)
            if action == "allow":
                size_multiplier = 1.0
            elif action == "block":
                size_multiplier = 0.0

            rationale = str(raw_action.get("rationale", "")).strip() or "No rationale provided"
            sanitized.append(
                LLMSignalAction(
                    signal_index=signal_index,
                    action=action,
                    size_multiplier=size_multiplier,
                    rationale=rationale,
                )
            )
            seen_indices.add(signal_index)
        return sanitized

    @staticmethod
    def _sanitize_parameter_suggestions(raw_suggestions: dict[str, Any]) -> dict[str, float]:
        """Keep only known numeric parameters for later logging or offline review."""
        allowed_keys = {
            "atr_multiplier",
            "dca_drop_percent",
            "dca_order_size_usd",
            "swing_entry_rsi_max",
            "swing_take_profit_percent",
        }
        suggestions: dict[str, float] = {}
        for key, value in raw_suggestions.items():
            if key not in allowed_keys:
                continue
            try:
                suggestions[key] = float(value)
            except (TypeError, ValueError):
                continue
        return suggestions

    @staticmethod
    def _sanitize_decision(raw_decision: Any) -> LLMDecision | None:
        """Validate the top-level advisory decision contract."""
        if not isinstance(raw_decision, dict):
            return None
        required_keys = {"action", "confidence", "reason", "reason_code", "score"}
        if any(key not in raw_decision for key in required_keys):
            return None
        action = str(raw_decision.get("action", "")).strip().lower()
        if action not in {"allow", "reduce", "block"}:
            return None
        try:
            confidence = float(raw_decision.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = min(max(confidence, 0.0), 1.0)
        reason = str(raw_decision.get("reason", "")).strip() or "No rationale provided"
        reason_code = str(raw_decision.get("reason_code", "")).strip()
        if not reason_code:
            return None
        try:
            score = float(raw_decision.get("score", 0.0))
        except (TypeError, ValueError):
            return None
        score = min(max(score, -1.0), 1.0)
        return LLMDecision(action=action, confidence=confidence, reason=reason, reason_code=reason_code, score=score)
