"""Extensible technical assessment families, never question-to-model routes."""

from abc import ABC, abstractmethod

from .intake import supplied, finding


class AssessmentStrategy(ABC):
    problem_type: str
    version: str = "1.0"
    work_type: str = "predictive"
    supported_constraints = frozenset()

    @abstractmethod
    def supports(self, requirement): ...

    def additional_findings(self, requirement, candidate, data_evidence):
        """Trusted backend extension; must return evidence-based findings, no ML."""
        return []


class ForecastAssessment(AssessmentStrategy):
    problem_type = "forecasting"
    def supports(self, r):
        return supplied(r, "intent") == "future" and supplied(r, "desired_output", {}).get("value_kind") in ("numeric", "count")


class RegressionAssessment(AssessmentStrategy):
    problem_type = "regression"
    def supports(self, r):
        return supplied(r, "intent") == "unknown_outcome" and supplied(r, "desired_output", {}).get("value_kind") in ("numeric", "count")


class ClassificationAssessment(AssessmentStrategy):
    problem_type = "classification"
    def supports(self, r):
        return supplied(r, "intent") in ("future", "unknown_outcome") and supplied(r, "desired_output", {}).get("value_kind") in ("categorical", "boolean")


class AnalyticsAssessment(AssessmentStrategy):
    problem_type = "analytics"
    work_type = "analytics"
    def supports(self, r):
        return supplied(r, "intent") == "historical"


class StrategyRegistry:
    def __init__(self, strategies=()):
        self._strategies = {}
        for strategy in strategies:
            self.register(strategy)

    def register(self, strategy):
        if not isinstance(strategy, AssessmentStrategy) or not strategy.problem_type or strategy.problem_type in self._strategies:
            raise ValueError("Register a distinct trusted assessment strategy.")
        self._strategies[strategy.problem_type] = strategy

    def select(self, requirement):
        hint = supplied(requirement, "task_hint")
        if supplied(requirement, "intent") is None or supplied(requirement, "desired_output") is None:
            return None, []  # Intake asks for the missing structure.
        matches = [s for s in self._strategies.values() if (hint is None or s.problem_type == hint) and s.supports(requirement)]
        if not matches:
            return None, [finding("unsupported_problem_characteristics", "unsupported", "No registered assessment strategy supports these structured task characteristics.")]
        if len(matches) > 1:
            return None, [finding("ambiguous_problem_type", "clarification", "Multiple technical task families fit; clarify the intended prediction problem.")]
        return matches[0], []

    def versions(self):
        return [[key, value.version] for key, value in sorted(self._strategies.items())]


def default_strategies():
    return StrategyRegistry([AnalyticsAssessment(), ForecastAssessment(), RegressionAssessment(), ClassificationAssessment()])
