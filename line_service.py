import requests

from config import LINE_CHANNEL_ACCESS_TOKEN, DIFY_API_KEY, DIFY_BASE_URL


def push_line_text(to_id, text):
    url = "https://api.line.me/v2/bot/message/push"

    headers = {
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "to": to_id,
        "messages": [
            {
                "type": "text",
                "text": text[:5000]
            }
        ]
    }

    r = requests.post(url, headers=headers, json=payload, timeout=15)
    print("LINE push status:", r.status_code, r.text)
    return r


def push_line_text_and_image(to_id, text, image_url=None):
    url = "https://api.line.me/v2/bot/message/push"

    headers = {
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    messages = []

    if text:
        messages.append({
            "type": "text",
            "text": text[:5000]
        })

    if image_url:
        messages.append({
            "type": "image",
            "originalContentUrl": image_url,
            "previewImageUrl": image_url
        })

    if not messages:
        messages.append({
            "type": "text",
            "text": "查詢完成。"
        })

    payload = {
        "to": to_id,
        "messages": messages
    }

    r = requests.post(url, headers=headers, json=payload, timeout=15)
    print("LINE push text/image status:", r.status_code, r.text)
    return r


def reply_line_text(reply_token, text):
    url = "https://api.line.me/v2/bot/message/reply"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }

    body = {
        "replyToken": reply_token,
        "messages": [
            {
                "type": "text",
                "text": text[:5000] if text else "處理中..."
            }
        ]
    }

    r = requests.post(url, headers=headers, json=body, timeout=15)
    print("LINE reply:", r.status_code, r.text)
    return r


def reply_line_text_and_image(reply_token, text, image_url=None):
    url = "https://api.line.me/v2/bot/message/reply"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }

    messages = [
        {
            "type": "text",
            "text": text[:5000] if text else "查詢完成。"
        }
    ]

    if image_url:
        messages.append({
            "type": "image",
            "originalContentUrl": image_url,
            "previewImageUrl": image_url
        })

    body = {
        "replyToken": reply_token,
        "messages": messages
    }

    r = requests.post(url, headers=headers, json=body, timeout=15)
    print("LINE reply:", r.status_code, r.text)
    return r


def call_dify(user_text, user_id="line-user"):
    url = f"{DIFY_BASE_URL}/chat-messages"

    headers = {
        "Authorization": f"Bearer {DIFY_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "inputs": {},
        "query": user_text,
        "response_mode": "blocking",
        "conversation_id": "",
        "user": user_id
    }

    r = requests.post(url, headers=headers, json=payload, timeout=180)
    print("Dify status:", r.status_code, r.text[:500])
    r.raise_for_status()

    data = r.json()
    return data.get("answer") or data.get("message") or str(data)


def clean_line_text(text):
    if not text:
        return ""
    return text.strip()


def should_reply(event):
    source = event.get("source", {})
    message = event.get("message", {})
    text = message.get("text", "")

    if source.get("type") == "user":
        return True, text

    mention = message.get("mention", {})
    if mention and mention.get("mentionees"):
        return True, text

    return False, text


def remove_mention(text, event):
    message = event.get("message", {})

    if "mention" not in message:
        return text

    mention = message.get("mention", {})
    indices = []

    for m in mention.get("mentionees", []):
        start = m.get("index", 0)
        end = start + m.get("length", 0)
        indices.append((start, end))

    for start, end in sorted(indices, reverse=True):
        text = text[:start] + text[end:]

    return text.strip()
