"""
Owner: Person 3

Purpose:
The 10 official evaluation questions from SPEC.md section 8, preserved
in the same numbering and order for repeatable automated evaluation.
"""

from dataclasses import dataclass

from agent.system_prompt import STATUS_REFUSED_MISSING_INFORMATION

Q10_EXPECTED_REFUSAL = "לא מופיע במסמכים"


@dataclass(frozen=True)
class EvaluationQuestion:
    number: int
    text: str
    category: str
    components_tested: str
    expected_status: str | None = None
    expected_exact_answer: str | None = None

    @property
    def id(self):
        return f"q{self.number}"


EVALUATION_QUESTIONS = (
    EvaluationQuestion(
        1,
        'Course number and credits for "׳\u009e׳‘׳•׳ ׳׳\u009e׳“׳¢׳™ ׳”׳\u009e׳—׳©׳‘"',
        "factual/table lookup",
        "course row extraction, search, citation",
    ),
    EvaluationQuestion(
        2,
        "Usual duration of undergraduate studies by regulations",
        "factual policy lookup",
        "regulations extraction, section retrieval",
    ),
    EvaluationQuestion(
        3,
        "Year B semester 4 courses and credits",
        "table lookup",
        "curriculum disambiguation, get_course_table",
    ),
    EvaluationQuestion(
        4,
        'Prerequisites for "׳׳׳’׳•׳¨׳™׳×׳׳™׳ 1"',
        "table lookup",
        "row lookup across tables/course descriptions",
    ),
    EvaluationQuestion(
        5,
        'Required courses in "׳¢׳™׳‘׳•׳“ ׳׳•׳×׳•׳× ׳•׳׳׳™׳“׳” ׳—׳™׳©׳•׳‘׳™׳×"',
        "cluster table lookup",
        "cluster model, required/recommended distinction",
    ),
    EvaluationQuestion(
        6,
        "Total credits required in year C",
        "aggregation",
        "full table retrieval, sum credits, curriculum handling",
    ),
    EvaluationQuestion(
        7,
        "Count year A courses with prerequisites",
        "aggregation",
        "complete year A rows, prerequisite detection",
    ),
    EvaluationQuestion(
        8,
        "Difference between single-major and dual-major, and relevance to CS",
        "cross-document/section reasoning",
        "yearbook degree routes, possibly regulations terminology",
    ),
    EvaluationQuestion(
        9,
        "Conditions for spreading studies to four years",
        "cross-document/policy lookup",
        "regulations + yearbook partial spread text",
    ),
    EvaluationQuestion(
        10,
        "Academic secretariat office hours",
        "refusal",
        "absence detection and exact refusal",
        expected_status=STATUS_REFUSED_MISSING_INFORMATION,
        expected_exact_answer=Q10_EXPECTED_REFUSAL,
    ),
)


def get_evaluation_questions():
    """Return a list copy so callers cannot mutate the canonical tuple."""
    return list(EVALUATION_QUESTIONS)
