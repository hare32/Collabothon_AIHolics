import asyncio
from typing import Any, Optional

import httpx
import speech_recognition as sr
import pyttsx3

API = "http://127.0.0.1:8000/assistant/chat"
USER = "user-1"


def init_tts() -> Optional[pyttsx3.Engine]:
    try:
        engine = pyttsx3.init()
    except Exception as e:
        print(f"[WARN] Failed to initialize TTS: {e}")
        return None

    rate_obj = engine.getProperty("rate")
    if isinstance(rate_obj, (int, float)):
        rate = int(rate_obj)
        engine.setProperty("rate", rate - 20)
    return engine


async def send_to_backend(text: str) -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.post(API, json={"user_id": USER, "message": text})
        resp.raise_for_status()
        data = resp.json()
        print(f"Assistant ({data['intent']}): {data['reply']}\n")
        return data["reply"]


async def main() -> None:
    recognizer = sr.Recognizer()
    tts_engine = init_tts()

    print("Bank Assistant (VOICE). Say 'stop' or 'exit' to quit.\n")

    while True:
        # --- RECORDING VOICE ---
        try:
            with sr.Microphone() as source:
                print("Listening... (speak in English)")
                recognizer.adjust_for_ambient_noise(source, duration=1)
                audio = recognizer.listen(source)
        except OSError as e:
            print(
                "[ERROR] No default audio input device detected.\n"
                f"Details: {e}\n"
                "This is typical in WSL — microphone access is not supported.\n"
                "Run this client on a system with a microphone "
                "(e.g. native Windows/macOS/Linux) or use the web/file version."
            )
            return

        try:
            # --- STT: SPEECH → TEXT ---
            rec: Any = recognizer
            text = rec.recognize_google(audio, language="en-US")
            text = text.strip()
            print(f"You (recognized): {text}")
        except sr.UnknownValueError:
            print("I didn't understand, please repeat.\n")
            continue
        except sr.RequestError as e:
            print(f"Speech recognition service error: {e}")
            break

        if text.lower() in ["stop", "exit", "quit", "end"]:
            print("Ending the conversation.")
            break

        # --- SEND TO BACKEND ---
        reply = await send_to_backend(text)

        # --- TTS: TEXT → SPEECH (if available) ---
        if tts_engine is not None:
            tts_engine.say(reply)
            tts_engine.runAndWait()
        else:
            print("[INFO] TTS disabled (engine not available).")


if __name__ == "__main__":
    asyncio.run(main())
