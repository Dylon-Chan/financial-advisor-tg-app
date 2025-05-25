from flask import Flask, request, jsonify
from config import Config
import requests
import time
from apps.gemini_finance import gemini_finance_response
from io import StringIO
import pandas as pd
import pypdf
import tempfile
import os

app = Flask(__name__)
app.config.from_object(Config)

telegram_api_key = Config.TELEGRAM_API_KEY
base_url = f'https://api.telegram.org/bot{telegram_api_key}/'

users_dict = {} # for simplicity, I am using a dictionary to store the user's state

# function to send message to telegram (by splitting the message into chunks if it is too long)
def send_message(id, text):
    MAX_MESSAGE_LENGTH = 4096
    data = {'chat_id': id}
    
    if len(text) <= MAX_MESSAGE_LENGTH:
        data['text'] = text
        response = requests.post(base_url + 'sendMessage', json=data)
    else:
        paragraphs = text.split('\n\n')
        current_chunk = ''

        for p in paragraphs:
            if len(current_chunk + p + '\n\n') > MAX_MESSAGE_LENGTH and current_chunk:
                data['text'] = current_chunk.strip()
                response = requests.post(base_url + 'sendMessage', json=data)

                current_chunk = p + '\n\n'
                time.sleep(1)
            else:
                current_chunk += p + '\n\n'
            
        if current_chunk.strip():
            data['text'] = current_chunk.strip()
            response = requests.post(base_url + 'sendMessage', json=data)
    return response.json()

# route to index
@app.route('/')
def index():
    return "Telegram Bot Webhook Server is running!"

# route to handle webhook
@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        return jsonify({'status': 'ok', 'message': 'Webhook is active'})
        
    if request.method == 'POST':
        update = request.get_json()
        message = update.get('message', {})
        
        if message:
            chat_id = message['chat']['id']
            file_upload = message.get('document',None)
            q = message.get('text','')

            if file_upload:
                caption = message.get('caption','')
                file_type = file_upload['mime_type']
                if not caption:
                    send_message(chat_id, 'Please enter your prompt in the caption when uploading a file!')
                    return jsonify({'error': 'no caption', 'status': 'error'})
                if file_type not in ['text/csv', 'application/vnd.ms-excel', 'application/pdf']:
                    send_message(chat_id, 'I am sorry that I can only accept CSV, Excel, or PDF file. Please re-upload a correct file.')
                    return jsonify({'error': 'not correct file type', 'status': 'error'})
                file_id = file_upload['file_id']
                get_file = requests.get(base_url + f'getFile?file_id={file_id}')
                file_path = get_file.json()['result']['file_path']
                download_file = requests.get(f'https://api.telegram.org/file/bot{telegram_api_key}/{file_path}')
                if file_upload['mime_type'] == 'text/csv':
                    df = pd.read_csv(StringIO(download_file.text))
                    file_text = df.to_string(index=False)
                elif file_upload['mime_type'] == 'application/vnd.ms-excel':
                    df = pd.read_excel(StringIO(download_file.text))
                    file_text = df.to_string(index=False)
                elif file_upload['mime_type'] == 'application/pdf':
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_pdf:
                        temp_pdf.write(download_file.content)
                        temp_pdf_path = temp_pdf.name
                    reader = pypdf.PdfReader(temp_pdf_path)
                    file_text = ''
                    for p in reader.pages:
                        txt = p.extract_text()
                        if txt:
                            file_text += txt + '\n'
                    os.remove(temp_pdf_path)

                q = f'{file_text}\n\n{caption}'
                
            if q == '/start' or not users_dict.get(chat_id, {}):
                users_dict[chat_id] = {'callback_data': None, 'status': 'start'}
                welcome_text = """Hi and welcome! 👋
FinSight helps you make smarter financial decisions by providing:

📄 Automated analysis of financial statements – Upload reports and get clear, actionable insights.
🏢 Public company insights – Dive into key metrics, trends, and performance indicators.
📈 Real-time stock data – Stay updated with the latest stock prices and market movements.
💡 Personalized financial guidance – Understand what the numbers really mean for your portfolio.

To attach a file, upload it and enter your question in the caption.
Or you can just enter your question directly to get started!

[Enter /end] - End the session"""
                send_message(chat_id, welcome_text)
                return jsonify({'action': 'welcome', 'status': 'success'})
            
            if q == '/end':
                users_dict[chat_id]['status'] = 'end'
                bye_text = """Thanks for using FinSight!
We hope the insights were helpful in guiding your financial decisions.

Until next time, stay informed and invest wisely!
Type /start whenever you're ready to begin a new session."""    
                send_message(chat_id, bye_text)
                return jsonify({'action': 'end', 'status': 'success'})
            
            if users_dict.get(chat_id, {}).get('status', '') != 'start':
                send_message(chat_id, 'Please enter /start to start a session')
                return jsonify({'action': 'ask_start', 'status': 'success'})
            
            r = gemini_finance_response(q)
            send_message(chat_id, r)
            return jsonify({'action': 'reply_message', 'status': 'success'})
        
    return jsonify({'status': 'error', 'message': 'Invalid request'})

# route to setup webhook by visiting the url (e.g. https://your-domain.com/setup_webhook?url=https://your-domain.com/webhook)
@app.route('/setup_webhook', methods=['GET'])
def setup_webhook():
    webhook_url = request.args.get('url')
    if not webhook_url:
        return jsonify({'status': 'error', 'message': 'No webhook URL provided'})
    data = {'url': webhook_url}
    response = requests.post(base_url + 'setWebhook', json=data)
    return jsonify(response.json())

# route to get webhook info
@app.route('/get_webhook_info', methods=['GET'])
def get_webhook_info():
    response = requests.get(base_url + 'getWebhookInfo')
    return jsonify(response.json())

# route to delete webhook
@app.route('/delete_webhook', methods=['GET'])
def delete_webhook():
    response = requests.get(base_url + 'deleteWebhook')
    return jsonify(response.json())

if __name__ == '__main__':
    app.run(debug=True)