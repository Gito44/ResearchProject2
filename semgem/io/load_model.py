import hashlib
from pathlib import Path
import cobra


def calculate_file_hash(path: str | Path) -> str:
    path = Path(path)
    digest = hashlib.sha256()
    with path.open("rb") as model_file:
        for chunk in iter(lambda: model_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def load_sbml_model(path: str | Path) -> cobra.Model:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Model file not found: {path}")

    model = cobra.io.read_sbml_model(path)
    return model
