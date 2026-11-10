import os

from app import create_app


app = create_app()


def run_server() -> None:
    app.run(
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "5000")),
        debug=False,
    )


if __name__ == "__main__":
    run_server()
