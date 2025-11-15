import httpx
import asyncio

API = "http://127.0.0.1:8000/assistant/chat"
USER = "user-1"


async def main():
    print("Banking assistant (CLI). Type 'exit' to quit.\n")

    async with httpx.AsyncClient() as client:
        while True:
            msg = input("You: ")
            if msg.lower() == "exit":
                break

            resp = await client.post(API, json={"user_id": USER, "message": msg})
            data = resp.json()

            print(f"Assistant ({data['intent']}): {data['reply']}\n")


if __name__ == "__main__":
    asyncio.run(main())
