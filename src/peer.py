import errno
import socket
import random
import string
from threading import Thread
from time import sleep
from datetime import datetime
from typing import Dict, List, Optional, Tuple

HEADER = 64
ENCODING = 'utf-8'
DISCONNNECT_MESSAGE = '!!DISCONNECT!!'
UUID_LENGTH = 8

DEFAULT_TAIL_LENGTH = 20
DEFAULT_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
PRE_CONNECTION_CLOSE_SLEEP_TIME = 1.5

class Message:
    def __init__(self, incoming: bool, text: str, time: datetime = datetime.now()) -> None:
        self.incoming = incoming
        self.text = text
        self.time = time


class PeerConnection:
    def __init__(self, uuid: str, conn: socket.socket, host: str, port: int, active: bool = True) -> None:
        self.uuid = uuid
        self.active = active
        self.conn = conn
        self.host = host
        self.port = port
        self.messages: List[Message] = []

    def get_messages(self, tail: int = DEFAULT_TAIL_LENGTH, time_format: str = DEFAULT_TIME_FORMAT) -> List[str]:
        messages = self.messages[-tail:]
        formatted_messages = []
        for m in messages:
            if m.incoming:
                formatted_messages.append(
                    f"[{m.time.strftime(time_format)}] {self.uuid}: {m.text}")
            else:
                formatted_messages.append(
                    f"[{m.time.strftime(time_format)}] You: {m.text}")
        return formatted_messages


class Peer:
    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self._listen_socket: socket.socket = None
        self._connections: Dict[str, PeerConnection] = {}

    @classmethod
    def get_uuid(cls, length=64) -> str:
        alphanumeric = string.ascii_letters + string.digits
        uuid = ''.join(random.choices(population=alphanumeric, k=length))
        return uuid

    @classmethod
    def wrap_message(cls, raw_message: str) -> bytes:
        message = raw_message.encode(ENCODING)
        message_length = str(len(message)).encode(ENCODING)
        header = message_length + b' ' * (HEADER - len(message_length))
        full_message = header + message
        return full_message

    @classmethod
    def read_message(cls, conn: socket) -> str:
        message_length_str = conn.recv(
            HEADER).decode(ENCODING).strip()
        # print(message_length_str)
        if message_length_str:
            message_length = int(message_length_str)
            msg = conn.recv(message_length).decode(ENCODING)
            return msg
        else:
            return None

    def handle_connection(self, conn: socket.socket, uuid: str) -> None:
        CONNECTED = True
        with conn:
            while CONNECTED:
                try:
                    msg = Peer.read_message(conn=conn)
                    # print(f"Var 'message' in 'handle_connection': {msg}")
                    if msg:
                        if msg == DISCONNNECT_MESSAGE:
                            CONNECTED = False
                        self._connections[uuid].messages.append(
                            Message(incoming=True, text=msg)
                        )
                    else:
                        continue
                except IOError as ex:
                    if ex.errno != errno.EAGAIN and ex.errno != errno.EWOULDBLOCK:
                        break
                    print(f"IOError handled: {ex}")
                    continue
                except Exception as ex:
                    print(f"Exception when handling connection {ex}")
                    break
        self._connections[uuid].active = False

    def _add_handler_thread(self, conn: socket.socket, addr: Tuple) -> Thread:
        uuid = Peer.get_uuid(length=UUID_LENGTH)
        connection_t = Thread(
            target=self.handle_connection,
            args=(conn, uuid),
            daemon=True,
        )
        self._connections[uuid] = PeerConnection(
            uuid=uuid,
            conn=conn,
            host=addr[0],
            port=addr[1],
        )
        connection_t.start()
        return connection_t

    def listen(self, addr: Tuple) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            self._listen_socket = s
            s.bind(addr)
            s.listen()
            while True:
                try:
                    conn, addr = s.accept()
                    print('Connected by', addr)
                    print("command > ", end='', flush=True)
                    self._add_handler_thread(conn=conn, addr=addr)
                except IOError as ex:
                    if ex.errno != errno.EAGAIN and ex.errno != errno.EWOULDBLOCK:
                        return
                    print(f"IOError handled: {ex}")
                    continue
                except Exception as ex:
                    print(f"Couldn't listen: {ex}")

    def start(self) -> bool:
        try:
            listen_thread = Thread(
                target=self.listen,
                args=((self.host, self.port),),
                daemon=True,
            )
            listen_thread.start()
            return True
        except Exception as ex:
            print(f"Exception when in 'start': {ex}")
            return False

    def connect(self, addr: Tuple[str, int]) -> Optional[socket.socket]:
        try:
            conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            conn.connect(addr)
            self._add_handler_thread(conn=conn, addr=addr)
            return conn
        except Exception as ex:
            print(f"Exception when connecting to {addr}: {ex}")
            return False

    def disconnect(self, uuid) -> Optional[bool]:
        if uuid in self._connections:
            pcon = self._connections[uuid]
        else:
            print(f"Connection uuid does not exist: {uuid}")
            return False
        try:
            pcon.active = False
            pcon.conn.sendall(Peer.wrap_message(DISCONNNECT_MESSAGE))
        except IOError as ex:
            if ex.errno != errno.EAGAIN and ex.errno != errno.EWOULDBLOCK:
                pass
            else:
                print(f"IOError handled: {ex}")
        except Exception as ex:
            print(f"Exception when disconnecting connection {uuid}: {ex}")
            return None
        sleep(PRE_CONNECTION_CLOSE_SLEEP_TIME)
        try:
            pcon.conn.close()
        except IOError as ex:
            if ex.errno != errno.EAGAIN and ex.errno != errno.EWOULDBLOCK:
                pass
            else:
                print(f"IOError handled: {ex}")
        except Exception as ex:
            print(f"Exception when ending peer connection: {ex}")
            return None
        return True

    def chat(self, uuid) -> bool:
        if uuid in self._connections:
            conn = self._connections[uuid].conn
            print(f"Chatting With {uuid}")
            CHAT_MODE = True
            while CHAT_MODE:
                try:
                    raw_message = input(f"You: > ")
                    splitted_raw_message = raw_message.split()
                    if raw_message:
                        if splitted_raw_message[0] == r"\b" or splitted_raw_message[0] == r"\back":
                            CHAT_MODE = False
                            continue
                        elif splitted_raw_message[0] == r"\t" or splitted_raw_message[0] == r"\tail":
                            if len(splitted_raw_message) == 2:
                                try:
                                    tail = int(splitted_raw_message[1])
                                    messages = self._connections[uuid].get_messages(tail=tail)
                                except Exception as ex:
                                    print(
                                        f"Tail's second parameter should be number: {splitted_raw_message[1]}")
                                    continue
                            else:
                                messages = self._connections[uuid].get_messages()
                            for m in messages:
                                print(m)
                        else:
                            if self._connections[uuid].active:
                                prepared_message = Peer.wrap_message(
                                    raw_message=raw_message)
                                conn.sendall(prepared_message)
                                self._connections[uuid].messages.append(
                                    Message(incoming=False, text=raw_message)
                                )
                            else:
                                print(
                                    "Connection is ended, only recent messages can be seen")
                    else:
                        continue
                except KeyboardInterrupt as ex:
                    print()
                    continue
                except Exception as ex:
                    print(f"Exception when chatting with {uuid}: {ex}")
            return True
        else:
            print(f"Connection with UUID does not exist: {uuid}")
            return None

    def list_actives(self) -> List:
        return [
            (
                uuid,
                f"{self._connections[uuid].host}:{self._connections[uuid].port}",
            ) for uuid in self._connections if self._connections[uuid].active
        ]

    def list_inactives(self) -> List:
        return [
            (
                uuid,
                f"{self._connections[uuid].host}:{self._connections[uuid].port}",
            ) for uuid in self._connections if not self._connections[uuid].active
        ]

    def end_gracefully(self) -> None:
        try:
            self._listen_socket.close()
        except IOError as ex:
            if ex.errno != errno.EAGAIN and ex.errno != errno.EWOULDBLOCK:
                pass
            else:
                print(f"IOError handled: {ex}")
        except Exception as ex:
            print(f"Exception when ending peer connection: {ex}")
        for pcon in self._connections.values():
            try:
                pcon.active = False
                pcon.conn.sendall(Peer.wrap_message(DISCONNNECT_MESSAGE))
            except IOError as ex:
                if ex.errno != errno.EAGAIN and ex.errno != errno.EWOULDBLOCK:
                    pass
                else:
                    print(f"IOError handled: {ex}")
            except Exception as ex:
                print(f"Exception when ending peer connection: {ex}")
        sleep(PRE_CONNECTION_CLOSE_SLEEP_TIME)
        for pcon in self._connections.values():
            try:
                pcon.conn.close()
            except IOError as ex:
                if ex.errno != errno.EAGAIN and ex.errno != errno.EWOULDBLOCK:
                    pass
                else:
                    print(f"IOError handled: {ex}")
            except Exception as ex:
                print(f"Exception when ending peer connection: {ex}")

    def end_forcefully(self) -> None:
        try:
            self._listen_socket.close()
        except IOError as ex:
            if ex.errno != errno.EAGAIN and ex.errno != errno.EWOULDBLOCK:
                pass
            else:
                print(f"IOError handled: {ex}")
        except Exception as ex:
            print(f"Exception when ending peer connection: {ex}")
        for pcon in self._connections.values():
            try:
                pcon.active = False
                pcon.conn.close()
            except IOError as ex:
                if ex.errno != errno.EAGAIN and ex.errno != errno.EWOULDBLOCK:
                    pass
                else:
                    print(f"IOError handled: {ex}")
            except Exception as ex:
                print(f"Exception when ending peer: {ex}")
