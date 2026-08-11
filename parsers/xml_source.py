# parsers/xml_source.py
import xml.etree.ElementTree as ET
import zipfile
from typing import Optional


def read_musicxml_root(file_path: str) -> Optional[ET.Element]:
    """Returns the root <score-partwise>/<score-timewise> Element for either
    a plain MusicXML file or a compressed .mxl one. .mxl is a zip container
    whose member the actual score lives in is named by
    META-INF/container.xml's rootfile - never the outer file's name, and not
    reliably "score.xml" either (that's just what the encoders creating this
    project's own test files happen to use), so the container manifest has
    to be read rather than guessed."""
    if not file_path.lower().endswith(".mxl"):
        return ET.parse(file_path).getroot()

    with zipfile.ZipFile(file_path) as archive:
        container = ET.fromstring(archive.read("META-INF/container.xml"))
        rootfile_path = container.find("./rootfiles/rootfile").attrib["full-path"]
        return ET.fromstring(archive.read(rootfile_path))
