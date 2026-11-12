import pytest

from app import create_app, evidence


def test_storage_modes_are_validated():
    assert evidence.validate_storage_mode(None) == "local"
    assert evidence.validate_storage_mode(" LOCAL ") == "local"
    assert evidence.validate_storage_mode("blob") == "blob"
    with pytest.raises(ValueError):
        evidence.validate_storage_mode("public")


def test_blob_object_names_are_case_scoped_and_safe():
    name = evidence.new_blob_name(42, "image/png")
    assert name.startswith("ev/42/")
    assert name.endswith(".png")
    assert len(name) <= 64
    assert evidence.is_safe_blob_name(name, 42)
    assert evidence.parse_blob_name(name, 42)[0] == 42

    assert not evidence.is_safe_blob_name(name, 43)
    assert not evidence.is_safe_blob_name("ev/42/../escape.png", 42)
    assert not evidence.is_safe_blob_name("ev/0/" + "a" * 32 + ".png", 0)
    assert not evidence.is_safe_blob_name("ev/42/" + "A" * 32 + ".png", 42)
    assert not evidence.is_safe_blob_name("ev/42/" + "a" * 32 + ".gif", 42)


def test_local_names_keep_the_existing_layout():
    name = evidence.new_local_name("image/webp")
    assert name.endswith(".webp")
    assert len(name) == 37
    with pytest.raises(ValueError):
        evidence.new_local_name("image/gif")


def test_content_type_and_extension_round_trip():
    for content_type, extension in (
        ("image/jpeg", "jpg"),
        ("image/png", "png"),
        ("image/webp", "webp"),
    ):
        assert evidence.extension_for_content_type(content_type) == extension
        assert evidence.content_type_for_extension(extension) == content_type
    assert evidence.extension_for_content_type("image/gif") is None
    assert evidence.content_type_for_extension("gif") is None


def test_local_storage_round_trip(tmp_path):
    app = create_app()
    app.config["EVIDENCE_UPLOAD_DIR"] = str(tmp_path)
    app.config["EVIDENCE_STORAGE"] = "local"

    with app.app_context():
        name = evidence.new_local_name("image/png")
        evidence.write_local(name, b"evidence")
        assert evidence.local_path(name).read_bytes() == b"evidence"
        evidence.delete_local(name)
        assert not evidence.local_path(name).exists()

        with pytest.raises(evidence.EvidenceObjectInvalid):
            evidence.local_path("../escape.png")
