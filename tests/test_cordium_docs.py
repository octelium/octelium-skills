from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import validate_cordium_docs as docs


class CordiumDocumentationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="octelium-skills-cordium-docs-test-")
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.source = self.directory / "docs"
        self.skill = self.directory / "skill"
        self.skill.mkdir()

    def write_doc(self, path: str, text: str) -> None:
        target = self.source / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    def write_links(self, *paths: str) -> None:
        (self.skill / "SKILL.md").write_text("\n".join(
            f"[Reference](https://octelium.com{docs.BASE}/{path})" for path in paths))

    def test_routes_use_frontmatter_ids_and_directory_indexes(self) -> None:
        self.write_doc("use/overview.mdx", "---\nid: access-methods\n---\n## Methods\n")
        self.write_doc("use/index.mdx", "---\nid: use\n---\nChoose a method.\n")
        self.write_links("use/access-methods.md#methods", "use")
        self.assertEqual(docs.validate_links(self.skill, self.source), (2, []))
        self.write_links("use/overview.md", "use/index.md")
        checked, errors = docs.validate_links(self.skill, self.source)
        self.assertEqual((checked, len(errors)), (2, 2))
        self.assertTrue(all("missing documentation page" in error for error in errors))

    def test_missing_pages_and_anchors_report_file_and_line(self) -> None:
        self.write_doc("use/cli.mdx", "## Creating Workspaces\n")
        self.write_links("use/cli.md#creating-workspaces", "use/cli.md#old-section", "use/config.md")
        checked, errors = docs.validate_links(self.skill, self.source)
        self.assertEqual((checked, len(errors)), (3, 2))
        self.assertIn("SKILL.md:2: missing documentation anchor", errors[0])
        self.assertIn("SKILL.md:3: missing documentation page", errors[1])

    def test_headings_in_fences_are_not_anchors(self) -> None:
        self.write_doc("use/cli.mdx", "## Real Section\n```bash\n# Fake Section\n```\n")
        self.write_links("use/cli.md#real-section", "use/cli.md#fake-section")
        checked, errors = docs.validate_links(self.skill, self.source)
        self.assertEqual((checked, len(errors)), (2, 1))
        self.assertIn("missing documentation anchor", errors[0])

    def test_repeated_headings_and_formatted_titles_have_anchors(self) -> None:
        self.write_doc("use/cli.mdx", "## Using `exec`\n## Using `exec`\n## Files, Ports and [IDEs](./ssh.mdx)\n")
        self.write_links("use/cli.md#using-exec", "use/cli.md#using-exec-1", "use/cli.md#files-ports-and-ides")
        self.assertEqual(docs.validate_links(self.skill, self.source), (3, []))

    def test_ignored_docs_are_not_routes(self) -> None:
        self.write_doc("use/cli.mdx", "---\nignore: true\n---\n## CLI\n")
        self.write_links("use/cli.md")
        self.assertEqual(len(docs.validate_links(self.skill, self.source)[1]), 1)

    def test_indexes_and_other_products_are_not_checked_as_pages(self) -> None:
        self.write_doc("use/cli.mdx", "## CLI\n")
        self.write_links("use/cli.md", "llms.txt")
        with (self.skill / "SKILL.md").open("a") as stream:
            stream.write("\nhttps://octelium.com/docs/octelium/latest/example.md\n")
        self.assertEqual(docs.validate_links(self.skill, self.source), (1, []))

    def test_empty_inputs_fail(self) -> None:
        with self.assertRaisesRegex(ValueError, "no documentation files"):
            docs.validate_links(self.skill, self.source)
        self.write_doc("use/cli.mdx", "## CLI\n")
        self.assertIn("no Cordium documentation links", docs.validate_links(self.skill, self.source)[1][0])


if __name__ == "__main__":
    unittest.main()
