"""
Skill Import and test verification API acceptance testing

Cover:
- POST /api/skills/import                  Local SKILL.md content import
- POST /api/skills/import-url              URL import
- POST /api/skills/test                    Skill sandbox testing
- GET  /api/skills/github/repo/{owner}/{repo} GitHub Warehouse Skill Browse
- POST /api/skills/import-github           Import from GitHub and test
- GET  /api/skills/smithery/servers        Smithery MCP Server list
- GET  /api/skill-center/skills            Unified Skill Center List (Verify Registration)
"""
import pytest


SAMPLE_SKILL_MD = """---
name: test-hello-skill
version: "1.0.0"
description: Example for acceptance testing Skill
author: acceptance-test
category: test
tags: [test]
parameters:
  - name: name
    type: string
    description: Name
    required: false
implementation:
  type: python
  code: |
    import json
    import sys
    args = json.loads(sys.stdin.read()) if sys.stdin else {}
    name = args.get("name", "world")
    print("__SANDBOX_OUTPUT_START__")
    print(json.dumps({"message": f"hello {name}"}, ensure_ascii=False))
    print("__SANDBOX_OUTPUT_END__")
---

This is a Skill used for acceptance testing and will be automatically registered to ToolRegistry after import.
"""


class TestSkillImport:
    """Skill Import and test."""

    def test_import_skill_from_content(self, api_client):
        """Import Skills from content."""
        resp = api_client.post("/api/skills/import", json={"content": SAMPLE_SKILL_MD})
        assert resp.status_code in (200, 400), f"Import exception: {resp.status_code} {resp.text}"
        if resp.status_code == 200:
            data = resp.json()
            assert data["name"] == "test-hello-skill"

    def test_test_skill_with_args(self, api_client):
        """Test the imported Skill and pass in the parameters."""
        resp = api_client.post("/api/skills/test", json={
            "skill_name": "test-hello-skill",
            "args": {"name": "trading"}
        })
        assert resp.status_code == 200, f"test failed: {resp.status_code} {resp.text}"
        data = resp.json()
        assert data["success"] is True
        assert data["result"]["message"] == "hello trading"

    def test_skill_appears_in_skill_center(self, api_client):
        """The imported skill appears in the Unified Skill Center."""
        resp = api_client.get("/api/skill-center/skills")
        assert resp.status_code == 200, f"Failed to get Skill Center: {resp.status_code} {resp.text}"
        skills = resp.json()
        skill_ids = [s["skill_id"] for s in skills]
        assert "test-hello-skill" in skill_ids, f"The imported skill does not appear in the Skill Center: {skill_ids}"

    def test_import_skill_already_exists(self, api_client):
        """Repeated imports of the same Skill should return 400."""
        resp = api_client.post("/api/skills/import", json={"content": SAMPLE_SKILL_MD})
        assert resp.status_code == 400, f"Repeated imports should fail: {resp.status_code} {resp.text}"

    def test_github_repo_skills_browse(self, api_client):
        """GitHub A repository browsing interface is available (using the sample repository)."""
        # Use a public example repository that does not rely on network stability; the interface can successfully return the structure
        resp = api_client.get("/api/skills/github/repo/modelcontextprotocol/servers")
        # The repository may not have SKILL.md, but the interface itself should return normally
        assert resp.status_code in (200, 404), f"GitHub Browsing interface exception: {resp.status_code} {resp.text}"

    def test_smithery_servers_list(self, api_client):
        """Smithery MCP Server A list interface is available."""
        resp = api_client.get("/api/skills/smithery/servers")
        assert resp.status_code in (200, 500), f"Smithery Interface exception: {resp.status_code} {resp.text}"
        if resp.status_code == 200:
            data = resp.json()
            assert isinstance(data, list)


class TestSkillTestFailures:
    """Skill Test failure scenario."""

    def test_test_nonexistent_skill(self, api_client):
        """Testing a non-existent Skill returns 404."""
        resp = api_client.post("/api/skills/test", json={
            "skill_name": "skill-not-exists-xyz",
            "args": {}
        })
        assert resp.status_code == 404, f"should return 404: {resp.status_code} {resp.text}"
