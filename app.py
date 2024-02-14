from __future__ import annotations

import string

from flask import Flask, request, jsonify
import requests
import os
from openai import OpenAI
from functools import lru_cache


app = Flask(__name__)

SLACK_BOT_TOKEN = os.environ.get('SLACK_TRANS_BOT_TOKEN')
TRANSLATE_API_KEY = os.environ.get('OPENAI_TOKEN')
ASCII_CHARS = set(string.printable)


def is_english(text):
    # 简单的检查方法：如果大部分字符都是 ASCII，就假定文本是英文
    non_ascii_chars_in_text = [char for char in text if char not in ASCII_CHARS]
    return len(non_ascii_chars_in_text) / len(text) < 0.1  # 可以调整阈值


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


@lru_cache
def get_user_name(user_id: str) -> str:
    url = 'https://slack.com/api/users.profile.get'
    headers = {'Authorization': f'Bearer {SLACK_BOT_TOKEN}'}
    params = {
        'user': user_id,
    }
    response = requests.get(url, headers=headers, params=params)
    response_data = response.json()
    if app.debug:
        print('获取用户信息：\n'+response.text)
    if 'profile' in response_data:
        profile = response_data['profile']
        return profile['display_name'] if profile['display_name'] else profile['real_name']
    else:
        return user_id


@app.route('/events', methods=['POST'])
def slack_events():
    json_data = request.json
    if app.debug:
        print(f'收到事件通知：\n{json_data}')

    if 'challenge' in json_data:
        return jsonify({'challenge': json_data['challenge']})

    if 'bot_id' in json_data['event'] and json_data['event']['bot_id']:
        if app.debug:
            print('收到机器人消息，不处理')
        return 'Not process', 200

    if json_data['event']['type'] == 'message' and 'subtype' not in json_data['event']:
        user_name = get_user_name(json_data['event']['user'])

        text = json_data['event']['text']
        translated_text = translate_to_english(text)
        if translated_text is None:
            if app.debug:
                print('文本是英文，无需翻译')
            return 'No translation', 200

        # 发送翻译后的文本到 Slack
        url = 'https://slack.com/api/chat.postMessage'
        headers = {'Authorization': f'Bearer {SLACK_BOT_TOKEN}'}
        data = {
            'channel': json_data['event']['channel'],
            'text': user_name + ' said: ' + translated_text
        }
        response = requests.post(url, headers=headers, data=data)
        if app.debug:
            print('发送翻译后的消息：\n' + response.text)

    return '', 200


if __name__ == '__main__':
    app.run(debug=True, port=5002)
    # app.debug = True
    # print(get_user_name('U0645QRJ31T'))
    # print(get_user_name('U0645QRJ31T'))
    # print(is_english('ETH/USDT市场的现货价格已超过网格策略的价格区间，你可手动终止策略或修改止盈止损价格。'))
