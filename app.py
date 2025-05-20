import os
import time
from openai import OpenAI
import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType

client = OpenAI()
vk_token     = os.getenv("VK_API_TOKEN")
assistant_id = os.getenv("OPENAI_ASSISTANT_ID")
# ВПИШИ сюда VK ID Максима (например, 12345678)
MAXIM_ID     = 12345678

# Фразы, по которым звать Максима (дополняй по желанию)
PING_PHRASES = [
    "позови максима", "свяжись с максимом", "пусть напишет максим",
    "зови владельца", "мне нужен максим", "максим, ответь",
    "переведи на оператора", "живой человек", "консультант",
    "максим, напиши мне"
]

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

        # ——— Логика пинга Максима ———
        if any(phrase in user_msg.lower() for phrase in PING_PHRASES):
            send_vk_message(
                MAXIM_ID,
                f"Вас зовут в чате! User: vk.com/id174129176\n\nСообщение: {user_msg}"
            )
            send_vk_message(
                user_id,
                "Максиму отправлено уведомление, он скоро напишет Вам. Сессия завершена. Чтобы снова начать, напиши 'Мурзик'."
            )
            if user_id in active_users:
                del active_users[user_id]
            continue

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
                send_vk_message(user_id, "Мурзик активирован! Теперь отвечаю на Ваши сообщения. Чтобы завершить — напиши 'Стоп' или 'Пока'.")
            else:
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
