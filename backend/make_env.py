"""Creates backend/.env from .env.example (with a fresh random JWT secret) if it doesn't exist."""
import pathlib
import secrets

env, example = pathlib.Path(".env"), pathlib.Path(".env.example")
if env.exists():
    print(".env already exists, leaving it as it is.")
else:
    text = example.read_text(encoding="utf-8").replace("change-this-to-a-long-random-string", secrets.token_hex(32))
    env.write_text(text, encoding="utf-8")
    print(".env created with a new JWT secret.")
