"""Print the OpenAPI schema as JSON. Used by the frontend's `npm run gen:api`."""

import json
import sys

from app.main import create_app


def main() -> None:
    json.dump(create_app().openapi(), sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
