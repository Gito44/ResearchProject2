import hashlib

from semgem.io.load_model import calculate_file_hash


def test_file_hash_uses_sha256(tmp_path):
    model_file = tmp_path / "model.xml"
    model_file.write_bytes(b"example model content")

    expected = hashlib.sha256(b"example model content").hexdigest()
    assert calculate_file_hash(model_file) == expected
