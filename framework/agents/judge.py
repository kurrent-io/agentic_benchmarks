"""Judge agent that evaluates answer correctness."""

from dataclasses import dataclass
from typing import Any

from framework.agents.ollama import OllamaClient, OllamaConfig, ChatMessage

# Optional Claude support
try:
    from framework.agents.claude import ClaudeClient, ClaudeConfig
    CLAUDE_AVAILABLE = True
except ImportError:
    CLAUDE_AVAILABLE = False
    ClaudeClient = None
    ClaudeConfig = None


@dataclass
class JudgmentResult:
    """Result from the judge agent."""
    question: str
    given_answer: str
    expected_answer: Any
    is_correct: bool
    confidence: float  # 0.0 to 1.0
    reasoning: str
    partial_credit: float  # 0.0 to 1.0 for partial correctness


class JudgeAgent:
    """Agent that judges whether an answer is correct."""

    SYSTEM_PROMPT = """You are a judge evaluating whether an answer provides the correct value.

You will be given:
1. A question asking for specific data
2. The expected/reference answer (usually a specific number or value)
3. The given answer to evaluate

Your task is to determine if the given answer contains the EXACT CORRECT VALUE.

RULES:
- Read through the entire answer carefully to find the actual value provided
- The answer is CORRECT only if it contains the EXACT expected number
- If the expected answer is "17", the given answer must contain "17" (not 16, not 18)
- If the expected answer is "171", the given answer must contain "171" (not 164, not 170)
- Ignore formatting, markdown, or explanatory text - just find the number
- If the answer says "I can't answer", "0", or provides the wrong number → WRONG

Respond in this exact format:
CORRECT: [yes/no]
CONFIDENCE: [0.0-1.0]
PARTIAL_CREDIT: [0.0-1.0]
REASONING: [your explanation including what number you found in the answer]

Examples:
- Expected "42", given "The answer is 42 items" → CORRECT: yes (found 42)
- Expected "17", given "**17** price changes occurred" → CORRECT: yes (found 17)
- Expected "17", given "16 price changes" → CORRECT: no (found 16, expected 17)
- Expected "171", given "I found 164 orders" → CORRECT: no (found 164, expected 171)
- Expected "50", given "Cannot be determined from the database" → CORRECT: no (no number provided)
- Expected "100", given "0 because schema doesn't track this" → CORRECT: no (found 0, expected 100)"""

    def __init__(self, ollama_config: OllamaConfig | None = None, llm_client=None):
        """Initialize judge agent.

        Args:
            ollama_config: Configuration for Ollama (deprecated, use llm_client)
            llm_client: Pre-configured LLM client (OllamaClient or ClaudeClient)
        """
        if llm_client:
            self.llm = llm_client
        else:
            self.llm = OllamaClient(ollama_config or OllamaConfig())

    def judge(
        self,
        question: str,
        given_answer: str,
        expected_answer: Any,
    ) -> JudgmentResult:
        """Judge whether the given answer is correct."""
        # Format expected answer
        if expected_answer is None:
            expected_str = "(No specific expected answer - judge based on question relevance and factual accuracy)"
        elif isinstance(expected_answer, (list, dict)):
            import json
            expected_str = json.dumps(expected_answer, indent=2, default=str)
        else:
            expected_str = str(expected_answer)

        prompt = f"""Question: {question}

Expected Answer: {expected_str}

Given Answer: {given_answer}

Please evaluate whether the given answer is correct."""

        messages = [
            ChatMessage(role="system", content=self.SYSTEM_PROMPT),
            ChatMessage(role="user", content=prompt),
        ]

        response = self.llm.chat(messages)
        response_text = response.content

        # Parse response
        is_correct = False
        confidence = 0.5
        partial_credit = 0.0
        reasoning = response_text

        lines = response_text.strip().split("\n")
        for line in lines:
            line_upper = line.upper().strip()

            if line_upper.startswith("CORRECT:"):
                value = line.split(":", 1)[1].strip().lower()
                if value in ("yes", "true", "1"):
                    is_correct = True
                    partial_credit = 1.0
                elif value == "partial":
                    is_correct = False
                    # Will be set by PARTIAL_CREDIT
                else:
                    is_correct = False
                    partial_credit = 0.0

            elif line_upper.startswith("CONFIDENCE:"):
                try:
                    confidence = float(line.split(":", 1)[1].strip())
                    confidence = max(0.0, min(1.0, confidence))
                except (ValueError, IndexError):
                    pass

            elif line_upper.startswith("PARTIAL_CREDIT:"):
                try:
                    partial_credit = float(line.split(":", 1)[1].strip())
                    partial_credit = max(0.0, min(1.0, partial_credit))
                except (ValueError, IndexError):
                    pass

            elif line_upper.startswith("REASONING:"):
                reasoning = line.split(":", 1)[1].strip()

        return JudgmentResult(
            question=question,
            given_answer=given_answer,
            expected_answer=expected_answer,
            is_correct=is_correct,
            confidence=confidence,
            reasoning=reasoning,
            partial_credit=partial_credit if not is_correct else 1.0,
        )
