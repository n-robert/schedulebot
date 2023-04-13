import math
import os
import traceback
import re
import sql
from telethon import Button
from telethon.tl.types import ChannelParticipantCreator, ChannelParticipantAdmin, PeerUser
from telethon.tl.functions.channels import GetParticipantRequest
from commands import Commands
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

if 'ON_HEROKU' not in os.environ:
    load_dotenv()

suffixes = {
    'male': {
        'name': {
            1: list(map(lambda x: x.strip(), os.environ['SUFFIX_MALE_NAME_1'].split(','))),
            2: list(map(lambda x: x.strip(), os.environ['SUFFIX_MALE_NAME_2'].split(','))),
        },
        'surname': {
            1: list(map(lambda x: x.strip(), os.environ['SUFFIX_MALE_SURNAME_1'].split(','))),
            2: list(map(lambda x: x.strip(), os.environ['SUFFIX_MALE_SURNAME_2'].split(','))),
        },
    },
    'female': {
        'name': {
            1: list(map(lambda x: x.strip(), os.environ['SUFFIX_FEMALE_NAME_1'].split(','))),
            2: list(map(lambda x: x.strip(), os.environ['SUFFIX_FEMALE_NAME_2'].split(','))),
        },
        'surname': {
            1: list(map(lambda x: x.strip(), os.environ['SUFFIX_FEMALE_NAME_1'].split(','))),
            2: list(map(lambda x: x.strip(), os.environ['SUFFIX_FEMALE_NAME_2'].split(','))),
        },
    },
}

custom_admins = list(map(lambda x: int(x.strip()), os.environ['CUSTOM_ADMINS'].split(',')))

user_commands = {
    **Commands.MY_COMMANDS.copy(),
    **Commands.GUEST_COMMANDS.copy(),
    **Commands.QUEUE_COMMANDS.copy(),
    **Commands.CONFIRM_COMMANDS.copy(),
    **Commands.DEBTORS_COMMANDS.copy(),
    '/cancel': Commands.CLOSE_COMMANDS['/cancel'],
}

admin_commands = {
    **Commands.ADMIN_COMMANDS.copy(),
    **Commands.ANNOUNCE_COMMANDS.copy(),
    '/close': Commands.CLOSE_COMMANDS['/close'],
}

timezone = timezone(timedelta(hours=3), name=os.environ['TZ'])


# Just to remember that this func exists
async def check(event) -> bool:
    return True


async def can(client, event, command) -> bool:
    entity = get_entity(event)['entity']

    if isinstance(entity, PeerUser):
        return True

    if f'/{command}' in user_commands:
        return True

    user = await get_user(event)

    participant = await client(
        GetParticipantRequest(channel=entity, participant=user)
    )

    if type(participant.participant) == ChannelParticipantAdmin or \
            type(participant.participant) == ChannelParticipantCreator or \
            user.id in custom_admins:
        if f'/{command}' in admin_commands:
            return True

    print('helper.can() failed')
    return False


async def do(client, event):
    commands = Commands(client)
    remove_commands = ['remove_me', 'remove_guest']

    if closed(event):
        await commands.stop(event)
        return

    if not (payload := await get_command(event)):
        return

    command, is_new, kwargs = payload

    if kwargs and '|' in kwargs:
        kwargs = list(map(lambda x: int(x) if x.isnumeric() else x, kwargs.split('|')))
        kwargs = dict(zip(i := iter(kwargs), i))
    else:
        kwargs = {}

    if await can(client, event, command) and \
            hasattr(commands, command) and \
            callable(func := getattr(commands, command)):
        await func(event, is_new, **kwargs)

    if command not in remove_commands:
        user = await get_user(event)
        keys = list(map(lambda key: f'{key}_{user.id}', remove_commands))
        await commands.remove_args(event=event, keys=keys)


async def get_command(event):
    all_commands = {**user_commands.copy(), **admin_commands.copy()}
    chat_id = get_entity(event=event)['chat_id']
    active_game = sql.active_game(chat_id)
    startup_commands = active_game.get('startup_commands') or [] if active_game else []
    possible_list = []
    is_new = False

    if hasattr(event, 'message'):
        possible_list.append(event.message.message)

    if hasattr(event, 'query') and getattr(event.query, 'data'):
        possible_list.append(event.query.data.decode("utf-8"))

    if hasattr(event, 'get_reply_message') and callable(event.get_reply_message):
        """Get command from previous message that this message is replying to"""
        reply_message = await event.get_reply_message()

        if reply_message is not None and hasattr(reply_message, 'message'):
            possible_list.append(reply_message.message)

    for text in possible_list:
        kwargs = re.sub(r'(/)*([\w\s]+)?(:*)([^@]*)?(@*)(.*)', r'\4', text)
        text = re.sub(r'(/)*([\w\s]+)?(:*)([^@]*)?(@*)(.*)', r'\1\2\3', text)

        for key, value in all_commands.items():
            if (key.startswith('/') and key == text.replace(':', '')) or value == text:
                command = key.replace('/', '')

                if startup_commands and \
                        command in startup_commands and \
                        command in Commands.STARTUP_COMMANDS:
                    is_new = True

                return [command, is_new, kwargs]

    return


def closed(event):
    if active_game := sql.active_game(get_entity(event)['chat_id']):
        return check_game_start(active_game['date'], active_game['time'], True)

    return False


def check_game_start(date, time, compare=False):
    if not date or not time:
        return False

    now = datetime.now(tz=timezone)
    year, second, microsecond = [now.year, now.second, now.microsecond]

    try:
        date = re.sub(r'^(\D*)(\d{1,2}[.\-/]\d{1,2})([.\-/]\d{2,4})*(\D*)$', r'\2', date)
        delimiter = re.sub(r'\d{1,2}([.\-/])\d{1,2}', r'\1', date)
        day, month = list(map(lambda x: int(x.strip()), date.split(delimiter)))

        time = re.sub(r'^(\D)*(\d{1,2}:\d{1,2})(\D)*$', r'\2', time)
        hour, minute = list(map(lambda x: int(x.strip()), time.split(':')))

        date_time = datetime(year, month, day, hour, minute, second, microsecond, tzinfo=timezone)

        if compare:
            return now > date_time
        else:
            return date_time
    except Exception:
        traceback.print_exc()
        return False


async def get_titles(chat_id, closed=False):
    titles = {}
    actual_game = sql.last_game(chat_id) if closed else sql.active_game(chat_id)

    for column, title in Commands.ADMIN_COMMANDS.items():
        column = column.replace('/', '')

        if column == 'launch':
            continue
        elif title is not None:
            titles[column] = title
            value = ''

            if actual_game:
                try:
                    value = actual_game.get(column, '') or ''
                    titles[column] += f' {value}'
                except IndexError:
                    traceback.print_exc()

                if (players := actual_game['players']) and len(players):
                    if column == 'price' and value:
                        titles[column] += f" ({math.ceil(int(value) / len(players) / 10) * 10} на игрока)"
                    elif column == 'players':
                        titles[column] = f"{title} {chr(10)}{await format_players(players)}"

    return titles


async def get_user(event):
    return await event.get_sender()


def get_buttons(launched=True, guests=True, closed=False, announce=0, announce_type=0, announced=0):
    if not launched:
        key = '/launch'
        return [[Button.inline(Commands.ADMIN_COMMANDS[key], key)]]

    upper_buttons = []
    lower_buttons = []

    if closed:
        if announce and announce_type == 2 and not announced:
            upper_commands = {'/announce_payment': Commands.ANNOUNCE_COMMANDS['/announce_payment']}
            lower_commands = {'/close': Commands.CLOSE_COMMANDS['/close']}
        else:
            upper_commands = {'/remove_debtor': Commands.CONFIRM_COMMANDS['/remove_debtor']}
            lower_commands = {'/debtors': Commands.DEBTORS_COMMANDS['/debtors']}
    else:
        upper_commands = Commands.MY_COMMANDS.copy()

        if guests:
            lower_commands = Commands.GUEST_COMMANDS.copy()
        else:
            lower_commands = {**Commands.QUEUE_COMMANDS.copy(), **Commands.GUEST_COMMANDS.copy()}
            lower_commands.pop('/add_guest', None)

    if upper_commands:
        for key in upper_commands:
            upper_buttons.append(Button.inline(upper_commands[key], key))

    if lower_commands:
        for key in lower_commands:
            lower_buttons.append(Button.inline(lower_commands[key], key))

    return [upper_buttons, lower_buttons]


def get_entity(event, entity=None):
    if event:
        entity = event.message.peer_id if hasattr(event, 'message') else event.query.peer

    chat_id = entity.channel_id if hasattr(entity, 'channel_id') else entity.user_id

    return {'entity': entity, 'chat_id': chat_id}


def get_players(event, user_id=None):
    chat_id = get_entity(event)['chat_id']
    user_id = user_id or event.query.user_id
    players_d = {'players': [], 'my_team': {}}

    if (active_game := sql.active_game(chat_id)) and (players := active_game['players']):
        players_d['players'] = players

        for idx, player in enumerate(players):
            if not player:
                continue

            if user_id and players[idx]['id'] == user_id:
                players_d['my_team'][idx] = players[idx]['status']

    return players_d


async def format_players(players) -> str:
    if not players:
        return ''

    c = 1
    u = 1
    g = 1
    count = 0
    c_exists = False
    u_exists = False
    g_exists = False
    tmp = []

    for player in players:
        if not player:
            continue

        if player['status'] == '+':
            if not c_exists:
                tmp.append(Commands.MESSAGES['player_status']['me'])
                c_exists = True

            count = c
            c += 1

        if player['status'] == '+/-':
            if not u_exists:
                tmp.append(Commands.MESSAGES['player_status']['me_opt'])
                u_exists = True

            count = u
            u += 1

        if player['status'] == 'guest':
            if not g_exists:
                tmp.append(Commands.MESSAGES['player_status']['guest'])
                g_exists = True

            count = g
            g += 1

        user_id = player['id']
        user_name = player['name']
        prefix = ''

        if player['status'] == 'guest':
            prefix = 'друг '
            user_name = declension(user_name, 2)

        tmp.append(f'          {count}. {prefix}<a href="tg://user?id={user_id}">{user_name}</a>')

    total = Commands.MESSAGES['player_status']['total']
    tmp.append(f'{total} {get_plural(len(players), ["игрок", "игрока", "игроков"])}')

    return chr(10).join(tmp)


def get_list(string, sep=','):
    return list(map(lambda x: x.strip(), string.split(sep)))


def get_plural(num, words):
    cases = [2, 0, 1, 1, 1, 2]
    key = 2 if (4 < num % 100 < 20) else cases[min(num % 10, 5)]

    return f'{num} {words[key]}'


def declension(string, case, gender='male'):
    words = string.strip().split(' ')

    for k, word in enumerate(words):
        name_type = 'name' if k == 0 else 'surname'

        for key, value in enumerate(suffixes[gender][name_type][1]):
            value = value.strip()
            pattern = fr'^(.+)({value})$'
            replacement = fr'\1{suffixes[gender][name_type][case][key].strip()}'

            if re.search(pattern, word):
                words[k] = re.sub(pattern, replacement, word)
                break

    return ' '.join(words)


def remove_emojis(string):
    pattern = u"[" \
              u"\U0001F600-\U0001F64F" \
              u"\U0001F300-\U0001F5FF" \
              u"\U0001F680-\U0001F6FF" \
              u"\U0001F1E0-\U0001F1FF" \
              u"\U00002500-\U00002BEF" \
              u"\U00002702-\U000027B0" \
              u"\U00002702-\U000027B0" \
              u"\U000024C2-\U0001F251" \
              u"\U0001f926-\U0001f937" \
              u"\U00010000-\U0010ffff" \
              u"\u2640-\u2642" \
              u"\u2600-\u2B55" \
              u"\u200d" \
              u"\u23cf" \
              u"\u23e9" \
              u"\u231a" \
              u"\ufe0f" \
              u"\u3030" \
              u"]+"

    return re.sub(pattern, '', string).strip()
