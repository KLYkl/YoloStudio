import shutil
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
import tempfile

from PIL import Image

from core.data_handler import AugmentConfig, DataHandler


def _create_image(path: Path, size: tuple[int, int] = (100, 50)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, "white").save(path)


def _create_xml_label(path: Path, image_name: str, width: int, height: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    root = ET.Element("annotation")
    ET.SubElement(root, "folder").text = "images"
    ET.SubElement(root, "filename").text = image_name
    size = ET.SubElement(root, "size")
    ET.SubElement(size, "width").text = str(width)
    ET.SubElement(size, "height").text = str(height)
    ET.SubElement(size, "depth").text = "3"
    obj = ET.SubElement(root, "object")
    ET.SubElement(obj, "name").text = "excavator"
    bndbox = ET.SubElement(obj, "bndbox")
    ET.SubElement(bndbox, "xmin").text = "10"
    ET.SubElement(bndbox, "ymin").text = "5"
    ET.SubElement(bndbox, "xmax").text = "30"
    ET.SubElement(bndbox, "ymax").text = "25"
    tree = ET.ElementTree(root)
    ET.indent(tree, space="    ")
    tree.write(path, encoding="utf-8", xml_declaration=True)


def test_augment_dataset_flips_yolo_labels_with_images() -> None:
    tmp_root = Path(tempfile.gettempdir()) / f"augment-yolo-{uuid.uuid4().hex}"
    try:
        image_dir = tmp_root / "images"
        label_dir = tmp_root / "labels"
        output_dir = tmp_root / "augmented"
        _create_image(image_dir / "a.jpg")
        label_dir.mkdir(parents=True, exist_ok=True)
        (label_dir / "a.txt").write_text("0 0.200000 0.400000 0.300000 0.200000\n", encoding="utf-8")

        handler = DataHandler()
        config = AugmentConfig(
            copies_per_image=1,
            include_original=True,
            seed=7,
            enable_horizontal_flip=True,
            enable_vertical_flip=False,
            enable_rotate=False,
            rotate_degrees=0.0,
            enable_brightness=False,
            brightness_strength=0.0,
            enable_contrast=False,
            contrast_strength=0.0,
            enable_color=False,
            color_strength=0.0,
            enable_hue=False,
            hue_degrees=0.0,
            enable_sharpness=False,
            sharpness_strength=0.0,
            enable_blur=False,
            blur_radius=0.0,
        )

        result = handler.augment_dataset(
            image_dir,
            config,
            label_dir=label_dir,
            output_dir=output_dir,
        )

        assert result.copied_originals == 1
        assert result.augmented_images == 1
        assert result.label_files_written == 2
        assert (output_dir / "images" / "a.jpg").exists()
        assert (output_dir / "images" / "a_aug_001.jpg").exists()

        original_label = (output_dir / "labels" / "a.txt").read_text(encoding="utf-8").strip()
        augmented_label = (output_dir / "labels" / "a_aug_001.txt").read_text(encoding="utf-8").strip()
        assert original_label == "0 0.200000 0.400000 0.300000 0.200000"

        parts = augmented_label.split()
        assert parts[0] == "0"
        assert abs(float(parts[1]) - 0.8) < 1e-6
        assert abs(float(parts[2]) - 0.4) < 1e-6
        assert abs(float(parts[3]) - 0.3) < 1e-6
        assert abs(float(parts[4]) - 0.2) < 1e-6
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def test_augment_dataset_fixed_mode_outputs_individual_and_combo_variants() -> None:
    tmp_root = Path(tempfile.gettempdir()) / f"augment-fixed-{uuid.uuid4().hex}"
    try:
        image_dir = tmp_root / "images"
        label_dir = tmp_root / "labels"
        output_dir = tmp_root / "augmented"
        _create_image(image_dir / "a.jpg", size=(100, 50))
        label_dir.mkdir(parents=True, exist_ok=True)
        source_label = "0 0.200000 0.400000 0.300000 0.200000\n"
        (label_dir / "a.txt").write_text(source_label, encoding="utf-8")

        handler = DataHandler()
        config = AugmentConfig(
            copies_per_image=1,
            include_original=False,
            seed=23,
            mode="fixed",
            custom_recipes=[
                ("rotate",),
                ("brightness",),
                ("noise",),
                ("rotate", "brightness", "noise"),
            ],
            enable_rotate=True,
            rotate_mode="counterclockwise",
            rotate_degrees=90.0,
            enable_brightness=True,
            brightness_strength=0.20,
            enable_noise=True,
            noise_strength=0.08,
        )

        result = handler.augment_dataset(
            image_dir,
            config,
            label_dir=label_dir,
            output_dir=output_dir,
        )

        assert result.copied_originals == 0
        assert result.augmented_images == 4
        assert result.label_files_written == 4

        rotate_image = output_dir / "images" / "a_rotate_001.jpg"
        brightness_image = output_dir / "images" / "a_brightness_001.jpg"
        noise_image = output_dir / "images" / "a_noise_001.jpg"
        combo_image = output_dir / "images" / "a_combo_rotate_brightness_noise_001.jpg"
        for path in (rotate_image, brightness_image, noise_image, combo_image):
            assert path.exists()

        with Image.open(rotate_image) as rotated:
            assert rotated.size == (50, 100)
        with Image.open(combo_image) as combined:
            assert combined.size == (50, 100)

        rotate_label = (output_dir / "labels" / "a_rotate_001.txt").read_text(encoding="utf-8").strip()
        brightness_label = (output_dir / "labels" / "a_brightness_001.txt").read_text(encoding="utf-8").strip()
        noise_label = (output_dir / "labels" / "a_noise_001.txt").read_text(encoding="utf-8").strip()
        combo_label = (output_dir / "labels" / "a_combo_rotate_brightness_noise_001.txt").read_text(encoding="utf-8").strip()

        assert brightness_label == source_label.strip()
        assert noise_label == source_label.strip()
        assert combo_label == rotate_label
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def test_augment_dataset_rotates_voc_boxes_and_updates_metadata() -> None:
    tmp_root = Path(tempfile.gettempdir()) / f"augment-voc-{uuid.uuid4().hex}"
    try:
        image_dir = tmp_root / "images"
        label_dir = tmp_root / "Annotations"
        output_dir = tmp_root / "augmented"
        _create_image(image_dir / "a.jpg", size=(100, 50))
        _create_xml_label(label_dir / "a.xml", "a.jpg", 100, 50)

        handler = DataHandler()
        config = AugmentConfig(
            copies_per_image=1,
            include_original=False,
            seed=11,
            enable_horizontal_flip=False,
            enable_vertical_flip=False,
            enable_rotate=True,
            rotate_mode="counterclockwise",
            rotate_degrees=90.0,
            enable_brightness=False,
            brightness_strength=0.0,
            enable_contrast=False,
            contrast_strength=0.0,
            enable_color=False,
            color_strength=0.0,
            enable_hue=False,
            hue_degrees=0.0,
            enable_sharpness=False,
            sharpness_strength=0.0,
            enable_blur=False,
            blur_radius=0.0,
        )

        result = handler.augment_dataset(
            image_dir,
            config,
            label_dir=label_dir,
            output_dir=output_dir,
        )

        assert result.copied_originals == 0
        assert result.augmented_images == 1
        assert result.label_files_written == 1

        xml_path = output_dir / "Annotations" / "a_aug_001.xml"
        assert xml_path.exists()
        root = ET.parse(xml_path).getroot()
        assert root.findtext("filename") == "a_aug_001.jpg"
        assert root.findtext("size/width") == "50"
        assert root.findtext("size/height") == "100"
        assert root.findtext("object/bndbox/xmin") == "5"
        assert root.findtext("object/bndbox/ymin") == "70"
        assert root.findtext("object/bndbox/xmax") == "25"
        assert root.findtext("object/bndbox/ymax") == "90"
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
