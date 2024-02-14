from __future__ import annotations

import string

from flask import Flask, request, jsonify
import requests
import os
from openai import OpenAI

app = Flask(__name__)

SLACK_BOT_TOKEN = os.environ.get('SLACK_TRANS_BOT_TOKEN')
TRANSLATE_API_KEY = os.environ.get('OPENAI_TOKEN')


def is_english(text):
    # 简单的检查方法：如果大部分字符都是 ASCII，就假定文本是英文
    ascii_chars = set(string.printable)
    non_ascii_chars = [char for char in text if char not in ascii_chars]
    return len(non_ascii_chars) / len(text) < 0.1  # 可以调整阈值


def translate_to_english(origin_text: str) -> str | None:
    # 使用翻译API将文本翻译成英文
    # 这里需要根据你使用的翻译服务API来实现
    if is_english(origin_text):
        return None

    try:
        client = OpenAI(
            # This is the default and can be omitted
            api_key=TRANSLATE_API_KEY,
        )
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",  # 使用 GPT-3.5 的最新模型
            messages=[{"role": "user", "content": f"Translate the following text to English:\n\n{origin_text}\n\n"}],  # 设置翻译提示
            max_tokens=2000,  # 根据需要调整最大令牌数
            temperature=0,
        )
        translated_text = response.choices[0].message.content.strip()
        return translated_text
    except Exception as e:
        print(f"An error occurred: {e}")
        return None


def get_user_name(user_id: str) -> str:
    url = 'https://slack.com/api/users.profile.get'
    headers = {'Authorization': f'Bearer {SLACK_BOT_TOKEN}'}
    params = {
        'user': user_id,
    }
    response = requests.get(url, headers=headers, params=params)
    if app.debug:
        print(response.json())
    return response.json()['display_name']


@app.route('/events', methods=['POST'])
def slack_events():
    json_data = request.json
    if app.debug:
        print(json_data)

    if 'challenge' in json_data:
        return jsonify({'challenge': json_data['challenge']})

    if json_data['event']['type'] == 'message' and 'subtype' not in json_data['event']:
        text = json_data['event']['text']
        translated_text = translate_to_english(text)
        if translated_text is None:
            return 'No translation', 200

        user_name = get_user_name(json_data['event']['user'])
        # 发送翻译后的文本到 Slack
        url = 'https://slack.com/api/chat.postMessage'
        headers = {'Authorization': f'Bearer {SLACK_BOT_TOKEN}'}
        data = {
            'channel': json_data['event']['channel'],
            'text': user_name + ' said: ' + translated_text
        }
        requests.post(url, headers=headers, data=data)

    return '', 200


if __name__ == '__main__':
    app.run(debug=True, port=5002)
