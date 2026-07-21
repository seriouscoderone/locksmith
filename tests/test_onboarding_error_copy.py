# -*- encoding: utf-8 -*-
from locksmith.ui.onboarding.home_page import OnboardingErrorPage


def test_onboarding_error_copy_has_full_detail(qapp):
    page = OnboardingErrorPage("document_said mismatch on brand bundle")

    content = page.copy_button.get_copy_content()
    assert "document_said mismatch on brand bundle" in content
    assert "isn't available" in content  # heading text included
