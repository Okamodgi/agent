import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
import random
import requests

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

TOKEN = ""
GROUP_ID = 240098258  
OPENROUTER_KEY = ""
SYSTEM_PROMPT = """Ты — мой напарник-детектив в реалистичном расследовании. Мы работаем вместе: я принимаю все решения, а ты раскрываешь мир вокруг меня, как будто мы реально стоим на месте преступления.
    Правила:
            - ответы должны быть котороткие, будто мы ведём диалог
            - Никогда не предлагай варианты действий, не делай нумерованные списки и не пиши «вы можете…». Пусть я сама решу, что делать.
            - На каждое моё действие отвечай как живой человек: короткими, ёмкими абзацами. Используй детали через 5 чувств: звуки, запахи, холод металла, капли дождя, скрип половиц.
            - Если я делаю что-то нестандартное — не блокируй и не говори «это невозможно». Наоборот, органично впиши это в сцену и покажи последствия.
            - Держи напряжение: иногда улики ведут в тупик, иногда свидетели врут, иногда ничего не происходит — это тоже часть работы детектива.
            - Не раскрывай развязку и не делай сюжетных выводов за меня. Не говори «это явно сделал он» или «вот ключ к разгадке».
            - Тон: реалистичный, без штампов про «злодей хохочет в темноте». Пусть всё выглядит как обычная, но напряжённая работа сыщика.
            - В конце ответа не давай никаких выводов, итогов или подталкиваний к действию. Просто оставь сцену «висящей» — чтобы я сама решила, куда идти дальше.

            Сейчас мы начинаем: дождливая ночь, старый дом, в руке у меня папка с делом, страницы чуть размокли от дождя. Ты стоишь рядом, воротник поднят, в глазах — усталость и внимание к деталям. Расскажи, что видишь прямо сейчас, без вариантов действий.
"""
MODEL = "openrouter/free" 

vk_session = vk_api.VkApi(token=TOKEN)
longpoll = VkBotLongPoll(vk_session, group_id=GROUP_ID)
vk = vk_session.get_api()

chat_history = {}
state = {}

MAX_VK_MESSAGE_LENGTH = 4000

def send_message(peer_id, text):
    if not text:
        return
    if len(text) <= MAX_VK_MESSAGE_LENGTH:
        vk.messages.send(
            peer_id=peer_id,
            message=text,
            random_id=random.randint(1, 2**31 - 1)
        )
        return
    for i in range(0, len(text), MAX_VK_MESSAGE_LENGTH):
        chunk = text[i:i + MAX_VK_MESSAGE_LENGTH]
        vk.messages.send(
            peer_id=peer_id,
            message=chunk,
            random_id=random.randint(1, 2**31 - 1)
        )


def ask_ai(peer_id, user_text):
    history = chat_history.setdefault(peer_id, [])
    history.append({"role": "user", "content": user_text})

    try:
        response = requests.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {OPENROUTER_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    *history],},
            timeout=60
        )
        data = response.json()
    except requests.RequestException as e:
        history.pop()
        return f"Ошибка соединения: {e}"

    if response.status_code != 200 or "choices" not in data or len(data["choices"]) == 0:
        history.pop()
        error_msg = data.get("error", {})
        if isinstance(error_msg, dict):
            msg = error_msg.get("message", "ошибка")
        else:
            msg = str(error_msg) if error_msg else "ошибка"
        return f"ошибка: {msg}"

    try:
        answer = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        history.pop()
        return "ошибка при разборе ответа от ИИ"

    if not answer:
        history.pop()
        return "пустой ответ от ИИ"

    history.append({"role": "assistant", "content": answer})
    if len(history) > 10:
        chat_history[peer_id] = history[-10:]

    return answer

def reset_dialog(peer_id):
    chat_history.pop(peer_id, None)
    state.pop(peer_id, None)

print("Бот запущен. Ожидаю сообщения...")

for event in longpoll.listen():
    if event.type == VkBotEventType.MESSAGE_NEW:
        msg = event.object.message
        peer_id = msg["peer_id"]
        text = msg["text"].strip()

        if not text:
            continue

        if text.lower().startswith("/reset"):
            reset_dialog(peer_id)
            send_message(peer_id, "Диалог сброшен.")
            continue

        answer = ask_ai(peer_id, text)
        send_message(peer_id, answer)
