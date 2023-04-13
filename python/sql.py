import os
import traceback
import psycopg2
import psycopg2.extras
import json
from dotenv import load_dotenv
from operator import itemgetter

if 'ON_HEROKU' not in os.environ:
    load_dotenv()

# database_url = os.environ['DATABASE_URL']

host = os.environ['DATABASE_HOST']
port = os.environ['DATABASE_PORT']
database = os.environ['DATABASE_NAME']
user = os.environ['DATABASE_USER']
password = os.environ['DATABASE_PASSWORD']
COLUMNS = {
    'id': 'SERIAL NOT NULL PRIMARY KEY',
    'chat_id': 'BIGINT NOT NULL',
    'message_id': 'INTEGER DEFAULT NULL',
    'status': 'VARCHAR(32) NOT NULL DEFAULT \'new\'',
    'pinned': 'SMALLINT NOT NULL DEFAULT 0',
    'launched': 'SMALLINT NOT NULL DEFAULT 0',
    'address': 'VARCHAR(256) DEFAULT NULL',
    'date': 'VARCHAR(32) DEFAULT NULL',
    'time': 'VARCHAR(32) DEFAULT NULL',
    'lim': 'INTEGER DEFAULT  NULL',
    'price': 'INTEGER DEFAULT NULL',
    'startup_commands': 'JSON DEFAULT NULL',
    'players': 'JSON DEFAULT NULL',
    'queuers': 'JSON DEFAULT NULL',
    'debtors': 'JSON DEFAULT NULL',
    'args': 'JSON DEFAULT NULL',
}


def connect():
    # return psycopg2.connect(database_url)
    return psycopg2.connect(host=host, port=port, database=database, user=user, password=password)


def init():
    with connect() as con, con.cursor() as cur:
        columns = ', '.join(list(map(lambda x, y: f'{x} {y}', COLUMNS.keys(), COLUMNS.values())))
        clause = f'CREATE TABLE IF NOT EXISTS games({columns})'
        cur.execute(clause)


def new(send_message):
    entity = send_message.peer_id
    chat_id = entity.channel_id if hasattr(entity, 'channel_id') else entity.user_id

    with connect() as con, con.cursor() as cur:
        cur.execute(f"""
            INSERT INTO games (chat_id, message_id, pinned) 
            VALUES ({chat_id}, {send_message.id}, 1)
        """)


def active_game(chat_id):
    return fetchone_dict(chat_id=chat_id, status='new')


def last_game(chat_id):
    return fetchone_dict(chat_id, 'old', 'id', True)


def fetchone_dict(chat_id, status=None, order_by=None, desc=False):
    with connect() as con, con.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        statement = f"SELECT * FROM games WHERE chat_id = {chat_id}"
        statement += f" AND status = '{status}'" if status else ''
        statement += f" ORDER BY {order_by}" if order_by else ''
        statement += " DESC" if desc else ''
        cur.execute(statement)
        result = cur.fetchone()

    return result


def update(chat_id, message_id, data):
    set_clause = []
    result = True

    if type(data) == dict and data.items():
        for column, value in data.items():
            if column not in COLUMNS:
                continue

            if column == 'players' or column == 'queuers':
                players = active_game(chat_id)[column] or []

                if value['add']:
                    players.append(value['player'])
                elif value['add'] is None and \
                        (player := next(item for item in players if item['id'] == value['player']['id'])):
                    players.remove(player)
                    players.append(value['player'])
                else:
                    players.remove(value['player'])

                if column == 'players':
                    players = sorted(players, key=itemgetter('status', 'name'))

                clause = f"{column} = '{json.dumps(players)}'"
                result = len(players) if type(result) == bool else result
            elif column in ['startup_commands', 'debtors', 'args']:
                clause = f"{column} = '{json.dumps(value)}'"
            elif column == 'price' and not (hasattr(value, 'isnumeric') and value.isnumeric()):
                continue
            elif hasattr(value, 'isnumeric') and value.isnumeric():
                clause = f"{column} = {int(value)}"
            elif isinstance(value, str):
                clause = f"{column} = '{value}'"
            else:
                clause = f"{column} = {value}"

            if clause:
                set_clause.append(clause)

    try:
        with connect() as con, con.cursor() as cur:
            cur.execute(f"""
                UPDATE games 
                SET {', '.join(set_clause)}
                WHERE chat_id = {chat_id} AND message_id = {message_id}
            """)
    except BaseException:
        result = False
        traceback.print_exc()

    return result


def test():
    with connect() as con, con.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute('SELECT * FROM games')
        rows = cur.fetchall()

        for row in rows:
            string = ''

            for key in row.keys():
                string += f'{key}: {row[key]},'

            print(string)
