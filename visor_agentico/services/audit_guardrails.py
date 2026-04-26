from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from visor_agentico.config import Settings


EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"\+?[0-9][0-9\s().-]{7,}[0-9]")
CREDIT_CARD_RE = re.compile(r"(?:\d[ -]*?){13,19}")
SECRET_TOKEN_RE = re.compile(r"\b(?:sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,})\b")

PROMPT_INJECTION_PATTERNS = (
    "ignore previous instructions",
    "ignore all previous instructions",
    "disregard previous instructions",
    "reveal the system prompt",
    "show hidden instructions",
    "developer message",
    "system prompt",
    "act as",
    "jailbreak",
    "do anything now",
)


@dataclass(slots=True)
class GuardrailCheckResult:
    content: str
    findings: list[dict[str, Any]]
    blocked: bool = False
    block_reason: str | None = None


class AuditGuardrails:
    """Applies best-effort guardrails for prompt injection and PII leakage.

    All integrations are optional. If third-party libraries are not available,
    lightweight regex heuristics are used instead.
    """

    def __init__(self, settings: Settings, observability: Any | None = None) -> None:
        self.enabled = settings.audit_enable_guardrails
        self.fail_on_prompt_injection = settings.audit_fail_on_prompt_injection
        self.enable_pii_anonymization = settings.audit_enable_pii_anonymization
        self.prompt_injection_threshold = max(0.0, min(1.0, settings.audit_prompt_injection_threshold))
        self.pii_entities = settings.audit_pii_entities
        self.observability = observability

        self._analyzer = None
        self._anonymizer = None
        self._llm_guard_scanner = None
        self._initialize_optional_engines()

    def sanitize_messages(
        self,
        messages: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool, str | None]:
        if not self.enabled:
            return messages, [], False, None

        sanitized_messages: list[dict[str, Any]] = []
        findings: list[dict[str, Any]] = []
        blocked = False
        block_reason: str | None = None

        for index, message in enumerate(messages):
            updated = dict(message)
            content = message.get("content")
            if isinstance(content, str):
                pii_check = self._apply_pii_filters(content)
                injection_findings, injection_score = self._scan_prompt_injection(pii_check.content)

                for finding in pii_check.findings:
                    findings.append({**finding, "scope": "input", "message_index": index})
                for finding in injection_findings:
                    findings.append({**finding, "scope": "input", "message_index": index})

                if self.fail_on_prompt_injection and injection_score >= self.prompt_injection_threshold:
                    blocked = True
                    block_reason = "prompt_injection"

                updated["content"] = pii_check.content

            sanitized_messages.append(updated)

        self._record_findings(findings, blocked=blocked, block_reason=block_reason)
        return sanitized_messages, findings, blocked, block_reason

    def sanitize_assistant_message(
        self,
        message: dict[str, Any] | None,
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        if not self.enabled or message is None:
            return message, []

        updated = dict(message)
        findings: list[dict[str, Any]] = []

        content = message.get("content")
        if isinstance(content, str):
            pii_check = self._apply_pii_filters(content)
            secret_findings, scrubbed_content = self._scrub_secrets(pii_check.content)
            updated["content"] = scrubbed_content

            findings.extend({**finding, "scope": "output"} for finding in pii_check.findings)
            findings.extend({**finding, "scope": "output"} for finding in secret_findings)

        self._record_findings(findings, blocked=False, block_reason=None)
        return updated, findings

    def _initialize_optional_engines(self) -> None:
        if self.enable_pii_anonymization:
            try:
                from presidio_analyzer import AnalyzerEngine  # type: ignore
                from presidio_anonymizer import AnonymizerEngine  # type: ignore

                self._analyzer = AnalyzerEngine()
                self._anonymizer = AnonymizerEngine()
            except Exception:
                self._analyzer = None
                self._anonymizer = None

        if self.enabled:
            try:
                from llm_guard.input_scanners import PromptInjection  # type: ignore

                self._llm_guard_scanner = PromptInjection(threshold=self.prompt_injection_threshold)
            except Exception:
                self._llm_guard_scanner = None

    def _apply_pii_filters(self, content: str) -> GuardrailCheckResult:
        if not self.enable_pii_anonymization:
            return GuardrailCheckResult(content=content, findings=[])

        if self._analyzer is not None and self._anonymizer is not None:
            return self._apply_presidio(content)

        return self._apply_regex_pii_fallback(content)

    def _apply_presidio(self, content: str) -> GuardrailCheckResult:
        try:
            analyzer_results = self._analyzer.analyze(
                text=content,
                entities=self.pii_entities or None,
                language="en",
            )
            if not analyzer_results:
                return GuardrailCheckResult(content=content, findings=[])

            anonymized = self._anonymizer.anonymize(
                text=content,
                analyzer_results=analyzer_results,
            )
            findings = [
                {
                    "kind": "pii",
                    "severity": "medium",
                    "source": "presidio",
                    "entity": result.entity_type,
                    "score": round(float(result.score), 4),
                    "start": int(result.start),
                    "end": int(result.end),
                    "message": f"Detected {result.entity_type}.",
                }
                for result in analyzer_results
            ]
            return GuardrailCheckResult(content=anonymized.text, findings=findings)
        except Exception:
            return self._apply_regex_pii_fallback(content)

    def _apply_regex_pii_fallback(self, content: str) -> GuardrailCheckResult:
        findings: list[dict[str, Any]] = []
        scrubbed = content

        for pattern, replacement, entity in (
            (EMAIL_RE, "[redacted:email]", "EMAIL_ADDRESS"),
            (PHONE_RE, "[redacted:phone]", "PHONE_NUMBER"),
            (CREDIT_CARD_RE, "[redacted:card]", "CREDIT_CARD"),
        ):
            matches = list(pattern.finditer(scrubbed))
            if not matches:
                continue
            scrubbed = pattern.sub(replacement, scrubbed)
            findings.append(
                {
                    "kind": "pii",
                    "severity": "medium",
                    "source": "regex",
                    "entity": entity,
                    "count": len(matches),
                    "message": f"Detected {len(matches)} {entity} match(es).",
                }
            )

        return GuardrailCheckResult(content=scrubbed, findings=findings)

    def _scan_prompt_injection(self, content: str) -> tuple[list[dict[str, Any]], float]:
        findings: list[dict[str, Any]] = []
        max_score = 0.0

        normalized = content.lower()
        matched = [pattern for pattern in PROMPT_INJECTION_PATTERNS if pattern in normalized]
        if matched:
            score = min(1.0, 0.35 + (0.15 * len(matched)))
            max_score = max(max_score, score)
            findings.append(
                {
                    "kind": "prompt_injection",
                    "severity": "high" if score >= self.prompt_injection_threshold else "medium",
                    "source": "heuristic",
                    "score": round(score, 4),
                    "patterns": matched,
                    "message": "Detected patterns commonly associated with prompt injection.",
                }
            )

        if self._llm_guard_scanner is not None:
            llm_guard_findings, llm_guard_score = self._scan_with_llm_guard(content)
            findings.extend(llm_guard_findings)
            max_score = max(max_score, llm_guard_score)

        return findings, max_score

    def _scan_with_llm_guard(self, content: str) -> tuple[list[dict[str, Any]], float]:
        try:
            scan_result = self._llm_guard_scanner.scan(content)
        except Exception:
            return [], 0.0

        score = 0.0
        verdict = "unknown"
        if isinstance(scan_result, tuple):
            for value in scan_result:
                if isinstance(value, bool):
                    verdict = "safe" if value else "unsafe"
                if isinstance(value, (int, float)):
                    score = max(score, float(value))
                if isinstance(value, dict):
                    score = max(score, self._extract_score_from_dict(value))
        elif isinstance(scan_result, dict):
            score = self._extract_score_from_dict(scan_result)
            unsafe = scan_result.get("is_valid") is False
            verdict = "unsafe" if unsafe else "safe"

        if score <= 0:
            return [], 0.0

        finding = {
            "kind": "prompt_injection",
            "severity": "high" if score >= self.prompt_injection_threshold else "medium",
            "source": "llm_guard",
            "score": round(score, 4),
            "message": f"LLM Guard classified prompt as {verdict}.",
        }
        return [finding], score

    @staticmethod
    def _extract_score_from_dict(value: dict[str, Any]) -> float:
        candidates = (
            value.get("risk"),
            value.get("risk_score"),
            value.get("score"),
            value.get("confidence"),
        )
        for candidate in candidates:
            if isinstance(candidate, (int, float)):
                return float(candidate)
        return 0.0

    def _scrub_secrets(self, content: str) -> tuple[list[dict[str, Any]], str]:
        matches = list(SECRET_TOKEN_RE.finditer(content))
        if not matches:
            return [], content

        scrubbed = SECRET_TOKEN_RE.sub("[redacted:secret]", content)
        findings = [
            {
                "kind": "secret",
                "severity": "high",
                "source": "regex",
                "count": len(matches),
                "message": "Detected possible API tokens in assistant output.",
            }
        ]
        return findings, scrubbed

    def _record_findings(self, findings: list[dict[str, Any]], *, blocked: bool, block_reason: str | None) -> None:
        if self.observability is None:
            return

        try:
            for finding in findings:
                self.observability.record_guardrail_finding(
                    kind=str(finding.get("kind") or "unknown"),
                    severity=str(finding.get("severity") or "unknown"),
                )
            if blocked:
                self.observability.record_guardrail_block(block_reason or "blocked")
        except Exception:
            return
