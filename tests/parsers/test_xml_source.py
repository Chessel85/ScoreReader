# tests/parsers/test_xml_source.py
import zipfile

from parsers.xml_source import read_musicxml_root

CONTAINER_XML = """<?xml version="1.0" encoding="UTF-8"?>
<container>
  <rootfiles>
    <rootfile full-path="{rootfile_name}"></rootfile>
  </rootfiles>
</container>
"""


def test_read_musicxml_root_handles_plain_musicxml(minimal_score):
    root = read_musicxml_root(minimal_score)
    assert root.tag == "score-partwise"


def test_read_musicxml_root_follows_container_manifest_not_a_guessed_name(tmp_path, minimal_score):
    """The container manifest, not a guessed member name (e.g. "score.xml"),
    is what identifies the real score inside a .mxl - this fixture uses a
    deliberately unrelated member name to prove the manifest is actually
    being read rather than a convention being assumed."""
    with open(minimal_score, "rb") as f:
        musicxml_bytes = f.read()

    mxl_path = tmp_path / "renamed.mxl"
    with zipfile.ZipFile(mxl_path, "w") as archive:
        archive.writestr(
            "META-INF/container.xml",
            CONTAINER_XML.format(rootfile_name="totally_unrelated_member_name.xml"),
        )
        archive.writestr("totally_unrelated_member_name.xml", musicxml_bytes)

    root = read_musicxml_root(str(mxl_path))
    assert root.tag == "score-partwise"
