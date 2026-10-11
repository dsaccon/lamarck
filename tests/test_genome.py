import pytest

from lamarck.genome import GEN0, Op, PatchError, apply

SKILL = 'def count_lines(text):\n    """Count lines."""\n    return text.count("\\n") + 1\n'
VALIDATOR = 'def check(answer, question):\n    return None if answer.strip() else "empty answer"\n'


def op(**kw):
    return Op(**kw)


def test_gen0_is_plain_inline():
    assert GEN0.context_mode == "inline" and GEN0.repl is False
    assert GEN0.skills == {} and GEN0.validators == {} and GEN0.system_notes == []


def test_repl_context_requires_repl():
    with pytest.raises(PatchError):
        apply(GEN0, [op(op="set", path="context_mode", value_json='"repl"')])
    g = apply(GEN0, [op(op="set", path="repl", value_json="true"), op(op="set", path="context_mode", value_json='"repl"')])
    assert g.repl and g.context_mode == "repl"


def test_unsettable_path_is_refused():
    with pytest.raises(PatchError, match="not settable"):
        apply(GEN0, [op(op="set", path="base_prompt", value_json='"x"')])


def test_caps_are_enforced():
    with pytest.raises(PatchError):
        apply(GEN0, [op(op="set", path="limits.max_steps", value_json="99")])
    with pytest.raises(PatchError):
        apply(GEN0, [op(op="set", path="root_model", value_json='"gpt-9"')])


def test_skill_must_define_its_function_and_parse():
    with pytest.raises(PatchError, match="must define"):
        apply(GEN0, [op(op="put_skill", name="count_lines", source="x = 1\n")])
    with pytest.raises(PatchError, match="syntax"):
        apply(GEN0, [op(op="put_skill", name="count_lines", source="def count_lines(:\n")])
    g = apply(GEN0, [op(op="put_skill", name="count_lines", source=SKILL)])
    assert "count_lines" in g.skills


def test_validator_must_define_check():
    with pytest.raises(PatchError):
        apply(GEN0, [op(op="put_validator", name="nonempty", source="def other(a, q):\n    return None\n")])
    assert "nonempty" in apply(GEN0, [op(op="put_validator", name="nonempty", source=VALIDATOR)]).validators


def test_notes_add_and_remove():
    g = apply(GEN0, [op(op="add_note", text="Use code for counting.")])
    assert g.system_notes == ["Use code for counting."]
    assert apply(g, [op(op="remove_note", index=0)]).system_notes == []
    with pytest.raises(PatchError):
        apply(g, [op(op="remove_note", index=5)])


def test_noop_and_empty_patches_are_refused():
    with pytest.raises(PatchError):
        apply(GEN0, [])
    with pytest.raises(PatchError, match="does not change"):
        apply(GEN0, [op(op="set", path="repl", value_json="false")])


def test_apply_does_not_mutate_input():
    before = GEN0.model_dump()
    apply(GEN0, [op(op="add_note", text="x")])
    assert GEN0.model_dump() == before
