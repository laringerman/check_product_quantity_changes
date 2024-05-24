import requests
from bs4 import BeautifulSoup
import pandas as pd
import gspread
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os
import ast
load_dotenv()

google_credentials = os.getenv('GOOGLE_CREDENTIALS')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')

# функция для отправки сообщения в телеграм
def send_message_tel(message):
    url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
    params = {
        'chat_id': TELEGRAM_CHANNEL_ID,
        'text': message
    }
    res = requests.post(url, params=params)


# подключаемся к гугл шит
credentials = ast.literal_eval(google_credentials)
gc = gspread.service_account_from_dict(credentials)
sh = gc.open('azadea_products_today')


def get_azadea_data():
    # категории, которые будем проверять
    categories = ['new-in',
                'women',
                'mens',
                'kids',
                'tech',
                'sports/all-sports',
                'lifestyle',
                'beauty',
                'sale'
                ]

    # домен
    domen = 'https://www.azadea.com/en/'
    data = []

    # сохраняем количество товара в каждой категории
    for cat in categories:
        url = domen + cat
        res = requests.get(url)
        soup = BeautifulSoup(res.text, features="html.parser")
        products = (soup
                .find('div', class_='sfmr--rt search-product-count display--small-only')
                .text
                .strip()
                .replace(' products', '')
                .replace(',', ''))
        data.append({
            cat:products
        })
    # сохраняем сегоднешнюю дату
    today = datetime.today().strftime('%Y-%m-%d')
    # сохраняем вчерашнюю дату
    yesterday = (datetime.today() - timedelta(days=1)).strftime('%Y-%m-%d')

    # делаем общий единый словарь
    merged_data = {k: v for d in data for k, v in d.items()}
    # сохраняем, как датафрейм, колонка с категориями называется категория, 
    # а колонка со значениями называется сегоднящним числом
    df = pd.DataFrame(list(merged_data.items()), columns=['Category', today])

    # загружаем лист из гугл шита
    wks = sh.sheet1
    # сохраняем его в датафрейм
    old_df = pd.DataFrame(wks.get_all_records())
    # выбираем только категории и данные за вчера
    old_df = old_df[['Category', yesterday]]

    # соединяем данные за вчера и сегодня
    new_df = pd.merge(df, old_df, how='left', on='Category')

    # приводим значения к цифрам
    new_df[yesterday] = new_df[yesterday].fillna(0).astype('int')
    new_df[today] = new_df[today].fillna(0).astype('int')

    # проверяем, были ли изменения
    chech_df = new_df.copy()
    chech_df['delta'] = chech_df[yesterday] - chech_df[today]

    # сохраняем измененные названия категорий
    changed_cat = chech_df.query('delta != 0')['Category'].unique()

    # в зависимости от того, были ли изменения, отправляем сообщения в телеграм канал
    if len(changed_cat) == 0:
        send_message_tel('No changes')
    else:
        send_message_tel(f'There have been changes in the following categories: {changed_cat}')

    # очищаем лист
    wks.clear()
    # загружаем новую таблицу
    wks.update([new_df.columns.values.tolist()] + new_df.values.tolist())



#запуск кода
if __name__ == '__main__':
    get_azadea_data()