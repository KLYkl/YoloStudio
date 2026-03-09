import shutil
import uuid
from pathlib import Path
import xml.etree.ElementTree as ET

from PIL import Image

from core.data_handler import DataHandler


def _create_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (100, 50), "white").save(path)


def test_convert_txt_to_xml_with_custom_label_dir() -> None:
    tmp_root = Path("D:/yolodo2.0") / f"convert-format-{uuid.uuid4().hex}"
    try:
        image_dir = tmp_root / "images"
        label_dir = tmp_root / "mylabels"
        label_dir.mkdir(parents=True)

        _create_image(image_dir / "a.jpg")
        (label_dir / "a.txt").write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")

        handler = DataHandler()

        preview = handler.preview_convert_format(tmp_root, to_xml=True, label_dir=label_dir)
        assert preview["total_labels"] == 1
        assert preview["source_type"] == "TXT"
        assert preview["target_type"] == "XML"

        converted = handler.convert_format(
            tmp_root,
            to_xml=True,
            classes=["cls0"],
            label_dir=label_dir,
            image_dir=image_dir,
        )

        assert converted == 1

        xml_path = tmp_root / "converted_labels_xml" / "a.xml"
        assert xml_path.exists()

        root = ET.parse(xml_path).getroot()
        assert root.findtext("filename") == "a.jpg"
        assert root.findtext("object/name") == "cls0"
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
