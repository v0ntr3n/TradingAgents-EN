# -*- coding: utf-8 -*-
"""Upgrade patch mode — Skill Iteratively upgraded parent contract  + delta] Specification generation.

Background: Upgrading a session has changed from the conversation text**Regenerate the full amount spec**, Specifications LLM has not read the parent version
Code and contract, re-invent everything based on upgrade requirements in one sentence——The parent version has been verified for multiple rounds
`rank_data_type: int = 11` (National monthly sales list) rewritten into a string
 [ Monthly Sales List is sent directly to the interface, and the interface silently returns to the hot list, and the business is verified and judged.
 [ Monthly sales of 1.02 million units is unreasonable , the repair cycle is to return the correct code according to the wrong spec, and it is an endless loop.

Align with the edit-apply model of mainstream programming agents (the original code is the base, LLM only outputs increments,
System deterministic application):
1. LLM Read the parent version first (complete contract + code verified)——read and write
2. Then understand the upgrade requirements and locate the change points
3. **Only output patches (delta)**——Fields not mentioned have no output channels, and structural rewriting is prohibited.
4. apply_upgrade_patch Deterministic application: parent contract + patch → new spec
5. The list of change points (change_points) is returned with spec.metadata and displayed in diff style on the confirmation page

Usage (requirement_analyzer):
    prompt = build_upgrade_patch_prompt(parent_contract, conversation)
    raw = llm.chat(prompt)                # LLM Output patch JSON
    spec = apply_upgrade_patch(parent_contract, json.loads(raw))

parent_contract Structure (service layer loads from external_skills and calculates version number):
    {
        "tool_id": parent version tool_id,
        "root_tool_id": Series root tool_id (parent_skill_id or tool_id),
        "new_tool_id": "{root}_v{N}" (Calculated in DB version order, consistent with _save_skill),
        "new_version": N,
        "display_name"/"description"/"category"/"data_source": ...,
        "parameters": [SkillParameter dict, ...],
        "expected_output": {"type", "fields", "description"},
        "constraints": [str, ...],
        "test_input": {...},
        "code": The complete verified code of the parent version (only for LLM to read, not included in spec),
    }
"""

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from core.tools.external.skill_spec import (
    ExpectedOutput,
    SkillParameter,
    SkillSpec,
    ValidationCheck,
)

# Patch the parameter fields that are allowed in JSON (to prevent LLM from being stuffed without keys)
_PARAM_FIELDS = {"name", "type", "description", "required", "default", "enum"}


def _strip_version_suffix(display_name: str) -> str:
    """Remove the version suffix at the end of the display name (  v2 /  v3 ) , Add new suffix."""
    return re.sub(r"\s*v\d+$", "", (display_name or "").strip())


def build_upgrade_patch_prompt(parent_contract: Dict[str, Any], conversation: str) -> str:
    """Construct upgrade patch generation prompt: parent contract + parent code + Upgrade dialogue → Only delta is output."""
    # Show the contract part to LLM (the code is in a separate column to avoid the contract JSON being too large)
    contract_view = {
        k: parent_contract.get(k)
        for k in (
            "tool_id", "display_name", "description", "category", "data_source",
            "parameters", "expected_output", "constraints", "test_input",
        )
    }
    code = str(parent_contract.get("code") or "").strip()

    return (
        "You are the Skill Upgrade Patch Generator. Instead of writing a specification from scratch, your task is to:"
        "First read the parent version (contract + verified code), and then understand the user s upgrade needs,"
        "finally**Only output the parts that need to be changed (patch)**. \n\n"
        "## Step 1: Understand the parent version (internal understanding, no need to output)\n\n"
        "### Parent version contract (a fact verified by multiple rounds of actual testing, not a reference recommendation)\n"
        f"```json\n{json.dumps(contract_view, ensure_ascii=False, indent=1)}\n```\n\n"
        "### Parent version verified code\n"
        f"```python\n{code}\n```\n\n"
        "## Step 2: Understand the upgrade requirements\n\n"
        f"Conversation content:\n{conversation}\n\n"
        "## Step 3: Output the patch (only changes are included, content not mentioned will be inherited as is)\n\n"
        " [patch rules — extremely important]\n"
        "1. **You do not have permission to override the parent version contract**: Parameter definition (name/type/default value/value semantics),"
        "Interface constraints (URL/request header/value requirements, such as rank_data_type needs to be 11 ) are the facts of multiple rounds of verification,"
        "Unless the upgrade requirements explicitly require modification, it must be inherited as it is without changing a word.\n"
        "2. The same applies to the output fields: only the fields involved in this upgrade will be added or deleted, and the other field names will remain the same.\n"
        "3. remove Class operations must be done with extreme caution: only used if the user explicitly requests removal\n"
        "4. change_points It is a change list for users, which corresponds to the actual changes one by one."
        "Let users understand at a glance What has been changed in this upgrade, and the rest will be inherited. \n"
        "5. If the upgrade requirement conflicts with the verified behavior of the parent version (such as requiring a change in parameter value semantics),"
        "Do so but specify in constraint_additions and include change_points\n\n"
        "Please output JSON only (nothing else):\n"
        "{\n"
        '  "upgrade_summary": "Summarize this upgrade in one sentence",\n'
        '  "change_points": ["Added price_range (manufacturer s guide price range) to the output field", "..."],\n'
        '  "description": "Optional——Provide a new description only when the function positioning changes, otherwise the key is omitted",\n'
        '  "parameter_changes": {\n'
        '    "add": [{"name": "new_param", "type": "string", "description": "...", "required": false}],\n'
        '    "modify": [{"name": "Parameter name already exists", "List only the fields that need to be modified": "..."}],\n'
        '    "remove": []\n'
        "  },\n"
        '  "output_field_changes": {"add": ["price_range"], "remove": []},\n'
        '  "output_description": "Optional——Provided only if the output meaning changes",\n'
        '  "constraint_additions": ["New behavioral constraints added in this upgrade"],\n'
        '  "test_input_updates": {}\n'
        "}"
    )


def _apply_parameter_changes(
    parent_params: List[Dict[str, Any]],
    changes: Optional[Dict[str, Any]],
) -> Tuple[List[SkillParameter], List[str]]:
    """Apply parameter patch: add to append / modify to merge only the listed fields / remove to delete.

    modify is a key line of defense: the patch only provides the fields to be changed (such as description).
    The remaining fields (type/default/required) are retained unchanged from the parent version——
    LLM No output channel overrides a parameter as a whole.
    """
    merged: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for p in parent_params or []:
        name = str(p.get("name") or "").strip()
        if name and name not in merged:
            merged[name] = dict(p)
            order.append(name)

    notes: List[str] = []
    changes = changes or {}

    for entry in changes.get("remove") or []:
        name = str(entry).strip()
        if name in merged:
            del merged[name]
            order.remove(name)
            notes.append(f"参数删除 {name}")

    for entry in changes.get("modify") or []:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        if not name or name not in merged:
            continue
        # Only legal fields with non-None values are merged, and the rest (including name itself) are left unchanged.
        touched = [
            k for k in entry
            if k != "name" and k in _PARAM_FIELDS and entry[k] is not None
        ]
        for k in touched:
            merged[name][k] = entry[k]
        if touched:
            notes.append(f"参数修改 {name}（{', '.join(sorted(touched))}）")

    for entry in changes.get("add") or []:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        clean = {k: entry[k] for k in entry if k in _PARAM_FIELDS}
        if name in merged:
            # Parameters with the same name already exist: press modify to merge (LLM should use modify, here is the bottom line)
            for k, v in clean.items():
                if k != "name" and v is not None:
                    merged[name][k] = v
            notes.append(f"参数合并 {name}")
        else:
            merged[name] = clean
            order.append(name)
            notes.append(f"参数新增 {name}")

    params = []
    for name in order:
        try:
            params.append(SkillParameter(**merged[name]))
        except Exception:
            continue
    return params, notes


def _apply_output_changes(
    parent_fields: List[str],
    changes: Optional[Dict[str, Any]],
) -> Tuple[List[str], List[str]]:
    """Apply output field patch:+add -remove, Preserve order and remove duplicates."""
    fields = [str(f) for f in (parent_fields or []) if str(f).strip()]
    changes = changes or {}
    remove = {str(f) for f in (changes.get("remove") or [])}
    notes: List[str] = []
    if remove:
        fields = [f for f in fields if f not in remove]
        notes.append(f"输出字段删除 {', '.join(sorted(remove))}")
    added = []
    for f in (changes.get("add") or []):
        f = str(f).strip()
        if f and f not in fields:
            fields.append(f)
            added.append(f)
    if added:
        notes.append(f"输出字段新增 {', '.join(added)}")
    return fields, notes


def apply_upgrade_patch(
    parent_contract: Dict[str, Any], patch: Dict[str, Any]
) -> SkillSpec:
    """Deterministically apply patch: parent contract + delta → New SkillSpec.

    All fields not mentioned in the patch are inherited from the parent version (parameters/constraints/output/test input),
    tool_id/display_name Determined by the version number calculated by the service layer.
    The list of change points is written to spec.metadata.upgrade_change_points (displayed on the confirmation page).
    """
    root_tool_id = str(parent_contract.get("root_tool_id") or parent_contract.get("tool_id") or "")
    new_tool_id = str(parent_contract.get("new_tool_id") or f"{root_tool_id}_v2")
    new_version = int(parent_contract.get("new_version") or 2)

    parent_params = list(parent_contract.get("parameters") or [])
    parameters, param_notes = _apply_parameter_changes(
        parent_params, patch.get("parameter_changes")
    )

    parent_output = dict(parent_contract.get("expected_output") or {})
    parent_fields = list(parent_output.get("fields") or [])
    fields, field_notes = _apply_output_changes(
        parent_fields, patch.get("output_field_changes")
    )
    output_desc = str(patch.get("output_description") or parent_output.get("description") or "")

    # Constraints: Inherit the parent version constraints as they are (including interface URL/value requirements), and then add new patches.
    constraints: List[str] = [str(c) for c in (parent_contract.get("constraints") or []) if str(c).strip()]
    if root_tool_id:
        iter_note = f"本 Skill 是 {root_tool_id} 的迭代优化版本"
        if iter_note not in constraints:
            constraints.append(iter_note)
    for c in patch.get("constraint_additions") or []:
        c = str(c).strip()
        if c and c not in constraints:
            constraints.append(c)

    # Test input: parent version + patch coverage
    test_input = dict(parent_contract.get("test_input") or {})
    updates = patch.get("test_input_updates")
    if isinstance(updates, dict):
        test_input.update(updates)

    # Change point list: Give priority to the change_points given by LLM, and if missing, use the actual records of the application process.
    change_points = [str(c) for c in (patch.get("change_points") or []) if str(c).strip()]
    if not change_points:
        change_points = param_notes + field_notes
    upgrade_summary = str(patch.get("upgrade_summary") or "").strip()

    # Acceptance check is derived from the final output field (existence check: upgrade fields may legally be empty strings, such as price_range)
    validation_checks: List[ValidationCheck] = [
        ValidationCheck(
            name="status_success", description="输出状态必须成功",
            required=True, check_type="status_success", rule_level="output",
            blocking=True, value_path="output", forbid_null=False,
        )
    ]
    for f in fields:
        validation_checks.append(
            ValidationCheck(
                name=f"required_field:{f}", description=f"成功输出时 {f} 字段存在",
                required=True, check_type="required_field", rule_level="data",
                blocking=True, field=f, value_path="data", forbid_null=False,
            )
        )

    parent_display = str(parent_contract.get("display_name") or "")
    display_name = f"{_strip_version_suffix(parent_display)} v{new_version}"

    description = str(patch.get("description") or parent_contract.get("description") or "")

    return SkillSpec(
        tool_id=new_tool_id,
        display_name=display_name,
        description=description,
        category=str(parent_contract.get("category") or "utility"),
        data_source=str(parent_contract.get("data_source") or ""),
        parameters=parameters,
        expected_output=ExpectedOutput(
            type=str(parent_output.get("type") or "list[dict]"),
            fields=fields,
            description=output_desc,
        ),
        validation_checks=validation_checks,
        constraints=constraints,
        test_input=test_input,
        metadata={
            "upgrade_mode": "patch",
            "upgrade_parent_tool_id": root_tool_id,
            "upgrade_change_points": change_points,
            "upgrade_summary": upgrade_summary,
        },
        parent_skill_id=root_tool_id,
        version=new_version,
    )


def parent_contract_to_json(contract: Dict[str, Any], max_code_chars: int = 12000) -> str:
    """Parent contract summary (used to inject the downgrade path into the old version full specification to generate prompt)."""
    view = {
        k: contract.get(k)
        for k in ("tool_id", "display_name", "description", "parameters",
                  "expected_output", "constraints", "test_input")
    }
    code = str(contract.get("code") or "")
    if len(code) > max_code_chars:
        code = code[:max_code_chars] + "\n... (截断)"
    view["code"] = code
    return json.dumps(view, ensure_ascii=False, indent=1)
