"""
StudySync AI: The Smart Study Buddy & Quiz Engine
--------------------------------------------------
A single-file FastAPI backend that:
  1. Persists users/quizzes/scores in a local SQLite DB (studysync.db)
  2. Serves a local quiz.html dashboard
  3. Streams AI-generated quiz content token-by-token via SSE (Server-Sent Events)
  4. Persists the completed quiz text to SQLite once streaming finishes
"""

import os
import sqlite3
import asyncio
import logging
from contextlib import closing

from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse
from openai import AsyncOpenAI

# --------------------------------------------------------------------------
# ENVIRONMENT & LOGGING SETUP
# --------------------------------------------------------------------------
# Load secrets from a local, gitignored .env file -- never hardcode keys.
load_dotenv()

# -----------------------------------------------------------------------------
# ENVIRONMENT & LOGGING SETUP
# -----------------------------------------------------------------------------
# Read the key from the environment (populated by load_dotenv() from quiz.env
# / .env above). Never hardcode real credentials in source.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("studysync")

if not OPENAI_API_KEY:
    logger.warning(
        "OPENAI_API_KEY is not set. Add it to your .env file, e.g.:\n"
        "OPENAI_API_KEY=sk-...\n"
        "Quiz generation will fail until this is set."
    )

DB_PATH = "studysync.db"

client = AsyncOpenAI(api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = (
    "You are an StudySync AI , AN expert academic tutor and quiz builder. Based on the concept or "
    "topic provided by the student, generate a structured practice quiz consisting "
    "of exactly 2 Multiple Choice Questions (MCQs). Provide clear choices (A, B, C, D). "
    "Do not provide the answers immediately. Instead, format them neatly so the "
    "student can test themselves."
)

# --------------------------------------------------------------------------
# EMBEDDED SQL DATA LAYER (SQLite)
# --------------------------------------------------------------------------
def init_db() -> None:
    """
    Initializes the local SQLite database and creates the three core tables
    (users, quizzes, scores) if they do not already exist. Called once at
    application startup.
    """
    with closing(sqlite3.connect(DB_PATH)) as conn:
        with conn:  # auto-commits / rolls back this block
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT,
                    email TEXT UNIQUE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS quizzes (
                    quiz_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    topic_name TEXT,
                    generated_quiz_text TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS scores (
                    score_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    quiz_id INTEGER,
                    total_questions INTEGER,
                    correct_answers INTEGER
                )
                """
            )
            # Ensure a default user (user_id = 1) exists, since streamed
            # quizzes are attributed to this default user in this single-user
            # local build. INSERT OR IGNORE keeps this idempotent.
            conn.execute(
                """
                INSERT OR IGNORE INTO users (user_id, username, email)
                VALUES (1, 'default_student', 'student@studysync.local')
                """
            )
    logger.info("SQLite database initialized at %s", DB_PATH)


async def save_quiz_to_db(topic: str, complete_text: str) -> None:
    """
    Persists a fully-generated quiz to the `quizzes` table once the SSE
    stream has finished accumulating all tokens. Runs the blocking sqlite3
    call in a background thread via asyncio.to_thread so it never blocks
    the event loop, and always closes the connection via `closing()`.
    """
    def _write():
        # `closing()` guarantees conn.close() runs even if commit() raises,
        # and the `with conn:` block wraps the INSERT in a transaction that
        # auto-commits on success or rolls back on exception.
        with closing(sqlite3.connect(DB_PATH)) as conn:
            with conn:
                conn.execute(
                    """
                    INSERT INTO quizzes (user_id, topic_name, generated_quiz_text)
                    VALUES (?, ?, ?)
                    """,
                    (1, topic, complete_text),  # default user_id = 1
                )

    try:
        await asyncio.to_thread(_write)
        logger.info("Quiz on topic '%s' saved to database.", topic)
    except sqlite3.Error as db_err:
        # DB failures shouldn't crash the stream -- just log them.
        logger.error("Failed to save quiz to DB: %s", db_err)


# --------------------------------------------------------------------------
# FASTAPI APP INSTANCE
# --------------------------------------------------------------------------
app = FastAPI(title="StudySync AI: The Smart Study Buddy & Quiz Engine")


@app.on_event("startup")
async def on_startup():
    """Ensure the database schema exists before the app starts accepting traffic."""
    init_db()


# --------------------------------------------------------------------------
# ROUTE: Serve local dashboard
# --------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
@app.get("/quiz.html", response_class=HTMLResponse)
async def serve_dashboard() -> HTMLResponse:
    """
    Reads quiz.html from disk and returns it as raw HTML. Standard
    synchronous file I/O is used here since it's a small, local static file
    read once per request.
    """
    try:
        with open("quiz.html", "r", encoding="utf-8") as f:
            html_content = f.read()
    except FileNotFoundError:
        html_content = (
            "<h1>StudySync AI</h1>"
            "<p>quiz.html not found on server. Please add a dashboard file.</p>"
            "</body></html>"
        )
        logger.warning("quiz.html not found in working directory.")
    return HTMLResponse(content=html_content, status_code=200)


# --------------------------------------------------------------------------
# ROUTES: Serve static assets referenced by quiz.html
# --------------------------------------------------------------------------
# quiz.html requests these as plain relative URLs (quiz.css, quiz.js), so
# FastAPI needs matching routes for them -- otherwise the browser gets a 404
# for both and the page renders with no styling and no interactivity.
@app.get("/quiz.css")
async def serve_css() -> FileResponse:
    return FileResponse("quiz.css", media_type="text/css")


@app.get("/quiz.js")
async def serve_js() -> FileResponse:
    return FileResponse("quiz.js", media_type="application/javascript")


# --------------------------------------------------------------------------
# ROUTE: Streaming quiz generation (SSE)
# --------------------------------------------------------------------------
@app.get("/api/quiz")
async def get_quiz_stream(topic: str = Query(..., description="Topic or concept to quiz on")):
    """
    Kicks off a Server-Sent Events stream. Each SSE 'data:' line carries a
    progressive chunk of the LLM's response as it's generated, giving the
    browser a live "typing" effect. Once the full quiz text has been
    accumulated, it is persisted to the `quizzes` table via save_quiz_to_db().
    """

    async def event_generator():
        accumulated_text = ""  # Buffer that mirrors what the browser has received so far

        try:
            # Open a streaming chat completion against gpt-4o-mini.
            stream = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Topic: {topic}"},
                ],
                stream=True,
            )

            async for chunk in stream:
                # Each chunk may or may not carry new text content.
                delta = chunk.choices[0].delta if chunk.choices else None
                token_text = getattr(delta, "content", None) if delta else None

                if token_text:
                    accumulated_text += token_text
                    # SSE wire format: "data: <payload>\n\n"
                    # Newlines inside token_text are escaped so they don't
                    # break the SSE frame boundary.
                    safe_token = token_text.replace("\n", "\\n")
                    yield f"data: {safe_token}\n\n"

            # Stream finished successfully -- persist the full quiz text.
            await save_quiz_to_db(topic, accumulated_text)

            # Signal completion to the client so the frontend can stop
            # listening / update UI state.
            yield "data: [DONE]\n\n"

        except Exception as exc:
            # Never let a broken API call or dropped connection crash the
            # server -- pipe a readable error token down the same channel.
            logger.error("Streaming error for topic '%s': %s", topic, exc)
            error_message = f"[ERROR] Quiz generation failed: {str(exc)}"
            yield f"data: {error_message}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Prevents proxies (e.g. nginx) from buffering the SSE stream.
            "X-Accel-Buffering": "no",
        },
    )


# --------------------------------------------------------------------------
# LOCAL DEV ENTRYPOINT
# --------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("quiz:app", host="0.0.0.0", port=8000, reload=True)