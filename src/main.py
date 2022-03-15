# import random
import socket
import sys
import os
from time import sleep
from peer import TCP_PORT, UDP_PORT, Peer

SERVER = socket.gethostbyname(socket.gethostname())
DISCOVER_SLEEP_TIME = 2


if __name__ == '__main__':
    mypeer = Peer(host=SERVER, tcp_port=TCP_PORT, udp_port=UDP_PORT)
    if not mypeer.start():
        sys.exit(os.EX_IOERR)
    ACTIVE = True
    while ACTIVE:
        try:
            command = input("command > ")
            words = command.split()
            if words:
                if words[0] == r"\quit" or words[0] == r"\q":
                    print("Good Bye!")
                    ACTIVE = False
                    mypeer.end_gracefully()
                elif words[0] == r"\connect" or words[0] == r"\c":
                    try:
                        if len(words[1:]) == 2:
                            host = words[1]
                            port = int(words[2])
                        elif len(words[1:]) == 1:
                            addr = words[1].split(':')
                            host = addr[0]
                            port = int(addr[1])
                        else:
                            # TODO: show correct usage
                            continue
                        mypeer.connect((host, port))
                    except Exception as ex:
                        print(f"Couldn't connect: {ex}")
                elif words[0] == r"\d" or words[0] == r"\disconnect":
                    try:
                        if len(words[1:]) == 1:
                            uuid = words[1]
                            mypeer.disconnect(uuid=uuid)
                        else:
                            print(f"Command '{words[0]}' gets 1 arguement")
                            continue
                    except Exception as ex:
                        print(f"Couldn't perform disconnection: {ex}")
                elif words[0] == r"\me":
                    me = mypeer.get_me()
                    print(f"My Info: {me}")
                    pass
                elif words[0] == r"\ls":
                    active_connections = mypeer.list_actives()
                    if active_connections:
                        print("Active Available Connections:")
                        number = 0
                        for uuid, addr in active_connections:
                            number += 1
                            print(f"\t{number}) {uuid} at {addr}")
                    else:
                        print("No active connections available!")
                    inactive_connections = mypeer.list_inactives()
                    if inactive_connections:
                        print("Inactive Available Connections:")
                        number = 0
                        for uuid, addr in inactive_connections:
                            number += 1
                            print(f"\t{number}) {uuid} at {addr}")
                    else:
                        print("No inactive connections available!")
                elif words[0] == r"\message" or words[0] == r"\chat":
                    try:
                        if len(words[1:]) == 1:
                            uuid = words[1]
                            mypeer.chat(uuid=uuid)
                        else:
                            # TODO: show correct usage
                            continue
                    except Exception as ex:
                        print(f"Couldn't start chat: {ex}")
                elif words[0] == r"\discover":
                    mypeer.discover()
                    sleep(DISCOVER_SLEEP_TIME)
                    discovereds = mypeer.get_discovered()
                    if discovereds:
                        print("Discovered Peers:")
                        number = 0
                        for d in discovereds:
                            number += 1
                            print(f"\t{number}) {d}")
                    else:
                        print("No Neighbor Discoverd")
                elif words[0] == r"\help" or words[0] == r"\h":
                    # TODO: help should be added
                    pass
                else:
                    continue
        except KeyboardInterrupt:
            print()
            pass
            # ACTIVE = False
            # mypeer.end_forcefully()
