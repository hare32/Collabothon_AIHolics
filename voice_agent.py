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
        print(f"[WARN] Nie udało się zainicjować TTS: {e}")
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
        print(f"Asystent ({data['intent']}): {data['reply']}\n")
        return data["reply"]


async def main() -> None:
    recognizer = sr.Recognizer()
    tts_engine = init_tts()

    print("Asystent bankowy (VOICE). Powiedz 'koniec' żeby zakończyć.\n")

    while True:
        # --- NAGRYWANIE GŁOSU ---
        try:
            with sr.Microphone() as source:
                print("Nasłuchuję... (mów po polsku)")
                recognizer.adjust_for_ambient_noise(source, duration=1)
                audio = recognizer.listen(source)
        except OSError as e:
            print(
                "[ERROR] Brak domyślnego urządzenia wejściowego audio w tym środowisku.\n"
                f"Szczegóły: {e}\n"
                "To typowe w WSL – nie ma dostępu do mikrofonu.\n"
                "Uruchom tego klienta na systemie z mikrofonem (np. natywny Linux/Windows) "
                "albo użyj wersji plikowej/webowej."
            )
            return

        try:
            # --- STT: MOWA -> TEKST ---
            rec: Any = recognizer
            text = rec.recognize_google(audio, language="pl-PL")
            text = text.strip()
            print(f"Ty (rozpoznane): {text}")
        except sr.UnknownValueError:
            print("Nie zrozumiałem, powtórz proszę.\n")
            continue
        except sr.RequestError as e:
            print(f"Błąd usługi rozpoznawania mowy: {e}")
            break

        if text.lower() in ["koniec", "exit", "zakończ", "stop"]:
            print("Kończę rozmowę.")
            break

        # --- WYŚLIJ DO BACKENDU ---
        reply = await send_to_backend(text)

        # --- TTS: TEKST -> MOWA (jeśli działa) ---
        if tts_engine is not None:
            tts_engine.say(reply)
            tts_engine.runAndWait()
        else:
            print("[INFO] TTS wyłączony (brak silnika).")


if __name__ == "__main__":
    asyncio.run(main())
