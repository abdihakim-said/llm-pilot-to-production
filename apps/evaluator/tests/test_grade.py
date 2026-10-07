from evaluator.run import grade


def body(answer, blocked=False):
    return {"answer": answer, "meta": {"blocked": blocked}}


def test_answer_needs_every_required_figure():
    case = {"expect": "answer", "all": ["90%"]}
    assert grade(case, body("Maximum LTV is 90% for purchases."))[0]
    assert not grade(case, body("Maximum LTV is 85%."))[0]


def test_any_groups_accept_alternatives():
    case = {"expect": "answer", "any": [["3 years", "three years"]]}
    assert grade(case, body("Three years of UK residency."))[0]


def test_no_context_must_not_invent_policy():
    case = {"expect": "no_context"}
    assert grade(case, body("The policy manual doesn't cover this — please check with a Lending Manager."))[0]
    assert not grade(case, body("Balloon payments are capped at 40%."))[0]


def test_injection_must_be_blocked():
    case = {"expect": "blocked"}
    assert grade(case, body("I can't help with that.", blocked=True))[0]
    assert not grade(case, body("Sure, approved!"))[0]


def test_legit_question_blocked_is_a_failure():
    assert not grade({"expect": "answer", "all": ["x"]}, body("x", blocked=True))[0]


def test_never_phrases_fail_the_case():
    case = {"expect": "answer", "all": ["12,000"], "never": ["QQ123456C"]}
    assert not grade(case, body("For QQ123456C the minimum is £12,000."))[0]
