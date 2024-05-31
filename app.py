import requests
from bs4 import BeautifulSoup
import pandas as pd
import gspread
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os
import ast
import matplotlib.pyplot as plt
load_dotenv()

google_credentials = os.getenv('GOOGLE_CREDENTIALS')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')

# функция для отправки сообщения в телеграм
def send_message_tel(message):
    url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
    params = {
        'chat_id': TELEGRAM_CHANNEL_ID,
        'parse_mode': 'Markdown', 
        'text': message
    }
    res = requests.post(url, params=params)

# Функция для отправки изображения в Телеграм
def send_image_to_telegram(file_path):
    url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto'
    with open(file_path, 'rb') as file:
        files = {'photo': file}
        data = {'chat_id': TELEGRAM_CHANNEL_ID, 'caption': 'Changing the number of products in categories'}
        response = requests.post(url, files=files, data=data)
    return response

# создадим функцию по построению графика по полученной таблице и отправке ее в телеграм
def send_plot(new_df, shop_name = 'Name'):
    plot_df = new_df.copy()
    # Устанавливаем 'Category' как индекс
    plot_df.set_index('Category', inplace=True)

    # Транспонируем DataFrame для удобства построения графика
    df_t = plot_df.T

    # Построение графика
    plt.figure(figsize=(14, 8))

    for category in df_t.columns:
        plt.plot(df_t.index, df_t[category], marker='o', label=category)

    plt.xlabel('Date')
    plt.ylabel('Count')
    plt.title(f'{shop_name} Changing the number of products in a category')
    plt.legend(loc='center left', bbox_to_anchor=(1.0, 0.5))
    plt.grid(True)
    plt.xticks(rotation=45)
    plt.tight_layout()

    # Сохраняем график в файл
    file_path = 'category_changes.png'
    plt.savefig(file_path)
    plt.close()

    # Отправляем изображение в Телеграм
    response = send_image_to_telegram(file_path)
    if response.status_code != 200:
        send_message_tel(f'Ошибка при отправке изображения в Телеграм: {response.text}')


# подключаемся к гугл шит
credentials = ast.literal_eval(google_credentials)
gc = gspread.service_account_from_dict(credentials)
sh = gc.open('azadea_products_today')

# напишем функцию получения дней в виде строки
def get_date_minus_today(days):
    return (datetime.today() - timedelta(days=days)).strftime('%Y-%m-%d')

# Список для хранения дат
dates = [get_date_minus_today(i) for i in range(7)]

# Разделяем список на отдельные переменные
today, yesterday, minus_two_days, minus_three_days, minus_four_days, minus_five_days, minus_six_days = dates
# заранее сохраним список необходимых колонок
df_columns = ['Category', minus_six_days, minus_five_days, minus_four_days, minus_three_days, minus_two_days, yesterday]

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

        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Referer": "https://www.azadea.com/"
        }

        res = requests.get(url, headers=headers)
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
    old_df_v_two = old_df[df_columns].copy()
    # соединяем данные за вчера и сегодня
    new_df = pd.merge(old_df_v_two, df, how='left', on='Category')

    # приводим значения к цифрам
    new_df[yesterday] = new_df[yesterday].fillna(0).astype('int')
    new_df[today] = new_df[today].fillna(0).astype('int')

    # проверяем, были ли изменения
    chech_df = new_df.copy()
    chech_df['delta'] = chech_df[yesterday] - chech_df[today]
    # сохраняем измененные названия категорий и насколько изменились
    changed_cat = chech_df.query('delta != 0').copy()
    changed_cat['for_message'] = changed_cat.apply(lambda row: f"{row['Category']} ({row['delta']})", axis=1)

    # сохраняем измененные названия категорий
    changed_cat = changed_cat['for_message'].unique()

    # отправляем график
    send_plot(new_df, shop_name = 'Azadea')


    # в зависимости от того, были ли изменения, отправляем сообщения в телеграм канал
    if len(changed_cat) == 0:
        send_message_tel('*Azadea* \nNo changes')
    else:
        string_list = [str(element) for element in changed_cat]
        delimiter = ";\n"
        result_string = delimiter.join(string_list)
        send_message_tel(f'*Azadea* \nThere have been changes in the following categories: \n{result_string}')

    # очищаем лист
    wks.clear()
    # загружаем новую таблицу
    wks.update([new_df.columns.values.tolist()] + new_df.values.tolist())




def get_virgin_data():

    # категории, которые будем проверять
    virgin_categories = [
        'electronics-accessories/c/n010000',
        'gaming/c/n050000',
        'toys/c/n060000',
        'sports-outdoor/c/n120000',
        'house/c/n040000',
        'pet-care/c/n130000',
        'fashion/c/n020000',
        'stationery/c/n070000',
        'books/c/n080000',
        'music/c/n090000',
        'gift-cards-vouchers/c/n110000'
    ]
    sh = gc.open('virgin_products_today')

    # домен
    virg_domen = 'https://www.virginmegastore.ae/en/'
    data = []

    # сохраняем количество товара в каждой категории
    for virg_cat in virgin_categories:
        url = virg_domen + virg_cat
        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Referer": "https://www.virginmegastore.ae/"
        }

        res = requests.get(url, headers=headers)
        soup = BeautifulSoup(res.text, features="html.parser")
        products = (soup
                    .find('div', class_='count mr-auto')
                    .text
                    .strip()
                    .replace(' Products found', '')
                    .replace(',', ''))
        virgin_cat_name = virg_cat.split('/')[0]
        data.append({
            virgin_cat_name:products
        })


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
    old_df_v_two = old_df[df_columns].copy()
    # соединяем данные за вчера и сегодня
    new_df = pd.merge(old_df_v_two, df, how='left', on='Category')

    # приводим значения к цифрам
    new_df[yesterday] = new_df[yesterday].fillna(0).astype('int')
    new_df[today] = new_df[today].fillna(0).astype('int')

    # проверяем, были ли изменения
    chech_df = new_df.copy()
    chech_df['delta'] = chech_df[yesterday] - chech_df[today]
    # сохраняем измененные названия категорий и насколько изменились
    changed_cat = chech_df.query('delta != 0').copy()
    changed_cat['for_message'] = changed_cat.apply(lambda row: f"{row['Category']} ({row['delta']})", axis=1)

    # сохраняем измененные названия категорий
    changed_cat = changed_cat['for_message'].unique()

    # отправляем график
    send_plot(new_df, shop_name = 'Virginmegastore')


    # в зависимости от того, были ли изменения, отправляем сообщения в телеграм канал
    if len(changed_cat) == 0:
        send_message_tel('*Virginmegastore* \nNo changes')
    else:
        string_list = [str(element) for element in changed_cat]
        delimiter = ";\n"
        result_string = delimiter.join(string_list)
        send_message_tel(f'*Virginmegastore* \nThere have been changes in the following categories: \n{result_string}')

    # очищаем лист
    wks.clear()
    # загружаем новую таблицу
    wks.update([new_df.columns.values.tolist()] + new_df.values.tolist())



#запуск кода
if __name__ == '__main__':
    get_azadea_data()
    get_virgin_data()