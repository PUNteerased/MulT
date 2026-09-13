"""Research agent package — proposals only (no auto-apply)."""
from subsystems.research.auditor import run_calculation_audit
from subsystems.research.agent_loop import check_quality, run_research_agent

__all__ = ["run_calculation_audit", "run_research_agent", "check_quality"]
