from pathlib import Path
import cobra

def load_sbml_model(path: str) -> cobra.Model:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Model file not found: {path}")

    model = cobra.io.read_sbml_model(path)
    return model
