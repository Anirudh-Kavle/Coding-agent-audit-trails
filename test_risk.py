"""Gate tests for deterministic risk classification (flight_recorder/risk.py
+ risk_rules.yaml).

Run: .venv/bin/python -m pytest test_risk.py
"""
from flight_recorder import risk


def _args(command: str) -> str:
    return f'{{"command": "{command}"}}'


def test_base_tier_by_tool():
    assert risk.classify("Read", "{}")[0] == "info"
    assert risk.classify("Edit", "{}")[0] == "write"
    assert risk.classify("Bash", "{}")[0] == "exec"
    assert risk.classify("WebFetch", "{}")[0] == "network"


def test_unknown_tool_falls_back_to_default_tier():
    assert risk.classify("mcp__foo__bar", "{}")[0] == "exec"


def test_permissive_chmod_plain():
    tier, reasons = risk.classify("Bash", _args("chmod 777 file.sh"))
    assert tier == "sensitive"
    assert "permissive chmod" in reasons


def test_permissive_chmod_with_recursive_flag():
    # Regression: chmod -R 777 (the common, more dangerous real-world form —
    # applies to a whole directory tree) used to slip through as plain "exec"
    # because the old regex required 7XX immediately after "chmod ", with no
    # room for a flag in between.
    tier, reasons = risk.classify("Bash", _args("chmod -R 777 ./dist"))
    assert tier == "sensitive"
    assert "permissive chmod" in reasons


def test_permissive_chmod_with_multiple_flags():
    tier, _ = risk.classify("Bash", _args("chmod -R -v 777 ./dist"))
    assert tier == "sensitive"


def test_permissive_chmod_with_long_flag():
    tier, _ = risk.classify("Bash", _args("chmod --recursive 777 dir"))
    assert tier == "sensitive"


def test_chmod_without_digits_is_not_flagged():
    tier, reasons = risk.classify("Bash", _args("chmod +x file.sh"))
    assert tier == "exec"
    assert reasons == []


def test_chmod_with_non_permissive_digits_is_not_flagged():
    tier, reasons = risk.classify("Bash", _args("chmod -R 644 dir"))
    assert tier == "exec"
    assert reasons == []


def test_destructive_delete_escalates_to_sensitive():
    tier, reasons = risk.classify("Bash", _args("rm -rf node_modules"))
    assert tier == "sensitive"
    assert "destructive delete" in reasons


def test_privilege_escalation_escalates_to_sensitive():
    tier, reasons = risk.classify("Bash", _args("sudo apt install foo"))
    assert tier == "sensitive"
    assert "privilege escalation" in reasons


def test_dotenv_file_escalates_regardless_of_tool():
    tier, reasons = risk.classify("Edit", '{"file_path": ".env"}')
    assert tier == "sensitive"
    assert "dotenv file" in reasons


def test_no_pattern_match_keeps_base_tier():
    tier, reasons = risk.classify("Bash", _args("ls -la"))
    assert tier == "exec"
    assert reasons == []


def test_pattern_reasons_are_case_insensitive():
    tier, reasons = risk.classify("Bash", _args("SUDO apt install foo"))
    assert tier == "sensitive"
    assert "privilege escalation" in reasons
