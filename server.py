#!/usr/bin/env python3

import json
import os
import urllib.request
import urllib.error
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# ============================================================
# SEWUA V2500 SERVER
# Pydroid 3 / Android
# ============================================================

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


# ============================================================
# LOAD .ENV FILE
# ============================================================

def load_env_file():
    env_file = ROOT / ".env"

    if not env_file.exists():
        return

    try:
        lines = env_file.read_text(encoding="utf-8").splitlines()

        for line in lines:
            line = line.strip()

            # Ignore empty lines and comments
            if not line or line.startswith("#"):
                continue

            if "=" not in line:
                continue

            key, value = line.split("=", 1)

            key = key.strip()
            value = value.strip()

            # Remove optional quotes
            if (
                len(value) >= 2
                and value[0] == value[-1]
                and value[0] in ('"', "'")
            ):
                value = value[1:-1]

            os.environ.setdefault(key, value)

    except Exception as e:
        print("Warning: Could not load .env:", e)


load_env_file()


# ============================================================
# MAKE SURE DATA FOLDER EXISTS
# ============================================================

DATA.mkdir(parents=True, exist_ok=True)


# ============================================================
# JSON DATABASE FUNCTIONS
# ============================================================

def read(name, default):
    p = DATA / name

    try:
        if not p.exists():
            return default

        return json.loads(
            p.read_text(encoding="utf-8")
        )

    except Exception:
        return default


def write(name, obj):
    p = DATA / name

    try:
        p.write_text(
            json.dumps(
                obj,
                ensure_ascii=False,
                indent=2
            ),
            encoding="utf-8"
        )

    except Exception as e:
        print(f"Database write error ({name}):", e)


# ============================================================
# HTTP HANDLER
# ============================================================

class Handler(SimpleHTTPRequestHandler):

    # --------------------------------------------------------
    # API PATH
    # --------------------------------------------------------

    def translate_path(self, path):

        if path.startswith("/api/"):
            return str(ROOT / "__api__")

        return super().translate_path(path)


    # --------------------------------------------------------
    # JSON RESPONSE
    # --------------------------------------------------------

    def send_json(self, obj, status=200):

        raw = json.dumps(
            obj,
            ensure_ascii=False
        ).encode("utf-8")

        self.send_response(status)

        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8"
        )

        self.send_header(
            "Content-Length",
            str(len(raw))
        )

        self.send_header(
            "Access-Control-Allow-Origin",
            "*"
        )

        self.end_headers()

        self.wfile.write(raw)


    # --------------------------------------------------------
    # GET REQUESTS
    # --------------------------------------------------------

    def do_GET(self):

        # Courses
        if self.path == "/api/courses":
            return self.send_json({
                "courses": read(
                    "courses.json",
                    {}
                )
            })


        # Quizzes
        if self.path == "/api/quizzes":
            return self.send_json({
                "quizzes": read(
                    "quizzes.json",
                    {}
                )
            })


        # Announcements
        if self.path == "/api/announcements":
            return self.send_json({
                "announcements": read(
                    "announcements.json",
                    []
                )
            })


        # Server status
        if self.path == "/api/status":
            return self.send_json({
                "ok": True,
                "app": "SEWUA V2500",
                "ai_configured": bool(
                    os.getenv(
                        "GEMINI_API_KEY",
                        ""
                    ).strip()
                )
            })


        return super().do_GET()


    # --------------------------------------------------------
    # POST REQUESTS
    # --------------------------------------------------------

    def do_POST(self):

        if not self.path.startswith("/api/"):
            return self.send_error(404)


        # Read request body
        try:
            n = int(
                self.headers.get(
                    "Content-Length",
                    "0"
                )
            )

        except ValueError:
            n = 0


        body = (
            self.rfile.read(n)
            if n
            else b"{}"
        )


        # Parse JSON
        try:
            data = json.loads(
                body or b"{}"
            )

        except Exception:
            return self.send_json(
                {
                    "error": "Invalid JSON"
                },
                400
            )


        # Activity
        if self.path == "/api/activity":

            arr = read(
                "activity.json",
                []
            )

            arr.append(data)

            write(
                "activity.json",
                arr[-500:]
            )

            return self.send_json({
                "ok": True
            })


        # AI
        if self.path == "/api/ai":
            return self.ai(data)


        return self.send_json(
            {
                "error": "Unknown endpoint"
            },
            404
        )


    # ========================================================
    # GEMINI AI
    # ========================================================

    def ai(self, data):

        # Get API key from .env
        key = os.getenv(
            "GEMINI_API_KEY",
            ""
        ).strip()


        # No API key
        if not key:

            return self.send_json(
                {
                    "error":
                    "GEMINI_API_KEY is not configured. "
                    "Create a .env file beside server.py."
                },
                503
            )


        # Gemini model
        model = os.getenv(
            "GEMINI_MODEL",
            "gemini-2.5-flash"
        ).strip()


        # User message
        msg = str(
            data.get(
                "message",
                ""
            )
        ).strip()


        # Empty message
        if not msg:

            return self.send_json(
                {
                    "error":
                    "Message is required"
                },
                400
            )


        # AI instruction
        prompt = (
            "You are SEWUA V2500, an educational "
            "assistant for technical students. "
            "Give accurate, clear, safe and useful "
            "answers. Explain technical subjects "
            "in a way that students can understand.\n\n"
            "User question:\n"
            + msg
        )


        # Gemini API URL
        url = (
            "https://generativelanguage.googleapis.com/"
            "v1beta/models/"
            + model
            + ":generateContent?key="
            + key
        )


        # Gemini request
        payload = json.dumps({
            "contents": [
                {
                    "parts": [
                        {
                            "text": prompt
                        }
                    ]
                }
            ]
        }).encode("utf-8")


        request = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type":
                "application/json"
            },
            method="POST"
        )


        # Send request
        try:

            with urllib.request.urlopen(
                request,
                timeout=45
            ) as response:

                result = json.loads(
                    response.read()
                )


            # Check candidates
            candidates = result.get(
                "candidates",
                []
            )

            if not candidates:

                return self.send_json(
                    {
                        "error":
                        "Gemini returned no response."
                    },
                    502
                )


            content = candidates[0].get(
                "content",
                {}
            )

            parts = content.get(
                "parts",
                []
            )


            if not parts:

                return self.send_json(
                    {
                        "error":
                        "Gemini returned an empty response."
                    },
                    502
                )


            reply = parts[0].get(
                "text",
                ""
            ).strip()


            if not reply:

                return self.send_json(
                    {
                        "error":
                        "Gemini returned empty text."
                    },
                    502
                )


            return self.send_json({
                "reply": reply
            })


        # Gemini HTTP error
        except urllib.error.HTTPError as e:

            try:
                error_body = e.read().decode(
                    "utf-8",
                    errors="replace"
                )

                print(
                    "Gemini HTTP error:",
                    e.code,
                    error_body
                )

            except Exception:
                error_body = ""


            return self.send_json(
                {
                    "error":
                    "Gemini API error "
                    + str(e.code),
                    "details":
                    error_body
                },
                502
            )


        # Internet / connection error
        except urllib.error.URLError as e:

            print(
                "Internet connection error:",
                e
            )

            return self.send_json(
                {
                    "error":
                    "Could not connect to Gemini. "
                    "Check your internet connection."
                },
                502
            )


        # Other error
        except Exception as e:

            print(
                "AI error:",
                repr(e)
            )

            return self.send_json(
                {
                    "error":
                    "AI request failed: "
                    + str(e)
                },
                502
            )


# ============================================================
# START SERVER
# ============================================================

if __name__ == "__main__":

    os.chdir(ROOT)

    host = "0.0.0.0"
    port = 8080

    print("")
    print("========================================")
    print("        SEWUA V2500 SERVER")
    print("========================================")
    print("")
    print("Folder:", ROOT)
    print("Gemini:", "CONFIGURED"
          if os.getenv("GEMINI_API_KEY", "").strip()
          else "NOT CONFIGURED")
    print("")
    print(
        "Open in browser:"
    )
    print(
        "http://127.0.0.1:8080"
    )
    print("")
    print("Server is running...")
    print("========================================")
    print("")


    server = ThreadingHTTPServer(
        (host, port),
        Handler
    )


    try:
        server.serve_forever()

    except KeyboardInterrupt:

        print("\nSEWUA server stopped.")

        server.server_close()
