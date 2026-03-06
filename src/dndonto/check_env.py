import os
import re
import shutil
import subprocess

import owlready2


def _parse_java_major(version_text: str) -> int | None:
    # Handles both legacy format ("1.8.0_...") and modern format ("11.0.22", "21")
    match = re.search(r'"([0-9]+)(?:\.([0-9]+))?', version_text)
    if not match:
        return None

    first = int(match.group(1))
    second = int(match.group(2)) if match.group(2) else None
    if first == 1 and second is not None:
        return second
    return first


def configure_java() -> str:
    # Prefer explicit setting if provided
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        java_exe = os.path.join(java_home, "bin", "java")
        if os.name == "nt":
            java_exe += ".exe"
        if os.path.exists(java_exe):
            owlready2.JAVA_EXE = java_exe

    # Otherwise fall back to PATH
    java_cmd = getattr(owlready2, "JAVA_EXE", None) or shutil.which("java")
    if not java_cmd:
        raise RuntimeError(
            "Java not found. Install Java 8+ and ensure `java` is on PATH, "
            "or set JAVA_HOME / owlready2.JAVA_EXE."
        )

    try:
        result = subprocess.run(
            [java_cmd, "-version"],
            capture_output=True,
            text=True,
            check=True,
        )
        version_text = result.stderr or result.stdout
    except Exception as exc:
        raise RuntimeError(f"Java found but could not be executed: {exc}") from exc

    major = _parse_java_major(version_text)
    if major is None:
        raise RuntimeError(
            "Could not determine Java version from `java -version` output. "
            "Ensure Java 8+ is installed and accessible."
        )
    if major < 8:
        raise RuntimeError(
            f"Java {major} detected. Java 8+ is required."
        )

    return version_text


if __name__ == "__main__":
    version_info = configure_java()
    print("Java version info:")
    print(version_info)