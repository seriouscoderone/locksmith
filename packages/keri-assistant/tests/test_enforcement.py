import pytest
from keri_assistant.enforcement import EnforcementStrength, SoftEnforcementError, require_hard


def test_members_and_values():
    assert EnforcementStrength.HARD.value == "hard"
    assert EnforcementStrength.SOFT.value == "soft"


def test_require_hard_accepts_hard():
    assert require_hard(EnforcementStrength.HARD) is None


def test_require_hard_rejects_soft():
    with pytest.raises(SoftEnforcementError) as exc:
        require_hard(EnforcementStrength.SOFT)
    assert "soft" in str(exc.value).lower()


def test_soft_enforcement_error_is_runtime_error():
    assert issubclass(SoftEnforcementError, RuntimeError)
