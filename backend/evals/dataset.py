"""
Labeled eval cases for the /query endpoint, run against the fixed sample
KB in sample_kb/. Each case checks two independent things:

1. Retrieval/answer quality -- for questions the KB actually covers, does
   the answer contain at least one of the expected keywords? This is a
   cheap proxy for "did retrieval find the right chunk and did the model
   use it", not a full semantic eval, but it catches the failures that
   matter most (wrong chunk retrieved, model ignored the source).

2. Escalation correctness -- does result["escalated"] match what a human
   would expect, given the category:
   - "kb_covered"     -> should NOT escalate, the KB has a clear answer
   - "explicit_human" -> should escalate, the customer asked for one
   - "out_of_scope"   -> should escalate, the KB has no relevant info

expect_keywords is empty for out_of_scope cases -- there's nothing correct
to check the answer against, only the escalation decision.
"""

EVAL_CASES = [
    {
        "id": "refund_policy",
        "category": "kb_covered",
        "question": "What is your refund policy?",
        "expect_keywords": ["30 days", "refund"],
        "expect_escalate": False,
    },
    {
        "id": "password_reset",
        "category": "kb_covered",
        "question": "How do I reset my password?",
        "expect_keywords": ["forgot password", "email", "reset"],
        "expect_escalate": False,
    },
    {
        "id": "free_plan_storage",
        "category": "kb_covered",
        "question": "How much storage do I get on the free plan?",
        "expect_keywords": ["5 GB"],
        "expect_escalate": False,
    },
    {
        "id": "data_export",
        "category": "kb_covered",
        "question": "Can I export my data, and what format do I get?",
        "expect_keywords": ["export", "zip", "csv"],
        "expect_escalate": False,
    },
    {
        "id": "account_deletion",
        "category": "kb_covered",
        "question": "How do I delete my account?",
        "expect_keywords": ["delete", "settings", "30-day", "30 day"],
        "expect_escalate": False,
    },
    {
        "id": "data_retention_after_cancel",
        "category": "kb_covered",
        "question": "If I cancel my subscription, how long do you keep my data?",
        "expect_keywords": ["30 days"],
        "expect_escalate": False,
    },
    {
        "id": "encryption",
        "category": "kb_covered",
        "question": "Is my data encrypted?",
        "expect_keywords": ["aes-256", "aes", "tls"],
        "expect_escalate": False,
    },
    {
        "id": "explicit_human_request",
        "category": "explicit_human",
        "question": "I don't want an AI, please connect me with a human agent right now.",
        "expect_keywords": [],
        "expect_escalate": True,
    },
    {
        "id": "urgent_billing_issue",
        "category": "explicit_human",
        "question": "I was charged twice for my subscription this month, I need someone to fix this urgently.",
        "expect_keywords": [],
        "expect_escalate": True,
    },
    {
        "id": "two_factor_auth",
        "category": "out_of_scope",
        "question": "Do you support two-factor authentication, and how do I enable it?",
        "expect_keywords": [],
        "expect_escalate": True,
    },
    {
        "id": "annual_discount",
        "category": "out_of_scope",
        "question": "Is there a discount if I pay annually instead of monthly?",
        "expect_keywords": [],
        "expect_escalate": True,
    },
    {
        "id": "team_invites",
        "category": "out_of_scope",
        "question": "How do I invite other team members to my Business plan account?",
        "expect_keywords": [],
        "expect_escalate": True,
    },
    {
        "id": "unrelated_question",
        "category": "out_of_scope",
        "question": "What's the weather like today?",
        "expect_keywords": [],
        "expect_escalate": True,
    },
]
