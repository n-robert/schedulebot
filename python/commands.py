import traceback
import random
import helper
import sql
from telethon import TelegramClient, Button
from telethon.errors import MessageNotModifiedError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta


class Commands:
    TITLES = [
        'Новая игра! Записываемся!',
        'Адрес:',
        'Дата:',
        'Начало игры:',
        'Лимит игроков:',
        'Арендная плата:',
        'Состав игроков:',
    ]

    ADMIN_COMMANDS = {
        '/new': 'Новая игра! Записываемся!',
        '/stop': 'Запись закрыта.',
        '/launch': 'Запуск',
        '/address': 'Адрес:',
        '/date': 'Дата:',
        '/time': 'Начало игры:',
        '/lim': 'Лимит игроков:',
        '/price': 'Арендная плата:',
        '/players': 'Состав игроков:',
        '/test': None,
    }

    MY_COMMANDS = {
        '/add_me': 'Я +',
        '/add_me_opt': 'Я +/-',
        '/remove_me': 'Я -',
    }

    GUEST_COMMANDS = {
        '/add_guest': 'Друг +',
        '/remove_guest': 'Друг -',
    }

    QUEUE_COMMANDS = {
        '/queue': 'Кто в очереди?',
    }

    ANNOUNCE_COMMANDS = {
        '/announce_payment': 'Напомнить об оплате',
        '/config': ['Никогда', 'Всегда', 'Иногда'],
    }

    CLOSE_COMMANDS = {
        '/close': 'Закрыть',
        '/cancel': 'Отмена',
    }

    CONFIRM_COMMANDS = {
        '/remove_debtor': 'Я заплатил за игру',
    }

    DEBTORS_COMMANDS = {
        '/debtors': 'Собираются заплатить',
    }

    STARTUP_COMMANDS = ['new', 'address', 'date', 'time', 'lim', 'price']

    MESSAGES = {
        'request': {
            'config': f"""
                Эту настройку нужно сделать только 1 раз.
                Нужно ли напоминать игрокам об оплате после игры?
                1. "Никогда" - нет, не напоминать.
                2. "Всегда" - выводяттся сообщение об оплате, подтверждение оплаты и список должников.
                3. "Иногда" - админу приходится каждый раз выбирать, вывести сообщение об оплате или нет.
                """,
        },
        'add_player': [
            ' забрал 1 слот.' + chr(10) + 'В списке {total}.',
            ' записался на игру.' + chr(10) + 'Теперь в списке {total}.',
            ' присоединился к игре.' + chr(10) + 'Всего {total} на данный момент.',
            ' записался {count}-ым в списке игроков',
            ' занял {count}-е место в списке игроков.',
        ],
        'remove_player': [
            ' слился.' + chr(10) + 'Осталось {}.',
            ' не придет.' + chr(10) + 'Осталось {}.',
            ' освободил 1 место.' + chr(10) + 'Осталось {}.',
        ],
        'player_status': {
            'me': '     Точно приду:',
            'me_opt': '     Возможно, приду:',
            'guest': '     Гости:',
            'total': '     Всего:',
        },
        'announce_payment': 'Всем спасибо за игру!' + chr(10) +
                            'Сделав оплату за себя и своих друзей, не забудьте нажать на кнопку "{payment_done}", '
                            'чтобы ваша оплата была засчитана.'
    }

    FEEDBACKS = {
        'lim': 'Достигнут лимит: {lim_f}.' + chr(10) +
               'Резиденты чата добавляются в очередь и '
               'автоматически записываются по мере появления свободных мест.' + chr(10) +
               'Вы - №{queue_number} в очереди.',
        'add_player': {
            'me_exists': 'Вы уже есть в списке!',
        },
        'remove_player': {
            'guest': 'Вы точно хотите удалить друга из записи? Если да, то нажмите кнопку "Друг -" еще раз.',
            'me': 'Вы уверены, что не хотите записаться на игру? Если да, то нажмите кнопку "Я -" еще раз.',
            'queuer': 'Вы сняты с очереди',
        },
        'queue': 'Очередь пока пуста.',
        'remove_debtor': 'Отлично, спасибо.',
        'debtors': 'Все сдали деньги за игру.'
    }

    def __init__(self, client: TelegramClient):
        self.client = client
        self.timezone = helper.timezone
        self.scheduler = AsyncIOScheduler()
        self.scheduler.start()

    async def new(self, event, is_new=False):
        entity, chat_id = helper.get_entity(event).values()
        actual_game = sql.active_game(chat_id) or sql.last_game(chat_id)
        message = chr(10).join(self.TITLES)
        buttons = helper.get_buttons(launched=False)

        try:
            await self.stop(event=event, message_id=actual_game['message_id'], show_buttons=False)
        except BaseException:
            traceback.print_exc()

        if hasattr(event, 'message'):
            await self.client.delete_messages(entity=entity, message_ids=event.message.id)

        send_message = await self.client.send_message(
            entity=entity,
            message=message,
            buttons=buttons
        )

        await self.client.pin_message(
            entity=entity,
            message=send_message,
            notify=True
        )

        sql.new(send_message)

        # if last_game := sql.last_game(chat_id):
        #     last_startup_commands = []
        #
        #     # Get actual commands by last game
        #     for command in self.STARTUP_COMMANDS:
        #         if last_game.get(command):
        #             last_startup_commands.append(command)
        #
        #     await self.update(event=event, data={'startup_commands': last_startup_commands, 'is_invoked': True})
        #     await self.populate(event=event)

        await self.config(event=event, is_new=True)

    async def stop(self, event, is_new=False, message_id=None, show_buttons=True, token=None):
        entity, chat_id = helper.get_entity(event).values()
        active_game = sql.active_game(chat_id)
        last_game = sql.last_game(chat_id)
        actual_game = active_game or last_game

        args = actual_game.get('args') or {}
        announce = args.get('announce')
        announce_type = args.get('announce_type')
        announced = args.get('announced')
        show_buttons = False if announce_type == 0 else show_buttons
        data = {
            'is_invoked': True,
            'pinned': 1 if show_buttons else 0,
            'announce': announce,
            'announce_type': announce_type,
            'announced': announced,
            'closed': True
        }

        if active_game:
            data['status'] = 'old'
            message_id = active_game['message_id']
            players = active_game['players']
            debtors = {}
        else:
            message_id = last_game['message_id']
            players = last_game['players']
            debtors = last_game['debtors']

        # If the job is abandoned, do nothing
        if token and token != f'{chat_id}:{message_id}':
            print("This job is abandoned, I'll skip it")
            return

        if announce_type and players and not debtors:
            debtors = {}

            for player in players:
                if debtor := debtors.get(player['id']):
                    debtors[player['id']] = {'name': debtor['name'], 'count': debtor['count'] + 1}
                else:
                    debtors[player['id']] = {'name': player['name'], 'count': 1}

            data['debtors'] = debtors

        if not debtors:
            show_buttons = False

        await self.update(event=event, data=data, message_id=message_id, show_buttons=show_buttons)

        if announce_type == 1:
            await self.announce_payment(event)

        if not show_buttons:
            await self.client.unpin_message(entity, message=message_id)

        if hasattr(event, 'message'):
            await self.client.delete_messages(entity=entity, message_ids=event.message.id)

    async def launch(self, event, is_new=False):
        chat_id = helper.get_entity(event)['chat_id']

        if (active_game := sql.active_game(chat_id)) and not active_game['launched']:
            data = {'launched': 1}
            await self.update(event=event, data=data)

    async def address(self, event, is_new=False, data=None, entity=None, user=None):
        data = {**data, 'address': None} if data else {'address': None}
        await self.update(event=event, data=data, is_new=is_new, entity=entity, user=user)

    async def date(self, event, is_new=False, data=None, entity=None, user=None):
        data = {**data, 'date': None} if data else {'date': None}
        await self.update(event=event, data=data, is_new=is_new, entity=entity, user=user)

    async def time(self, event, is_new=False, data=None, entity=None, user=None):
        data = {**data, 'time': None} if data else {'time': None}
        await self.update(event=event, data=data, is_new=is_new, entity=entity, user=user)

    async def lim(self, event, is_new=False, data=None, entity=None, user=None):
        data = {**data, 'lim': None} if data else {'lim': None}
        result = await self.update(event=event, data=data, is_new=is_new, entity=entity, user=user)
        chat_id = helper.get_entity(event)['chat_id']
        active_game = sql.active_game(chat_id)
        players = active_game.get('players') or []
        queuers = active_game.get('queuers') or []
        lim = active_game.get('lim') or 0
        diff = lim - len(players) if lim else len(queuers)

        if queuers and result and (lim == 0 or diff > 0):
            for idx in range(diff):
                if idx < len(queuers):
                    queuer = queuers[idx]
                    await self.add_player(event, queuer['status'], queuer['id'], queuer['name'])
                    await self.remove_queuer(event, queuer['id'])

    async def price(self, event, is_new=False, entity=None, user=None):
        await self.update(event=event, data={'price': None}, is_new=is_new, entity=entity, user=user)

    async def add_me(self, event, is_new=False):
        await self.add_player(event, '+')

    async def add_me_opt(self, event, is_new=False):
        await self.add_player(event, '+/-')

    async def add_guest(self, event, is_new=False):
        await self.add_player(event, 'guest')

    async def add_player(self, event, status, user_id=None, user_name=None, is_self=True):
        entity, chat_id = helper.get_entity(event).values()
        user = await helper.get_user(event)
        user_id = user_id or user.id
        user_name = user_name or \
            user.first_name + (f' {user.last_name}' if getattr(user, 'last_name', '') else '')
        feedback = None
        alert = False
        answered = False
        changed = False
        send_message = True
        data = None

        player_d = helper.get_players(event, user_id)
        my_team = player_d['my_team']
        mt_values = list(my_team.values())

        active_game = sql.active_game(chat_id)
        players = active_game.get('players') or []
        lim = active_game.get('lim') or len(players) + 1

        if status != 'guest' and status in mt_values:
            if hasattr(event, 'query'):
                feedback = self.FEEDBACKS['add_player']['me_exists']
                alert = True
                answered = True
                await event.answer(message=feedback, alert=alert)
        elif len(players) < lim or \
                (len(players) == lim and status == '+' and '+/-' in mt_values) or \
                (len(players) == lim and status == '+/-' and '+' in mt_values):

            me_exists = '+' in mt_values or '+/-' in mt_values
            new_player = {"id": user_id, "name": user_name, "status": status}
            changed = True
            add = True

            if status != 'guest' and me_exists:
                add = None
                send_message = False

            data = {'players': {'player': new_player, 'add': add}}
        else:
            queue_number = await self.add_queuer(event, status, user_id, user_name)

            if is_self:
                lim_f = helper.get_plural(lim, ["игрок", "игрока", "игроков"])

                if hasattr(event, 'query'):
                    feedback = self.FEEDBACKS['lim'].format(lim_f=lim_f, queue_number=queue_number)
                    alert = True
                    answered = True
                    await event.answer(message=feedback, alert=alert)

        if changed and data:
            result = await self.update(
                event=event,
                data=data
            )

            if type(result) == int and send_message:
                prefix = ''

                if status == 'guest':
                    prefix = 'Друг '
                    user_name = helper.declension(user_name, 2)

                mention = f'<a href="tg://user?id={user_id}">{user_name}</a>'
                message_list = self.MESSAGES['add_player']
                player_added = f'{prefix}{mention} {random.choice(message_list)}'
                players_f = helper.get_plural(result, ["игрок", "игрока", "игроков"])

                await self.client.send_message(
                    entity=entity,
                    message=player_added.format(count=result, total=players_f)
                )

        if hasattr(event, 'query') and not answered:
            await event.answer(message=feedback, alert=alert)

    async def add_queuer(self, event, status, user_id=None, user_name=None, is_self=True):
        chat_id = helper.get_entity(event)['chat_id']
        user_id = user_id or event.query.user_id
        result = True

        if not user_name:
            user = await self.client.get_entity(user_id)
            user_name = user.first_name + (f' {user.last_name}' if getattr(user, 'last_name', '') else '')

        queuers = sql.active_game(chat_id).get('queuers') or []
        new_queuer = {"id": user_id, "name": user_name, "status": status}
        existing_queuer = False

        for queuer in queuers:
            if queuer['id'] == new_queuer['id']:
                existing_queuer = True
                result = queuers.index(queuer) + 1
                break

        if not existing_queuer:
            data = {'queuers': {'player': new_queuer, 'add': True}}
            result = await self.update(event=event, data=data)

        return result

    async def remove_me(self, event, is_new=False):
        await self.remove_player(event, ['+', '+/-'])

    async def remove_guest(self, event, is_new=False):
        await self.remove_player(event, ['guest'])

    async def config(self, event, is_new=False, announce_type=None, edit=0):
        entity, chat_id = helper.get_entity(event).values()
        args = {}

        if (active_game := sql.active_game(chat_id)) and active_game.get('args'):
            args = active_game.get('args')
        elif (last_game := sql.last_game(chat_id)) and last_game.get('args') and not args:
            args = last_game.get('args')

        if edit:
            announce_type = None
        elif announce_type is None and args.get('announce_type') is not None:
            announce_type = args.get('announce_type')

        if announce_type is None:
            user = await helper.get_user(event)
            message = self.MESSAGES['request']['config']
            message += f'<a href="tg://user?id={user.id}">&#8203</a>'
            buttons = []
            command = '/config'

            for text in self.ANNOUNCE_COMMANDS[command]:
                idx = self.ANNOUNCE_COMMANDS[command].index(text)
                data = f'{command}:announce_type|{idx}'
                buttons.append([Button.inline(text, data)])

            return await self.client.send_message(
                entity=entity,
                message=message,
                buttons=buttons,
            )

        if announce_type is not None:
            announce = 1 if announce_type == 2 else 0
            data = {
                'args': {'announce': announce, 'announce_type': announce_type},
                'is_invoked': True,
            }
            await self.update(event=event, data=data)

        if hasattr(event, 'query'):
            await self.client.delete_messages(entity=entity, message_ids=event.query.msg_id)

    async def remove_player(self, event, status, is_self=True):
        entity, chat_id = helper.get_entity(event).values()
        active_game = sql.active_game(chat_id)

        players = active_game.get('players') or []
        queuers = active_game.get('queuers') or []
        args = active_game.get('args') or {}
        lim = active_game.get('lim') or 0

        user = await helper.get_user(event)
        user_id = user.id
        user_name = user.first_name + (f' {user.last_name}' if getattr(user, 'last_name', '') else '')

        feedback = None
        alert = False
        answered = False
        confirm = f'remove_guest_{user.id}' if status == ['guest'] else f'remove_me_{user.id}'

        if confirm not in args:
            player_exists = next((player for player in players
                                  if player['id'] == user_id and player['status'] in status), None)
            queuer_exists = next((queuer for queuer in queuers if queuer['id'] == user_id), None)

            if status == ['guest']:
                if player_exists:
                    feedback = self.FEEDBACKS['remove_player']['guest']
                    alert = True
            else:
                if player_exists or queuer_exists:
                    feedback = self.FEEDBACKS['remove_player']['me']
                    alert = True

            if hasattr(event, 'query'):
                answered = True
                await event.answer(message=feedback, alert=alert)

            args[confirm] = 1
            data = {'args': args}
            await self.update(event=event, data=data)

            kwargs = {
                'id': f'remove_args_{confirm}',
                'run_date': datetime.now(tz=self.timezone) + timedelta(seconds=30),
                'kwargs': {'event': event, 'keys': [confirm]},
            }
            await self.add_job(event=event, func_name='remove_args', **kwargs)
        else:
            if players:
                data = {}
                new_player = None

                for player in players:
                    if player and player['id'] == user_id and player['status'] in status:
                        data['players'] = {'player': player, 'add': False}
                        data['price'] = None
                        diff = lim - len(players) + 1

                        if queuers and diff > 0:
                            new_player = queuers.pop(0)
                            data['queuers'] = {'player': new_player, 'add': False}

                        try:
                            args.pop(confirm)
                            data['args'] = args
                        except BaseException:
                            pass

                        result = await self.update(event=event, data=data)

                        if type(result) == int:
                            prefix = ''

                            if 'guest' in status:
                                prefix = 'Друг '
                                user_name = helper.declension(user_name, 2)

                            mention = f'<a href="tg://user?id={user_id}">{user_name}</a>'
                            message_list = self.MESSAGES['remove_player']
                            player_removed = f'{prefix}{mention} {random.choice(message_list)}'
                            players_f = helper.get_plural(result, ["игрок", "игрока", "игроков"])

                            await self.client.send_message(entity=entity, message=player_removed.format(players_f))

                        if new_player:
                            await self.add_player(
                                event,
                                status=new_player['status'],
                                user_id=new_player['id'],
                                user_name=new_player['name'],
                                is_self=False
                            )

                        break

                if not data:
                    result = await self.remove_queuer(event, user_id, status, queuers)

                    if result is not False:
                        feedback = self.FEEDBACKS['remove_player']['queuer']
                        alert = True

        if hasattr(event, 'query') and not answered:
            await event.answer(message=feedback, alert=alert)

    async def remove_queuer(self, event, user_id, status, queuers=None):
        if status == ['guest']:
            return False

        chat_id = helper.get_entity(event)['chat_id']
        queuers = queuers or sql.active_game(chat_id).get('queuers') or []
        result = False

        if queuer := next((queuer for queuer in queuers if queuer['id'] == user_id), None):
            data = {'queuers': {'player': queuer, 'add': False}}
            result = await self.update(event=event, data=data)

        return result

    async def remove_debtor(self, event, is_new=False):
        chat_id = helper.get_entity(event)['chat_id']
        feedback = None
        alert = False
        answered = False

        if debtors := sql.last_game(chat_id).get('debtors'):
            user_id = event.query.user_id

            if debtors.pop(str(user_id), False):
                if hasattr(event, 'query'):
                    feedback = self.FEEDBACKS['remove_debtor']
                    alert = True
                    answered = True
                    await event.answer(message=feedback, alert=alert)
                await self.update(
                    event=event,
                    data={'debtors': debtors, 'closed': True}
                )

        if hasattr(event, 'query') and not answered:
            await event.answer(message=feedback, alert=alert)

    async def remove_args(self, event, **kwargs):
        chat_id = helper.get_entity(event)['chat_id']
        keys = kwargs.get('keys') or []

        if keys and (active_game := sql.active_game(chat_id)):
            args = active_game.get('args') or {}

            for key in keys:
                try:
                    if key in args:
                        args.pop(key)
                except BaseException:
                    print(f'key {key} not exists.')
                    traceback.print_exc()

            await self.update(event, data={'args': args})

    async def add_job(self, event, func_name, **kwargs):
        chat_id = helper.get_entity(event)['chat_id']

        if (active_game := sql.active_game(chat_id)) and active_game['launched']:
            message_id = active_game['message_id']
            kwargs = {
                **kwargs,
                'trigger': 'date',
                # 'next_run_time': run_date,
                'replace_existing': True,
             }

            if func_name == 'stop' and active_game['date'] and active_game['time']:
                kwargs['id'] = f'{func_name}_{chat_id}'
                kwargs['run_date'] = helper.check_game_start(active_game['date'], active_game['time'])
                kwargs['kwargs'] = {'event': event, 'token': f'{chat_id}:{message_id}'}

            if kwargs.get('run_date') and callable(func := getattr(self, func_name)):
                try:
                    self.scheduler.add_job(func, **kwargs)
                except BaseException:
                    print(f'Cannot add job #{func_name}_{chat_id}:')
                    traceback.print_exc()

                try:
                    self.scheduler.print_jobs()
                except BaseException:
                    print('print_jobs() error:')
                    traceback.print_exc()

    async def announce_payment(self, event, is_new=False):
        entity, chat_id = helper.get_entity(event=event).values()
        actual_game = sql.active_game(chat_id) or sql.last_game(chat_id)
        args = actual_game.get('args') or {}
        announce_type = args.get('announce_type', 0)
        payment_done = self.CONFIRM_COMMANDS['/remove_debtor']

        if hasattr(event, 'query'):
            await event.answer()

        if (last_game := sql.last_game(chat_id)) and (debtors := last_game.get('debtors')):
            message = self.MESSAGES['announce_payment'].format(payment_done=payment_done)

            for key in debtors:
                message += f'<a href="tg://user?id={key}">&#8203</a>'

            await self.client.send_message(
                entity=entity,
                message=message
            )

        if announce_type == 2:
            args['announced'] = 1
            await self.update(event=event, data={'is_invoked': True, 'closed': True, 'args': args})
            await self.stop(event=event)

    async def close(self, event, is_new=False):
        if hasattr(event, 'query'):
            await event.answer()

        await self.stop(event=event, show_buttons=False)

    async def update(
            self,
            event,
            data,
            message_id=None,
            show_buttons=True,
            is_new=False,
            entity=None,
            user=None
    ):
        user = await helper.get_user(event) if event else user
        entity, chat_id = helper.get_entity(event, entity).values()
        is_invoked = False
        result = True
        closed = data.get('closed', False)
        announce = data.get('announce', 0)
        announce_type = data.get('announce_type', 0)
        announced = data.get('announced', 0)

        if 'is_invoked' in data:
            is_invoked = data['is_invoked']  # Add 'is_invoked': True to data to force update
        elif hasattr(event, 'message') and hasattr(event.message, 'reply_to'):
            is_invoked = event.message.reply_to
        elif hasattr(event, 'query') and hasattr(event.query, 'data'):
            is_invoked = event.query.data

        # Message is invoked by other message or command and contains data to be updated
        if is_invoked:
            active_game = sql.active_game(chat_id)
            actual_game = active_game or sql.last_game(chat_id)
            message_id = message_id or actual_game['message_id']

            for column, value in data.items():
                if value is None:
                    if hasattr(event, 'message') and getattr(event.message, 'reply_to'):
                        data[column] = event.message.message
                    else:
                        if column == 'price':
                            data[column] = actual_game['price']

            # if is_new and active_game and (startup_commands := active_game.get('startup_commands')):
            #     startup_commands.pop(0)
            #     data['startup_commands'] = startup_commands

            if len(data):
                result = sql.update(chat_id, message_id, data)

            titles = await helper.get_titles(chat_id, closed)

            if closed:
                if 'new' in titles:
                    del titles['new']
            else:
                del titles['stop']

            text = chr(10).join(titles.values())
            buttons = None

            if show_buttons:
                # Get actual_game after data were updated
                actual_game = sql.last_game(chat_id) if closed else sql.active_game(chat_id)
                launched = actual_game['launched']
                players = actual_game.get('players') or []
                lim = actual_game.get('lim') or 0
                guests = not players or not lim or len(players) < lim
                buttons = helper.get_buttons(
                    launched=launched,
                    guests=guests,
                    closed=closed,
                    announce=announce,
                    announce_type=announce_type,
                    announced=announced,
                )

            try:
                await self.client.edit_message(
                    entity=entity,
                    message=message_id,
                    text=text,
                    buttons=buttons,
                )
            except MessageNotModifiedError:
                pass
            except BaseException:
                traceback.print_exc()

            if hasattr(event, 'message') and \
                    hasattr(event.message, 'reply_to') and \
                    hasattr(event.message.reply_to, 'reply_to_msg_id'):
                reply_to_msg_id = getattr(event.message.reply_to, 'reply_to_msg_id')
                await self.client.delete_messages(
                    entity=entity, message_ids=[event.message.id, reply_to_msg_id]
                )

            if 'date' in data or 'time' in data or 'launched' in data:
                await self.add_job(event=event, func_name='stop')

            # if is_new:
            #     # Automatically call next commands when new game started
            #     await self.populate(event, entity, user)
        else:
            # Invoking (forcing reply, etc.) another message, which contains requested data
            for column in data:
                key = f'/{column}'

                if key in self.ADMIN_COMMANDS:
                    title = self.ADMIN_COMMANDS[key]
                    mention = f'<a href="tg://user?id={user.id}">&#8203</a>' if is_new else ''
                    reply_to = event.message.id if event else None

                    await self.client.send_message(
                        entity=entity,
                        message=title + mention,
                        reply_to=reply_to,
                        buttons=Button.force_reply(selective=True, placeholder=title),
                    )

                    break

            if not is_new and hasattr(event, 'message'):
                await self.client.delete_messages(entity=entity, message_ids=event.message.id)

        return result

    async def queue(self, event, is_new=False):
        chat_id = helper.get_entity(event)['chat_id']
        feedback = []

        if queuers := sql.active_game(chat_id).get('queuers'):
            for idx, queuer in enumerate(queuers):
                feedback.append(f"{idx + 1}. {queuer['name']}")
        else:
            feedback.append(self.FEEDBACKS['queue'])

        await event.answer(message=chr(10).join(feedback), alert=True)

    async def debtors(self, event, is_new=False):
        entity, chat_id = helper.get_entity(event).values()
        feedback = []
        answered = False

        if debtors := sql.last_game(chat_id).get('debtors'):
            for debtor in debtors.values():
                text = helper.remove_emojis(debtor['name'])
                text = text.split(' ')[::-1][0]
                text += f' + {count}' if (count := debtor['count'] - 1) else ''
                feedback.append(text)
        else:
            feedback.append(self.FEEDBACKS['debtors'])

        if (message := chr(10).join(feedback)) and len(message) < 201:
            answered = True
            await event.answer(message=chr(10).join(feedback), alert=True)
        else:
            await self.client.send_message(
                entity=entity,
                message=message,
            )

        if hasattr(event, 'query') and not answered:
            await event.answer()

    async def populate(self, event=None, entity=None, user=None):
        chat_id = helper.get_entity(event, entity)['chat_id']
        startup_commands = sql.active_game(chat_id).get('startup_commands') or []
        next_command = startup_commands[0] if startup_commands else None

        if next_command and hasattr(self, next_command) and callable(func := getattr(self, next_command)):
            await func(event=event, is_new=True, data={'is_invoked': False}, entity=entity, user=user)

    async def test(self, event, is_new=False):
        # row = sql.active_game(1222717882)
        # string = ''
        #
        # for key in row.keys():
        #     string += f'{key}: {row[key]},'

        print(sql.test())
