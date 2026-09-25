import os

import uvicorn

from eidolon.app import create_app
from eidolon.config import Settings


def main() -> None:
    uvicorn.run(
        create_app(Settings.from_env()),
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "8000")),
    )


if __name__ == "__main__":
    main()
