"""Gate tests for deterministic risk classification (zetesis/risk.py
+ risk_rules.yaml).

Run: .venv/bin/python -m pytest test_risk.py
"""
from zetesis import risk


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


def test_curl_in_shell_escalates_to_network_not_sensitive():
    # Regression: this pattern used to force "sensitive" like every other
    # pattern, so "network" activity done via shell was indistinguishable
    # from an actually dangerous action (secrets, destructive delete, etc).
    tier, reasons = risk.classify("Bash", _args("curl https://api.example.com/data"))
    assert tier == "network"
    assert "remote network tool in shell" in reasons


def test_a_genuinely_sensitive_pattern_still_outranks_network():
    # curl AND a secret in the same command — sensitive must win, since the
    # final tier is the highest matched, never a downgrade.
    tier, reasons = risk.classify("Bash", _args("curl -H 'Authorization: token abc' https://x"))
    assert tier == "sensitive"
    assert "remote network tool in shell" in reasons
    assert "secret-like keyword" in reasons


def test_grep_searching_for_a_risky_word_is_not_flagged():
    # Regression: Grep's entire argument is a search pattern — searching FOR
    # "sudo" or "password" is a benign audit action, not the action itself.
    tier, reasons = risk.classify("Grep", '{"pattern": "sudo"}')
    assert tier == "info"
    assert reasons == []

    tier, reasons = risk.classify("Grep", '{"pattern": "password"}')
    assert tier == "info"
    assert reasons == []


def test_glob_and_websearch_are_also_exempt_from_argument_matching():
    assert risk.classify("Glob", '{"pattern": "**/*rm -rf*"}') == ("info", [])
    assert risk.classify("WebSearch", '{"query": "how sudo works"}') == ("network", [])


def test_grep_result_containing_a_real_secret_is_still_flagged():
    # The exemption is for the QUERY, not the RESULT — if Grep's output
    # actually surfaces a hardcoded secret, that's real content, not intent.
    tier, reasons = risk.classify(
        "Grep", '{"pattern": "API_KEY"}', result_text='config.py:3:API_KEY = "sk-abc123"'
    )
    assert tier == "sensitive"
    assert "secret-like keyword" in reasons


def test_bash_result_containing_a_secret_escalates_even_with_clean_arguments():
    tier, reasons = risk.classify(
        "Bash", _args("cat config.py"), result_text='API_KEY = "sk-abc123"'
    )
    assert tier == "sensitive"
    assert "secret-like keyword" in reasons


def test_duplicate_reason_from_args_and_result_is_not_repeated():
    tier, reasons = risk.classify(
        "Bash", _args("echo my password"), result_text="password: hunter2"
    )
    assert tier == "sensitive"
    assert reasons.count("secret-like keyword") == 1


def test_patterns_are_compiled_once(monkeypatch):
    risk._compiled_patterns.cache_clear()
    compile_calls = 0
    original_compile = risk.re.compile

    def counting_compile(*args, **kwargs):
        nonlocal compile_calls
        compile_calls += 1
        return original_compile(*args, **kwargs)

    monkeypatch.setattr(risk.re, "compile", counting_compile)
    risk.classify("Bash", _args("sudo whoami"))
    risk.classify("Bash", _args("rm -rf build"))

    assert compile_calls == len(risk._load_rules()["patterns"])
    risk._compiled_patterns.cache_clear()
