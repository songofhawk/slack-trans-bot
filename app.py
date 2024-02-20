from __future__ import annotations

import string
import sys

from flask import Flask, request, jsonify
import requests
import os
from openai import OpenAI
from functools import lru_cache
import logging

logger = logging.getLogger()
logger.addHandler(logging.StreamHandler(stream=sys.stdout))

app = Flask(__name__)

SLACK_BOT_TOKEN = os.environ.get('SLACK_BOT_TOKEN')
SLACK_DEBUG_TOKEN = os.environ.get('SLACK_DEBUG_TOKEN')
OPENAI_TOKEN = os.environ.get('OPENAI_TOKEN')

SLACK_APP_ID = 'A06JKLQNMK8'
ASCII_CHARS = set(string.printable)


class MessageCache:
    MAX_MESSAGE_COUNT = 100

    def __init__(self):
        self.message_id_set = set()
        self.message_id_list = []

    def add(self, message_id):
        if len(self.message_id_list) > self.MAX_MESSAGE_COUNT:
            self.message_id_list = self.message_id_list[self.MAX_MESSAGE_COUNT // 2:]
            self.message_id_set = set(self.message_id_list)
        self.message_id_list.append(message_id)
        self.message_id_set.add(message_id)

    def __contains__(self, message_id):
        return message_id in self.message_id_set


message_cache = MessageCache()


def is_english(text):
    # 简单的检查方法：如果大部分字符都是 ASCII，就假定文本是英文
    non_ascii_chars_in_text = [char for char in text if char not in ASCII_CHARS]
    log(f'非 ASCII 字符数量：{len(non_ascii_chars_in_text)}\n'
                       f'总数量：{len(text)}\n '
                       f'比例：{len(non_ascii_chars_in_text) / len(text)}\n'
                       f'文本：{text}')
    return len(non_ascii_chars_in_text) / len(text) < 0.1  # 可以调整阈值


def translate_to_english(origin_text: str) -> str | None:
    # 使用翻译API将文本翻译成英文
    # 这里需要根据你使用的翻译服务API来实现
    if is_english(origin_text):
        return None

    try:
        client = OpenAI(
            # This is the default and can be omitted
            api_key=OPENAI_TOKEN,
        )
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",  # 使用 GPT-3.5 的最新模型
            messages=[{"role": "user", "content": f"Translate the following text to English:\n\n{origin_text}\n\n"}],
            # 设置翻译提示
            max_tokens=2000,  # 根据需要调整最大令牌数
            temperature=0,
        )
        translated_text = response.choices[0].message.content.strip()
        return translated_text
    except Exception as e:
        logger.warning(f"An error occurred: {e}")
        return f"An error occurred: {e}"


@lru_cache
def get_user_name(user_id: str, token: str) -> str:
    url = 'https://slack.com/api/users.profile.get'
    headers = {'Authorization': f'Bearer {token}'}
    params = {
        'user': user_id,
    }
    response = requests.get(url, headers=headers, params=params)
    response_data = response.json()
    log('获取用户信息：\n' + response.text)
    if 'profile' in response_data:
        profile = response_data['profile']
        return profile['display_name'] if profile['display_name'] else profile['real_name']
    else:
        return user_id


def send_message_to_slack(message, channel: str, token: str):
    url = 'https://slack.com/api/chat.postMessage'
    headers = {'Authorization': f'Bearer {token}'}
    data = {
        'channel': channel,
        'text': message
    }
    response = requests.post(url, headers=headers, data=data)
    log('发送消息到 slack：\n' + response.text)


@app.route('/events', methods=['POST'])
def slack_events():
    json_data = request.json
    log(f'收到事件通知：\n{json_data}')

    if 'challenge' in json_data:
        log('收到授权验证消息，确认')
        return jsonify({'challenge': json_data['challenge']})

    event_data = json_data['event']
    if 'bot_id' in event_data and event_data['bot_id']:
        log('收到机器人消息，不处理')
        return 'Not process', 200

    if event_data['type'] != 'message':
        log('不是消息事件，不处理')
        return 'Not message,', 200
        
    message_id = event_data['client_msg_id']
    if message_id in message_cache:
        log(f'消息已处理过，message_id：{message_id}')
        return 'Has processed', 200
    else:
        message_cache.add(message_id)

    user_name = get_user_name(
        event_data['user'],
        SLACK_BOT_TOKEN if json_data['api_app_id'] == SLACK_APP_ID else SLACK_DEBUG_TOKEN,
    )

    text = event_data['text']
    translated_text = translate_to_english(text)
    if translated_text is None:
        log('文本是英文，无需翻译')
        return 'No translation', 200
    if translated_text.startswith('An error occurred:'):
        log('翻译失败')
        return 'Translation failed', 200

    # 发送翻译后的文本到 Slack
    if json_data['api_app_id'] == SLACK_APP_ID:
        # 来自正式 channel 的消息，才会往正式 channel 转发
        log(f'准备发送到 正式 Slack, token: {SLACK_BOT_TOKEN}, channel: {json_data["event"]["channel"]}')
        send_message_to_slack(
            user_name + ' said: ' + translated_text,
            event_data['channel'],
            token=SLACK_BOT_TOKEN
        )

    log(f'准备发送到 调试 Slack, token: {SLACK_DEBUG_TOKEN}, channel: slack-bot')
    send_message_to_slack(
        f"In【{event_data['channel']}】，{user_name} said: {translated_text}",
        'slack-bot',
        token=SLACK_DEBUG_TOKEN
    )

    return '', 200


def log(msg):
    if app.debug:
        logger.warning(msg)


if __name__ == '__main__':
    log(f'SLACK_BOT_TOKEN: {SLACK_BOT_TOKEN}')
    log(f'SLACK_DEBUG_TOKEN: {SLACK_DEBUG_TOKEN}')
    log(f'OPENAI_TOKEN: {OPENAI_TOKEN}')

    app.run(debug=True, port=5002)
    # app.debug = True
    # logger.warning(get_user_name('U0645QRJ31T'))
    # logger.warning(get_user_name('U0645QRJ31T'))
    # logger.warning(is_english('ETH/USDT市场的现货价格已超过网格策略的价格区间，你可手动终止策略或修改止盈止损价格。'))
