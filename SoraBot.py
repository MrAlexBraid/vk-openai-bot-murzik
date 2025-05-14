import os
import time
import openai
import vk_api
from dotenv import load_dotenv
from vk_api.longpoll import VkLongPoll, VkEventType

# Загрузка токенов из .env
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")
vk_token = os.getenv("VK_API_TOKEN")
assistant_id = os.getenv("OPENAI_ASSISTANT_ID")

# Подключение к VK
vk_session = vk_api.VkApi(token=vk_token)
vk = vk_session.get_api()
longpoll = VkLongPoll(vk_session)

# Память по пользователям
user_last_message_time = {}
user_threads = {}  # 🧵 Сохраняем thread_id для каждого user_id
RESPONSE_COOLDOWN = 5  # секунд между ответами

def send_vk_message(user_id, text):
    vk.messages.send(
        user_id=user_id,
        message=text,
        random_id=int(time.time() * 1000000)
    )

print("🟢 Бот запущен и слушает ВКонтакте...")

# Основной цикл событий
for event in longpoll.listen():
    if event.type == VkEventType.MESSAGE_NEW and event.to_me:
        user_id = event.user_id
        user_msg = event.text.strip()
        now = time.time()
        last_time = user_last_message_time.get(user_id, 0)

        # ⏳ Антифлуд
        if now - last_time < RESPONSE_COOLDOWN:
            continue

        # ❌ Игнорируем мусор
        if len(user_msg) < 3 or all(c in ",.?!<>|\\/ " for c in user_msg):
            continue

        # ✅ Проверка имени
        if "мурзик" not in user_msg.lower():
            continue

        user_last_message_time[user_id] = now

        try:
            # 🧵 Создаём ветку, если ещё не создана
            if user_id not in user_threads:
                thread = openai.beta.threads.create()
                thread_id = thread.id
                user_threads[user_id] = thread_id
            else:
                thread_id = user_threads[user_id]

            # ✉️ Отправляем сообщение в диалог
            openai.beta.threads.messages.create(
                thread_id=thread_id,
                role="user",
                content=user_msg
            )

            # ▶️ Запускаем ассистента
            run = openai.beta.threads.runs.create(
                thread_id=thread_id,
                assistant_id=assistant_id
            )

            # ⏱ Ожидаем завершения
            while True:
                run_status = openai.beta.threads.runs.retrieve(
                    thread_id=thread_id,
                    run_id=run.id
                )
                if run_status.status == "completed":
                    break
                time.sleep(1)

            # 📩 Получаем ответ
            messages = openai.beta.threads.messages.list(thread_id=thread_id)
            reply = messages.data[0].content[0].text.value
            send_vk_message(user_id, reply)

        except Exception as e:
            send_vk_message(user_id, "Произошла ошибка. Попробуйте позже.")
            print(f"❌ Ошибка: {e}")
