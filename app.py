import os
import time
from openai import OpenAI
import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType

client = OpenAI()
vk_token     = os.getenv("VK_API_TOKEN")
assistant_id = os.getenv("OPENAI_ASSISTANT_ID")

if not vk_token or not assistant_id:
    raise ValueError("❌ Нет VK_API_TOKEN или OPENAI_ASSISTANT_ID в переменных Railway")

vk_session = vk_api.VkApi(token=vk_token)
vk         = vk_session.get_api()
longpoll   = VkLongPoll(vk_session)

user_last_message_time = {}
user_threads           = {}
active_users           = {}    # user_id: last_active_time
RESPONSE_COOLDOWN      = 5  # секунд
SESSION_TIMEOUT        = 30 * 60  # 30 минут

def send_vk_message(user_id: int, text: str):
    vk.messages.send(user_id=user_id,
                     message=text,
                     random_id=int(time.time() * 1_000_000))

def is_active(user_id):
    # Если активен и не истёк timeout
    if user_id in active_users:
        if time.time() - active_users[user_id] < SESSION_TIMEOUT:
            return True
        else:
            del active_users[user_id]
    return False

print("🟢 Мурзик запущен и слушает ВКонтакте…")

for event in longpoll.listen():
    if event.type == VkEventType.MESSAGE_NEW and event.to_me:
        user_id  = event.user_id
        user_msg = event.text.strip()

        now, last = time.time(), user_last_message_time.get(user_id, 0)
        if now - last < RESPONSE_COOLDOWN:
            continue
        user_last_message_time[user_id] = now

        # ——— Логика активации ———
        if is_active(user_id):
            # “СТОП” завершает сессию
            if user_msg.lower() in ["стоп", "пока", "отключиться"]:
                del active_users[user_id]
                send_vk_message(user_id, "Сессия завершена. Чтобы снова начать, напиши 'Мурзик'.")
                continue
            else:
                active_users[user_id] = now  # обновляем время активности
        else:
            if "мурзик" in user_msg.lower():
                active_users[user_id] = now
                send_vk_message(user_id, "Мурзик активирован! Теперь отвечаю на любые сообщения. Чтобы завершить — напиши 'Стоп' или 'Пока'.")
            else:
                # Если не активен и не написал ключевое слово — не реагируем
                continue

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
