import ast, inspect
from locksmith.core import ipexing


def test_all_admit_complete_emits_carry_credential_said():
    tree = ast.parse(inspect.getsource(ipexing))
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        kw = {k.arg: k.value for k in node.keywords}
        et = kw.get("event_type")
        if isinstance(et, ast.Constant) and et.value == "admit_complete":
            data = kw.get("data")
            keys = ({k.value for k in data.keys if isinstance(k, ast.Constant)}
                    if isinstance(data, ast.Dict) else set())
            if "credential_said" not in keys:
                offenders.append(ast.dump(node)[:80])
    assert not offenders, f"admit_complete emit(s) missing credential_said: {offenders}"
