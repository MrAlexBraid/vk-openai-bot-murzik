import os
import time
import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType
from openai import OpenAI          # ⬅️ новый клиент-объект

# ────────────────────
# 🔐 переменные среды
# ────────────────────
client       = OpenAI()            # ключ берётся из OPENAI_API_KEY
vk_token     = os.getenv("VK_API_TOKEN")
assistant_id = os.getenv("OPENAI_ASSISTANT_ID")

if not (vk_token and assistant_id and client.api_key):
    raise ValueError("❌ Нет переменных окружения (VK_API_TOKEN / OPENAI_*).")

# ────────────────────
# 🤖 VK
# ────────────────────
vk_session = vk_api.VkApi(token=vk_token)
vk         = vk_session.get_api()
longpoll   = VkLongPoll(vk_session)

# антифлуд и память тредов
user_last_message_time: dict[int, float] = {}
user_threads: dict[int, str] = {}
RESPONSE_COOLDOWN = 5            # сек

def send_vk_message(uid: int, text: str) -> None:
    vk.messages.send(user_id=uid, message=text,
                     random_id=int(time.time() * 1e6))

print("🟢 Мурзик запущен и слушает ВКонтакте…")

# ────────────────────
# 🔁 цикл longpoll
# ────────────────────
for event in longpoll.listen():
    if event.type == VkEventType.MESSAGE_NEW and event.to_me:
        uid      = event.user_id
        msg      = event.text.strip()
        now      = time.time()
        last     = user_last_message_time.get(uid, 0)

        if now - last < RESPONSE_COOLDOWN:
            continue
        if len(msg) < 3 or all(c in ",.?!<>|\\/ " for c in msg):
            continue
        if "мурзик" not in msg.lower():
            continue

        user_last_message_time[uid] = now

        try:
            # ─── создаём / берём thread ─────────────────────────────
            thread_id = user_threads.get(uid)
            if not thread_id:
                thread = client.beta.threads.create()
                thread_id = thread.id
                user_threads[uid] = thread_id

            # ─── отправляем сообщение пользователя ─────────────────
            client.beta.threads.messages.create(
                thread_id=thread_id,
                role="user",
                content=msg
            )

            # ─── запускаем ассистента ───────────────────────────────
            run = client.beta.threads.runs.create(
                thread_id=thread_id,
                assistant_id=assistant_id
            )

            # ─── ждём завершения ────────────────────────────────────
            while True:
                run_status = client.beta.threads.runs.retrieve(
                    thread_id=thread_id, run_id=run.id
                )
                if run_status.status == "completed":
                    break
                time.sleep(1)

            # ─── получаем ответ ─────────────────────────────────────
            messages = client.beta.threads.messages.list(thread_id=thread_id)
            reply    = messages.data[0].content[0].text.value
            send_vk_message(uid, reply)

        except Exception as e:
            send_vk_message(uid, "Произошла ошибка. Попробуйте позже.")
            print("❌ Ошибка:", e)
