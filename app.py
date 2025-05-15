import os
import time
from openai import OpenAI          # ✅ новый клиент
import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType

# 🔐 Ключи и ID ассистента берём из переменных окружения Railway
client       = OpenAI()                            # OPENAI_API_KEY читается из env
vk_token     = os.getenv("VK_API_TOKEN")
assistant_id = os.getenv("OPENAI_ASSISTANT_ID")

if not vk_token or not assistant_id:
    raise ValueError("❌ Нет VK_API_TOKEN или OPENAI_ASSISTANT_ID в переменных Railway")

# 🤖 VK + long-poll
vk_session = vk_api.VkApi(token=vk_token)
vk         = vk_session.get_api()
longpoll   = VkLongPoll(vk_session)

# ⚙️ антифлуд и кэш тредов
user_last_message_time = {}
user_threads           = {}
RESPONSE_COOLDOWN      = 5  # секунд

def send_vk_message(user_id: int, text: str):
    vk.messages.send(user_id=user_id,
                     message=text,
                     random_id=int(time.time() * 1_000_000))

print("🟢 Мурзик запущен и слушает ВКонтакте…")

# 🔁 основной цикл
for event in longpoll.listen():
    if event.type == VkEventType.MESSAGE_NEW and event.to_me:
        user_id  = event.user_id
        user_msg = event.text.strip()

        if len(user_msg) < 3 or "мурзик" not in user_msg.lower():
            continue

        now, last = time.time(), user_last_message_time.get(user_id, 0)
        if now - last < RESPONSE_COOLDOWN:
            continue
        user_last_message_time[user_id] = now

        try:
            # 🧵 один thread на пользователя
            thread_id = user_threads.setdefault(
                user_id, client.beta.threads.create().id
            )

            client.beta.threads.messages.create(
                thread_id=thread_id, role="user", content=user_msg
            )

            run = client.beta.threads.runs.create(
                thread_id=thread_id, assistant_id=assistant_id
            )

            # ⏳ ждём завершение
            while client.beta.threads.runs.retrieve(
                thread_id=thread_id, run_id=run.id
            ).status != "completed":
                time.sleep(1)

            reply = client.beta.threads.messages.list(
                thread_id=thread_id
            ).data[0].content[0].text.value

            send_vk_message(user_id, reply)

        except Exception as e:
            send_vk_message(user_id, "Произошла ошибка. Попробуйте позже.")
            print("❌ Ошибка:", e)
