import sqlite3
import json


def init():
    with sqlite3.connect('/mnt/c/users/robert/brotherbot.db') as con:
        cur = con.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS `games`(
                `id` INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                `chat_id` VARCHAR(32) NOT NULL,
                `message_id` INTEGER DEFAULT NULL,
                `status` VARCHAR(32) NOT NULL DEFAULT 'new',
                `pinned` TINYINT NOT NULL DEFAULT 0,
                `address` VARCHAR(256) DEFAULT NULL,
                `date` VARCHAR(32) DEFAULT NULL,
                `time` VARCHAR(32) DEFAULT NULL,
                `lim` INTEGER DEFAULT  NULL,
                `price` INTEGER DEFAULT  NULL,
                `players` TEXT DEFAULT NULL,
                `queuers` TEXT DEFAULT NULL
            )
        """)


def new(send_message):
    entity = send_message.peer_id
    chat_id = entity.channel_id if hasattr(entity, 'channel_id') else entity.user_id
    with sqlite3.connect('/mnt/c/users/robert/brotherbot.db') as con:
        cur = con.cursor()

        cur.execute(f"""
            INSERT INTO games (chat_id, message_id, pinned) 
            VALUES ({chat_id}, {send_message.id}, 1)
        """)


def active_game(chat_id):
    return fetchone_dict(chat_id, 'new')


def last_game(chat_id):
    return fetchone_dict(chat_id, 'old', 'id', True)


def fetchone_dict(chat_id, status, order_by=None, desc=False):
    with sqlite3.connect('/mnt/c/users/robert/brotherbot.db') as con:
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        statement = f"SELECT * FROM games WHERE chat_id = {chat_id} AND status = '{status}'"
        statement += f" ORDER BY {order_by}" if order_by else ''
        statement += " DESC" if desc else ''
        cur.execute(statement)
        result = dict(cur.fetchone())

        result['players'] = [] if not result['players'] else json.loads(result['players'])
        result['queuers'] = [] if not result['queuers'] else json.loads(result['queuers'])

    return result


def update(chat_id, message_id, update_data=None):
    # set_clause = f"SET message = '{edited_message.message}'"
    set_clause = []
    with sqlite3.connect('/mnt/c/users/robert/brotherbot.db') as con:
        cur = con.cursor()

        if update_data is not None:
            for column, value in update_data.items():
                if column == 'players' or column == 'queuers':
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

        cur.execute(f"""
            UPDATE games 
            SET {', '.join(set_clause)}
            WHERE chat_id = {chat_id} AND message_id = {message_id} AND status = 'new'
        """)


def test():
    with sqlite3.connect('/mnt/c/users/robert/brotherbot.db') as con:
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute('SELECT * FROM games')
        rows = cur.fetchall()

        for row in rows:
            string = ''

            for key in row.keys():
                string += f'{key}: {row[key]},'

            print(string)
